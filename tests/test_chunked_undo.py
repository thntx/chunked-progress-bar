"""Regression checks against Chunked Progress Bar with a disposable Anki DB.

The add-on logic is executed without importing its Qt UI.  Collection/scheduler
behaviour is real Anki; only the GUI globals, timer and user_files persistence
layer are small in-memory fakes.
"""

import ast
import copy
import datetime as _dt
import logging
import runpy
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace as NS

from anki.collection import Collection


SOURCE = Path(sys.argv.pop(1))
SessionState = runpy.run_path(str(SOURCE.with_name("state.py")))["SessionState"]


class MemoryStateStore:
    def __init__(self):
        self.saved = {}

    def collection_key(self, col):
        return str(Path(col.path).resolve()).lower()

    def load_day_state(self, col, day_key, tracking_started_ms):
        state = self.saved.get(self.collection_key(col))
        if not state or int(state.get("day_key", -1)) != int(day_key):
            return {
                "day_key": int(day_key),
                "tracking_started_ms": int(tracking_started_ms),
                "filtered_memberships": {},
                "filtered_reviews": {},
                "manual_actions": [],
                "undo_tombstones": [],
            }
        return copy.deepcopy(state)

    def save_day_state(self, col, state):
        self.saved[self.collection_key(col)] = copy.deepcopy(state)


def get_config_val(config, defaults, *keys):
    current = config
    fallback = defaults
    for key in keys:
        current = current.get(key) if isinstance(current, dict) else None
        fallback = fallback.get(key) if isinstance(fallback, dict) else None
    return current if current is not None else fallback


class ChunkedLogicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.col = Collection(str(Path(self.tmp.name) / "collection.anki2"))
        self.did = self.col.decks.selected()
        self.config = {
            "fail_policy": "acknowledge",
            "undo_policy": "undo",
            "bury_policy": "acknowledge",
            "suspend_policy": "acknowledge",
            "delete_policy": "acknowledge",
            "timer": {"use_anki_cap": True},
        }
        self.state = SessionState()
        self.timers = []
        self.store = MemoryStateStore()
        self.mw = NS(
            col=self.col,
            state="review",
            addonManager=NS(getConfig=lambda _: self.config),
            reviewer=NS(card=None),
        )
        self.env = {
            "mw": self.mw,
            "session": self.state,
            "time": time,
            "_dt": _dt,
            "uuid": uuid,
            "log": logging.getLogger("chunked-test"),
            "state_store": self.store,
            "QTimer": NS(singleShot=lambda ms, fn: self.timers.append(fn)),
            "DEFAULT_CONFIG": {},
            "get_config_val": get_config_val,
            "PENDING_ACTION_TTL_SECONDS": 15,
            "__name__": "test_addon",
        }
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        functions = ast.Module(
            body=[node for node in tree.body if isinstance(node, ast.FunctionDef)],
            type_ignores=[],
        )
        exec(compile(functions, str(SOURCE), "exec"), self.env)
        self.env["refresh_bar"] = lambda: None
        self.assertTrue(self.env["_ensure_session_state"]())
        self.state.initial_total = 100

    def tearDown(self):
        self.col.close()
        self.tmp.cleanup()

    def card(self):
        note = self.col.new_note(self.col.models.current())
        note["Front"] = str(time.time_ns())
        self.col.add_note(note, self.did)
        return note.cards()[0]

    def review(self, card, timestamp, ease=3):
        self.col.db.execute(
            "insert into revlog values (?, ?, 0, ?, 1, 1, 2500, 1000, 1)",
            timestamp,
            card.id,
            ease,
        )

    def manual_action(self, card, kind, timestamp_ms, did=None, elapsed=2):
        return {
            "event_id": uuid.uuid4().hex,
            "cid": card.id,
            "did": self.did if did is None else did,
            "type": kind,
            "time_ms": int(timestamp_ms),
            "elapsed": elapsed,
        }

    def rebuild(self):
        return self.env["reconstruct_history"]()

    def answer_current(self, ease=4):
        card = self.col.sched.getCard()
        self.assertIsNotNone(card)
        self.mw.reviewer.card = card
        self.env["on_show_question"](card)
        self.col.sched.answerCard(card, ease)
        self.env["on_answer"](None, card, ease)
        return card

    def filtered_deck(self, card_count=5):
        for _ in range(card_count):
            self.card()
        did = self.col.decks.new_filtered("Custom Study")
        deck = self.col.decks.get(did)
        deck["terms"] = [["deck:Default", 100, 0]]
        deck["resched"] = True
        self.col.decks.save(deck)
        self.col.sched.rebuild_filtered_deck(did)
        self.col.decks.select(did)
        self.assertEqual(len(self.col.decks.cids(did)), card_count)
        return did

    def simulate_manual_operation(self, kind, card):
        self.mw.reviewer.card = card
        self.env["on_show_question"](card)
        if kind == "buried":
            self.env["on_bury"](None, card)
            result = self.col.sched.bury_cards([card.id])
        elif kind == "suspended":
            self.env["on_suspend"](None, card)
            result = self.col.sched.suspend_cards([card.id])
        else:
            raise AssertionError(kind)
        self.env["on_operation"](result)
        return result

    def nested_filtered_deck(self, card_count=5, resched=True, home_inside=False):
        parent = self.col.decks.id("Study")
        if home_inside:
            home = self.col.decks.get(self.did)
            home["name"] = "Study::Home"
            self.col.decks.save(home)
        conf = self.col.decks.config_dict_for_deck_id(self.did)
        conf["new"]["delays"] = [1]
        self.col.decks.update_config(conf)
        for _ in range(card_count):
            self.card()
        filtered = self.col.decks.new_filtered("Study::Section::Filtered")
        deck = self.col.decks.get(filtered)
        deck["terms"] = [[f'deck:"{self.col.decks.name(self.did)}"', 100, 0]]
        deck["resched"] = resched
        self.col.decks.save(deck)
        self.col.sched.rebuild_filtered_deck(filtered)
        self.col.decks.select(parent)
        self.assertTrue(self.rebuild())
        return parent, filtered

    def check_parent_answers(self, resched):
        parent, filtered = self.nested_filtered_deck(resched=resched)
        expected = []
        for ease in (1, 2, 3, 4):
            with self.subTest(ease=ease):
                self.answer_current(ease)
                expected.append(ease)
                self.env["on_operation"](NS(card=True, study_queues=True))
                self.assertEqual(self.state.status_log, expected)
        self.col.decks.select(filtered)
        self.rebuild()
        self.assertEqual(self.state.status_log, expected)
        self.col.decks.select(parent)
        self.state.reset_collection_state()
        self.rebuild()
        self.assertEqual(self.state.status_log, expected)

    def test_filtered_descendant_all_grades_survive_parent_rebuild_and_restart(self):
        self.check_parent_answers(resched=True)

    def test_filtered_preview_descendant_all_grades_survive_parent_rebuild(self):
        self.check_parent_answers(resched=False)

    def test_filtered_direct_entry_records_origin_before_card_returns_home(self):
        _, filtered = self.nested_filtered_deck()
        self.col.decks.select(filtered)
        self.rebuild()
        card = self.answer_current(4)
        self.assertEqual(card.did, self.did)  # Anki mutates this same object.
        self.assertIn(filtered, self.state.filtered_reviews)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4])

    def test_filtered_parent_undo_redo_after_all_cards_return_home(self):
        parent, filtered = self.nested_filtered_deck(card_count=2)
        for _ in range(2):
            self.answer_current(4)
        self.assertEqual(self.col.decks.cids(filtered), [])
        self.rebuild()
        self.assertEqual(self.state.status_log, [4, 4])
        changes = self.col.undo()
        self.env["on_undo"](changes)
        self.env["on_operation"](changes)
        self.assertEqual(self.state.status_log, [4])
        self.col.redo()
        self.rebuild()
        self.assertEqual(self.state.status_log, [4, 4])
        self.col.decks.select(filtered)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4, 4])
        self.col.decks.select(parent)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4, 4])

    def test_filtered_parent_acknowledged_undo_visible_in_child_after_restart(self):
        self.config["undo_policy"] = "acknowledge"
        _, filtered = self.nested_filtered_deck()
        self.answer_current(4)
        self.rebuild()
        changes = self.col.undo()
        self.env["on_undo"](changes)
        self.env["on_operation"](changes)
        self.assertEqual(self.state.status_log, ["undone"])
        self.state.reset_collection_state()
        self.rebuild()
        self.assertEqual(self.state.status_log, ["undone"])
        self.col.redo()
        self.rebuild()
        self.assertEqual(self.state.status_log, [4])
        changes = self.col.undo()
        self.env["on_undo"](changes)
        self.env["on_operation"](changes)
        self.col.decks.select(filtered)
        self.state.reset_collection_state()
        self.rebuild()
        self.assertEqual(self.state.status_log, ["undone"])

    def test_filtered_child_reviews_aggregate_in_parent_without_duplicates(self):
        parent, filtered = self.nested_filtered_deck(home_inside=True)
        self.col.decks.select(filtered)
        self.rebuild()
        self.answer_current(4)
        self.col.decks.select(parent)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4])

    def test_home_history_survives_cards_borrowed_by_an_unrelated_filter(self):
        parent = self.col.decks.id("Study")
        home = self.col.decks.get(self.did)
        home["name"] = "Study::Home"
        self.col.decks.save(home)
        card = self.card()
        self.answer_current(4)
        filtered = self.col.decks.new_filtered("Elsewhere")
        deck = self.col.decks.get(filtered)
        deck["terms"] = [[f"cid:{card.id}", 100, 0]]
        self.col.decks.save(deck)
        self.col.sched.rebuild_filtered_deck(filtered)
        self.col.decks.select(parent)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4])

    def test_borrowed_card_does_not_import_unrelated_home_reviews(self):
        card = self.card()
        self.answer_current(4)
        parent = self.col.decks.id("Study")
        filtered = self.col.decks.new_filtered("Study::Filtered")
        deck = self.col.decks.get(filtered)
        deck["terms"] = [[f"cid:{card.id}", 100, 0]]
        self.col.decks.save(deck)
        self.col.sched.rebuild_filtered_deck(filtered)
        self.col.decks.select(parent)
        self.rebuild()
        self.assertEqual(self.state.status_log, [])
        self.col.decks.select(filtered)
        self.rebuild()
        self.assertEqual(self.state.status_log, [])

    def test_filtered_manual_actions_follow_origin_between_parent_and_child(self):
        parent, filtered = self.nested_filtered_deck()
        expected = []
        for kind in ("buried", "suspended"):
            with self.subTest(kind=kind):
                self.col.decks.select(parent)
                card = self.col.sched.getCard()
                self.assertIsNotNone(card)
                self.simulate_manual_operation(kind, card)
                expected.append(kind)
                self.col.decks.select(filtered)
                self.rebuild()
                self.assertEqual(self.state.status_log, expected)

    def test_filtered_parent_manual_undo_redo_before_switching_context(self):
        _, filtered = self.nested_filtered_deck()
        card = self.col.sched.getCard()
        self.simulate_manual_operation("buried", card)
        changes = self.col.undo()
        self.env["on_undo"](changes)
        self.env["on_operation"](changes)
        self.assertEqual(self.state.status_log, [])
        self.col.redo()
        self.rebuild()
        self.assertEqual(self.state.status_log, ["buried"])
        self.col.decks.select(filtered)
        self.rebuild()
        self.assertEqual(self.state.status_log, ["buried"])

    def test_moving_between_sibling_filters_keeps_review_histories_separate(self):
        parent, first = self.nested_filtered_deck(card_count=1)
        card = self.answer_current(4)
        second = self.col.decks.new_filtered("Study::Second")
        deck = self.col.decks.get(second)
        deck["terms"] = [[f"cid:{card.id}", 100, 0]]
        self.col.decks.save(deck)
        self.col.sched.rebuild_filtered_deck(second)
        self.col.decks.select(second)
        self.rebuild()
        self.assertEqual(self.state.status_log, [])
        self.answer_current(3)
        self.rebuild()
        self.assertEqual(self.state.status_log, [3])
        self.col.decks.select(first)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4])
        self.col.decks.select(parent)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4, 3])

    def test_filtered_delete_from_parent_visible_in_child(self):
        _, filtered = self.nested_filtered_deck()
        card = self.col.sched.getCard()
        self.env["on_show_question"](card)
        self.env["on_delete"](None, card)
        result = self.col.remove_notes([card.nid])
        self.env["on_operation"](result)
        self.col.decks.select(filtered)
        self.rebuild()
        self.assertEqual(self.state.status_log, ["deleted"])

    def test_repeated_manual_action_in_another_filter_replaces_old_origin(self):
        _, first = self.nested_filtered_deck()
        self.col.decks.select(first)
        card = self.col.sched.getCard()
        self.simulate_manual_operation("buried", card)
        changes = self.col.undo()
        self.env["on_undo"](changes)
        self.env["on_operation"](changes)
        self.col.sched.empty_filtered_deck(first)
        second = self.col.decks.new_filtered("Study::Other")
        deck = self.col.decks.get(second)
        deck["terms"] = [[f"cid:{card.id}", 100, 0]]
        self.col.decks.save(deck)
        self.col.sched.rebuild_filtered_deck(second)
        self.col.decks.select(second)
        card = self.col.get_card(card.id)
        self.simulate_manual_operation("buried", card)
        self.col.decks.select(first)
        self.rebuild()
        self.assertEqual(self.state.status_log, [])
        self.col.decks.select(second)
        self.rebuild()
        self.assertEqual(self.state.status_log, ["buried"])

    def test_preserves_baseline_on_undo(self):
        card = self.card()
        self.review(card, int(time.time() * 1000))
        self.rebuild()
        self.state.initial_total = 100
        self.state.current_count = 2
        self.state.status_log = [3, 3]
        self.state.time_log = [1, 1]
        self.env["on_undo"](NS(changes=NS(card=True, note=False, study_queues=False)))
        self.assertEqual(self.state.current_count, 1)
        self.assertEqual(self.state.initial_total, 100)

    def test_preserves_chronological_manual_entries(self):
        a, b, buried = self.card(), self.card(), self.card()
        now = int(time.time() * 1000)
        self.review(a, now - 3000)
        self.review(b, now - 1000)
        self.col.sched.bury_cards([buried.id])
        self.state.manual_actions = [
            self.manual_action(buried, "buried", now - 2000)
        ]
        self.rebuild()
        self.assertEqual(self.state.status_log, [3, "buried", 3])

    def test_ignored_bury_stays_ignored(self):
        card = self.card()
        self.col.sched.bury_cards([card.id])
        self.config["bury_policy"] = "ignore"
        self.state.manual_actions = [
            self.manual_action(card, "buried", int(time.time() * 1000))
        ]
        self.rebuild()
        self.assertEqual(self.state.status_log, [])

    def test_manual_redo_restores_entry(self):
        card = self.card()
        self.col.sched.bury_cards([card.id])
        self.state.manual_actions = [
            self.manual_action(card, "buried", int(time.time() * 1000))
        ]
        self.col.undo()
        self.rebuild()
        self.assertEqual(self.state.status_log, [])
        self.col.redo()
        self.rebuild()
        self.assertEqual(self.state.status_log, ["buried"])

    def test_failed_rebuild_keeps_existing_progress(self):
        self.state.current_count = 2
        self.state.status_log = [3, 4]
        self.state.time_log = [1, 2]
        original = self.col.decks.cids
        self.col.decks.cids = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("query failed")
        )
        try:
            self.assertFalse(self.rebuild())
            self.assertEqual(self.state.status_log, [3, 4])
        finally:
            self.col.decks.cids = original

    def test_real_answer_undo_redo(self):
        for _ in range(4):
            self.card()
        for _ in range(3):
            self.answer_current(3)
        self.rebuild()
        self.assertEqual(self.state.status_log, [3, 3, 3])
        changes = self.col.undo()
        self.env["on_undo"](changes)
        self.assertEqual(self.state.status_log, [3, 3])
        self.assertEqual(self.state.initial_total, 100)
        self.env["on_operation"](changes)  # consumes same-undo reconciliation guard
        self.col.redo()
        self.rebuild()
        self.assertEqual(self.state.status_log, [3, 3, 3])

    def test_undo_ignored_again_does_not_remove_previous_pass(self):
        self.config["fail_policy"] = "ignore"
        for _ in range(3):
            self.card()
        self.answer_current(3)
        self.answer_current(1)
        self.rebuild()
        self.assertEqual(self.state.status_log, [3])
        self.env["on_undo"](self.col.undo())
        self.assertEqual(self.state.status_log, [3])

    def test_deck_switch_resets_baseline_not_same_deck_reentry(self):
        self.rebuild()
        self.state.initial_total = 100
        self.rebuild()
        self.assertEqual(self.state.initial_total, 100)
        self.col.decks.select(self.col.decks.id("Other"))
        self.rebuild()
        self.assertIsNone(self.state.initial_total)

    def test_filtered_undo_preserves_completed_cards_returned_home(self):
        self.filtered_deck()
        self.rebuild()  # captures/persists cohort before cards return home
        for _ in range(3):
            card = self.answer_current(4)
            self.assertEqual(self.col.get_card(card.id).did, self.did)
        self.rebuild()
        self.assertEqual(self.state.status_log, [4, 4, 4])
        changes = self.col.undo()
        self.env["on_undo"](changes)
        self.assertEqual(self.state.status_log, [4, 4])
        self.env["on_operation"](changes)
        self.col.redo()
        self.rebuild()
        self.assertEqual(self.state.status_log, [4, 4, 4])

    def test_filtered_reentry_preserves_completed_membership(self):
        self.filtered_deck()
        self.rebuild()
        for _ in range(3):
            self.answer_current(4)
        self.rebuild()
        self.assertEqual(self.state.current_count, 3)

    def test_filtered_switch_away_and_back_keeps_membership(self):
        filtered = self.filtered_deck()
        self.rebuild()
        for _ in range(3):
            self.answer_current(4)
        self.col.decks.select(self.did)
        self.rebuild()
        self.col.decks.select(filtered)
        self.rebuild()
        self.assertEqual(self.state.current_count, 3)

    def test_filtered_undo_after_all_cards_return_home(self):
        filtered = self.filtered_deck()
        self.rebuild()
        for _ in range(5):
            self.answer_current(4)
        self.assertEqual(self.col.decks.cids(filtered), [])
        self.rebuild()
        self.assertEqual(self.state.current_count, 5)
        self.env["on_undo"](self.col.undo())
        self.assertEqual(self.state.current_count, 4)

    def test_restart_mid_filtered_session_keeps_completed_reviews(self):
        self.filtered_deck()
        self.rebuild()
        for _ in range(3):
            self.answer_current(4)
        self.assertEqual(self.state.current_count, 3)

        # Simulate Anki/add-on restart: all process-global session state disappears.
        self.state.reset_collection_state()
        self.assertEqual(self.state.current_count, 0)
        self.rebuild()
        self.assertEqual(self.state.current_count, 3)
        self.assertEqual(self.state.status_log, [4, 4, 4])

    def test_repeat_manual_action_after_undo_does_not_duplicate(self):
        card = self.card()
        first = self.simulate_manual_operation("buried", card)
        self.assertEqual(self.state.status_log, ["buried"])
        self.assertEqual(len(self.state.manual_actions), 1)

        undo = self.col.undo()
        self.env["on_undo"](undo)
        self.env["on_operation"](undo)
        self.assertEqual(self.state.status_log, [])

        # Same card, same action, new operation. Old inactive record must be replaced.
        self.simulate_manual_operation("buried", card)
        self.assertEqual(self.state.status_log, ["buried"])
        self.assertEqual(len(self.state.manual_actions), 1)

    def test_same_card_new_presentation_can_be_manually_handled(self):
        card = self.card()
        self.env["on_show_question"](card)
        self.state.was_answered = True
        self.state.last_action_handled = True

        # Relearning/Again can present the identical cid again.
        self.env["on_show_question"](card)
        self.assertFalse(self.state.last_action_handled)
        self.env["on_bury"](None, card)
        self.assertEqual(len(self.state.pending_manual_actions), 1)

    def test_manual_action_is_committed_only_after_successful_state_change(self):
        card = self.card()
        self.mw.reviewer.card = card
        self.env["on_show_question"](card)
        self.env["on_bury"](None, card)
        self.assertEqual(self.state.manual_actions, [])

        # An unrelated operation cannot turn intent into progress while the card
        # is still live and unburied.
        self.env["on_operation"](NS(card=True, study_queues=True))
        self.assertEqual(self.state.manual_actions, [])
        self.assertEqual(self.state.status_log, [])

        result = self.col.sched.bury_cards([card.id])
        self.env["on_operation"](result)
        self.assertEqual(len(self.state.manual_actions), 1)
        self.assertEqual(self.state.status_log, ["buried"])

    def test_acknowledge_undo_survives_rebuild_restart_and_redo(self):
        self.config["undo_policy"] = "acknowledge"
        for _ in range(2):
            self.card()
        self.answer_current(3)
        self.rebuild()
        self.assertEqual(self.state.status_log, [3])

        undo = self.col.undo()
        self.env["on_undo"](undo)
        self.assertEqual(self.state.status_log, ["undone"])
        self.env["on_operation"](undo)

        self.state.reset_collection_state()
        self.rebuild()
        self.assertEqual(self.state.status_log, ["undone"])

        self.col.redo()
        self.rebuild()
        self.assertEqual(self.state.status_log, [3])
        self.assertEqual(self.state.undo_tombstones, [])

    def test_note_only_undo_does_not_acknowledge_unrelated_progress(self):
        self.config["undo_policy"] = "acknowledge"
        self.card()
        self.answer_current(3)
        self.rebuild()
        self.assertEqual(self.state.status_log, [3])
        self.env["on_undo"](
            NS(changes=NS(card=False, note=True, study_queues=False))
        )
        self.assertEqual(self.state.status_log, [3])
        self.assertEqual(self.state.undo_tombstones, [])

    def test_manual_state_does_not_leak_across_collections(self):
        card = self.card()
        self.simulate_manual_operation("suspended", card)
        self.assertEqual(self.state.status_log, ["suspended"])

        other_tmp = tempfile.TemporaryDirectory()
        other = Collection(str(Path(other_tmp.name) / "collection.anki2"))
        old_col = self.mw.col
        try:
            self.mw.col = other
            self.state.reset_collection_state()
            self.assertTrue(self.env["_ensure_session_state"]())
            self.assertEqual(self.state.manual_actions, [])
            self.assertEqual(self.state.filtered_memberships, {})
            self.assertEqual(self.state.undo_tombstones, [])
        finally:
            self.mw.col = old_col
            other.close()
            other_tmp.cleanup()

    def test_ignored_manual_action_still_reconciles_scheduler_state(self):
        self.config["bury_policy"] = "ignore"
        card = self.card()
        self.timers.clear()
        self.simulate_manual_operation("buried", card)
        self.assertEqual(self.state.status_log, [])
        self.assertTrue(self.timers, "operation completion should schedule a refresh")


if __name__ == "__main__":
    unittest.main()
