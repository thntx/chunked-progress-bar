from .config_utils import DEFAULT_CONFIG, get_config_val
from aqt import mw
from aqt.utils import tooltip
from .state import session


def calculate_fsrs_intervals(chunk_size, retention):
    # Standardize weights to binary (0=Again, 1=Pass) for retention calculation.
    # This ensures that chunk averages correspond to the percentage of passes,
    # making them comparable to the 0.0 - 1.0 retention intervals.
    weights = {
        "again": 0,
        "hard": 1,
        "good": 1,
        "easy": 1
    }
    
    # 2. Calculate x and y
    # Discrete steps = k / chunk_size
    steps = [i / chunk_size for i in range(chunk_size + 1)]
    
    # x: highest number < retention (or second highest if equal)
    # Filter strictly lower
    lower = [s for s in steps if s < retention]
    if lower:
        x = max(lower)
    else:
        x = 0.0 # Extreme case
        
    # y: lowest number > retention (or second lowest if equal)
    higher = [s for s in steps if s > retention]
    if higher:
        y = min(higher)
    else:
        y = 1.0 # Extreme case
        
    # 3. Configure Intervals
    # Return list of interval objects compliant with settings.py/config expectations
    # 0: Again [0, x)
    # 1: Again/Hard [x, R)
    # 2: Hard [R, R]
    # 3: Hard/Good (R, y]
    # 4: Good (y, 1]
    
    intervals = []
    
    def add_iv(en, sb, sv, ev, eb, ck, pk=None):
        intervals.append({
            "enabled": en,
            "start_bracket": sb,
            "start_val": float(sv),
            "end_val": float(ev),
            "end_bracket": eb,
            "color_key": ck,
            "pattern_key": pk
        })

    # 0: Again [0, x)
    add_iv(True, "[", 0.0, x, ")", "again")
    
    # 1: Again/Hard [x, retention)
    add_iv(True, "[", x, retention, ")", "again", "hard")
    
    # 2: Hard [retention, retention]
    add_iv(True, "[", retention, retention, "]", "hard")
    
    # 3: Hard/Good (retention, y]
    add_iv(True, "(", retention, y, "]", "hard", "good")
    
    # 4: Good (y, 1]
    add_iv(True, "(", y, 1.0, "]", "good")

    # 5: Good/Easy (Padding at 1.0) - Disabled for FSRS
    add_iv(False, "(", 1.0, 1.0, ")", "good", "easy")
    
    # 6: Easy [1.0, 1.0] - Disabled for FSRS
    add_iv(False, "[", 1.0, 1.0, "]", "easy")
    
    return weights, intervals

def get_avg_retention(deck_id):
    """Recursively fetch and average desiredRetention for a deck and its subdecks."""
    
    # Fetch all deck names/ids
    try:
        # Modern Anki 2.1.50+
        name = mw.col.decks.name(deck_id)
        # subdecks logic: find all decks starting with "name::" or name itself
        all_decks = mw.col.decks.all_names_and_ids()
        target_ids = []
        for d in all_decks:
            if d.name == name or d.name.startswith(name + "::"):
                target_ids.append(d.id)
    except:
        # Fallback/Safe
        target_ids = [deck_id]

    retentions = []
    for did in target_ids:
        try:
            # Try to get retention from deck config
            # 1. Get conf ID
            deck_obj = mw.col.decks.get(did)
            if not deck_obj: continue
            
            conf_id = deck_obj.get("conf")
            if not conf_id: continue
            
            # 2. Get config dict
            dconf = mw.col.decks.get_config(conf_id)
            if not dconf: continue
            
            # 3. Try common FSRS keys
            # FSRS v3/v4: desiredRetention
            # Also sometimes nested in 'fsrs' subdict in some versions
            ret = dconf.get("desiredRetention")
            if ret is None:
                fsrs_part = dconf.get("fsrs")
                if isinstance(fsrs_part, dict):
                    ret = fsrs_part.get("d") # 'd' is often used for desired retention in some FSRS setups
            
            if ret is not None:
                retentions.append(float(ret))
        except:
            continue
             
    if not retentions:
        return None
        
    return sum(retentions) / len(retentions)

def _canon_ce(ce):
    """Canonical, comparison-friendly view of a chunk_evaluation dict: only the
    fields that affect the colouring, with floats rounded and numbers coerced.
    This lets us detect a *real* colouring change while ignoring int/float and
    float-precision noise, so the tooltip fires only when the colouring truly
    changes (and not on every deck selection)."""
    ce = ce or {}
    w = ce.get("weights", {}) or {}
    weights = tuple(round(float(w.get(k, 0.0)), 6) for k in ("again", "hard", "good", "easy"))
    ivs = []
    for iv in (ce.get("intervals", []) or []):
        ivs.append((
            bool(iv.get("enabled", True)),
            iv.get("start_bracket"),
            round(float(iv.get("start_val", 0.0)), 6),
            round(float(iv.get("end_val", 0.0)), 6),
            iv.get("end_bracket"),
            iv.get("color_key"),
            iv.get("pattern_key"),
        ))
    return (weights, tuple(ivs))

def check_fsrs_deck_update(force=False):
    """
    Checks if deck changed and updates config with deck-specific FSRS retention.
    Returns True if config was updated.
    """
    if not mw.col: return
    
    config = mw.addonManager.getConfig(__name__)
    if not get_config_val(config, DEFAULT_CONFIG, "fsrs_use_deck"):
        return
        
    # Get current deck ID
    did = mw.col.decks.get_current_id()
    if not did:
        did = mw.col.decks.selected()
    if not did: return
    
    # Get deck name for tooltip
    try:
        dname = mw.col.decks.name(did)
    except:
        dname = "Unknown Deck"
    
    if did == session.last_deck_id and not force:
        return
        
    session.last_deck_id = did
    
    # Calculate Target Retention
    retention = get_avg_retention(did)
    
    # Track if we used fallback
    using_fallback = False
    
    # Fallback to user default
    if retention is None:
        retention = get_config_val(config, DEFAULT_CONFIG, "fsrs_retention")
        using_fallback = True
    
    # Standardize retention to float
    retention = float(retention)
        
    # Calculate New Intervals
    chunk_size = get_config_val(config, DEFAULT_CONFIG, "chunk_size")
    weights, intervals = calculate_fsrs_intervals(chunk_size, retention)
    
    new_ce = {
        "weights": weights,
        "intervals": intervals
    }
    
    # Compare with existing, ignoring int/float and float-precision noise so we
    # only act on a genuinely different colouring (fixes the "updated intervals"
    # tooltip firing on every deck selection).
    current_ce = config.get("chunk_evaluation", {})
    changed = _canon_ce(new_ce) != _canon_ce(current_ce)

    if changed:
        config["chunk_evaluation"] = new_ce
        # Persist
        mw.addonManager.writeConfig(__name__, config)
        # Note: writeConfig triggers update_all_widgets via existing hook
        # Explicitly call it with fresh config to guarantee UI refresh
        fresh_config = mw.addonManager.getConfig(__name__)
        from . import layout
        layout.update_all_widgets(fresh_config)

        # Notify User (only reached when the colouring actually changed)
        if using_fallback:
            tooltip(f"Could not fetch FSRS targets for '{dname}', using default {retention*100:.0f}%")
        else:
            tooltip(f"Updated coloring intervals for {retention*100:.0f}% desired retention", period=3000)

    return changed
