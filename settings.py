
from aqt.qt import *
from aqt import mw

from . import progressbar
from . import fsrs_logic
import copy
from .config_utils import DEFAULT_CONFIG, get_config_val

class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()

class NoScrollDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()

class SettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        
        # Ensure DEFAULT_CONFIG is fresh from disk
        from .config_utils import reload_defaults
        self.default_config = copy.deepcopy(reload_defaults())
        
        self.original_config = copy.deepcopy(config) # Backup for Cancel
        self.colours = self.config.get("colors", self.default_config.get("colors", {})) 
        self.style_widgets = {}
        self.setWindowTitle("Progress Bar Settings")
        
        self.setup_ui()
        
        # Connect signals after UI is fully built
        self.connect_live_preview()
        
        # Initial Interval Setup (Must be after UI built for scrape check)
        self.setup_intervals_ui()

    def get(self, *keys):
        return get_config_val(self.config, self.default_config, *keys)


    def setup_ui(self):
        def add_reset_btn(layout, callback, text="Restore Defaults"):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(callback)
            # Align right
            h = QHBoxLayout()
            h.addStretch()
            h.addWidget(btn)
            layout.addLayout(h)
            
        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # --- Tab 1: Style ---
        style_widget = QWidget()
        style_layout = QVBoxLayout()
        

        
        top_group = QGroupBox("Chunk Bar Text")
        top_layout = QVBoxLayout()
        self.top_num_widgets = self.add_text_section(top_layout, "Tile Numbers", self.get("text_options", "top", "numbers"), self.default_config["text_options"]["top"]["numbers"], options=["chunks", "cards"])
        self.top_bar_num_widgets = self.add_text_section(top_layout, "Bar Number", self.get("text_options", "top", "bar_numbers"), self.default_config["text_options"]["top"]["bar_numbers"], options=["chunks", "cards"], dir_options=["done", "remaining", "done/total", "remaining/total"])
        
        self.top_pct_widgets = self.add_text_section(top_layout, "Tile Percentages", self.get("text_options", "top", "percentages"), self.default_config["text_options"]["top"]["percentages"], options=["chunks", "cards"], show_decimals_opt=True)
        self.top_bar_pct_widgets = self.add_text_section(top_layout, "Bar Percentage", self.get("text_options", "top", "bar_percentages"), self.default_config["text_options"]["top"]["bar_percentages"], options=["chunks", "cards"], show_decimals_opt=True)
        
        # Timer Integration
        self.chunk_timer_widgets = self.add_timer_section(top_layout, "Timer", self.get("timer", "chunk_timer"), self.default_config["timer"]["chunk_timer"])
        
        top_group.setLayout(top_layout)
        add_reset_btn(top_layout, self.reset_text_settings)
        style_layout.addWidget(top_group)
        
        bot_group = QGroupBox("Card Bar Text")
        bot_layout = QVBoxLayout()
        self.bot_num_widgets = self.add_text_section(bot_layout, "Tile Numbers", self.get("text_options", "bottom", "numbers"), self.default_config["text_options"]["bottom"]["numbers"], options=["relative", "absolute"])
        self.bot_bar_num_widgets = self.add_text_section(bot_layout, "Bar Number", self.get("text_options", "bottom", "bar_numbers"), self.default_config["text_options"]["bottom"]["bar_numbers"], options=["relative", "absolute"], dir_options=["done", "remaining", "done/total", "remaining/total"])
        
        self.bot_pct_widgets = self.add_text_section(bot_layout, "Tile Percentages", self.get("text_options", "bottom", "percentages"), self.default_config["text_options"]["bottom"]["percentages"], options=["relative", "absolute"], show_decimals_opt=True)
        self.bot_bar_pct_widgets = self.add_text_section(bot_layout, "Bar Percentage", self.get("text_options", "bottom", "bar_percentages"), self.default_config["text_options"]["bottom"]["bar_percentages"], options=["relative", "absolute"], show_decimals_opt=True)
        
        # Timer Integration
        self.card_timer_widgets = self.add_timer_section(bot_layout, "Timer", self.get("timer", "card_timer"), self.default_config["timer"]["card_timer"])

        bot_group.setLayout(bot_layout)
        add_reset_btn(bot_layout, self.reset_text_settings)
        style_layout.addWidget(bot_group)
        
        self.auto_hide_cb = QCheckBox("Remove text when stretched (too small)")
        self.auto_hide_cb.setChecked(self.get("visual_options", "auto_hide_text"))
        style_layout.addWidget(self.auto_hide_cb)
        
        self.timer_cap = QCheckBox("Use Anki's timer cap (usually 60s)")
        self.timer_cap.setChecked(self.get("timer", "use_anki_cap"))
        style_layout.addWidget(self.timer_cap)
        
        style_layout.addStretch()
        add_reset_btn(style_layout, self.reset_tab_style, "Restore Tab Defaults")
        
        style_widget.setLayout(style_layout)
        self.style_scroll = QScrollArea()
        self.style_scroll.setWidget(style_widget)
        self.style_scroll.setWidgetResizable(True)
        self.tabs.addTab(self.style_scroll, "Text")

        # --- Tab 2: Colours ---
        colours_tab = QWidget()
        colours_tab_layout = QVBoxLayout()
        
        colour_group = QGroupBox("Base Colours")
        # Colour Grid
        colour_layout = QGridLayout() 
        colour_layout.setColumnStretch(1, 1)
        colour_layout.setColumnStretch(2, 0) # Force label
        colour_layout.setColumnStretch(3, 1)
        
        self.colour_btns = {} 
        
        # Row 0: Current / Pending
        colour_layout.addWidget(QLabel("Current:"), 0, 0)
        self.current_colour_btn = self.create_colour_btn(self.get("colors", "current"), "current")
        colour_layout.addWidget(self.current_colour_btn, 0, 1)
        
        colour_layout.addWidget(QLabel("Pending:"), 0, 2)
        self.pending_colour_btn = self.create_colour_btn(self.get("colors", "pending"), "pending")
        colour_layout.addWidget(self.pending_colour_btn, 0, 3)
        
        # Row 1: Again / Hard
        colour_layout.addWidget(QLabel("Again:"), 1, 0)
        self.again_colour_btn = self.create_colour_btn(self.get("colors", "again"), "again")
        colour_layout.addWidget(self.again_colour_btn, 1, 1)

        self.hard_label = QLabel("Hard:")
        colour_layout.addWidget(self.hard_label, 1, 2)
        self.hard_colour_btn = self.create_colour_btn(self.get("colors", "hard"), "hard")
        colour_layout.addWidget(self.hard_colour_btn, 1, 3)
        
        # Row 2: Good / Easy
        colour_layout.addWidget(QLabel("Good:"), 2, 0)
        self.good_colour_btn = self.create_colour_btn(self.get("colors", "good"), "good")
        colour_layout.addWidget(self.good_colour_btn, 2, 1)
        
        self.easy_label = QLabel("Easy:")
        colour_layout.addWidget(self.easy_label, 2, 2)
        self.easy_colour_btn = self.create_colour_btn(self.get("colors", "easy"), "easy")
        colour_layout.addWidget(self.easy_colour_btn, 2, 3)
        
        # Row 3: Buried / Suspended
        colour_layout.addWidget(QLabel("Buried:"), 3, 0)
        self.buried_colour_btn = self.create_colour_btn(self.get("colors", "buried"), "buried")
        colour_layout.addWidget(self.buried_colour_btn, 3, 1)
        
        colour_layout.addWidget(QLabel("Suspended:"), 3, 2)
        self.suspended_colour_btn = self.create_colour_btn(self.get("colors", "suspended"), "suspended")
        colour_layout.addWidget(self.suspended_colour_btn, 3, 3)
        
        # Row 4: Undone / Excess
        colour_layout.addWidget(QLabel("Undone:"), 4, 0)
        self.undone_colour_btn = self.create_colour_btn(self.get("colors", "undone"), "undone")
        colour_layout.addWidget(self.undone_colour_btn, 4, 1)
        
        self.excess_label = QLabel("Excess Chunk:")
        colour_layout.addWidget(self.excess_label, 4, 2)
        self.excess_colour_btn = self.create_colour_btn(self.get("colors", "excess"), "excess")
        colour_layout.addWidget(self.excess_colour_btn, 4, 3)

        # Row 5: Deleted
        colour_layout.addWidget(QLabel("Deleted:"), 5, 0)
        self.deleted_colour_btn = self.create_colour_btn(self.get("colors", "deleted"), "deleted")
        colour_layout.addWidget(self.deleted_colour_btn, 5, 1)

        # Checkboxes and their dependencies
        self.use_good_as_pass_cb = QCheckBox("Use Good for all pass")
        self.use_good_as_pass_cb.setChecked(self.get("visual_options", "use_good_for_all_pass"))
        colour_layout.addWidget(self.use_good_as_pass_cb, 6, 0, 1, 2)

        self.highlight_excess_cb = QCheckBox("Highlight excess chunks")
        self.highlight_excess_cb.setChecked(self.get("visual_options", "highlight_excess"))
        colour_layout.addWidget(self.highlight_excess_cb, 6, 2, 1, 2) # Place next to it or below? User asked for checkbox "then make a checkbox..."
        
        
        # Dependencies
        def update_pass_deps(checked):
            self.hard_colour_btn.setEnabled(not checked); self.hard_label.setEnabled(not checked)
            self.easy_colour_btn.setEnabled(not checked); self.easy_label.setEnabled(not checked)
        self.use_good_as_pass_cb.toggled.connect(update_pass_deps)
        update_pass_deps(self.use_good_as_pass_cb.isChecked())
        
        def update_excess_deps(checked):
            self.excess_colour_btn.setEnabled(checked); self.excess_label.setEnabled(checked)
        self.highlight_excess_cb.toggled.connect(update_excess_deps)
        update_excess_deps(self.highlight_excess_cb.isChecked())
        
        colour_group.setLayout(colour_layout)
        
        # Restore Defaults Base Colours
        c_reset_btn = QPushButton("Restore Defaults")
        c_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        c_reset_btn.clicked.connect(self.reset_base_colours)
        
        # Align right
        h_c_reset = QHBoxLayout()
        h_c_reset.addStretch()
        h_c_reset.addWidget(c_reset_btn)
        
        # Position at the bottom of the grid
        colour_layout.addLayout(h_c_reset, 6, 0, 1, 4) 
        
        colours_tab_layout.addWidget(colour_group)
        
        # Chunk Evaluation Group
        eval_group = QGroupBox("Completed Chunk Colouring")
        eval_layout = QVBoxLayout()
        
        # Explanation
        eval_layout.addWidget(QLabel("When a chunk is completed, the add-on will take the values of each card and calculate an average.\nThe chunk will then be given a colour based on that average."))
        
        # Weights
        eval_layout.addWidget(QLabel("<b>Change these numbers to modify the value of each difficulty:</b>"))
        w_layout = QGridLayout()
        w_layout.addWidget(QLabel("Again:"), 0, 0)
        self.w_again_spin = NoScrollDoubleSpinBox(); self.w_again_spin.setRange(0, 10); self.w_again_spin.setSingleStep(0.1)
        w_layout.addWidget(self.w_again_spin, 0, 1)
        
        w_layout.addWidget(QLabel("Hard:"), 0, 2)
        self.w_hard_spin = NoScrollDoubleSpinBox(); self.w_hard_spin.setRange(0, 10); self.w_hard_spin.setSingleStep(0.1)
        w_layout.addWidget(self.w_hard_spin, 0, 3)
        
        w_layout.addWidget(QLabel("Good:"), 1, 0)
        self.w_good_spin = NoScrollDoubleSpinBox(); self.w_good_spin.setRange(0, 10); self.w_good_spin.setSingleStep(0.1)
        w_layout.addWidget(self.w_good_spin, 1, 1)
        
        w_layout.addWidget(QLabel("Easy:"), 1, 2)
        self.w_easy_spin = NoScrollDoubleSpinBox(); self.w_easy_spin.setRange(0, 10); self.w_easy_spin.setSingleStep(0.1)
        w_layout.addWidget(self.w_easy_spin, 1, 3)
        
        eval_layout.addLayout(w_layout)
        
        # Intervals
        eval_layout.addWidget(QLabel("<b>Change these numbers to modify the intervals in which each colour is chosen.</b>"))
        
        # Interval Container
        self.interval_widget = QWidget()
        self.interval_layout = QVBoxLayout()
        self.interval_layout.setSpacing(2)
        self.interval_widget.setLayout(self.interval_layout)
        eval_layout.addWidget(self.interval_widget)
        
        eval_group.setLayout(eval_layout)
        
        # FSRS Retention
        fsrs_layout = QHBoxLayout()
        fsrs_layout.addWidget(QLabel("Desired Retention:"))
        self.fsrs_retention = NoScrollDoubleSpinBox()
        self.fsrs_retention.setRange(0.0, 1.0)
        self.fsrs_retention.setSingleStep(0.01)
        # Load saved retention or default from config.json
        def_ret = self.get("fsrs_retention")
        self.fsrs_retention.setValue(def_ret)
        
        fsrs_layout.addWidget(self.fsrs_retention)
        
        self.fsrs_btn = QPushButton("Set values based on desired retention")
        self.fsrs_btn.clicked.connect(self.apply_fsrs_settings)
        fsrs_layout.addWidget(self.fsrs_btn)
        
        eval_layout.addLayout(fsrs_layout)
        
        # Advanced Options
        adv_layout = QVBoxLayout()
        self.cb_auto_chunk = QCheckBox("Update on cards per chunk change")
        self.cb_auto_chunk.setToolTip("Update intervals when changing chunk size")
        def_auto = self.default_config["fsrs_auto_chunk"]
        self.cb_auto_chunk.setChecked(self.get("fsrs_auto_chunk"))
        
        self.cb_use_deck_retention = QCheckBox("Update on deck selection")
        self.cb_use_deck_retention.setToolTip("Fetch FSRS desired retention and update intervals when selecting a deck")
        self.cb_use_deck_retention.setChecked(self.get("fsrs_use_deck"))
        
        adv_layout.addWidget(self.cb_auto_chunk)
        adv_layout.addWidget(self.cb_use_deck_retention)
        eval_layout.addLayout(adv_layout)
        fsrs_layout.addWidget(self.fsrs_btn)
        
        add_reset_btn(eval_layout, self.reset_chunk_evaluation)
        colours_tab_layout.addWidget(eval_group)
        
        # Load values
        self.w_again_spin.setValue(self.get("chunk_evaluation", "weights", "again"))
        self.w_hard_spin.setValue(self.get("chunk_evaluation", "weights", "hard"))
        self.w_good_spin.setValue(self.get("chunk_evaluation", "weights", "good"))
        self.w_easy_spin.setValue(self.get("chunk_evaluation", "weights", "easy"))
        
        self.interval_rows = []
        # setup_intervals_ui call moved to end of setup_ui
        
        perfect_group = QGroupBox("Perfect Chunks")
        perfect_layout = QHBoxLayout()
        self.highlight_perfect_cb = QCheckBox("Highlight perfect chunks")
        self.highlight_perfect_cb.setChecked(self.get("visual_options", "highlight_perfect"))
        perfect_layout.addWidget(self.highlight_perfect_cb)
        
        self.perfect_include_hard_cb = QCheckBox("Include hard cards")
        self.perfect_include_hard_cb.setToolTip("If checked, Hard cards are considered perfect (only 'Again' breaks perfection).")
        self.perfect_include_hard_cb.setChecked(self.get("visual_options", "perfect_include_hard"))
        perfect_layout.addWidget(self.perfect_include_hard_cb)
        
        self.perfect_colour_btn = self.create_colour_btn(self.get("colors", "perfect_color"), "perfect_color")
        perfect_layout.addWidget(self.perfect_colour_btn)
        
        def update_perfect_deps(checked):
            self.perfect_include_hard_cb.setEnabled(checked); self.perfect_colour_btn.setEnabled(checked)
        self.highlight_perfect_cb.toggled.connect(update_perfect_deps)
        update_perfect_deps(self.highlight_perfect_cb.isChecked())
        perfect_group.setLayout(perfect_layout); colours_tab_layout.addWidget(perfect_group)
        # Reset perfect inside group? Layout is HBox.
        # Add a tool button? Or just add it to the layout.
        p_reset = QPushButton("Restore Defaults"); p_reset.clicked.connect(self.reset_perfect_settings)
        perfect_layout.addWidget(p_reset)
        
        colours_tab_layout.addStretch()
        add_reset_btn(colours_tab_layout, self.reset_tab_colours, "Restore Tab Defaults")
        colours_tab.setLayout(colours_tab_layout)
        self.colours_scroll = QScrollArea()
        self.colours_scroll.setWidget(colours_tab)
        self.colours_scroll.setWidgetResizable(True)
        self.tabs.insertTab(1, self.colours_scroll, "Style")
 
        # =======================
        # Tab 2: Behaviour
        # =======================
        behaviour_widget = QWidget()
        behaviour_layout = QVBoxLayout()
        
        # Chunk Size
        h = QHBoxLayout()
        h.addWidget(QLabel("Chunk Size:"))
        self.chunk_spin = NoScrollSpinBox()
        self.chunk_spin.setRange(1, 9999)
        self.chunk_spin.setValue(self.get("chunk_size"))
        # Connect to auto-update logic
        self.chunk_spin.valueChanged.connect(self.on_chunk_size_change)
        h.addWidget(self.chunk_spin)
        behaviour_layout.addLayout(h)

        # --- Layout Settings Moved Here ---
        layout_group = QGroupBox("Layout")
        layout_grid = QGridLayout()
        layout_grid.addWidget(QLabel("Chunk Bar:"), 0, 0)
        self.chunk_pos_combo = NoScrollComboBox()
        self.chunk_pos_combo.addItems(["top", "bottom", "hidden"])
        self.chunk_pos_combo.setCurrentText(self.get("positions", "chunks"))
        layout_grid.addWidget(self.chunk_pos_combo, 0, 1)
        
        layout_grid.addWidget(QLabel("Card Bar:"), 1, 0)
        self.card_pos_combo = NoScrollComboBox()
        self.card_pos_combo.addItems(["top", "bottom", "hidden"])
        self.card_pos_combo.setCurrentText(self.get("positions", "cards"))
        layout_grid.addWidget(self.card_pos_combo, 1, 1)
        
        layout_grid.addWidget(QLabel("Which should be on top of the other:"), 2, 0)
        self.stack_order_combo = NoScrollComboBox()
        self.stack_order_combo.addItem("chunk bar", "chunk")
        self.stack_order_combo.addItem("card bar", "card")
        cur_stack = self.get("positions", "stack_order")
        idx = self.stack_order_combo.findData(cur_stack)
        if idx >= 0: self.stack_order_combo.setCurrentIndex(idx)
        layout_grid.addWidget(self.stack_order_combo, 2, 1)
        
        layout_v = QVBoxLayout() # Wrap grid to add reset button at bottom
        layout_v.addLayout(layout_grid)
        add_reset_btn(layout_v, self.reset_layout_settings)
        
        layout_group.setLayout(layout_v)
        behaviour_layout.addWidget(layout_group)
        # --------------------------------
 
        # Double New Option
        self.double_new_cb = QCheckBox("Assume new cards are reviewed twice")
        self.double_new_cb.setChecked(self.get("double_new"))
        behaviour_layout.addWidget(self.double_new_cb)
        
        # --- Concrete Response Policy ---
        policy_group = QGroupBox("Concrete Response Policy")
        policy_layout = QFormLayout()
        
        # Fail Policy
        self.fail_policy_cb = NoScrollComboBox()
        self.fail_policy_cb.addItems(["ignore", "acknowledge"])
        self.fail_policy_cb.setCurrentText(self.get("fail_policy"))
        self.fail_policy_cb.currentIndexChanged.connect(self.live_update_handler)
        policy_layout.addRow("Action on Again:", self.fail_policy_cb)
        
        # Bury Policy
        self.bury_policy_cb = NoScrollComboBox()
        self.bury_policy_cb.addItems(["ignore", "acknowledge"])
        self.bury_policy_cb.setCurrentText(self.get("bury_policy"))
        self.bury_policy_cb.currentIndexChanged.connect(self.live_update_handler)
        policy_layout.addRow("Action on Bury:", self.bury_policy_cb)
        
        # Suspend Policy
        self.suspend_policy_cb = NoScrollComboBox()
        self.suspend_policy_cb.addItems(["ignore", "acknowledge"])
        self.suspend_policy_cb.setCurrentText(self.get("suspend_policy"))
        self.suspend_policy_cb.currentIndexChanged.connect(self.live_update_handler)
        policy_layout.addRow("Action on Suspend:", self.suspend_policy_cb)

        # Delete Policy
        self.delete_policy_cb = NoScrollComboBox()
        self.delete_policy_cb.addItems(["ignore", "acknowledge"])
        self.delete_policy_cb.setCurrentText(self.get("delete_policy"))
        self.delete_policy_cb.currentIndexChanged.connect(self.live_update_handler)
        policy_layout.addRow("Action on Delete:", self.delete_policy_cb)

        # Undo Policy
        self.undo_policy_cb = NoScrollComboBox()
        self.undo_policy_cb.addItems(["undo", "acknowledge"])
        self.undo_policy_cb.setCurrentText(self.get("undo_policy"))
        self.undo_policy_cb.currentIndexChanged.connect(self.live_update_handler)
        policy_layout.addRow("Action on Undo:", self.undo_policy_cb)
        
        # Reset Button Inside Group
        self.p_reset_btn = QPushButton("Restore Defaults")
        self.p_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.p_reset_btn.clicked.connect(self.reset_behaviour_settings)
        
        # Use HBox to prevent full stretching and align like others
        h_p_reset = QHBoxLayout()
        h_p_reset.setContentsMargins(0, 0, 0, 0)
        h_p_reset.addStretch()
        h_p_reset.addWidget(self.p_reset_btn)
        
        # Add as a row spanning columns, but inside the layout control
        self.w_p_reset = QWidget()
        self.w_p_reset.setLayout(h_p_reset)
        policy_layout.addRow(self.w_p_reset)
        
        policy_group.setLayout(policy_layout)
        behaviour_layout.addWidget(policy_group)
        
        behaviour_layout.addStretch()
        behaviour_widget.setLayout(behaviour_layout)
        self.behaviour_scroll = QScrollArea()
        self.behaviour_scroll.setWidget(behaviour_widget)
        self.behaviour_scroll.setWidgetResizable(True)
        self.tabs.insertTab(0, self.behaviour_scroll, "General") 
 
        
        # Restore Defaults Tab Behaviour
        add_reset_btn(behaviour_layout, self.reset_tab_behaviour, "Restore Tab Defaults")
        
        self.tabs.setCurrentIndex(0)
        
        # --- Main Buttons ---
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        restore_btn = btns.addButton("Restore Defaults", QDialogButtonBox.ButtonRole.ResetRole)
        restore_btn.clicked.connect(self.restore_defaults)
        
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)
        
        self.setLayout(main_layout)




    def add_text_section(self, parent_layout, label_text, config_dict, default_dict, options=None, dir_options=None, show_decimals_opt=False):
        # Create a horizontal row for the main options
        h = QHBoxLayout()
        
        # Checkbox
        enabled_cb = QCheckBox(label_text)
        enabled_cb.setChecked(config_dict.get("enabled", default_dict.get("enabled")))
        h.addWidget(enabled_cb)
        
        # Type
        type_combo = NoScrollComboBox()
        if options is None:
            options = ["relative", "absolute", "total"]
            
        if options: # Non-empty list
            type_combo.addItems(options)
            type_combo.setCurrentText(config_dict.get("type", default_dict.get("type")))
        else:
            type_combo.setVisible(False)
            
        h.addWidget(type_combo)
        
        # Direction
        dir_combo = NoScrollComboBox()
        if dir_options is None:
             dir_options = ["done", "remaining"]
        dir_combo.addItems(dir_options)
        dir_combo.setCurrentText(config_dict.get("count_direction", default_dict.get("count_direction")))
        h.addWidget(dir_combo)
        
        # Decimals (Optional)
        dec_cb = None
        dec_spin = None
        if show_decimals_opt:
            dec_cb = QCheckBox("Show Decimals")
            dec_cb.setChecked(config_dict.get("show_decimals", default_dict.get("show_decimals", False)))
            h.addWidget(dec_cb)
            
            dec_spin = NoScrollSpinBox()
            dec_spin.setRange(1, 5)
            dec_spin.setValue(config_dict.get("decimals", default_dict.get("decimals", 2)))
            dec_spin.setEnabled(dec_cb.isChecked())
            dec_cb.toggled.connect(dec_spin.setEnabled)
            h.addWidget(dec_spin)
        
        h.addStretch() # Keep packed to left
        parent_layout.addLayout(h)
        
        # Style Row
        h_style = QHBoxLayout()
        h_style.setContentsMargins(20, 0, 0, 5) # Indent
        
        h_style.addWidget(QLabel("Style:"))
        # User requested: "Style: Colour: [selector] Bold [x] Outline [X] [Colour selector]"
        h_style.addWidget(QLabel("Colour:"))
        
        # Color
        cur_style = config_dict.get("style", default_dict.get("style", {}))
        def_style = default_dict["style"]
        
        color_btn = QPushButton()
        c_val = cur_style.get("color", default_dict.get("style", {}).get("color"))
        color_btn.setStyleSheet(f"background-color: {c_val}")
        color_btn.setProperty("hex_color", c_val)
        # Fixed width for color buttons to look like small squares/rects as in standard UI
        color_btn.setFixedWidth(40) 
        color_btn.clicked.connect(lambda: self.pick_style_colour(color_btn))
        h_style.addWidget(color_btn)
        
        # Bold
        bold_cb = QCheckBox("Bold")
        bold_cb.setChecked(cur_style.get("bold", default_dict.get("style", {}).get("bold")))
        h_style.addWidget(bold_cb)
        
        # Outline
        outline_cb = QCheckBox("Outline")
        outline_cb.setChecked(cur_style.get("outline", default_dict.get("style", {}).get("outline")))
        h_style.addWidget(outline_cb)
        
        # Outline Color
        oc_val = cur_style.get("outline_color", default_dict.get("style", {}).get("outline_color"))
        outline_btn = QPushButton()
        outline_btn.setStyleSheet(f"background-color: {oc_val}")
        outline_btn.setProperty("hex_color", oc_val)
        outline_btn.setFixedWidth(40)
        outline_btn.clicked.connect(lambda: self.pick_style_colour(outline_btn))
        h_style.addWidget(outline_btn)
        
        h_style.addStretch() # Keep packed to left
        parent_layout.addLayout(h_style)
        
        return {
            "enabled": enabled_cb,
            "type": type_combo,
            "dir": dir_combo,
            "show_decimals": dec_cb,
            "decimals": dec_spin,
            "color": color_btn,
            "bold": bold_cb,
            "outline": outline_cb,
            "outline_color": outline_btn
        }

    def add_timer_section(self, parent_layout, label_text, config_dict, default_dict):
        # Main Enable + Live Row
        h = QHBoxLayout()
        enabled_cb = QCheckBox(label_text)
        enabled_cb.setChecked(config_dict.get("enabled", default_dict.get("enabled")))
        h.addWidget(enabled_cb)
        
        h.addSpacing(20)
        
        live_cb = QCheckBox("Show Live Timer")
        live_cb.setChecked(config_dict.get("live_enabled", default_dict.get("live_enabled")))
        h.addWidget(live_cb)
        
        h.addStretch()
        parent_layout.addLayout(h)
        
        # Format Row
        h_fmt = QHBoxLayout()
        h_fmt.setContentsMargins(20, 0, 0, 0)
        h_fmt.addWidget(QLabel("Format:"))
        
        fmt = config_dict.get("format", {})
        def_fmt = default_dict.get("format", {})
        
        min_cb = QCheckBox("Minutes")
        min_cb.setChecked(fmt.get("minutes", default_dict.get("format", {}).get("minutes")))
        h_fmt.addWidget(min_cb)
        
        sec_cb = QCheckBox("Seconds")
        sec_cb.setChecked(fmt.get("seconds", default_dict.get("format", {}).get("seconds")))
        h_fmt.addWidget(sec_cb)
        
        ms_cb = QCheckBox("Milliseconds")
        ms_cb.setChecked(fmt.get("milliseconds", default_dict.get("format", {}).get("milliseconds")))
        h_fmt.addWidget(ms_cb)
        
        # Logic: ms enabled only if sec enabled
        ms_cb.setEnabled(sec_cb.isChecked())
        def on_sec_change(checked):
            ms_cb.setEnabled(checked)
            if not checked: ms_cb.setChecked(False)
        sec_cb.toggled.connect(on_sec_change)

        h_fmt.addStretch()
        parent_layout.addLayout(h_fmt)
        
        # Style Row
        h_style = QHBoxLayout()
        h_style.setContentsMargins(20, 0, 0, 5)
        h_style.addWidget(QLabel("Style:"))
        # Match text section layout: "Style: Colour: [selector] Bold [x] Outline [X] [Colour selector]"
        h_style.addWidget(QLabel("Colour:"))
        
        cur_style = config_dict.get("style", default_dict.get("style", {}))
        def_style = default_dict["style"]
        
        color_btn = QPushButton()
        c_val = cur_style.get("color", default_dict.get("style", {}).get("color"))
        color_btn.setStyleSheet(f"background-color: {c_val}")
        color_btn.setProperty("hex_color", c_val)
        color_btn.setFixedWidth(40)
        color_btn.clicked.connect(lambda: self.pick_style_colour(color_btn))
        h_style.addWidget(color_btn)
        
        bold_cb = QCheckBox("Bold")
        bold_cb.setChecked(cur_style.get("bold", default_dict.get("style", {}).get("bold")))
        h_style.addWidget(bold_cb)
        
        # Outline
        outline_cb = QCheckBox("Outline")
        outline_cb.setChecked(cur_style.get("outline", default_dict.get("style", {}).get("outline")))
        h_style.addWidget(outline_cb)
        
        # Outline Color
        oc_val = cur_style.get("outline_color", default_dict.get("style", {}).get("outline_color"))
        outline_btn = QPushButton()
        outline_btn.setStyleSheet(f"background-color: {oc_val}")
        outline_btn.setProperty("hex_color", oc_val)
        outline_btn.setFixedWidth(40)
        outline_btn.clicked.connect(lambda: self.pick_style_colour(outline_btn))
        h_style.addWidget(outline_btn)
        
        h_style.addStretch()
        parent_layout.addLayout(h_style)
        
        return {
            "enabled": enabled_cb,
            "live": live_cb,
            "minutes": min_cb,
            "seconds": sec_cb,
            "milliseconds": ms_cb,
            "color": color_btn,
            "bold": bold_cb,
            "outline": outline_cb,
            "outline_color": outline_btn
        }



    def create_colour_btn(self, colour_str, key):
        btn = QPushButton()
        # Handle cases where config might have None or missing keys
        defaults = self.default_config.get("colors", {})
        def_c = defaults.get("pending", "#333333")
        c_val = (colour_str or def_c).upper()
        btn.setText(c_val)
        btn.setStyleSheet(f"background-color: {c_val}")
        self.colours[key] = c_val
        self.colour_btns[key] = btn 
        btn.clicked.connect(lambda _, k=key, b=btn: self.pick_colour(k, b))
        return btn

    def pick_colour(self, key, btn):
        curr = QColor(self.colours[key])
        color = QColorDialog.getColor(curr, self)
        if color.isValid():
            hex_c = color.name().upper()
            self.colours[key] = hex_c
            btn.setText(hex_c)
            btn.setStyleSheet(f"background-color: {hex_c}")
            self.live_update_handler()

    def reject(self):
        # Restore original config on Cancel
        mw.addonManager.writeConfig(__name__, self.original_config)
        super().reject()

    def connect_live_preview(self):
        # Connect all widgets to update handler
        # Style
        self.chunk_pos_combo.currentIndexChanged.connect(self.live_update_handler)
        self.card_pos_combo.currentIndexChanged.connect(self.live_update_handler)
        self.stack_order_combo.currentIndexChanged.connect(self.live_update_handler) # Connect new option
        self.auto_hide_cb.toggled.connect(self.live_update_handler)
        self.card_pos_combo.currentIndexChanged.connect(self.live_update_handler)
        self.auto_hide_cb.toggled.connect(self.live_update_handler)
        
        # Colors
        self.use_good_as_pass_cb.toggled.connect(self.live_update_handler)
        self.highlight_excess_cb.toggled.connect(self.live_update_handler)
        self.highlight_perfect_cb.toggled.connect(self.live_update_handler)
        self.perfect_include_hard_cb.toggled.connect(self.live_update_handler)
        
        # Link Weights to Interval Logic (Dynamic Min/Max)
        self.w_again_spin.valueChanged.connect(self.update_intervals_logic)
        self.w_hard_spin.valueChanged.connect(self.update_intervals_logic)
        self.w_good_spin.valueChanged.connect(self.update_intervals_logic)
        self.w_easy_spin.valueChanged.connect(self.update_intervals_logic)
        
        # Behaviors
        self.chunk_spin.valueChanged.connect(self.live_update_handler)
        self.double_new_cb.toggled.connect(self.live_update_handler)
        self.fail_policy_cb.currentIndexChanged.connect(self.live_update_handler)
        self.undo_policy_cb.currentIndexChanged.connect(self.live_update_handler)
        
        # Timer
        self.timer_cap.toggled.connect(self.live_update_handler)
        
        # Helper to connect dictionaries of widgets
        def connect_dict(widgets):
            widgets["enabled"].toggled.connect(self.live_update_handler)
            widgets["type"].currentIndexChanged.connect(self.live_update_handler)
            widgets["dir"].currentIndexChanged.connect(self.live_update_handler)
            widgets["bold"].toggled.connect(self.live_update_handler)
            widgets["outline"].toggled.connect(self.live_update_handler)
            
            if widgets.get("show_decimals"):
                widgets["show_decimals"].toggled.connect(self.live_update_handler)
            if widgets.get("decimals"):
                widgets["decimals"].valueChanged.connect(self.live_update_handler)
            # Buttons connect via their click handlers which call pick_colour/style_colour
            # But the actual value change needs to trigger update.
            # We can modify pick_colour and pick_style_colour to call live_update_handler
        
        connect_dict(self.top_num_widgets)
        connect_dict(self.top_bar_num_widgets)
        connect_dict(self.top_pct_widgets)
        connect_dict(self.top_bar_pct_widgets)
        connect_dict(self.bot_num_widgets)
        connect_dict(self.bot_bar_num_widgets)
        connect_dict(self.bot_pct_widgets)
        connect_dict(self.bot_bar_pct_widgets)
        
        def connect_timer_dict(widgets):
            widgets["enabled"].toggled.connect(self.live_update_handler)
            widgets["live"].toggled.connect(self.live_update_handler)
            widgets["minutes"].toggled.connect(self.live_update_handler)
            widgets["seconds"].toggled.connect(self.live_update_handler)
            widgets["milliseconds"].toggled.connect(self.live_update_handler)
            widgets["bold"].toggled.connect(self.live_update_handler)
            widgets["outline"].toggled.connect(self.live_update_handler)
            
        connect_timer_dict(self.chunk_timer_widgets)
        connect_timer_dict(self.card_timer_widgets)
        
    def pick_style_colour(self, btn):
        # Allow picking colour for style buttons (bg colour)
        curr_hex = btn.property("hex_color")
        curr = QColor(curr_hex)
        color = QColorDialog.getColor(curr, self)
        
        if color.isValid():
            hex_c = color.name().upper()
            btn.setProperty("hex_color", hex_c)
            btn.setStyleSheet(f"background-color: {hex_c}")
            
            self.live_update_handler() 



    def reset_layout_settings(self):
        def_pos = self.default_config.get("positions", {})
        self.chunk_pos_combo.setCurrentText(def_pos.get("chunks", "top"))
        self.card_pos_combo.setCurrentText(def_pos.get("cards", "bottom"))
        
        def_stack = def_pos.get("stack_order", "chunk")
        idx = self.stack_order_combo.findData(def_stack)
        if idx >= 0: self.stack_order_combo.setCurrentIndex(idx)
        
        self.live_update_handler()

    def reset_text_settings(self):
        def_txt = self.default_config.get("text_options", {})
        
        def restore_section(widgets, conf):
            widgets["enabled"].setChecked(conf["enabled"])
            widgets["type"].setCurrentText(conf["type"])
            widgets["dir"].setCurrentText(conf["count_direction"])
            style = conf["style"]
            c_val = style["color"].upper()
            widgets["color"].setProperty("hex_color", c_val)
            widgets["color"].setStyleSheet(f"background-color: {c_val}")
            widgets["bold"].setChecked(style["bold"])
            widgets["outline"].setChecked(style["outline"])
            oc_val = style["outline_color"].upper()
            widgets["outline_color"].setProperty("hex_color", oc_val)
            widgets["outline_color"].setStyleSheet(f"background-color: {oc_val}")

        top_conf = def_txt.get("top", {})
        bot_conf = def_txt.get("bottom", {})
        
        restore_section(self.top_num_widgets, top_conf.get("numbers", {}))
        restore_section(self.top_bar_num_widgets, top_conf.get("bar_numbers", {}))
        restore_section(self.top_pct_widgets, top_conf.get("percentages", {}))
        restore_section(self.top_bar_pct_widgets, top_conf.get("bar_percentages", {}))
        restore_section(self.bot_num_widgets, bot_conf.get("numbers", {}))
        restore_section(self.bot_bar_num_widgets, bot_conf.get("bar_numbers", {}))
        restore_section(self.bot_pct_widgets, bot_conf.get("percentages", {}))
        restore_section(self.bot_bar_pct_widgets, bot_conf.get("bar_percentages", {}))

        self.reset_timer_settings()
        self.live_update_handler()

    def reset_style_misc_settings(self):
        vis_opts = self.default_config["visual_options"]
        self.auto_hide_cb.setChecked(vis_opts["auto_hide_text"])
        self.live_update_handler()

    def reset_base_colours(self):
        def_colours = self.default_config["colors"]
        for k, v in def_colours.items():
            if v is None: continue # Skip non-core colors
            k_upper = v.upper()
            if k in self.colour_btns: 
                if k == "perfect_color": continue
                
                self.colours[k] = k_upper
                btn = self.colour_btns.get(k)
                if btn:
                    btn.setText(k_upper)
                    btn.setStyleSheet(f"background-color: {k_upper}")
        
        vis_opts = self.default_config["visual_options"]
        self.use_good_as_pass_cb.setChecked(vis_opts["use_good_for_all_pass"])
        self.highlight_excess_cb.setChecked(vis_opts["highlight_excess"])
        self.live_update_handler()

    def reset_chunk_evaluation(self):
        ce_def = self.default_config["chunk_evaluation"]
        ws_def = ce_def["weights"] 
        
        # Block signals to prevent intermediate logic passes
        self.w_again_spin.blockSignals(True)
        self.w_hard_spin.blockSignals(True)
        self.w_good_spin.blockSignals(True)
        self.w_easy_spin.blockSignals(True)
        
        self.w_again_spin.setValue(ws_def["again"])
        self.w_hard_spin.setValue(ws_def["hard"])
        self.w_good_spin.setValue(ws_def["good"])
        self.w_easy_spin.setValue(ws_def["easy"])

        # FSRS Logic Resets
        self.fsrs_retention.setValue(self.default_config.get("fsrs_retention", 0.9))
        self.cb_auto_chunk.setChecked(self.default_config.get("fsrs_auto_chunk", True))
        self.cb_use_deck_retention.setChecked(self.default_config.get("fsrs_use_deck", False))

        # Re-initialize with defaults
        self.setup_intervals_ui(self.default_config)
        
        self.w_again_spin.blockSignals(False)
        self.w_hard_spin.blockSignals(False)
        self.w_good_spin.blockSignals(False)
        self.w_easy_spin.blockSignals(False)
        
        self.live_update_handler()

    def reset_perfect_settings(self):
        vis_opts = self.default_config["visual_options"]
        self.highlight_perfect_cb.setChecked(vis_opts["highlight_perfect"])
        self.perfect_include_hard_cb.setChecked(vis_opts["perfect_include_hard"])
        
        # Colour
        def_colours = self.default_config["colors"]
        # Fallback to config.json default
        pc = (def_colours.get("perfect_color") or vis_opts["perfect_color"]).upper()
        self.colours["perfect_color"] = pc
        if "perfect_color" in self.colour_btns:
            self.colour_btns["perfect_color"].setText(pc)
            self.colour_btns["perfect_color"].setStyleSheet(f"background-color: {pc}")
            
        self.live_update_handler()

    def reset_behaviour_settings(self):
        self.chunk_spin.setValue(self.default_config["chunk_size"])
        self.double_new_cb.setChecked(self.default_config["double_new"])
        self.fail_policy_cb.setCurrentText(self.default_config["fail_policy"])
        self.bury_policy_cb.setCurrentText(self.default_config["bury_policy"])
        self.suspend_policy_cb.setCurrentText(self.default_config["suspend_policy"])
        self.delete_policy_cb.setCurrentText(self.default_config["delete_policy"])
        self.undo_policy_cb.setCurrentText(self.default_config["undo_policy"])
        self.live_update_handler()

    def reset_timer_settings(self):
        dt = self.default_config["timer"]
        self.timer_cap.setChecked(dt["use_anki_cap"])
        
        def restore_timer_section(widgets, conf):
            widgets["enabled"].setChecked(conf["enabled"])
            widgets["live"].setChecked(conf["live_enabled"])
            fmt = conf["format"]
            widgets["minutes"].setChecked(fmt["minutes"])
            widgets["seconds"].setChecked(fmt["seconds"])
            widgets["milliseconds"].setChecked(fmt["milliseconds"])
            
            style = conf["style"]
            c_val = style["color"].upper()
            widgets["color"].setProperty("hex_color", c_val)
            widgets["color"].setStyleSheet(f"background-color: {c_val}")
            widgets["bold"].setChecked(style["bold"])
            widgets["outline"].setChecked(style["outline"])
            oc_val = style["outline_color"].upper()
            widgets["outline_color"].setProperty("hex_color", oc_val)
            widgets["outline_color"].setStyleSheet(f"background-color: {oc_val}")

        restore_timer_section(self.chunk_timer_widgets, dt.get("chunk_timer", {}))
        restore_timer_section(self.card_timer_widgets, dt.get("card_timer", {}))
        self.live_update_handler()

    def reset_tab_style(self):
        self.reset_text_settings()
        self.reset_timer_settings()
        self.reset_style_misc_settings()

    def reset_tab_colours(self):
        self.reset_base_colours()
        self.reset_chunk_evaluation()
        self.reset_perfect_settings()

    def reset_tab_behaviour(self):
        self.reset_behaviour_settings()
        self.reset_layout_settings()

    def restore_defaults(self):
        if QMessageBox.question(self, "Restore Defaults", "Are you sure you want to restore ALL settings to default?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.reset_tab_style()
            self.reset_tab_colours()
            self.reset_tab_behaviour()

    def get_default_iv(self, index):
        try:
            return self.default_config["chunk_evaluation"]["intervals"][index]
        except (KeyError, IndexError):
            return {}

    def setup_intervals_ui(self, source_config=None):
        if source_config is None:
            source_config = self.config
            
        # Clear existing
        # Note: We must check if itemAt returns a widget before accessing .widget()
        # and handle spacer items if any. But here we just have widgets.
        while self.interval_layout.count():
            item = self.interval_layout.takeAt(0)
            w = item.widget()
            if w: w.setParent(None)
            
        self.interval_rows = []
        
        ce_conf = source_config.get("chunk_evaluation", {})
        # Ensure default intervals if missing
        intervals = ce_conf.get("intervals", [])
        if not intervals and source_config != self.default_config:
             intervals = self.default_config.get("chunk_evaluation", {}).get("intervals", [])
        
        for idx, iv in enumerate(intervals):
            row_w = QWidget()
            row_l = QHBoxLayout()
            row_l.setContentsMargins(0, 0, 0, 0)
            
            # Enable
            en_cb = QCheckBox()
            def_iv = self.get_default_iv(idx)
            en_cb.setChecked(iv.get("enabled", def_iv.get("enabled", True)))
            row_l.addWidget(en_cb)
            
            # Start Bracket
            start_bk = NoScrollComboBox()
            start_bk.addItems(["[", "("])
            start_bk.setCurrentText(iv.get("start_bracket", def_iv.get("start_bracket", "[")))
            start_bk.setFixedWidth(45)
            row_l.addWidget(start_bk)
            
            # Start Val
            start_val = NoScrollDoubleSpinBox()
            start_val.setRange(0, 100)
            start_val.setSingleStep(0.1)
            start_val.setFixedWidth(60)
            
            s_val = iv.get("start_val", def_iv.get("start_val", 0.0))
            start_val.setValue(float(s_val)) 
            row_l.addWidget(start_val)
            
            row_l.addWidget(QLabel(","))
            
            # End Val (Editable)
            end_spin = NoScrollDoubleSpinBox()
            end_spin.setRange(0, 100) # Open range, logic constrains it
            end_spin.setSingleStep(0.1)
            end_spin.setFixedWidth(60)
            end_spin.setValue(iv.get("end_val", def_iv.get("end_val", 0.0)))
            row_l.addWidget(end_spin)
            
            # End Bracket (Editable)
            end_bk = NoScrollComboBox()
            end_bk.addItems([")", "]"])
            end_bk.setCurrentText(iv.get("end_bracket", def_iv.get("end_bracket", ")")))
            end_bk.setFixedWidth(45)
            # Lock last row to ]
            if idx == len(intervals) - 1:
                end_bk.setEnabled(False)
                end_bk.setCurrentText("]")
            row_l.addWidget(end_bk)
            
            # Colour Indication
            # Labels and keys should ALWAYS come from the standardized sequence in DEFAULT_CONFIG
            ck = def_iv.get("color_key", "good")
            pk = def_iv.get("pattern_key", None)
            lbl_txt = ck.capitalize()
            if pk: lbl_txt += f" / {pk.capitalize()} (Stripped pattern)"
            row_l.addWidget(QLabel(lbl_txt))
            
            row_l.addStretch()
            row_w.setLayout(row_l)
            self.interval_layout.addWidget(row_w)
            
            row_obj = {
                "enable": en_cb,
                "start_bk": start_bk,
                "start_val": start_val,
                "end_spin": end_spin,
                "end_bk": end_bk,
                "color_key": ck,
                "pattern_key": pk,
                "index": idx 
            }
            self.interval_rows.append(row_obj)
            
            # Connect signals
            # Use lambdas to identify source row for bidirectional updates
            en_cb.toggled.connect(self.update_intervals_logic)
            
            # We need to distinguish direction.
            # However, update_intervals_logic reconstructs the whole chain. 
            # If we simply connect them, we must handle the circularity in logic.
            # Let's attach them all to a unified handler that detects the sender?
            # Or simplified: Start change triggers Prev End update. End change triggers Next Start update.
            # BUT: update_intervals_logic enforces the chain Top-Down.
            # If I edit Start, and then logic runs Top-Down, it might overwrite my edit with Prev End.
            # So the logic needs to be aware of what changed.
            
            # Define helper to capture index correctly (closure fix)
            def make_handler(i, key):
                return lambda *args: self.on_interval_change(i, key)

            start_bk.currentIndexChanged.connect(make_handler(idx, "start_bk"))
            start_val.valueChanged.connect(make_handler(idx, "start_val"))
            end_spin.valueChanged.connect(make_handler(idx, "end_val"))
            end_bk.currentIndexChanged.connect(make_handler(idx, "end_bk"))
            
        self.update_intervals_logic() # Initial pass

    def on_interval_change(self, changed_idx, field):
        # Handle linking immediately to prevent desync
        # We block signals during programmatic updates to prevent feedback loops
        
        rows = self.interval_rows
        
        if field == "start_val":
            # Start Changed -> Update Prev End
            # Find closest enabled PREV row
            prev_row = None
            for i in range(changed_idx - 1, -1, -1):
                if rows[i]["enable"].isChecked():
                    prev_row = rows[i]
                    break
            
            if prev_row:
                val = rows[changed_idx]["start_val"].value()
                prev_row["end_spin"].blockSignals(True)
                prev_row["end_spin"].setValue(val)
                prev_row["end_spin"].blockSignals(False)
                
        elif field == "end_val":
            # End Changed -> Update Next Start
            # Find closest enabled NEXT row
            next_row = None
            for i in range(changed_idx + 1, len(rows)):
                if rows[i]["enable"].isChecked():
                    next_row = rows[i]
                    break
            
            if next_row:
                val = rows[changed_idx]["end_spin"].value()
                next_row["start_val"].blockSignals(True)
                next_row["start_val"].setValue(val)
                next_row["start_val"].blockSignals(False)

        elif field == "start_bk":
            # Start Bracket Changed -> Update Prev End Bracket (Opposite)
            # Find closest enabled PREV row (skip check same as val)
            prev_row = None
            for i in range(changed_idx - 1, -1, -1):
                if rows[i]["enable"].isChecked():
                    prev_row = rows[i]
                    break
            
            if prev_row:
                sb = rows[changed_idx]["start_bk"].currentText()
                target = ")" if sb == "[" else "]" # Assuming ) if [ matches standard interval notation [a,b) U [b, c)
                # But wait, logic: [ means inclusive start. 
                # ( means exclusive start.
                # If Next Start is [, Prev End could be ) (standard) or ]?
                # Usually: [a, b) and [b, c). Overlap at b is covered by one.
                # If I swap start from [ to (, Prev End should become ]?
                # User said: "parenthesis selector of each starting interval will also be linked to the previous one and will be always the opposite".
                target = "]" if sb == "(" else ")"
                
                prev_row["end_bk"].blockSignals(True)
                prev_row["end_bk"].setCurrentText(target)
                prev_row["end_bk"].blockSignals(False)

        elif field == "end_bk":
             # End Bracket Changed -> Update Next Start Bracket (Opposite)
            next_row = None
            for i in range(changed_idx + 1, len(rows)):
                if rows[i]["enable"].isChecked():
                    next_row = rows[i]
                    break
            if next_row:
                 eb = rows[changed_idx]["end_bk"].currentText()
                 target = "(" if eb == "]" else "["
                 next_row["start_bk"].blockSignals(True)
                 next_row["start_bk"].setCurrentText(target)
                 next_row["start_bk"].blockSignals(False)

        self.update_intervals_logic()

    def update_intervals_logic(self):
        # Validates constraints and handles the "Chain" for disabled rows
        # Enforce global min/max and consistent chain
        
        # Determine strict min/max from all defined weights
        weights = [
            self.w_again_spin.value(),
            self.w_hard_spin.value(),
            self.w_good_spin.value(),
            self.w_easy_spin.value()
        ]
        min_limit = min(weights)
        max_limit = max(weights)
        
        rows = self.interval_rows

        # 0. Unlock all constraints temporarily to allow value updates
        # Prevents clamping to OLD strict limits when values are shifting
        for row in rows:
            row["start_val"].setRange(-9999, 9999)
            row["end_spin"].setRange(-9999, 9999)
        
        # 1. Lock First Enabled Start
        first_enabled_idx = -1
        for i, row in enumerate(rows):
            if row["enable"].isChecked():
                first_enabled_idx = i
                break
        
        if first_enabled_idx != -1:
            r = rows[first_enabled_idx]
            r["start_val"].blockSignals(True)
            r["start_val"].setValue(min_limit)
            r["start_val"].setEnabled(False) # Fixed
            r["start_val"].blockSignals(False)
            
            r["start_bk"].blockSignals(True)
            r["start_bk"].setCurrentText("[")
            r["start_bk"].setEnabled(False)
            r["start_bk"].blockSignals(False)
            
        # 2. Lock Last Enabled End
        last_enabled_idx = -1
        for i in range(len(rows)-1, -1, -1):
            if rows[i]["enable"].isChecked():
                last_enabled_idx = i
                break
                
        if last_enabled_idx != -1:
            r = rows[last_enabled_idx]
            r["end_spin"].blockSignals(True)
            r["end_spin"].setValue(max_limit)
            r["end_spin"].blockSignals(False)
            # r["end_spin"].setEnabled(False) # Maybe keep enabled but force value reset?
            # User said "locked to ] and the highest value".
            r["end_spin"].setEnabled(False)
            
            r["end_bk"].blockSignals(True)
            r["end_bk"].setCurrentText("]")
            r["end_bk"].setEnabled(False)
            r["end_bk"].blockSignals(False)

        # 3. Propagate disabled rows (Bridge the gap)
        # If row i is disabled, it effectively shouldn't break the chain. 
        # But visually it's greyed out. 
        # For logic, we handle connections between *enabled* rows in `on_interval_change`.
        # Here we just enforce enabled states.
        
        for i, row in enumerate(rows):
            en = row["enable"].isChecked()
            # Start widgets only editable if enabled AND not first
            is_first = (i == first_enabled_idx)
            row["start_val"].setEnabled(en and not is_first)
            row["start_bk"].setEnabled(en and not is_first)
            
            # End widgets only editable if enabled AND not last
            is_last = (i == last_enabled_idx)
            row["end_spin"].setEnabled(en and not is_last)
            row["end_bk"].setEnabled(en and not is_last)
            
            # Enforce Value Constraints (Start <= End)
            # Note: This checks every row individually
            s = row["start_val"].value()
            e = row["end_spin"].value()
            if e < s:
                # Which one to move? 
                # Depends on what triggered it, but here we just ensure sanity.
                # Usually push End up, unless it's maxed.
                 if en:
                     row["end_spin"].blockSignals(True)
                     row["end_spin"].setValue(s) 
                     row["end_spin"].blockSignals(False)
        
        # 4. Enforce Chain Consistency (Initialization)
        # Ensure Start[i] == End[i-1] for enabled sequences
        # This handles the "0" initialization bug
        current_end_val = None
        current_end_bk = None
        
        for i, row in enumerate(rows):
            if not row["enable"].isChecked():
                continue
                
            if current_end_val is not None:
                # Update this start to match previous end
                row["start_val"].blockSignals(True)
                row["start_val"].setValue(current_end_val)
                row["start_val"].blockSignals(False)
                
                # Update bracket (opposite)
                target_bk = "(" if current_end_bk == "]" else "["
                row["start_bk"].blockSignals(True)
                row["start_bk"].setCurrentText(target_bk)
                row["start_bk"].blockSignals(False)
            
            # Store for next
            current_end_val = row["end_spin"].value()
            current_end_bk = row["end_bk"].currentText()

        # 5. Enforce User Input Constraints (Dynamic Min/Max)
        # Iterate again to set limits based on neighbours so user cannot input invalid values
        enabled_indices = [idx for idx, r in enumerate(rows) if r["enable"].isChecked()]
        
        for k, idx in enumerate(enabled_indices):
            row = rows[idx]
            
            # Find Previous Constraint (The Start of the Previous Interval)
            if k > 0:
                prev_idx = enabled_indices[k-1]
                prev_start = rows[prev_idx]["start_val"].value()
                lower_limit = prev_start
            else:
                lower_limit = min_limit
            
            # Find Next Constraint (The End of the Next Interval)
            if k < len(enabled_indices) - 1:
                next_idx = enabled_indices[k+1]
                next_end = rows[next_idx]["end_spin"].value()
                upper_limit = next_end
            else:
                upper_limit = max_limit
                
            # Set Start Limits (Range: [PrevStart, CurrentEnd])
            # Note: Changing min/max doesn't trigger valueChanged unless current value is clipped
            row["start_val"].setMinimum(lower_limit)
            row["start_val"].setMaximum(row["end_spin"].value())
            
            # Set End Limits (Range: [CurrentStart, NextEnd])
            row["end_spin"].setMinimum(row["start_val"].value())
            row["end_spin"].setMaximum(upper_limit)

        self.live_update_handler()

    def live_update_handler(self):
        # Gather current state and write to config (live)
        self.update_config_from_ui()
        mw.addonManager.writeConfig(__name__, self.config)
        
        # Direct callback for immediate updates (bypassing addonManager hooks if needed)
        if hasattr(self, "live_callback"):
            self.live_callback(self.config)

    def update_config_from_ui(self):
        # Central logic to scrape UI to self.config
        self.config["chunk_size"] = self.chunk_spin.value()
        self.config["double_new"] = self.double_new_cb.isChecked()
        self.config["fsrs_retention"] = self.fsrs_retention.value()
        self.config["fsrs_auto_chunk"] = self.cb_auto_chunk.isChecked()
        self.config["fsrs_use_deck"] = self.cb_use_deck_retention.isChecked()
        
        self.config["positions"] = {
            "chunks": self.chunk_pos_combo.currentText(),
            "cards": self.card_pos_combo.currentText(),
            "stack_order": self.stack_order_combo.currentData()
        }
        if "dock_area" in self.config:
            del self.config["dock_area"]
            
        self.config["fail_policy"] = self.fail_policy_cb.currentText()
        self.config["bury_policy"] = self.bury_policy_cb.currentText()
        self.config["suspend_policy"] = self.suspend_policy_cb.currentText()
        self.config["delete_policy"] = self.delete_policy_cb.currentText()
        self.config["undo_policy"] = self.undo_policy_cb.currentText()
        self.config["colors"] = self.colours
        
        def_vis = self.default_config.get("visual_options", {})
        self.config["visual_options"] = {
            "highlight_excess": self.highlight_excess_cb.isChecked(),
            "auto_hide_text": self.auto_hide_cb.isChecked(),
            "use_good_for_all_pass": self.use_good_as_pass_cb.isChecked(),
            "highlight_perfect": self.highlight_perfect_cb.isChecked(),
            "perfect_include_hard": self.perfect_include_hard_cb.isChecked(),
            "perfect_color": self.colours.get("perfect_color", def_vis["perfect_color"])
        }
        
        def build_conf(widgets):
            conf = {
                "enabled": widgets["enabled"].isChecked(),
                "type": widgets["type"].currentText(),
                "count_direction": widgets["dir"].currentText(),
                "style": {
                    "color": widgets["color"].property("hex_color"),
                    "bold": widgets["bold"].isChecked(),
                    "outline": widgets["outline"].isChecked(),
                    "outline_color": widgets["outline_color"].property("hex_color")
                }
            }
            if widgets.get("show_decimals"):
                conf["show_decimals"] = widgets["show_decimals"].isChecked()
                conf["decimals"] = widgets["decimals"].value()
            return conf
            
        self.config["text_options"] = {
            "top": {
                "numbers": build_conf(self.top_num_widgets),
                "percentages": build_conf(self.top_pct_widgets),
                "bar_numbers": build_conf(self.top_bar_num_widgets),
                "bar_percentages": build_conf(self.top_bar_pct_widgets)
            },
            "bottom": {
                "numbers": build_conf(self.bot_num_widgets),
                "percentages": build_conf(self.bot_pct_widgets),
                "bar_numbers": build_conf(self.bot_bar_num_widgets),
                "bar_percentages": build_conf(self.bot_bar_pct_widgets)
            }
        }
        
        # Chunk Evaluation
        intervals_conf = []
        for idx, row in enumerate(self.interval_rows):
            def_iv = self.get_default_iv(idx)
            intervals_conf.append({
                "enabled": row["enable"].isChecked(),
                "start_bracket": row["start_bk"].currentText(),
                "start_val": row["start_val"].value(),
                "end_bracket": row["end_bk"].currentText(),
                "end_val": row["end_spin"].value(),
                # Enforce standardized keys from defaults
                "color_key": def_iv.get("color_key", "good"),
                "pattern_key": def_iv.get("pattern_key")
            })
            
        self.config["chunk_evaluation"] = {
            "weights": {
                "again": self.w_again_spin.value(),
                "hard": self.w_hard_spin.value(),
                "good": self.w_good_spin.value(),
                "easy": self.w_easy_spin.value()
            },
            "intervals": intervals_conf
        }
        
        def build_timer_conf(widgets):
            return {
                "enabled": widgets["enabled"].isChecked(),
                "live_enabled": widgets["live"].isChecked(),
                "format": {
                    "minutes": widgets["minutes"].isChecked(),
                    "seconds": widgets["seconds"].isChecked(),
                    "milliseconds": widgets["milliseconds"].isChecked()
                },
                "style": {
                    "color": widgets["color"].property("hex_color"),
                    "bold": widgets["bold"].isChecked(),
                    "outline": widgets["outline"].isChecked(),
                    "outline_color": widgets["outline_color"].property("hex_color")
                }
            }

        self.config["timer"] = {
            "use_anki_cap": self.timer_cap.isChecked(),
            "chunk_timer": build_timer_conf(self.chunk_timer_widgets),
            "card_timer": build_timer_conf(self.card_timer_widgets)
        }

    def on_chunk_size_change(self):
        self.live_update_handler() # Standard update
        if self.cb_auto_chunk.isChecked():
            # Trigger FSRS recalc without re-enabling checkboxes (just apply logic)
            self._apply_fsrs_logic()

    def apply_fsrs_settings(self):
        msg = ("Clicking this will overwrite the current settings for diffculty values and coloring intervals. "
               "The intervals will be set in a way that tries to convey having or not reached desired retention for each chunk.\n\n"
               "This will also enable two settings:\n\n"
               "- Update on cards per chunk change will overwrite these settings every time you change the size of your chunks in the settings.\n"
               "- Update on deck selection will overwrite these settings every time you select a deck, fetching the desired retention (if set) for said deck.\n\n"
               "Make sure to disable them if you choose to use your own custom values.")
               
        reply = QMessageBox.question(self, "Overwrite Settings?", msg, 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            # Button clicked: Enable features & Apply
            self.cb_auto_chunk.setChecked(True)
            self.cb_use_deck_retention.setChecked(True)
            self._apply_fsrs_logic()
        
    def _apply_fsrs_logic(self):
        retention = self.fsrs_retention.value()
        chunk_size = self.chunk_spin.value()
        
        # Save retention to config immediately (so it persists as default)
        self.config["fsrs_retention"] = retention
        
        # Use helper
        weights, interval_data = fsrs_logic.calculate_fsrs_intervals(chunk_size, retention)
        
        # Block signals to prevent recursive logic/crashes during batch update
        self.w_again_spin.blockSignals(True)
        self.w_hard_spin.blockSignals(True)
        self.w_good_spin.blockSignals(True)
        self.w_easy_spin.blockSignals(True)
        
        for row in self.interval_rows:
            row["enable"].blockSignals(True)
            row["start_val"].blockSignals(True)
            row["end_spin"].blockSignals(True)
            row["start_bk"].blockSignals(True)
            row["end_bk"].blockSignals(True)
            # Unclamp ranges to ensure setValue doesn't get rejected/clamped by old state
            row["start_val"].setRange(-9999, 9999)
            row["end_spin"].setRange(-9999, 9999)
        
        # 1. Set Weights
        self.w_again_spin.setValue(weights["again"])
        self.w_hard_spin.setValue(weights["hard"])
        self.w_good_spin.setValue(weights["good"])
        self.w_easy_spin.setValue(weights["easy"])
            
        # 3. Configure Intervals
        rows = self.interval_rows
        
        # Helper to set row (assuming signals blocked)
        def set_row(idx, data):
            if idx >= len(rows): return
            r = rows[idx]
            r["enable"].setChecked(data["enabled"])
            if not data["enabled"]: return
            
            r["start_bk"].setCurrentText(data["start_bracket"])
            r["start_val"].setValue(data["start_val"])
            r["end_spin"].setValue(data["end_val"])
            r["end_bk"].setCurrentText(data["end_bracket"])
            # keys? Logic usually derives them? No, Settings UI expects them in config, 
            # but visual edit is just intervals. 
            # Ideally we'd update color/pattern key if supported by UI, but UI is fixed rows?
            # Wait, UI *generates* rows from config. Here we are updating *existing* widgets.
            # Does UI allow changing color/pattern key? No, it's fixed labels in setup_intervals_ui.
            # So we assume the structure matches (Again, Again/Hard, Hard...).
                
        for i, data in enumerate(interval_data):
            set_row(i, data)
        
        # Disable extras if more rows than data
        for i in range(len(interval_data), len(rows)):
             rows[i]["enable"].setChecked(False)
            
        # Unblock signals
        self.w_again_spin.blockSignals(False)
        self.w_hard_spin.blockSignals(False)
        self.w_good_spin.blockSignals(False)
        self.w_easy_spin.blockSignals(False)
        
        for row in self.interval_rows:
            row["enable"].blockSignals(False)
            row["start_val"].blockSignals(False)
            row["end_spin"].blockSignals(False)
            row["start_bk"].blockSignals(False)
            row["end_bk"].blockSignals(False)
            
        # Trigger logic to re-apply constraints properly
        self.update_intervals_logic()
        self.live_update_handler()

    def accept(self):
        # Final save (redundant if live update is on, but safe)
        self.live_update_handler()
        super().accept()

