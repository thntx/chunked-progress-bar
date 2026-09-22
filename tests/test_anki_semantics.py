import tempfile
import unittest
from pathlib import Path

from anki.collection import Collection


class CurrentAnkiSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.col = Collection(str(Path(self.tmp.name) / "collection.anki2"))
        self.did = self.col.decks.selected()

    def tearDown(self):
        self.col.close()
        self.tmp.cleanup()

    def add_card(self):
        note = self.col.new_note(self.col.models.current())
        note["Front"] = "front"
        self.col.add_note(note, self.did)
        return note.cards()[0]

    def test_review_redo_restores_same_revlog_id(self):
        self.add_card()
        card = self.col.sched.getCard()
        self.col.sched.answerCard(card, 3)
        before = self.col.db.list("select id from revlog order by id")
        self.assertEqual(len(before), 1)

        undo = self.col.undo()
        self.assertEqual(self.col.db.list("select id from revlog"), [])

        redo = self.col.redo()
        after = self.col.db.list("select id from revlog order by id")
        self.assertEqual(after, before)

        self.assertTrue(undo.changes.card)
        self.assertTrue(undo.changes.study_queues)
        self.assertTrue(redo.changes.card)
        self.assertTrue(redo.changes.study_queues)

    def test_bury_suspend_changes_flags(self):
        card = self.add_card()

        buried = self.col.sched.bury_cards([card.id])
        self.assertTrue(buried.changes.card)
        self.assertTrue(buried.changes.study_queues)
        self.col.undo()

        suspended = self.col.sched.suspend_cards([card.id])
        self.assertTrue(suspended.changes.card)
        self.assertTrue(suspended.changes.study_queues)

    def test_filtered_review_revlog_shape(self):
        for _ in range(2):
            self.add_card()
        filtered = self.col.decks.new_filtered("Filtered")
        deck = self.col.decks.get(filtered)
        deck["terms"] = [["deck:Default", 100, 0]]
        deck["resched"] = True
        self.col.decks.save(deck)
        self.col.sched.rebuild_filtered_deck(filtered)
        self.col.decks.select(filtered)

        card = self.col.sched.getCard()
        original = card.id
        self.col.sched.answerCard(card, 4)
        row = self.col.db.first(
            "select id, cid, ease, type from revlog where cid=? order by id desc limit 1",
            original,
        )
        self.assertIsNotNone(row)
        # A rescheduling filtered-deck review can be logged as a normal learning
        # review (type 0), so revlog.type cannot identify which filtered deck it
        # came from.  This is why the add-on persists explicit attribution.
        self.assertEqual(row[3], 0)
        self.assertEqual(self.col.get_card(original).did, self.did)


if __name__ == "__main__":
    unittest.main()
