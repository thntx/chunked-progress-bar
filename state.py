
# Stores the session state for the addon
# This centralized object replaces the global variables previously in __init__.py

class SessionState:
    def __init__(self):
        self.last_deck_id = None  # FSRS tracking
        self.reset_collection_state()

    def reset_collection_state(self):
        """Clear everything tied to the currently loaded collection/profile."""
        self.history = []
        self.status_log = []
        self.time_log = []
        self.event_log = []
        self.start_time = 0
        self.current_count = 0
        self.initial_total = None

        self.collection_key = None
        self.day_key = None
        self.day_start_ms = None
        self.day_end_ms = None
        self.tracking_started_ms = None
        self.filtered_memberships = {}
        self.filtered_reviews = {}
        self.manual_actions = []
        self.undo_tombstones = []

        # Reviewer presentation/action tracking.
        self.last_card_id = None
        self.was_answered = False
        self.last_action_handled = False
        self.pending_manual_actions = []

        # state_did_undo fires inside the CollectionOp success callback, before
        # operation_did_execute for that same undo.  This flag prevents the latter
        # from immediately overwriting acknowledge-mode undo rendering.
        self.skip_next_operation_reconcile = False
        self.progress_context = None

    def reset_for_new_day(self):
        """Reset progress while retaining profile-independent FSRS cache state."""
        self.reset_collection_state()

# Singleton instance
session = SessionState()
