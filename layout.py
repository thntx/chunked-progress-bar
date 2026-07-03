from aqt import mw
from aqt.qt import *
from .progressbar import ProgressBarWidget
from .config_utils import DEFAULT_CONFIG, get_config_val
# Note: circular dependency avoidance - we don't import init/logic here.
# Settings dialog will need to be imported inside functions if needed.

# Global Widget Instances
chunk_widget = None
card_widget = None

def init_widgets():
    global chunk_widget, card_widget
    
    # Cleanup previous instances to prevent duplicates if re-initialized
    if chunk_widget:
        try:
            chunk_widget.setParent(None)
            mw.mainLayout.removeWidget(chunk_widget)
            chunk_widget.deleteLater()
        except:
            pass
            
    if card_widget:
        try:
            card_widget.setParent(None)
            mw.mainLayout.removeWidget(card_widget)
            card_widget.deleteLater()
        except:
            pass
            
    chunk_widget = ProgressBarWidget("chunks")
    chunk_widget.settings_callback = open_settings
    
    card_widget = ProgressBarWidget("cards")
    card_widget.settings_callback = open_settings
    
    config = mw.addonManager.getConfig(__name__)
    chunk_widget.update_config(config)
    card_widget.update_config(config)
    
    # Link hover states
    chunk_widget.hover_callback = card_widget.set_hover_state
    card_widget.hover_callback = chunk_widget.set_hover_state
    chunk_widget.sibling_bar = card_widget
    card_widget.sibling_bar = chunk_widget
    
    apply_layout(config)
    
    # Start hidden (will be shown by logic on_state_change)
    chunk_widget.hide()
    card_widget.hide()

def open_settings():
    from .settings import SettingsDialog
    config = mw.addonManager.getConfig(__name__)
    # Ensure default structure if missing keys
    d = SettingsDialog(mw, config)
    
    # Inject live update callback
    d.live_callback = update_all_widgets
    
    d.exec()
    # Updates are handled via setConfigUpdatedAction which is triggered by writeConfig in the dialog

def update_all_widgets(config):
    if chunk_widget: chunk_widget.update_config(config)
    if card_widget: card_widget.update_config(config)
    apply_layout(config)
    
    # Invalidate FSRS cache to force re-check if settings changed
    from .state import session
    session.last_deck_id = None
    session.initial_total = None # Reset total to recalculate with new settings (e.g. double_new)
    
    # Force logic refresh to apply new calculation settings (like double_new)
    from . import logic
    logic.refresh_bar()

def apply_layout(config):
    global chunk_widget, card_widget
    
    # Determine positions
    # Use centralized config defaults
    chunk_pos = get_config_val(config, DEFAULT_CONFIG, "positions", "chunks")
    card_pos = get_config_val(config, DEFAULT_CONFIG, "positions", "cards")
    
    # Remove existing
    if chunk_widget:
        chunk_widget.setParent(None)
        mw.mainLayout.removeWidget(chunk_widget)
        
    if card_widget:
        card_widget.setParent(None)
        mw.mainLayout.removeWidget(card_widget)
        
    # Re-insert based on stacking order
    stack = get_config_val(config, DEFAULT_CONFIG, "positions", "stack_order")
    
    # TOP DOCK: insertWidget(0, w) pushes previous 0 to 1.
    top_sequence = [card_widget, chunk_widget] if stack == "chunk" else [chunk_widget, card_widget]
    
    # BOTTOM DOCK: addWidget(w) appends.
    bot_sequence = [chunk_widget, card_widget] if stack == "chunk" else [card_widget, chunk_widget]
    
    # Apply Top
    for w in top_sequence:
        pos = card_pos if w == card_widget else chunk_pos
        if pos == "top":
            mw.mainLayout.insertWidget(0, w)
            
    # Apply Bottom
    for w in bot_sequence:
        pos = card_pos if w == card_widget else chunk_pos
        if pos == "bottom":
             mw.mainLayout.addWidget(w)

    # Visibility is primarily handled by logic (show/hide on state change),
    # but re-applying layout might reset visibility if we aren't careful.
    # We leave explicit show/hide to the logic module's on_state_change.
    if mw.state == "review":
        if chunk_pos != "hidden": chunk_widget.show()
        if card_pos != "hidden": card_widget.show()

def refresh_widgets(total, current, status_log, time_log, start_time, initial_total):
    """Updates the data in both widgets"""
    if chunk_widget:
        chunk_widget.set_params(total, current, status_log, time_log, start_time, initial_total)
    if card_widget:
        card_widget.set_params(total, current, status_log, time_log, start_time, initial_total)
