from __future__ import annotations

import datetime as _dt
import logging
import time
import uuid

from aqt import mw
from aqt.qt import QTimer

from . import fsrs_logic, layout, state_store
from .config_utils import DEFAULT_CONFIG, get_config_val
from .state import session


log = logging.getLogger(__name__)
PENDING_ACTION_TTL_SECONDS = 15


def _config():
    return mw.addonManager.getConfig(__name__)


def _day_bounds_ms():
    """Return (day_key, start_ms, end_ms) for Anki's current scheduler day.

    Anki exposes the next rollover timestamp.  Work backwards by one *local
    calendar day*, rather than 86,400 seconds, so a DST transition cannot move
    the review boundary by an hour.
    """
    cutoff = int(mw.col.sched.day_cutoff)
    next_rollover = time.localtime(cutoff)
    next_date = _dt.date(
        next_rollover.tm_year,
        next_rollover.tm_mon,
        next_rollover.tm_mday,
    )
    start_date = next_date - _dt.timedelta(days=1)
    start = int(
        time.mktime(
            (
                start_date.year,
                start_date.month,
                start_date.day,
                next_rollover.tm_hour,
                next_rollover.tm_min,
                next_rollover.tm_sec,
                0,
                0,
                -1,
            )
        )
    )
    return int(mw.col.sched.today), start * 1000, cutoff * 1000


def _decode_memberships(raw):
    memberships = {}
    if not isinstance(raw, dict):
        return memberships
    for did, cids in raw.items():
        try:
            deck_id = int(did)
        except (TypeError, ValueError):
            continue
        if not isinstance(cids, list):
            continue
        parsed = set()
        for cid in cids:
            try:
                parsed.add(int(cid))
            except (TypeError, ValueError):
                continue
        memberships[deck_id] = parsed
    return memberships


def _decode_filtered_reviews(raw):
    reviews = {}
    if not isinstance(raw, dict):
        return reviews
    for did, records in raw.items():
        try:
            deck_id = int(did)
        except (TypeError, ValueError):
            continue
        if isinstance(records, list):
            reviews[deck_id] = [record for record in records if isinstance(record, dict)]
    return reviews


def _ensure_session_state():
    """Load the persisted state for this collection/day when context changes."""
    if not mw.col:
        return False

    key = state_store.collection_key(mw.col)
    day_key, start_ms, end_ms = _day_bounds_ms()
    if session.collection_key == key and session.day_key == day_key:
        # Rollover timestamps can be recalculated by Anki; keep our bounds fresh.
        session.day_start_ms = start_ms
        session.day_end_ms = end_ms
        return True

    loaded = state_store.load_day_state(mw.col, day_key, int(time.time() * 1000))
    session.reset_collection_state()
    session.collection_key = key
    session.day_key = day_key
    session.day_start_ms = start_ms
    session.day_end_ms = end_ms
    session.tracking_started_ms = int(loaded.get("tracking_started_ms", int(time.time() * 1000)))
    session.filtered_memberships = _decode_memberships(loaded.get("filtered_memberships"))
    session.filtered_reviews = _decode_filtered_reviews(loaded.get("filtered_reviews"))
    session.manual_actions = [
        action for action in loaded.get("manual_actions", []) if isinstance(action, dict)
    ]
    session.undo_tombstones = [
        item for item in loaded.get("undo_tombstones", []) if isinstance(item, dict)
    ]
    return True


def _serialized_state():
    return {
        "day_key": int(session.day_key),
        "tracking_started_ms": int(session.tracking_started_ms),
        "filtered_memberships": {
            str(did): sorted(int(cid) for cid in cids)
            for did, cids in session.filtered_memberships.items()
        },
        "filtered_reviews": {
            str(did): list(records)
            for did, records in session.filtered_reviews.items()
        },
        "manual_actions": list(session.manual_actions),
        "undo_tombstones": list(session.undo_tombstones),
    }


def _persist_state():
    if not mw.col or session.collection_key is None or session.day_key is None:
        return
    try:
        state_store.save_day_state(mw.col, _serialized_state())
    except Exception:
        # Review progress must never be blocked because the auxiliary state file
        # is unwritable.  The revlog still remains the source of truth for normal
        # reviews, and we leave a traceback in Anki's log for diagnosis.
        log.exception("Chunked Progress Bar could not save session state")


def _selected_deck_id():
    if not mw.col:
        return None
    return mw.col.decks.selected()


def _is_filtered_deck(did):
    if not mw.col or not did:
        return False
    deck = mw.col.decks.get(did)
    return bool(deck and deck.get("dyn"))


