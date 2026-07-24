from aqt import mw
import aqt
from aqt.reviewer import Reviewer
from aqt.gui_hooks import reviewer_did_answer_card, state_did_change, sync_did_finish, reviewer_did_show_question
from aqt.qt import *
from . import logic
from . import layout

# Initialize UI
layout.init_widgets()

# Hooks
reviewer_did_answer_card.append(logic.on_answer)
reviewer_did_show_question.append(logic.on_show_question)
state_did_change.append(logic.on_state_change)
sync_did_finish.append(logic.on_sync_finished)

# --- BURY HOOKS ---
# We always wrap the manually triggered methods (Menu/Shortcuts) because Anki's hook might not fire for them
# or might fire too late. logic.on_bury handles double-counting.

# 1. Wrap onBuryNote (Menu often triggers this)
if hasattr(Reviewer, "onBuryNote"):
    _old_on_bury_note = Reviewer.onBuryNote
    def _new_on_bury_note(self, *args, **kwargs):
        card = self.card
        if card:
            try:
                logic.on_bury(self, card)
            except:
                pass
        
        try:
            res = _old_on_bury_note(self, *args, **kwargs)
        except TypeError:
            res = _old_on_bury_note(self)
        return res
    Reviewer.onBuryNote = _new_on_bury_note
if hasattr(Reviewer, "on_bury_note"):
    _old_on_bury_note = Reviewer.on_bury_note
    def _new_on_bury_note(self, *args, **kwargs):
        card = self.card
        if card:
            try:
                logic.on_bury(self, card)
            except:
                pass

        try:
            res = _old_on_bury_note(self, *args, **kwargs)
        except TypeError:
            res = _old_on_bury_note(self)
        return res
    Reviewer.on_bury_note = _new_on_bury_note

# 2. Wrap standard bury (Buttons/Shortcuts)
if hasattr(aqt.gui_hooks, "reviewer_did_bury_card"):
    aqt.gui_hooks.reviewer_did_bury_card.append(logic.on_bury)
else:
    # Fallback for older Anki
    _old_bury = Reviewer.bury_current_card
    def _new_bury(self, *args, **kwargs):
        card = self.card
        if card:
            try:
                logic.on_bury(self, card)
            except:
                pass

        try:
            res = _old_bury(self, *args, **kwargs)
        except TypeError:
             # Fallback: original might not accept args (e.g. from signal)
            res = _old_bury(self)
        return res
    Reviewer.bury_current_card = _new_bury
    
    if hasattr(Reviewer, "bury_current_note"):
        _old_bury_note = Reviewer.bury_current_note
        def _new_bury_note(self, *args, **kwargs):
            card = self.card
            if card:
                try:
                    logic.on_bury(self, card)
                except:
                    pass

            try:
                res = _old_bury_note(self, *args, **kwargs)
            except TypeError:
                res = _old_bury_note(self)
            return res
        Reviewer.bury_current_note = _new_bury_note
    
    # Also wrap onBuryCard (UI slot)
    if hasattr(Reviewer, "onBuryCard"):
        _old_on_bury = Reviewer.onBuryCard
        def _new_on_bury(self, *args, **kwargs):
            card = self.card
            if card:
                try:
                    logic.on_bury(self, card)
                except:
                    pass

            try:
                res = _old_on_bury(self, *args, **kwargs)
            except TypeError:
                res = _old_on_bury(self)
            return res
        Reviewer.onBuryCard = _new_on_bury
    elif hasattr(Reviewer, "onBury"):
         _old_on_bury = Reviewer.onBury
         def _new_on_bury(self, *args, **kwargs):
            card = self.card
            if card:
                try:
                    logic.on_bury(self, card)
                except:
                    pass

            try:
                res = _old_on_bury(self, *args, **kwargs)
            except TypeError:
                res = _old_on_bury(self)
            return res
         Reviewer.onBury = _new_on_bury

# --- SUSPEND HOOKS ---

# 1. Wrap onSuspendNote (Menu often triggers this)
if hasattr(Reviewer, "onSuspendNote"):
    _old_on_suspend_note = Reviewer.onSuspendNote
    def _new_on_suspend_note(self, *args, **kwargs):
        card = self.card
        if card:
            try:
                logic.on_suspend(self, card)
            except:
                pass

        try:
            res = _old_on_suspend_note(self, *args, **kwargs)
        except TypeError:
            res = _old_on_suspend_note(self)
        return res
    Reviewer.onSuspendNote = _new_on_suspend_note
