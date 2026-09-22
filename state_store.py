"""Small, local persistence layer for review-session data Anki cannot reconstruct.

The collection revlog is authoritative for normal reviews, so we deliberately do
not duplicate it here.  We only persist information that would otherwise vanish
on an add-on reload/restart: which filtered deck a review belonged to, filtered
deck membership used to migrate older sessions, manual reviewer actions, and
acknowledged undo tombstones.

The file lives under ``user_files``.  Anki preserves that directory when an
add-on is updated, and the data is intentionally local rather than synced.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Any


SCHEMA_VERSION = 1
STATE_FILENAME = "progress_state.json"


def _state_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "user_files")


def _state_path() -> str:
    return os.path.join(_state_dir(), STATE_FILENAME)


def collection_key(col: Any) -> str:
    """Return a stable, non-identifying key for one local collection file."""
    path = getattr(col, "path", "") or ""
    normalized = os.path.normcase(os.path.abspath(str(path)))
    return hashlib.sha256(normalized.encode("utf-8", "surrogatepass")).hexdigest()


def empty_day_state(day_key: int, tracking_started_ms: int) -> dict[str, Any]:
    return {
        "day_key": int(day_key),
        "tracking_started_ms": int(tracking_started_ms),
        "filtered_memberships": {},
        "filtered_reviews": {},
        "manual_actions": [],
        "undo_tombstones": [],
    }


def _read_root() -> dict[str, Any]:
    try:
        with open(_state_path(), "r", encoding="utf-8") as handle:
            root = json.load(handle)
        if not isinstance(root, dict):
            raise ValueError("state root is not an object")
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        root = {}

    if root.get("version") != SCHEMA_VERSION or not isinstance(root.get("collections"), dict):
        root = {"version": SCHEMA_VERSION, "collections": {}}
    return root


def load_day_state(col: Any, day_key: int, tracking_started_ms: int) -> dict[str, Any]:
    root = _read_root()
    saved = root["collections"].get(collection_key(col))
    if not isinstance(saved, dict):
        return empty_day_state(day_key, tracking_started_ms)
    try:
        saved_day = int(saved.get("day_key", -1))
    except (TypeError, ValueError):
        return empty_day_state(day_key, tracking_started_ms)
    if saved_day != int(day_key):
        return empty_day_state(day_key, tracking_started_ms)

    state = empty_day_state(day_key, tracking_started_ms)
    try:
        state["tracking_started_ms"] = int(saved.get("tracking_started_ms", tracking_started_ms))
    except (TypeError, ValueError):
        pass

    memberships = saved.get("filtered_memberships")
    if isinstance(memberships, dict):
        state["filtered_memberships"] = memberships
    reviews = saved.get("filtered_reviews")
    if isinstance(reviews, dict):
        state["filtered_reviews"] = reviews
    manual = saved.get("manual_actions")
    if isinstance(manual, list):
        state["manual_actions"] = manual
    tombstones = saved.get("undo_tombstones")
    if isinstance(tombstones, list):
        state["undo_tombstones"] = tombstones
    return state


def save_day_state(col: Any, state: dict[str, Any]) -> None:
    """Atomically replace this collection's current-day state."""
    root = _read_root()
    root["collections"][collection_key(col)] = state

    directory = _state_dir()
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".progress_state-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(root, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, _state_path())
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def clear_collection_state(col: Any) -> None:
    """Forget persisted state for one collection without touching other profiles."""
    root = _read_root()
    if root["collections"].pop(collection_key(col), None) is None:
        return
    directory = _state_dir()
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".progress_state-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(root, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, _state_path())
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