def _reviewer_card():
    reviewer = getattr(mw, "reviewer", None)
    return getattr(reviewer, "card", None)


def _elapsed_for_card(card):
    config = _config()
    use_cap = get_config_val(config, DEFAULT_CONFIG, "timer", "use_anki_cap")
    if use_cap:
        if card is None:
            return 0
        try:
            return card.time_taken() / 1000.0
        except Exception:
            return 0
    if session.start_time > 0:
        return max(0, time.time() - session.start_time)
    return 0


def _queue_manual_intent(kind, cid, card=None):
    """Remember reviewer intent; commit only after Anki's operation succeeds."""
    if mw.state != "review" or not _ensure_session_state() or not cid:
        return
    did = _selected_deck_id()
    if not did:
        return

    now = time.time()
    # The current official hook should fire once, but compatibility wrappers and
    # third-party add-ons can lead to duplicate signals.  One pending intent per
    # presentation/action is enough.
    session.pending_manual_actions = [
        item
        for item in session.pending_manual_actions
        if now - float(item.get("queued_at", 0)) <= PENDING_ACTION_TTL_SECONDS
        and not (
            int(item.get("cid", -1)) == int(cid)
            and item.get("type") == kind
            and int(item.get("did", -1)) == int(did)
        )
    ]
    session.pending_manual_actions.append(
        {
            "event_id": uuid.uuid4().hex,
            "cid": int(cid),
            "did": int(did),
            "type": kind,
            "time_ms": int(now * 1000),
            "elapsed": float(_elapsed_for_card(card)),
            "queued_at": now,
        }
    )
    session.last_action_handled = True


def _manual_action_applies(kind, cid):
    if not mw.col:
        return False
    queue = mw.col.db.scalar("select queue from cards where id=?", cid)
    if kind == "buried":
        return queue in (-2, -3)
    if kind == "suspended":
        return queue == -1
    if kind == "deleted":
        return queue is None
    return False


def _upsert_manual_action(action):
    """Keep only the newest occurrence of one currently repeatable action.

    If the old occurrence was undone and the user performs the action again,
    Anki's redo stack is gone, so retaining the inactive record would only allow
    reconstruction to count the new live state twice.
    """
    key = (int(action["did"]), int(action["cid"]), action["type"])
    session.manual_actions = [
        existing
        for existing in session.manual_actions
        if (
            int(existing.get("did", -1)),
            int(existing.get("cid", -1)),
            existing.get("type"),
        )
        != key
    ]
    session.manual_actions.append(action)


def _commit_pending_manual_actions():
    """Commit pending intents whose requested state is now present in Anki."""
    if not _ensure_session_state():
        return False
    now = time.time()
    remaining = []
    committed = False
    for intent in session.pending_manual_actions:
        try:
            age = now - float(intent.get("queued_at", 0))
            cid = int(intent["cid"])
            kind = intent["type"]
        except (KeyError, TypeError, ValueError):
            continue
        if age > PENDING_ACTION_TTL_SECONDS:
            continue
        if not _manual_action_applies(kind, cid):
            remaining.append(intent)
            continue

        action = {
            "event_id": intent["event_id"],
            "cid": cid,
            "did": int(intent["did"]),
            "type": kind,
            "time_ms": int(intent["time_ms"]),
            "elapsed": float(intent.get("elapsed", 0)),
        }
        _upsert_manual_action(action)
        committed = True

    session.pending_manual_actions = remaining
    if committed:
        _persist_state()
    return committed


def _record_filtered_review(did, card, ease, elapsed):
    if not _is_filtered_deck(did) or not mw.col:
        return
    row = mw.col.db.first(
        "select id, cid, ease, time from revlog where cid=? order by id desc limit 1",
        card.id,
    )
    if not row:
        return
    revlog_id, cid, stored_ease, stored_time = row
    if int(stored_ease) not in (1, 2, 3, 4):
        return

    record = {
        "revlog_id": int(revlog_id),
        "cid": int(cid),
        "ease": int(stored_ease),
        "time_ms": int(revlog_id),
        "elapsed": float(elapsed if elapsed is not None else stored_time / 1000.0),
    }
    records = session.filtered_reviews.setdefault(int(did), [])
    records[:] = [
        existing
        for existing in records
        if int(existing.get("revlog_id", -1)) != int(revlog_id)
    ]
    records.append(record)
    session.filtered_memberships.setdefault(int(did), set()).add(int(cid))
    _persist_state()


def _event_id_for_revlog(revlog_id):
    return f"revlog:{int(revlog_id)}"


