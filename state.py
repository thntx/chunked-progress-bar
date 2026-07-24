
# Stores the session state for the addon
# This centralized object replaces the global variables previously in __init__.py

class SessionState:
    def __init__(self):
        self.history = [] # Stores (current_count, status_log_list, time_log_list) snapshots
        self.last_deck_id = None # For FSRS tracking
        self.status_log = [] # True=Pass, False/1=Fail
        self.time_log = [] # Float seconds
        self.start_time = 0
        self.current_count = 0
        self.initial_total = None # Original total at session start (for excess calculation)
        
        # State-based detection tracking
        self.last_card_id = None
        self.was_answered = False
        self.last_action_handled = False
        self.last_handled_card_id = None
        self.pending_redo = False # Set when Anki's Redo action fires, consumed on op complete

# Singleton instance
session = SessionState()
