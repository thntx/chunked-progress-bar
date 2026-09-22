from aqt import gui_hooks, mw
from aqt.qt import QAction, QTimer
from aqt.reviewer import Reviewer

from . import layout, logic, notices


# Initialize UI once the add-on is imported.
layout.init_widgets()


# Review lifecycle.
gui_hooks.reviewer_did_answer_card.append(logic.on_answer)
gui_hooks.reviewer_did_show_question.append(logic.on_show_question)
gui_hooks.state_did_change.append(logic.on_state_change)
gui_hooks.sync_did_finish.append(logic.on_sync_finished)

if hasattr(gui_hooks, "collection_did_load"):
    gui_hooks.collection_did_load.append(logic.on_collection_loaded)
if hasattr(gui_hooks, "profile_will_close"):
    gui_hooks.profile_will_close.append(logic.on_profile_will_close)
if hasattr(gui_hooks, "day_did_change"):
    gui_hooks.day_did_change.append(logic.on_day_did_change)


# Current Anki exposes reviewer *will* hooks for bury/suspend.  They are intent
# signals only: logic.py waits for operation_did_execute and verifies the live DB
# state before counting them, so a failed async CollectionOp cannot create a
# phantom progress tile.
_modern_manual_hooks = True
for _hook_name, _handler in (
    ("reviewer_will_bury_card", logic.on_will_bury_card),
    ("reviewer_will_bury_note", logic.on_will_bury_note),
    ("reviewer_will_suspend_card", logic.on_will_suspend_card),
    ("reviewer_will_suspend_note", logic.on_will_suspend_note),
):
    _hook = getattr(gui_hooks, _hook_name, None)
    if _hook is None:
        _modern_manual_hooks = False
    else:
        _hook.append(_handler)


def _wrap_reviewer_intent(method_name, handler):
    """Compatibility fallback for Anki versions lacking the modern will hooks."""
    original = getattr(Reviewer, method_name, None)
    if original is None or getattr(original, "_chunked_progress_intent_wrapper", False):
        return

    def wrapped(self, *args, **kwargs):
        card = getattr(self, "card", None)
        if card:
            handler(self, card)
        return original(self, *args, **kwargs)

    wrapped._chunked_progress_intent_wrapper = True
    setattr(Reviewer, method_name, wrapped)


if not _modern_manual_hooks:
    _wrap_reviewer_intent("bury_current_card", logic.on_bury)
    _wrap_reviewer_intent("bury_current_note", logic.on_bury)
    _wrap_reviewer_intent("suspend_current_card", logic.on_suspend)
    _wrap_reviewer_intent("suspend_current_note", logic.on_suspend)


# There is still no reviewer-specific delete hook.  Wrap only the intent point;
# the actual event is committed later, after operation_did_execute confirms the
# card really disappeared.
_wrap_reviewer_intent("delete_current_note", logic.on_delete)


# All successful collection operations, including redo, arrive here.  This makes
# database state authoritative and removes the old QAction/pending-redo race.
if hasattr(gui_hooks, "operation_did_execute"):
    gui_hooks.operation_did_execute.append(logic.on_operation)

if hasattr(gui_hooks, "state_did_undo"):
    gui_hooks.state_did_undo.append(logic.on_undo)
elif hasattr(gui_hooks, "reviewer_did_undo"):
    gui_hooks.reviewer_did_undo.append(logic.on_undo)


# One-time default-change notices.
gui_hooks.profile_did_open.append(
    lambda: QTimer.singleShot(500, notices.check_default_change_notices)
)


# Settings.
mw.addonManager.setConfigUpdatedAction(__name__, layout.update_all_widgets)
action = QAction("Progress Bar Settings", mw)
action.triggered.connect(layout.open_settings)
mw.form.menuTools.addAction(action)