def _active_revlog_rows():
    return mw.col.db.all(
        "select id, cid, ease, time from revlog where id >= ? and id < ? order by id",
        session.day_start_ms,
        session.day_end_ms,
    )


def _tracked_filtered_reviews_by_id():
    by_id = {}
    for did, records in session.filtered_reviews.items():
        for record in records:
            try:
                rid = int(record["revlog_id"])
            except (KeyError, TypeError, ValueError):
                continue
            by_id[rid] = (int(did), record)
    return by_id


def _manual_action_by_event_id(event_id):
    for action in session.manual_actions:
        if action.get("event_id") == event_id:
            return action
    return None


def _event_is_active(event):
    """Check whether one rendered event still exists after an undo."""
    if not mw.col or not event:
        return False
    kind = event.get("kind")
    if kind == "review":
        revlog_id = event.get("revlog_id")
        return bool(
            revlog_id is not None
            and mw.col.db.scalar("select 1 from revlog where id=?", int(revlog_id))
        )
    if kind == "manual":
        action = _manual_action_by_event_id(event.get("event_id"))
        if not action:
            return False
        return _manual_action_applies(action.get("type"), int(action.get("cid", -1)))
    return False


def _tombstone_is_active_again(tombstone, revlog_ids):
    event_id = tombstone.get("event_id", "")
    if event_id.startswith("revlog:"):
        try:
            return int(event_id.split(":", 1)[1]) in revlog_ids
        except (ValueError, IndexError):
            return False
    action = _manual_action_by_event_id(event_id)
    if not action:
        return False
    try:
        return _manual_action_applies(action.get("type"), int(action["cid"]))
    except (KeyError, TypeError, ValueError):
        return False


def _should_include_ease(ease, fail_policy):
    return int(ease) != 1 or fail_policy in ("acknowledge", "count")


def reconstruct_history():
    """Rebuild displayed progress from authoritative + persisted session data.

    Work is built off to the side and committed only after all collection reads
    succeed.  A transient query/API failure therefore cannot blank the bar.
    """
    if not _ensure_session_state():
        return False
    did = _selected_deck_id()
    if not did:
        return False

    try:
        config = _config()
        fail_policy = get_config_val(config, DEFAULT_CONFIG, "fail_policy")
        live_cids = set(mw.col.decks.cids(did, children=True))
        is_filtered = _is_filtered_deck(did)
        memberships = {
            deck_id: set(cids) for deck_id, cids in session.filtered_memberships.items()
        }
        if is_filtered:
            memberships.setdefault(int(did), set()).update(live_cids)
            valid_cids = set(memberships[int(did)])
        else:
            valid_cids = live_cids

        revlog_rows = _active_revlog_rows()
        revlog_by_id = {int(row[0]): row for row in revlog_rows}
        filtered_by_id = _tracked_filtered_reviews_by_id()
        events = []

        for revlog_id, cid, ease, elapsed_ms in revlog_rows:
            revlog_id = int(revlog_id)
            cid = int(cid)
            ease = int(ease)
            if ease not in (1, 2, 3, 4) or not _should_include_ease(ease, fail_policy):
                continue

            tracked = filtered_by_id.get(revlog_id)
            elapsed = float(elapsed_ms) / 1000.0
            if is_filtered:
                if tracked:
                    tracked_did, record = tracked
                    if tracked_did != int(did):
                        continue
                    elapsed = float(record.get("elapsed", elapsed))
                else:
                    # Legacy migration path: before this release there was no
                    # durable filtered-deck attribution.  Trust the saved/live
                    # cohort only for entries predating tracking, or cards that
                    # are still visibly in this filtered deck now.
                    if cid not in valid_cids:
                        continue
                    if (
                        revlog_id >= int(session.tracking_started_ms)
                        and cid not in live_cids
                    ):
                        continue
            elif cid not in valid_cids:
                continue

            events.append(
                {
                    "timestamp_ms": revlog_id,
                    "status": ease,
                    "elapsed": elapsed,
                    "event_id": _event_id_for_revlog(revlog_id),
                    "kind": "review",
                    "revlog_id": revlog_id,
                    "cid": cid,
                    "did": int(did),
                }
            )

        policies = {
            "buried": "bury_policy",
            "suspended": "suspend_policy",
            "deleted": "delete_policy",
        }
        for action in session.manual_actions:
            try:
                action_did = int(action["did"])
                cid = int(action["cid"])
                kind = action["type"]
                timestamp_ms = int(action["time_ms"])
            except (KeyError, TypeError, ValueError):
                continue
            if action_did != int(did):
                continue
            if not (session.day_start_ms <= timestamp_ms < session.day_end_ms):
                continue
            if kind not in policies:
                continue
            if get_config_val(config, DEFAULT_CONFIG, policies[kind]) != "acknowledge":
                continue
            if not _manual_action_applies(kind, cid):
                continue
            events.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "status": kind,
                    "elapsed": float(action.get("elapsed", 0)),
                    "event_id": action.get("event_id", f"manual:{timestamp_ms}:{cid}:{kind}"),
                    "kind": "manual",
                    "cid": cid,
                    "did": action_did,
                }
            )

        # Acknowledge-mode undo is intentionally visible even though its source
        # event is no longer in revlog/live card state.  Redo restores the exact
        # revlog/manual event; when that happens, discard the tombstone.
        active_revlog_ids = set(revlog_by_id)
        tombstones = []
        tombstones_changed = False
        for tombstone in session.undo_tombstones:
            if _tombstone_is_active_again(tombstone, active_revlog_ids):
                tombstones_changed = True
                continue
            tombstones.append(tombstone)
            try:
                tombstone_did = int(tombstone["did"])
                timestamp_ms = int(tombstone["timestamp_ms"])
            except (KeyError, TypeError, ValueError):
                continue
            if tombstone_did != int(did):
                continue
            if not (session.day_start_ms <= timestamp_ms < session.day_end_ms):
                continue
            events.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "status": "undone",
                    "elapsed": 0,
                    "event_id": f"undone:{tombstone.get('event_id', '')}",
                    "kind": "undone",
                    "did": tombstone_did,
                }
            )

        events.sort(key=lambda event: (event["timestamp_ms"], event["event_id"]))
    except Exception:
        log.exception("Chunked Progress Bar could not reconstruct review history")
        return False

    context = (session.collection_key, session.day_key, int(did))
    if session.progress_context is not None and session.progress_context != context:
        session.initial_total = None
    session.progress_context = context
    session.filtered_memberships = memberships
    session.undo_tombstones = tombstones
    session.event_log = events
    session.status_log = [event["status"] for event in events]
    session.time_log = [event["elapsed"] for event in events]
    session.current_count = len(events)
    session.history = []

    # Save filtered membership at reviewer entry, before reviewed cards begin
    # returning home.  Also persist tombstone cleanup after a redo.
    if is_filtered or tombstones_changed:
        _persist_state()
    return True


