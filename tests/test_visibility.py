"""Review lifecycle regressions using real Qt widgets, without launching Anki.

Run with: python -m unittest discover -s tests -p test_visibility.py -v
"""

import ast
import os
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget


ROOT = Path(__file__).resolve().parents[1]
CONFIG = runpy.run_path(str(ROOT / "config_utils.py"))


def load_functions(filename, env):
    # Match the existing logic tests: skip add-on imports and their GUI hooks.
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    functions = ast.Module(
        body=[node for node in tree.body if isinstance(node, ast.FunctionDef)],
        type_ignores=[],
    )
    exec(compile(functions, filename, "exec"), env)


class VisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QWidget()
        self.main_layout = QVBoxLayout(self.window)
        self.chunk = QWidget(self.window)
        self.card = QWidget(self.window)
        self.config = {"positions": {"chunks": "top", "cards": "bottom"}}
        self.mw = NS(
            state="review",
            col=Mock(),
            mainLayout=self.main_layout,
            addonManager=NS(getConfig=lambda _: self.config),
        )
        self.layout_env = {
            "mw": self.mw,
            "chunk_widget": self.chunk,
            "card_widget": self.card,
            "DEFAULT_CONFIG": CONFIG["DEFAULT_CONFIG"],
            "get_config_val": CONFIG["get_config_val"],
            "__name__": "test_addon.layout",
        }
        load_functions("layout.py", self.layout_env)
        self.timers = []
        self.logic_env = {}
        load_functions("logic.py", self.logic_env)
        self.logic_env.update(
            mw=self.mw,
            layout=NS(**self.layout_env),
            session=NS(),
            fsrs_logic=NS(check_fsrs_deck_update=Mock()),
            QTimer=NS(singleShot=lambda ms, fn: self.timers.append(fn)),
            _ensure_session_state=Mock(return_value=True),
            reconstruct_history=Mock(),
        )
        self.layout_env["apply_layout"](self.config)
        self.window.show()

    def tearDown(self):
        for widget in (self.chunk, self.card, self.window):
            widget.close()
            widget.deleteLater()
        self.app.processEvents()

    def transition(self, state):
        old_state = self.mw.state
        self.mw.state = state
        self.logic_env["on_state_change"](state, old_state)

    def test_leaving_review_hides_both_bars_in_every_other_state(self):
        for state in ("deckBrowser", "overview", "resetRequired", "profileManager", "startup"):
            with self.subTest(state=state):
                self.transition("review")
                self.assertTrue(self.chunk.isVisible())
                self.assertTrue(self.card.isVisible())
                self.transition(state)
                self.assertTrue(self.chunk.isHidden())
                self.assertTrue(self.card.isHidden())

    def test_review_entry_respects_independent_hidden_settings(self):
        for chunks, cards in (("hidden", "bottom"), ("top", "hidden"), ("hidden", "hidden")):
            with self.subTest(chunks=chunks, cards=cards):
                self.config["positions"].update(chunks=chunks, cards=cards)
                self.transition("deckBrowser")
                self.transition("review")
                self.assertEqual(self.chunk.isHidden(), chunks == "hidden")
                self.assertEqual(self.card.isHidden(), cards == "hidden")

    def test_relayout_outside_review_cannot_reveal_bars(self):
        self.transition("deckBrowser")
        for position in ("top", "bottom", "hidden"):
            with self.subTest(position=position):
                self.config["positions"].update(chunks=position, cards=position)
                self.layout_env["apply_layout"](self.config)
                self.app.processEvents()
                self.assertTrue(self.chunk.isHidden())
                self.assertTrue(self.card.isHidden())

    def test_relayout_during_review_applies_hidden_and_docked_positions(self):
        for position in ("hidden", "bottom", "top"):
            with self.subTest(position=position):
                self.config["positions"].update(chunks=position, cards=position)
                self.layout_env["apply_layout"](self.config)
                self.app.processEvents()
                self.assertEqual(self.chunk.isVisible(), position != "hidden")
                self.assertEqual(self.card.isVisible(), position != "hidden")
                if position != "hidden":
                    self.assertGreaterEqual(self.main_layout.indexOf(self.chunk), 0)
                    self.assertGreaterEqual(self.main_layout.indexOf(self.card), 0)

    def test_queued_refresh_after_leaving_review_does_no_collection_work(self):
        self.transition("review")
        self.assertTrue(self.timers)
        self.transition("deckBrowser")
        self.logic_env["_ensure_session_state"].reset_mock()
        for callback in self.timers:
            callback()
        self.logic_env["_ensure_session_state"].assert_not_called()
        self.mw.col.sched.counts.assert_not_called()
        self.assertTrue(self.chunk.isHidden())
        self.assertTrue(self.card.isHidden())

    def test_visibility_update_tolerates_uninitialized_widgets(self):
        self.layout_env.update(chunk_widget=None, card_widget=None)
        self.layout_env["update_visibility"](state="deckBrowser")


if __name__ == "__main__":
    unittest.main()
