import os
import json

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QDialogButtonBox, Qt,
)

# One entry per default-value change we want to announce ONCE to existing users.
# A change is offered only to a user who has explicitly stored a value that
# differs from the new default (so they won't silently inherit it). Fresh installs
# and users who already match the new default are never bothered.
#
# To announce a future default change, just append a new entry here.
DEFAULT_CHANGE_NOTICES = [
    {
        "id": "perfect_color_white_v1",
        "title": "Perfect-chunk highlight colour is now white by default",
        # Where the value may live in the config (all are read/written).
        "keys": [("colors", "perfect_color"), ("visual_options", "perfect_color")],
        "new_default": "#FFFFFF",
        "explanation": (
            "I've reworked how the “perfect chunk” highlight looks — it now lays "
            "subtle stripes over the chunk's own colour — and I think white suits it "
            "best, so the default highlight colour is now white."
        ),
    },
]

_SEEN_KEY = "_default_change_notices"


def _raw_user_config():
    """The user's STORED config (meta.json), without config.json defaults merged in.
    Lets us tell an explicitly-set value apart from an inherited default."""
    try:
        path = os.path.join(os.path.dirname(__file__), "meta.json")
        with open(path, encoding="utf-8") as f:
            return (json.load(f) or {}).get("config") or {}
    except Exception:
        return {}


def _get_stored(raw, keys):
    cur = raw
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _set_stored(raw, keys, value):
    cur = raw
    for k in keys[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def _differs_from_new_default(raw, notice):
    """True only if the user has a stored value that isn't the new default."""
    for keys in notice["keys"]:
        v = _get_stored(raw, keys)
        if v is not None:
            return str(v).strip().upper() != notice["new_default"].upper()
    return False  # nothing stored -> user inherits the new default -> no prompt


class DefaultChangesDialog(QDialog):
    def __init__(self, notices, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Chunked Progress Bar — updated defaults")
        self._items = []

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Some default settings changed in this update. Tick the changes you'd "
            "like to apply to your current settings; leave the rest unchecked to keep "
            "what you have."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addSpacing(6)

        for n in notices:
            cb = QCheckBox(n.get("title", n["id"]))
            cb.setChecked(False)  # opt-in: don't overwrite a custom value by accident
            layout.addWidget(cb)

            exp = QLabel(n.get("explanation", ""))
            exp.setWordWrap(True)
            exp.setStyleSheet("color: gray;")
            row = QHBoxLayout()
            row.addSpacing(22)
            row.addWidget(exp, 1)
            layout.addLayout(row)
            layout.addSpacing(8)

            self._items.append((cb, n))

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def checked_notices(self):
        return [n for cb, n in self._items if cb.isChecked()]


def check_default_change_notices():
    """Offer any newly-announced default changes that affect this (existing) user in
    a single popup, letting them pick which to apply. Safe to call every profile open."""
    raw = _raw_user_config()
    seen = list(raw.get(_SEEN_KEY) or [])

    unseen = [n for n in DEFAULT_CHANGE_NOTICES if n["id"] not in seen]
    if not unseen:
        return

    applicable = [n for n in unseen if _differs_from_new_default(raw, n)]

    # Nothing to offer this user (fresh install / already matching): quietly mark the
    # unseen notices handled so they never linger.
    if not applicable:
        raw[_SEEN_KEY] = seen + [n["id"] for n in unseen]
        mw.addonManager.writeConfig(__name__, raw)
        return

    dlg = DefaultChangesDialog(applicable)
    if not dlg.exec():
        return  # cancelled: leave unseen so we can offer again next launch

    # Apply the ticked changes, then mark every offered notice handled.
    for notice in dlg.checked_notices():
        for keys in notice["keys"]:
            _set_stored(raw, keys, notice["new_default"])

    raw[_SEEN_KEY] = seen + [n["id"] for n in unseen]
    mw.addonManager.writeConfig(__name__, raw)  # also refreshes the bars via the hook