def on_show_question(card):
    if not _ensure_session_state():
        return

    # Catch operations performed by another add-on or code path that bypassed
    # the reviewer_will_* hooks.  At this point the previous card's DB state has
    # already changed, so the intent can be committed immediately.
    if session.last_card_id and not session.was_answered and not session.last_action_handled:
        cid = int(session.last_card_id)
        queue = mw.col.db.scalar("select queue from cards where id=?", cid)
        kind = None
        if queue == -1:
            kind = "suspended"
        elif queue in (-2, -3):
            kind = "buried"
        elif queue is None:
            kind = "deleted"
        if kind:
            _queue_manual_intent(kind, cid)
            _commit_pending_manual_actions()
            reconstruct_history()

    # A card can legitimately appear again immediately after Again/relearning.
    # De-duplication is per presentation, never per card id across presentations.
    session.last_card_id = int(card.id)
    session.was_answered = False
    session.last_action_handled = False
    session.start_time = time.time()


def on_answer(reviewer, card, ease):
    if not _ensure_session_state():
        return
    config = _config()
    fail_policy = get_config_val(config, DEFAULT_CONFIG, "fail_policy")
    elapsed = _elapsed_for_card(card)

    session.was_answered = True
    session.last_action_handled = True

    if int(ease) != 1 or fail_policy in ("acknowledge", "count"):
        session.current_count += 1
        session.status_log.append(int(ease))
        session.time_log.append(elapsed)

    did = _selected_deck_id()
    if did and _is_filtered_deck(did):
        try:
            _record_filtered_review(int(did), card, int(ease), elapsed)
        except Exception:
            log.exception("Chunked Progress Bar could not record filtered review")

    # The answer CollectionOp has completed by the time this hook fires.  A zero
    # delay keeps the UI responsive, while operation_did_execute immediately
    # afterwards performs the authoritative reconstruction.
    QTimer.singleShot(0, refresh_bar)


def on_bury(reviewer, card):
    _queue_manual_intent("buried", card.id, card)


def on_suspend(reviewer, card):
    _queue_manual_intent("suspended", card.id, card)


def on_delete(reviewer, card):
    _queue_manual_intent("deleted", card.id, card)


