
from aqt.qt import *
from aqt import mw
import time
from .config_utils import DEFAULT_CONFIG, get_config_val, reload_defaults

class ProgressBarWidget(QWidget):
    def __init__(self, bar_type="chunks"):
        super().__init__()
        self.bar_type = bar_type
        self.setFixedHeight(20) # Single bar height
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        
        self.total = 0
        self.current = 0
        self.chunk_size = 10 
        self.status_log = []
        self.time_log = []
        self.start_time = 0
        
        self.config = {} # Will hold full config
        self.runtime_colors = {} # Holds QColor objects
        self.text_config = {} 
        self.timer_conf = {}
        self.is_hovering = False
        self.hover_index = -1
        self.hover_callback = None

        # Sibling bar (set by layout.init_widgets) used to keep hover alive
        # while the cursor sits in the small gap between the two stacked bars.
        self.sibling_bar = None
        self._gap_watch = QTimer(self)
        self._gap_watch.setInterval(100)
        self._gap_watch.timeout.connect(self._check_gap_hover)

        # Live Timer Trigger
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)

    def get(self, *keys):
        return get_config_val(self.config, DEFAULT_CONFIG, *keys)
        # Check timer config to start/stop provided in update_config

    def enterEvent(self, event):
        self._gap_watch.stop()
        if self.sibling_bar is not None:
            try:
                self.sibling_bar._gap_watch.stop()
            except RuntimeError:
                pass
        self.is_hovering = True
        if self.hover_callback:
            self.hover_callback(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._cursor_in_sibling_gap():
            # The cursor only moved into the small gap between the two bars:
            # keep hover active and watch until it truly leaves the area.
            self._gap_watch.start()
            super().leaveEvent(event)
            return
        self.is_hovering = False
        self.hover_index = -1
        if self.hover_callback:
            self.hover_callback(False)
        self.update()
        super().leaveEvent(event)

    def set_hover_state(self, is_hovering):
        """Called by sibling widget to synchronize hover state"""
        self.is_hovering = is_hovering
        if not is_hovering:
            self.hover_index = -1
        self.update()

    GAP_HOVER_TOLERANCE = 12  # px: max height treated as "small gap" between the bars

    def _sibling_gap_rect(self):
        """Global rect spanning this bar and its sibling's facing edges, when
        both bars are docked in the same place (stacked with a small gap)."""
        sib = self.sibling_bar
        if sib is None:
            return None
        try:
            if not self.isVisible() or not sib.isVisible():
                return None
            r1 = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            r2 = QRect(sib.mapToGlobal(QPoint(0, 0)), sib.size())
        except RuntimeError:
            # Sibling widget was deleted
            return None
        top, bottom = (r1, r2) if r1.top() <= r2.top() else (r2, r1)
        gap_h = bottom.top() - top.bottom() - 1
        if gap_h < 0 or gap_h > self.GAP_HOVER_TOLERANCE:
            return None
        left = max(top.left(), bottom.left())
        right = min(top.right(), bottom.right())
        if right < left:
            return None
        # Include the boundary rows of both bars so edge pixels count as inside
        return QRect(QPoint(left, top.bottom()), QPoint(right, bottom.top()))

    def _cursor_in_sibling_gap(self):
        gap = self._sibling_gap_rect()
        return gap is not None and gap.contains(QCursor.pos())

    def _check_gap_hover(self):
        if self._cursor_in_sibling_gap():
            return  # still in the gap: keep hovering
        self._gap_watch.stop()
        # If the cursor moved into one of the bars its enterEvent keeps hover on
        try:
            if self.underMouse() or (self.sibling_bar is not None and self.sibling_bar.underMouse()):
                return
        except RuntimeError:
            pass
        self.is_hovering = False
        self.hover_index = -1
        if self.hover_callback:
            self.hover_callback(False)
        self.update()

    @staticmethod
    def is_perfect_grade(status, include_hard):
        """True if a status_log entry counts towards a perfect chunk.
        Grades: 1=Again, 2=Hard, 3=Good, 4=Easy. True = legacy pass."""
        if status is True:
            return True
        if isinstance(status, bool) or not isinstance(status, int):
            return False  # fails, undone, buried and suspended break perfection
        return status >= (2 if include_hard else 3)

    def set_params(self, total, current, status_log=[], time_log=[], start_time=0, initial_total=None):
        self.total = total
        self.current = current
        self.status_log = status_log
        self.time_log = time_log
        self.start_time = start_time
        # Track original total for excess calculation
        # If initial_total is not provided, assume current total is the initial
        self.initial_total = initial_total if initial_total is not None else total
        self.update()

    def update_config(self, config):
        self.config = config
        self.chunk_size = self.get("chunk_size")
        
        # Populate runtime QColor objects from hex strings
        # MERGE defaults with user config to ensure new keys (buried/suspended) are present
        self.runtime_colors = {}
        
        # RELOAD defaults from disk to ensure we have latest keys (e.g. buried/suspended)
        global DEFAULT_CONFIG
        DEFAULT_CONFIG = reload_defaults()
        
        def_colors = DEFAULT_CONFIG.get("colors", {})
        user_colors = self.get("colors")
        
        # 1. Load Defaults
        for key, hex_val in def_colors.items():
            if hex_val:
                self.runtime_colors[key] = QColor(hex_val)
                
        # 2. Overwrite with User Config
        for key, hex_val in user_colors.items():
            if hex_val:
                self.runtime_colors[key] = QColor(hex_val)
        
        # Ensure perfect_color is also included if it exists in visual_options or colors
        pc = self.get("colors", "perfect_color")
        if pc:
            self.runtime_colors["perfect_color"] = QColor(pc)
        else:
            # Fallback for older configs
            self.runtime_colors["perfect_color"] = QColor(self.get("visual_options", "perfect_color"))
        
        self.text_config = self.get("text_options")
        self.timer_conf = self.get("timer")
        
        # Check if we need live timer running
        chunk_live = self.get("timer", "chunk_timer", "live_enabled")
        card_live = self.get("timer", "card_timer", "live_enabled")
        
        if chunk_live or card_live:
             if not self.timer.isActive():
                 self.timer.start(100) # 100ms update
        else:
             self.timer.stop()
             
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.settings_callback:
            self.settings_callback()

    def get_text_pen(self, style_conf):
        def_c = self.get("text_options", "top", "numbers", "style", "color")
        c = QColor(style_conf.get("color", def_c))
        return QPen(c)

    def config_font(self, painter, rect_height, style_conf, bold_override=False):
        font = painter.font()
        font.setPixelSize(int(rect_height * 0.75))
        is_bold = style_conf.get("bold", self.get("text_options", "top", "numbers", "style", "bold")) or bold_override
        font.setBold(is_bold)
        painter.setFont(font)
        return font

    def draw_styled_text(self, painter, rect, text, style_conf, alignment=Qt.AlignmentFlag.AlignCenter, auto_hide=False):
        if not text: return
        
        # Setup Font
        font = self.config_font(painter, rect.height(), style_conf)
        
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text)
        
        # Auto-Hide Logic
        if auto_hide:
            # 2px padding
            if text_w > (rect.width() - 2):
                return
        
        # Outline logic using PainterPath
        path = QPainterPath()
        text_h = fm.height()
        ascent = fm.ascent()
        
        # Calculate center
        x = rect.x() + (rect.width() - text_w) / 2
        y = rect.y() + (rect.height() - text_h) / 2 + ascent
        
        path.addText(x, y, font, text)
        
        if style_conf.get("outline", self.get("text_options", "top", "numbers", "style", "outline")):
            def_oc = self.get("text_options", "top", "numbers", "style", "outline_color")
            o_col = QColor(style_conf.get("outline_color", def_oc))
            pen = QPen(o_col)
            pen.setWidth(3)
            painter.strokePath(path, pen)
            
        def_c = self.get("text_options", "top", "numbers", "style", "color")
        color = QColor(style_conf.get("color", def_c))
        painter.fillPath(path, QBrush(color))

    def get_display_value(self, index, max_val, type_mode, is_chunk_bar, chunk_start=0):
        key = "top" if is_chunk_bar else "bottom"
        conf = self.get("text_options", key, "numbers")
        direction = conf.get("count_direction", self.get("text_options", key, "numbers", "count_direction"))
        
        val = 0
        if direction in ["done", "passed"]:
            # Standard counting 1..N
            if type_mode in ["relative", "chunks"]:
                val = index + 1
            else: # Absolute / cards
                if is_chunk_bar:
                     # Cumulative Cards (e.g., 10, 20, 30...)
                    val = min((index + 1) * self.chunk_size, self.total)
                else:
                    # Global Card Index
                    val = chunk_start + index + 1
        else: # Remaining
            # Countdown: N..1
            if type_mode in ["relative", "chunks"]:
                val = max_val - index
            else: # Absolute / cards
                if is_chunk_bar:
                    # Cards remaining at START of chunk (e.g., 30, 20, 10...)
                    val = max(0, self.total - (index * self.chunk_size))
                else:
                    # Cards remaining at START of card slot
                    val = self.total - (chunk_start + index)
        return str(val)

    def fmt_duration(self, seconds, fmt_conf):
        if seconds is None: return ""
        
        parts = []
        
        # Minutes
        if fmt_conf.get("minutes", self.get("timer", "chunk_timer", "format", "minutes")):
            m = int(seconds // 60)
            seconds = seconds % 60
            parts.append(f"{m}m")
            
        # Seconds
        s_en = fmt_conf.get("seconds", self.get("timer", "chunk_timer", "format", "seconds"))
        ms_en = fmt_conf.get("milliseconds", self.get("timer", "chunk_timer", "format", "milliseconds"))
        
        if s_en:
            if ms_en:
                val = f"{seconds:.3f}"
                parts.append(f"{val}s")
            else:
                parts.append(f"{int(seconds)}s")
        elif ms_en:
             ms = int((seconds - int(seconds)) * 1000)
             parts.append(f"{ms}ms")
             
        return " ".join(parts).strip()

    def draw_rect_pattern(self, painter, rect, bg_color, fg_color):
        painter.fillRect(rect, bg_color)
        
        painter.save()
        painter.setClipRect(rect)
        
        # Draw striped pattern manually for equal width control
        # We want 50/50 ratio.
        # W = 4. Step = 11 (approx 2W * sqrt(2))
        pen_width = 4
        step = 11
        
        pen = QPen(fg_color)
        pen.setWidth(pen_width)
        painter.setPen(pen)
        
        h = rect.height()
        # Ensure we cover the whole rect including diagonals
        start_x = int(rect.left()) - int(h) - step
        end_x = int(rect.right()) + step
        
        for x in range(start_x, end_x, step):
            # Draw Diagonal /
            p1 = QPointF(x, rect.bottom())
            p2 = QPointF(x + h, rect.top())
            painter.drawLine(p1, p2)
            
        painter.restore()

    def paintEvent(self, event):
        if self.total <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        bar_height = height 
        
        # Configs
        fail_policy = self.get("fail_policy")
        vis_opts = self.get("visual_options")
        auto_hide = self.get("visual_options", "auto_hide_text") 
        
        chunk_timer = self.get("timer", "chunk_timer")
        card_timer = self.get("timer", "card_timer")
        
        width = self.width()
        height = self.height()
        bar_height = height # Simple fill
        
        # Helper to resolve styles
        def resolve_style(specific, global_def):
            s = global_def.copy()
            s.update(specific)
            return s
            
        default_style = self.text_config.get("style", {})

        # --- CHUNKS BAR ---
        if self.bar_type == "chunks":
            import math
            import time
            # Use initial_total (original total at session start) for excess calculation
            # If initial_total wasn't set, fall back to self.total
            normal_total = getattr(self, 'initial_total', self.total)
            # Ensure bar grows if total (including fails) exceeds initial total
            # Use self.total here, not self.current, so the bar grows immediately when cards are failed
            effective_total = max(normal_total, self.total)
            total_chunks = (effective_total + self.chunk_size - 1) // self.chunk_size
            if total_chunks < 1: total_chunks = 1
            
            current_chunk_idx = self.current // self.chunk_size
            
            chunk_w = width / total_chunks
            
            # --- Text Config ---
            # Read from text_options.top for chunks bar
            top_text_conf = self.text_config.get("top", {})
            numbers_conf = top_text_conf.get("numbers", {})
            percent_conf = top_text_conf.get("percentages", {})
            bar_num_conf = top_text_conf.get("bar_numbers", {})
            bar_pct_conf = top_text_conf.get("bar_percentages", {})
            
            # Segment Text Config
            tn_en = self.get("text_options", "top", "numbers", "enabled")
            tn_type = self.get("text_options", "top", "numbers", "type")
            tn_style = resolve_style(self.get("text_options", "top", "numbers", "style"), default_style)
            
            tp_en = self.get("text_options", "top", "percentages", "enabled")
            tp_type = self.get("text_options", "top", "percentages", "type") 
            tp_dir = self.get("text_options", "top", "percentages", "count_direction")
            tp_show_dec = self.get("text_options", "top", "percentages", "show_decimals")
            tp_dec = self.get("text_options", "top", "percentages", "decimals")
            tp_style = resolve_style(self.get("text_options", "top", "percentages", "style"), default_style)
            
            chunk_timer_en = self.get("timer", "chunk_timer", "enabled")
            chunk_live_en = self.get("timer", "chunk_timer", "live_enabled")
            
            t_num_en = tn_en
            t_num_type = tn_type
            t_pct_en = tp_en
            t_pct_type = tp_type
            t_pct_dir = tp_dir
            t_pct_show_dec = tp_show_dec
            t_pct_dec = tp_dec
            
            # Bar Text (Centered) Config
            bn_en = self.get("text_options", "top", "bar_numbers", "enabled")
            bn_type = self.get("text_options", "top", "bar_numbers", "type")
            # Default to remaining if not set
            bn_dir = self.get("text_options", "top", "bar_numbers", "count_direction") or "remaining"
            bn_style = resolve_style(self.get("text_options", "top", "bar_numbers", "style"), default_style)
            
            bp_en = self.get("text_options", "top", "bar_percentages", "enabled")
            bp_type = self.get("text_options", "top", "bar_percentages", "type")
            bp_dir = self.get("text_options", "top", "bar_percentages", "count_direction")
            bp_show_dec = self.get("text_options", "top", "bar_percentages", "show_decimals")
            bp_dec = self.get("text_options", "top", "bar_percentages", "decimals")
            bp_style = resolve_style(self.get("text_options", "top", "bar_percentages", "style"), default_style)
            
            # Pre-calculate Top Centered Text (Bar Text)
            centered_str_top = ""
            c_style_top = bn_style # Default style for center
            
            parts_top = []
            
            # Bar Numbers
            if bn_en:
                val = ""
                # Calculate Base Values
                c_done = current_chunk_idx + 1
                c_total = total_chunks
                c_rem = max(0, c_total - current_chunk_idx) # Current chunk is "remaining" until done? 
                # Existing logic: `val = current_chunk_idx + 1 if bn_dir in ["done", "passed"] else total_chunks - current_chunk_idx`
                # If idx=0 (1st chunk), done=1, rem=total. 
                # Wait, "remaining" usually implies "chunks left to do".
                # If I am in chunk 1 (idx=0), I have 1 done (inclusive)? Or 0 done?
                # "done" mode usually shows current position (1).
                # "remaining" mode usually shows remaining (Tot - Current + 1?)
                # Existing logic used `total_chunks - current_chunk_idx`.
                # If total=10, idx=0. rem=10.
                
                k_done = self.current
                k_total = self.total
                k_rem = max(0, k_total - k_done)

                if bn_type == "cards":
                    # Cards Logic
                    v_done = k_done
                    v_rem = k_rem
                    v_total = k_total
                else: 
                    # Chunks Logic
                    v_done = c_done
                    v_rem = c_rem
                    v_total = c_total
                
                # Format
                if bn_dir == "remaining":
                    val = str(v_rem)
                elif bn_dir == "done/total" or bn_dir == "done/remaining":
                    val = f"{v_done}/{v_total}"
                elif bn_dir == "remaining/total" or bn_dir == "remaining/done":
                    val = f"{v_rem}/{v_total}"
                else: # done (default)
                    val = str(v_done)
                
                parts_top.append(val)
                c_style_top = bn_style
            
            # Bar Percentages
            if bp_en:
                if bp_type == "chunks":
                     # Percentage of CHUNKS completed
                     # current_chunk_idx is 0-indexed count of fully completed or entered chunks?
                     # Logic used elsewhere: `c_done = current_chunk_idx + 1` (if entering 2nd chunk, 1 is done?)
                     # No, current_chunk_idx=0 means I am in the 1st chunk. 0 chunks FULLY done.
                     # But most bars show progress INCLUDING current?
                     # Let's align with Bar Numbers: `v_done = c_done` where `c_done = current_chunk_idx + 1`
                     # Wait, if I am at card 1 of chunk 10, have I done 10%? No.
                     # Chunks "Done" generally means fully completed.
                     # But `c_done` calc says `current_chunk_idx + 1`. This implies "current chunk is being counted".
                     # Let's stick to the ratio `(current_chunk_idx) / total_chunks` ?
                     # Or `(current_chunk_idx + 1) / total_chunks`?
                     # If I use `self.current / self.total` for cards, it is exact progress.
                     # For chunks, exact progress is `current / total`.
                     # "Chunks" mode usually implies discrete steps.
                     # Let's use `current_chunk_idx / total_chunks` for "completed chunks".
                     # BUT `c_done` above uses +1. "Done" often means "Current Step".
                     # Let's assume user wants "Percent of Chunks Passed".
                     # If I am in chunk 1 (idx 0), I have passed 0.
                     ratio = current_chunk_idx / total_chunks if total_chunks > 0 else 0
                else:
                     # Cards (Default)
                     ratio = self.current / self.total if self.total > 0 else 0
                
                pct_val = ratio * 100
                if bp_dir == "remaining": pct_val = 100 - pct_val
                
                if bp_show_dec:
                    val_str = f"{pct_val:.{bp_dec}f}%"
                else:
                    val_str = f"{int(pct_val)}%"
                parts_top.append(val_str)
                if not bn_en:
                     c_style_top = bp_style
            
            top_safe_zone = QRectF()
            if parts_top:
                centered_str_top = " - ".join(parts_top)
                # Measure text width
                temp_font = self.config_font(painter, bar_height, c_style_top)
                fm = QFontMetrics(temp_font)
                text_width = fm.horizontalAdvance(centered_str_top)
                # Define safe zone with padding
                padding = 4
                left_x = (width - text_width) / 2 - padding
                top_safe_zone = QRectF(left_x, 0, text_width + 2*padding, bar_height)


                # Pre-calculate symmetric skips
            # All-or-Nothing Auto Hide (Chunks)
            hide_all_chunk_text = False
            if self.get("visual_options", "auto_hide_text"):
                 # Sample most likely scenario for overflow
                 # Number strings usually at most 4-5 digits (including timer)
                 s_parts = []
                 # 1. Check relative number (e.g. 99)
                 if t_num_en and t_num_type != "total": s_parts.append(str(total_chunks))
                 # 2. Check percentage (e.g. 100%)
                 if t_pct_en and t_pct_type != "total": s_parts.append("100%")
                 # 3. Check timer (e.g. 99s)
                 if chunk_timer_en: s_parts.append("99s") 
                 
                 if s_parts:
                     temp_font = self.config_font(painter, bar_height, tn_style)
                     # Check if total width of all enabled parts exceeds cell width
                     # Space-delimited if multiple
                     sample_str = " ".join(s_parts)
                     if QFontMetrics(temp_font).horizontalAdvance(sample_str) > chunk_w:
                         hide_all_chunk_text = True

            # 2. All-or-Nothing Collision Detection (Symmetry) - REVERTED TO INDIVIDUAL
            # We keep hide_all_chunk_text for width, but we don't hide the whole bar for a single overlap.
            # This allows the side numbers to stay visible unless they themselves hit the middle text.

                         
            # Draw Top Chunks
            has_total_top = bool(centered_str_top) and not self.is_hovering
            
            # --- VISUAL OPTIONS LIFT ---
            hl_excess = self.get("visual_options", "highlight_excess")
            str_again = self.get("visual_options", "striped_again")
            # Note: str_excess is now removed, striping is default for mixed excess if hl_excess is True
            for i in range(total_chunks):
                x = i * chunk_w
                rect_f = QRectF(x, 0, chunk_w - 1, bar_height - 1)
                
                # Base Colors & Logic
                c_start = i * self.chunk_size
                c_end = (i + 1) * self.chunk_size
                
                # Identify special states
                is_mixed_excess = False
                is_mixed_fail = False
                is_mixed_undo = False
                has_all_fail = False
                fail_count = 0
                undo_count = 0
                
                # Check Mixed Excess (Pending + Excess) - ALWAYS check regardless of fail_policy
                # This is needed to visualize chunks that extend beyond normal_total
                # Only mark if we are ACTUALLY exceeding the initial total (e.g. via fails)
                # Otherwise, the last chunk is just the last chunk (partial or full).
                if c_start < normal_total and c_end > normal_total and effective_total > normal_total:
                    is_mixed_excess = True
                
                if fail_policy in ["count", "acknowledge"]: # updated check
                    # Check Mixed Fail (Done + Fail)
                    if i <= current_chunk_idx:
                        # Check log for fails
                        safe_end = min(c_end, len(self.status_log))
                        if c_start < safe_end:
                             chunk_slice = self.status_log[c_start:safe_end]
                             # 1 = Fail, but True = 1. Must check type for True.
                             fails = [x for x in chunk_slice if (x == 1 and x is not True) or x is False]
                             if fails:
                                 if len(fails) == len(chunk_slice) and i < current_chunk_idx:
                                     # Only mark "all fail" if the chunk is actually finished
                                     has_all_fail = True
                                 else:
                                     is_mixed_fail = True
                                 fail_count = len(fails)
                                     
                             undos = [x for x in chunk_slice if x == "undone"]
                             if undos:
                                 undo_count = len(undos)
                                 # Check All Undo
                                 # ... logic handled later
                                 is_mixed_undo = True

                # Apply Color
                if i < current_chunk_idx:
                    safe_end = min(c_end, len(self.status_log))
                    chunk_slice = self.status_log[c_start:safe_end]
                    
                    only_pass_fail = self.get("visual_options", "only_pass_fail")
                    u_good_pass = self.get("visual_options", "use_good_for_all_pass")
                    # Use DEFAULT_CONFIG as a robust fallback for the entire object
                    weights = self.get("chunk_evaluation", "weights")
                    
                    scores = []
                    fails = 0
                    hards = 0
                    buried_count = 0
                    suspended_count = 0
                    undone_count = 0
                    deleted_count = 0

                    for s in chunk_slice:
                        # Map Status to Score
                        score = weights["good"]
                        
                        if s is False or s == 1: 
                            score = weights["again"]
                            fails += 1
                        elif s == 2: 
                            score = weights["good"] if u_good_pass else weights["hard"]
                            hards += 1
                        elif s == 3 or s is True: 
                            score = weights["good"]
                        elif s == 4: 
                            score = weights["good"] if u_good_pass else weights["easy"]
                        elif s == "undone": 
                            score = weights["again"] # Treat undone as fail
                            fails += 1
                            undone_count += 1
                        elif s == "buried":
                            score = weights["good"]
                            buried_count += 1
                        elif s == "suspended":
                            score = weights["good"]
                            suspended_count += 1
                        elif s == "deleted":
                            score = weights["good"]
                            deleted_count += 1

                        scores.append(score)
                    
                    avg = sum(scores) / len(scores) if scores else weights["good"]
                    
                    intervals = self.get("chunk_evaluation", "intervals") or []
                    final_color = self.runtime_colors["good"]
                    pattern_color = None
                    
                    # 1e-9 to prevent floating point issues (e.g. 2.99999999 < 3.0)
                    EPSILON = 1e-9
                    
                    for iv in intervals:
                        if not iv.get("enabled", True):
                            continue
                            
                        # Use explicit boundaries from config
                        # Fallback for start_val needs to be smart if missing (backward compatibility)
                        iv_start = iv.get("start_val", 0.0) 
                        iv_end = iv.get("end_val", 1.0)
                        start_b = iv.get("start_bracket", "[")
                        end_b = iv.get("end_bracket", ")")
                        
                        # Check logic with epsilon safety
                        if start_b == "[":
                            match_start = (avg >= iv_start - EPSILON)
                        else:
                            match_start = (avg > iv_start + EPSILON)
                            
                        if end_b == "]":
                            match_end = (avg <= iv_end + EPSILON)
                        else:
                            match_end = (avg < iv_end - EPSILON)
                        
                        if match_start and match_end:
                            # Found match - don't break yet, better ones might match too!
                            # Since we go top-down (Again -> Easy), later equals better.
                            c_key = iv.get("color_key", "good")
                            p_key = iv.get("pattern_key", None)
                            
                            final_color = self.runtime_colors.get(c_key, self.runtime_colors["good"])
                            if p_key:
                                pattern_color = self.runtime_colors.get(p_key, None)
                            # NO break - allow Easy/Good to override Hard/Again if both match (e.g. at boundary)
                        
                        # Optimization: if after our score range, we can stop
                        if iv_start > avg + EPSILON:
                            break

                    # Override for All-Buried / All-Suspended / All-Deleted / All-Skipped
                    if chunk_slice:
                        if buried_count == len(chunk_slice):
                            final_color = self.runtime_colors["buried"]
                        elif suspended_count == len(chunk_slice):
                            final_color = self.runtime_colors["suspended"]
                        elif deleted_count == len(chunk_slice):
                            final_color = self.runtime_colors["deleted"]
                        elif undone_count == len(chunk_slice):
                            final_color = self.runtime_colors["undone"]
                        elif buried_count + suspended_count + deleted_count == len(chunk_slice):
                             # Mixed skipped (buried/suspended/deleted) -> majority skip colour wins
                             skip_counts = {"buried": buried_count, "suspended": suspended_count, "deleted": deleted_count}
                             final_color = self.runtime_colors[max(skip_counts, key=skip_counts.get)]

                    # Perfect Chunk Override
                    # A chunk is perfect when every card in it was answered with a
                    # passing grade (Good/Easy, plus Hard if perfect_include_hard).
                    # Anything else (Again, undone, buried, suspended, deleted) breaks it.
                    # Instead of recolouring the tile, lay perfect-colour stripes over
                    # its normal (highest) colour so the underlying grade stays visible.
                    if chunk_slice and self.get("visual_options", "highlight_perfect"):
                        include_hard = self.get("visual_options", "perfect_include_hard")
                        if all(self.is_perfect_grade(s, include_hard) for s in chunk_slice):
                            pattern_color = self.runtime_colors.get("perfect_color", pattern_color)

                    # 3. Paint
                    if pattern_color:
                        self.draw_rect_pattern(painter, rect_f, final_color, pattern_color)
                    else:
                        painter.fillRect(rect_f, final_color)
                    
                    # 4. Striped Patterns for Fail/Undo/Mix
                    # Fail Overrides (Explicit Red Stripe)
                    if is_mixed_fail or has_all_fail:
                         # We want to show a red stripe over the quality color
                         # If all fail, maybe solid red?
                         if has_all_fail:
                             # Actually, average logic handles pure fails (score=0 -> again color)
                             # Mixed fail logic needed?
                             # IF standard scoring gave it a "Pass" color but it has a fail inside, warn user?
                             pass
                         elif is_mixed_fail:
                             # Draw stripe
                             if str_again:
                                 self.draw_rect_pattern(painter, rect_f, final_color, self.runtime_colors["again"])
                    
                    if is_mixed_undo:
                         # Undo stripe
                         self.draw_rect_pattern(painter, rect_f, final_color, self.runtime_colors["undone"])

                elif i == current_chunk_idx:
                    # Current Chunk
                    # Use special 'current' color unless explicit highlight
                    col = self.runtime_colors["current"]
                    

                    # User Request: "just want the stripes to be gone and just have the current color"
                    # We ignore is_mixed_excess for the current chunk and just draw it solid
                    painter.fillRect(rect_f, col)
                         
                    # --- ADDED: Visualize mixed states in current chunk ---
                    # If we have fails/buries in the CURRENT chunk, we should show them 
                    # otherwise the user sees "nothing happened"
                    if is_mixed_fail:
                         if str_again:
                             self.draw_rect_pattern(painter, rect_f, col, self.runtime_colors["again"])
                    
                    if is_mixed_undo:
                         self.draw_rect_pattern(painter, rect_f, col, self.runtime_colors["undone"])
                         
                    # Check for Buried/Suspended in current chunk (partial)
                    # We need to check the slice again since we didn't calculate avg/counts for current chunk above
                    safe_end = min(c_end, len(self.status_log))
                    if c_start < safe_end:
                        chunk_slice = self.status_log[c_start:safe_end]
                        cur_buried = sum(1 for x in chunk_slice if x == "buried")
                        cur_suspended = sum(1 for x in chunk_slice if x == "suspended")
                        


                         
                else: # i > current_chunk_idx (Future)
                    # Future Chunks
                    col = self.runtime_colors["pending"]
                    
                    if is_mixed_excess and hl_excess:
                         self.draw_rect_pattern(painter, rect_f, col, self.runtime_colors["excess"])
                    else:
                         painter.fillRect(rect_f, col)
                    # Check if this is an excess chunk (beyond original total)
                    if c_start >= normal_total:
                        # Fully excess future chunk - solid color
                        if hl_excess:
                            painter.fillRect(rect_f, self.runtime_colors["excess"])
                        else:
                            painter.fillRect(rect_f, self.runtime_colors["pending"])
                    elif is_mixed_excess:
                        # Mixed excess future chunk - partially contains excess cards
                        # Automatically stripe if highlight is on
                        if hl_excess:
                            # Stripe: future background with again_chunk foreground
                            self.draw_rect_pattern(painter, rect_f, self.runtime_colors["pending"], self.runtime_colors["excess"])
                        else:
                            painter.fillRect(rect_f, self.runtime_colors["pending"])
                    else:
                        # Normal future chunk
                        painter.fillRect(rect_f, self.runtime_colors["pending"])
                
                
                # Determine what text would be shown
                # Render individual chunk text
                if not hide_all_chunk_text:
                    cur_n_style = tn_style
                    cur_p_style = tp_style
                    
                    # 1. Determine base visibility/content (relative/absolute)
                    show_num_chunk = (t_num_en and t_num_type != "total")
                    show_pct_chunk = (t_pct_en and t_pct_type != "total")
                    
                    num_str_chunk = ""
                    pct_str_chunk = ""
                    if show_num_chunk: num_str_chunk = self.get_display_value(i, total_chunks, t_num_type, True)
                    if show_pct_chunk:
                        if t_pct_type == "chunks":
                             if t_pct_dir == "remaining":
                                 rem_chunks = max(0, total_chunks - i)
                                 ratio_calc = rem_chunks / total_chunks if total_chunks > 0 else 0
                             else:
                                 done_chunks = i + 1
                                 ratio_calc = done_chunks / total_chunks if total_chunks > 0 else 0
                        else:
                            if t_pct_dir == "remaining":
                                rem_cards = max(0, self.total - (i * self.chunk_size))
                                ratio_calc = rem_cards / self.total if self.total > 0 else 0
                            else:
                                c_end_c = (i + 1) * self.chunk_size
                                ratio_calc = min(c_end_c, self.total) / self.total if self.total > 0 else 0
                        
                        p_val = ratio_calc * 100
                        if t_pct_show_dec:
                            pct_str_chunk = f"{p_val:.{t_pct_dec}f}%"
                        else:
                            pct_str_chunk = f"{int(p_val)}%"

                    # 2. Check for Timer Overrides
                    override_time_str = None
                    if chunk_timer_en and i < current_chunk_idx:
                        c_time = sum(self.time_log[c_start : min(c_end, len(self.time_log))])
                        if c_time > 0:
                            override_time_str = self.fmt_duration(c_time, chunk_timer.get("format", {}))
                            cur_n_style = chunk_timer.get("style", tn_style)
                    elif chunk_live_en and i == current_chunk_idx:
                         if self.start_time > 0:
                             # Current card elapsed
                             elapsed = time.time() - self.start_time
                             # Sum of previous cards in THIS chunk
                             prev_sum = sum(self.time_log[c_start : self.current])
                             total_chunk_time = prev_sum + elapsed
                             
                             if total_chunk_time > 0:
                                 override_time_str = self.fmt_duration(total_chunk_time, chunk_timer.get("format", {}))
                                 cur_n_style = chunk_timer.get("style", tn_style)

                    if override_time_str:
                        num_str_chunk = override_time_str
                        pct_str_chunk = ""
                        show_num_chunk = True
                        show_pct_chunk = False

                    # 3. Individual Collision Detection
                    if has_total_top and (show_num_chunk or show_pct_chunk):
                        fm = QFontMetrics(self.config_font(painter, bar_height, cur_n_style))
                        sample_full = " ".join([parts for parts in [num_str_chunk, pct_str_chunk] if parts])
                        tw_calc = fm.horizontalAdvance(sample_full)
                        tx_calc = i * chunk_w + (chunk_w - tw_calc) / 2
                        if QRectF(tx_calc - 2, 0, tw_calc + 4, bar_height).intersects(top_safe_zone):
                            show_num_chunk = show_pct_chunk = False

                    # 4. Rendering
                    if show_num_chunk and show_pct_chunk:
                        r_num = QRectF(x, 0, chunk_w/2, bar_height - 1)
                        r_pct = QRectF(x + chunk_w/2, 0, chunk_w/2, bar_height - 1)
                        self.draw_styled_text(painter, r_num, num_str_chunk, cur_n_style, auto_hide=False)
                        self.draw_styled_text(painter, r_pct, pct_str_chunk, cur_p_style, auto_hide=False)
                    elif show_num_chunk:
                        self.draw_styled_text(painter, rect_f, num_str_chunk, cur_n_style, auto_hide=False)
                    elif show_pct_chunk:
                        self.draw_styled_text(painter, rect_f, pct_str_chunk, cur_p_style, auto_hide=False)


            # Draw Top Centered Text
            if centered_str_top and not self.is_hovering:
                self.draw_styled_text(painter, QRectF(0, 0, width, bar_height), centered_str_top, c_style_top, auto_hide=auto_hide)


        # --- CARDS BAR ---
        elif self.bar_type == "chunks": # Defensive check, but we are in elif
             pass
        else: # cards
            # Chunk Zoom Mode (Cards Bar)
            chunk_size = self.chunk_size
            current_chunk_idx = self.current // chunk_size
            start_offset = current_chunk_idx * chunk_size
            
            # Show only the cards that exist in this chunk
            normal_total = getattr(self, 'initial_total', self.total)
            effective_total_c = max(normal_total, self.total)
            total_chunks = (effective_total_c + chunk_size - 1) // chunk_size
            if total_chunks < 1: total_chunks = 1
            total_items = min(chunk_size, max(0, effective_total_c - start_offset))
            if total_items < 1: total_items = 1
            
            # Re-read Timer Config for Cards
            card_timer = self.timer_conf.get("card_timer", {}) # Ensure card_timer is defined here
            
            # Read from text_options.bottom for cards bar
            bottom_text_conf = self.text_config.get("bottom", {})
            numbers_conf = bottom_text_conf.get("numbers", {})
            percent_conf = bottom_text_conf.get("percentages", {})
            bar_num_conf = bottom_text_conf.get("bar_numbers", {})
            bar_pct_conf = bottom_text_conf.get("bar_percentages", {})
            
            # Segment Text
            tn_en = self.get("text_options", "bottom", "numbers", "enabled")
            tn_type = self.get("text_options", "bottom", "numbers", "type")
            tn_style = resolve_style(self.get("text_options", "bottom", "numbers", "style"), default_style)
            tp_en = self.get("text_options", "bottom", "percentages", "enabled")
            tp_type = self.get("text_options", "bottom", "percentages", "type") 
            tp_dir = self.get("text_options", "bottom", "percentages", "count_direction")
            tp_show_dec = self.get("text_options", "bottom", "percentages", "show_decimals")
            tp_dec = self.get("text_options", "bottom", "percentages", "decimals")
            tp_style = resolve_style(self.get("text_options", "bottom", "percentages", "style"), default_style)
            
            card_timer_en = self.get("timer", "card_timer", "enabled")
            card_live_en = self.get("timer", "card_timer", "live_enabled")
            import time # Ensure time is imported here if not globally
            
            # Bar Text
            bn_en = self.get("text_options", "bottom", "bar_numbers", "enabled")
            bn_type = self.get("text_options", "bottom", "bar_numbers", "type")
            bn_dir = self.get("text_options", "bottom", "bar_numbers", "count_direction") or "remaining"
            bn_style = resolve_style(self.get("text_options", "bottom", "bar_numbers", "style"), default_style)
            
            bp_en = self.get("text_options", "bottom", "bar_percentages", "enabled")
            bp_type = self.get("text_options", "bottom", "bar_percentages", "type")
            bp_dir = self.get("text_options", "bottom", "bar_percentages", "count_direction")
            bp_show_dec = self.get("text_options", "bottom", "bar_percentages", "show_decimals")
            bp_dec = self.get("text_options", "bottom", "bar_percentages", "decimals")
            bp_style = resolve_style(self.get("text_options", "bottom", "bar_percentages", "style"), default_style)
            
            item_w = width / total_items
            
            # Determine Top Text (Safe Zone)
            centered_str_top = ""
            c_style_top = bn_style
            parts_top = []
            
            # Bar Numbers
            if bn_en:
                val = ""
                # Calculate Base Values
                # Note: Card Bar "chunks" mode uses global chunk counts too?
                # Existing logic: `current_chunk_idx + 1` etc. Yes, global.
                c_done = current_chunk_idx + 1
                c_total = total_chunks
                c_rem = max(0, c_total - current_chunk_idx)
                
                k_done = self.current
                k_total = self.total
                k_rem = max(0, k_total - k_done)

                if bn_type == "relative":
                    # Relative to Chunk Limit (Cards in this chunk)
                    # We need "current card in this chunk". 
                    # If we are in chunk 2 (idx 1), cards 0-9 are done. current=10. start=10. curr_in_chunk=0.
                    # If current=15. start=10. curr_in_chunk=5.
                    cur_in_chunk = max(0, min(total_items, self.current - start_offset))
                    
                    v_done = cur_in_chunk
                    v_total = total_items
                    v_rem = max(0, v_total - v_done)
                else: 
                    # Absolute (Total Session Cards)
                    v_done = k_done
                    v_rem = k_rem
                    v_total = k_total
                
                if bn_dir == "remaining":
                    val = str(v_rem)
                elif bn_dir == "done/total" or bn_dir == "done/remaining":
                    val = f"{v_done}/{v_total}"
                elif bn_dir == "remaining/total" or bn_dir == "remaining/done":
                    val = f"{v_rem}/{v_total}"
                else: # done
                    val = str(v_done)
                    
                parts_top.append(val)
                c_style_top = bn_style
                
            # Bar Percentages
            if bp_en:
                if bp_type == "relative":
                    # Relative to Chunk (Cards in this chunk)
                    cur_in_chunk = max(0, min(total_items, self.current - start_offset))
                    ratio = cur_in_chunk / total_items if total_items > 0 else 0
                else:
                    # Absolute (Total Session)
                    ratio = self.current / self.total if self.total > 0 else 0
                
                pct_val = ratio * 100
                if bp_dir == "remaining": pct_val = 100 - pct_val
                
                if bp_show_dec:
                    val_str = f"{pct_val:.{bp_dec}f}%"
                else:
                    val_str = f"{int(pct_val)}%"
                parts_top.append(val_str)
                if not bn_en:
                     c_style_top = bp_style
            
            top_safe_zone = QRectF()
            if parts_top:
                centered_str_top = " - ".join(parts_top)
                temp_font = self.config_font(painter, bar_height, c_style_top)
                fm = QFontMetrics(temp_font)
                text_width = fm.horizontalAdvance(centered_str_top)
                padding = 4
                left_x = (width - text_width) / 2 - padding
                top_safe_zone = QRectF(left_x, 0, text_width + 2*padding, bar_height)
            
            # Draw Cards
            has_total_top = bool(centered_str_top) and not self.is_hovering
            
            # Define auto_hide for cards bar
            auto_hide = self.get("visual_options", "auto_hide_text")
            hl_excess = self.get("visual_options", "highlight_excess")
            str_again = self.get("visual_options", "striped_again")

            # All-or-Nothing Auto Hide (Cards)
            hide_all_card_text = False
            if auto_hide:
                 # Sample most likely scenario for overflow
                 s_parts = []
                 # 1. Check relative number (e.g. 10)
                 if tn_en and tn_type != "total": s_parts.append(str(total_items))
                 # 2. Check percentage (e.g. 100%)
                 if tp_en and tp_type != "total": s_parts.append("100%")
                 # 3. Check card timer (e.g. 99s)
                 if card_timer_en: s_parts.append("99s") 
                 
                 if s_parts:
                     temp_font = self.config_font(painter, bar_height, tn_style)
                     # Check if total width of all enabled parts exceeds cell width
                     sample_str = " ".join(s_parts)
                     if QFontMetrics(temp_font).horizontalAdvance(sample_str) > item_w:
                         hide_all_card_text = True
            
            # 2. All-or-Nothing Collision Detection (Symmetry) - REVERTED TO INDIVIDUAL
            # Individual collision detection is handled inside the rendering loop.

            
            for i in range(total_items):
                x = i * item_w
                rect_f = QRectF(x, 0, item_w - 1, bar_height - 1)
                
                # For 'cards' bar showing all cards, global index is just i
                global_idx = start_offset + i
                
                # Colors
                # Colors
                if global_idx < self.current:
                    try:
                        color = self.runtime_colors["good"]
                        if global_idx < len(self.status_log):
                            stat = self.status_log[global_idx]
                            
                            u_good_pass = self.get("visual_options", "use_good_for_all_pass")
                            # Handle Legacy Bools
                            if stat is True: color = self.runtime_colors["good"]
                            elif stat is False: color = self.runtime_colors["again"]
                            elif stat == 1: color = self.runtime_colors["again"]
                            elif stat == 2: color = self.runtime_colors["good"] if u_good_pass else self.runtime_colors["hard"]
                            elif stat == 3: color = self.runtime_colors["good"]
                            elif stat == 4: color = self.runtime_colors["good"] if u_good_pass else self.runtime_colors["easy"]
                            elif stat == "undone": color = self.runtime_colors["undone"]
                            elif stat == "buried": color = self.runtime_colors["buried"]
                            elif stat == "suspended": color = self.runtime_colors["suspended"]
                            elif stat == "deleted": color = self.runtime_colors["deleted"]
                        
                        painter.fillRect(rect_f, color)
                    except Exception:
                         # Fallback
                         painter.fillRect(rect_f, self.runtime_colors["good"])
                elif global_idx == self.current:
                    # Current card being reviewed
                    painter.fillRect(rect_f, self.runtime_colors["current"])
                else:
                    # Future cards in this chunk
                    painter.fillRect(rect_f, self.runtime_colors["pending"])
                    
                # Render Individual Card Text (if not hidden)
                if not hide_all_card_text:
                    cur_n_style = tn_style
                    cur_p_style = tp_style
                    
                    # 1. Determine base visibility/content
                    show_num_card = (tn_en and tn_type != "total")
                    show_pct_card = (tp_en and tp_type != "total")
                    
                    num_str_card = ""
                    pct_str_card = ""
                    if show_num_card: 
                        num_str_card = self.get_display_value(i, total_items, tn_type, False, start_offset)
                    
                    if show_pct_card:
                        if tp_type in ["total", "absolute"]:
                             # Global Percentage (of session total)
                             current_global = start_offset + i + 1
                             ratio_calc = current_global / self.total if self.total > 0 else 0
                        else:
                             # Relative Percentage (of chunk)
                             ratio_calc = (i + 1) / total_items if total_items > 0 else 0
                             
                        p_val = ratio_calc * 100
                        if tp_dir == "remaining": p_val = 100 - p_val
                        
                        if tp_show_dec:
                            pct_str_card = f"{p_val:.{tp_dec}f}%"
                        else:
                            pct_str_card = f"{int(p_val)}%"

                    # 2. Check for Timer Overrides
                    override_time_str = None
                    if card_timer_en and global_idx < len(self.time_log):
                        t_card = self.time_log[global_idx]
                        if t_card > 0:
                            override_time_str = self.fmt_duration(t_card, card_timer.get("format", {}))
                            cur_n_style = card_timer.get("style", tn_style)
                    elif card_live_en and global_idx == self.current:
                        if self.start_time > 0:
                            elapsed_card = time.time() - self.start_time
                            override_time_str = self.fmt_duration(elapsed_card, card_timer.get("format", {}))
                            cur_n_style = card_timer.get("style", tn_style)

                    if override_time_str:
                        num_str_card = override_time_str
                        pct_str_card = ""
                        show_num_card = True
                        show_pct_card = False

                    # 3. Individual Collision Detection
                    if has_total_top and (show_num_card or show_pct_card):
                         fm = QFontMetrics(self.config_font(painter, bar_height, cur_n_style))
                         sample_full_card = " ".join([p for p in [num_str_card, pct_str_card] if p])
                         tw_calc_card = fm.horizontalAdvance(sample_full_card)
                         tx_calc_card = i * item_w + (item_w - tw_calc_card) / 2
                         if QRectF(tx_calc_card - 2, 0, tw_calc_card + 4, bar_height).intersects(top_safe_zone):
                             show_num_card = show_pct_card = False

                    # 4. Rendering
                    if show_num_card and show_pct_card:
                        r_num = QRectF(x, 0, item_w/2, bar_height - 1)
                        r_pct = QRectF(x + item_w/2, 0, item_w/2, bar_height - 1)
                        self.draw_styled_text(painter, r_num, num_str_card, cur_n_style, auto_hide=False)
                        self.draw_styled_text(painter, r_pct, pct_str_card, cur_p_style, auto_hide=False)
                    elif show_num_card:
                        self.draw_styled_text(painter, rect_f, num_str_card, cur_n_style, auto_hide=False)
                    elif show_pct_card:
                        self.draw_styled_text(painter, rect_f, pct_str_card, cur_p_style, auto_hide=False)


            # Draw Top Centered Text (Cards Bar)
            if centered_str_top and not self.is_hovering:
                self.draw_styled_text(painter, QRectF(0, 0, width, bar_height), centered_str_top, c_style_top, auto_hide=auto_hide)