if hasattr(Reviewer, "on_suspend_note"):
     _old_on_suspend_note = Reviewer.on_suspend_note
     def _new_on_suspend_note(self, *args, **kwargs):
         card = self.card
         if card:
             try:
                 logic.on_suspend(self, card)
             except:
                 pass

         try:
             res = _old_on_suspend_note(self, *args, **kwargs)
         except TypeError:
             res = _old_on_suspend_note(self)
         return res
     Reviewer.on_suspend_note = _new_on_suspend_note

# 2. Wrap standard suspend
if hasattr(aqt.gui_hooks, "reviewer_did_suspend_card"):
    aqt.gui_hooks.reviewer_did_suspend_card.append(logic.on_suspend)
else:
    # Fallback
    _old_suspend = Reviewer.suspend_current_card
    def _new_suspend(self, *args, **kwargs):
        card = self.card
        if card:
            try:
                logic.on_suspend(self, card)
            except:
                pass

        try:
            res = _old_suspend(self, *args, **kwargs)
        except TypeError:
            res = _old_suspend(self)
        return res
    Reviewer.suspend_current_card = _new_suspend
    
    if hasattr(Reviewer, "suspend_current_note"):
        _old_suspend_note = Reviewer.suspend_current_note
        def _new_suspend_note(self, *args, **kwargs):
            card = self.card
            if card:
                try:
                    logic.on_suspend(self, card)
                except:
                    pass

            try:
                res = _old_suspend_note(self, *args, **kwargs)
            except TypeError:
                res = _old_suspend_note(self)
            return res
        Reviewer.suspend_current_note = _new_suspend_note
    
    # Also wrap onSuspendCard (UI slot)
    if hasattr(Reviewer, "onSuspendCard"):
        _old_on_suspend = Reviewer.onSuspendCard
        def _new_on_suspend(self, *args, **kwargs):
            card = self.card
            if card:
                try:
                    logic.on_suspend(self, card)
                except:
                    pass
            res = _old_on_suspend(self, *args, **kwargs)
            return res
        Reviewer.onSuspendCard = _new_on_suspend
    elif hasattr(Reviewer, "onSuspend"):
         _old_on_suspend = Reviewer.onSuspend
         def _new_on_suspend(self, *args, **kwargs):
            card = self.card
            if card:
                try:
                    logic.on_suspend(self, card)
                except:
                    pass
            res = _old_on_suspend(self, *args, **kwargs)
            return res
         Reviewer.onSuspend = _new_on_suspend

# --- DELETE HOOKS ---
# There is no reviewer_did_delete hook, so wrap the reviewer's delete method
# directly (same pattern as the bury/suspend fallbacks). on_delete de-dupes.
if hasattr(Reviewer, "delete_current_note"):
    _old_delete_note = Reviewer.delete_current_note
    def _new_delete_note(self, *args, **kwargs):
        card = self.card
        if card:
            try:
                logic.on_delete(self, card)
            except:
                pass

        try:
            res = _old_delete_note(self, *args, **kwargs)
        except TypeError:
            res = _old_delete_note(self)
        return res
    Reviewer.delete_current_note = _new_delete_note

# Reliable Undo Hook
if hasattr(aqt.gui_hooks, "state_did_undo"):
    aqt.gui_hooks.state_did_undo.append(logic.on_undo)
elif hasattr(aqt.gui_hooks, "reviewer_did_undo"):
    aqt.gui_hooks.reviewer_did_undo.append(logic.on_undo)

# Redo handling: Anki exposes no redo hook and its Redo action is already bound to
# mw.redo, so we add a second slot to the action (fires for menu + Ctrl+Shift+Z)
# and reconcile once the async op lands via operation_did_execute.
try:
    mw.form.actionRedo.triggered.connect(logic.on_redo_triggered)
except Exception:
    pass
if hasattr(aqt.gui_hooks, "operation_did_execute"):
    aqt.gui_hooks.operation_did_execute.append(logic.on_operation)

# Settings (Note: layout.update_all_widgets is passed as callback)
mw.addonManager.setConfigUpdatedAction(__name__, layout.update_all_widgets)

# Add menu item
action = QAction("Progress Bar Settings", mw)
action.triggered.connect(layout.open_settings)
mw.form.menuTools.addAction(action)