def on_will_bury_card(cid):
    card = _reviewer_card()
    _queue_manual_intent("buried", cid, card if card and card.id == cid else None)


def on_will_suspend_card(cid):
    card = _reviewer_card()
    _queue_manual_intent("suspended", cid, card if card and card.id == cid else None)


def on_will_bury_note(nid):
    card = _reviewer_card()
    if not card or card.nid != nid:
        return
    _queue_manual_intent("buried", card.id, card)


def on_will_suspend_note(nid):
    card = _reviewer_card()
    if not card or card.nid != nid:
        return
    _queue_manual_intent("suspended", card.id, card)


def _op_touched_review_state(changes):
    """True for operations that can change visible review progress/counts."""
    if changes is None:
        return True
    inner = getattr(changes, "changes", changes)
    try:
        return bool(
            getattr(inner, "card", False)
            or getattr(inner, "study_queues", False)
        )
    except Exception:
        return True


def on_undo(changes=None):
    if mw.state != "review" or not _ensure_session_state():
        return
    if not _op_touched_review_state(changes):
        return

    # state_did_undo runs before operation_did_execute for the same CollectionOp.
    session.skip_next_operation_reconcile = True
    config = _config()
    policy = get_config_val(config, DEFAULT_CONFIG, "undo_policy")

    if policy == "acknowledge":
        target = None
        for event in reversed(session.event_log):
            if event.get("kind") != "undone":
                target = event
                break
        # Only acknowledge the undo if the most recent tracked event actually
        # disappeared.  Undoing a note edit, ignored Again, flag, etc. must not
        # grey an unrelated progress tile.
        if target and not _event_is_active(target):
            original_event_id = target.get("event_id")
            if not any(
                item.get("event_id") == original_event_id
                for item in session.undo_tombstones
            ):
                session.undo_tombstones.append(
                    {
                        "event_id": original_event_id,
                        "did": int(target.get("did", _selected_deck_id() or 0)),
                        "timestamp_ms": int(target.get("timestamp_ms", time.time() * 1000)),
                    }
                )
                _persist_state()

    reconstruct_history()
    session.last_action_handled = False
    QTimer.singleShot(0, refresh_bar)


def on_operation(changes=None, handler=None):
    if session.skip_next_operation_reconcile:
        session.skip_next_operation_reconcile = False
        return
    if mw.state != "review" or not mw.col or not _op_touched_review_state(changes):
        return
    if not _ensure_session_state():
        return

    _commit_pending_manual_actions()
    reconstruct_history()
    QTimer.singleShot(0, refresh_bar)


def on_state_change(new_state, old_state):
    if new_state in ("overview", "review"):
        fsrs_logic.check_fsrs_deck_update()

    if new_state == "review":
        if not _ensure_session_state():
            return
        session.last_card_id = None
        session.last_action_handled = False
        session.was_answered = False
        session.pending_manual_actions = []
        reconstruct_history()
        QTimer.singleShot(0, refresh_bar)
    # D returns directly to deckBrowser, bypassing the deck overview.
    layout.update_visibility(state=new_state)


def on_collection_loaded(col=None):
    session.reset_collection_state()
    session.last_deck_id = None


def on_profile_will_close():
    session.reset_collection_state()
    session.last_deck_id = None


def on_day_did_change():
    session.reset_for_new_day()
    if mw.col and mw.state == "review":
        _ensure_session_state()
        reconstruct_history()
        QTimer.singleShot(0, refresh_bar)


def on_sync_finished():
    if mw.state == "review" and mw.col:
        _ensure_session_state()
        reconstruct_history()
        QTimer.singleShot(0, refresh_bar)


def refresh_bar():
    # Queued refreshes can arrive after the user has already left the reviewer.
    if mw.state != "review" or not mw.col or not _ensure_session_state():
        return

    counts = mw.col.sched.counts()
    config = _config()
    if get_config_val(config, DEFAULT_CONFIG, "double_new"):
        remaining = (counts[0] * 2) + counts[1] + counts[2]
    else:
        remaining = sum(counts)

    total = session.current_count + remaining
    if session.initial_total is None:
        fail_policy = get_config_val(config, DEFAULT_CONFIG, "fail_policy")
        if fail_policy in ("acknowledge", "count"):
            num_fails = sum(1 for status in session.status_log if status == 1 or status is False)
            session.initial_total = total - num_fails
        else:
            session.initial_total = total

    layout.refresh_widgets(
        total,
        session.current_count,
        session.status_log,
        session.time_log,
        session.start_time,
        session.initial_total,
    )
