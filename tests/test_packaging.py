"""Check the distributed archive's identity and separation of user data."""

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_addon", ROOT / "tools/build_addon.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackagingTests(unittest.TestCase):
    def test_archive_updates_existing_id_and_excludes_user_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            addon = builder.build_addon(Path(tmp) / "update.ankiaddon")
            with zipfile.ZipFile(addon) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["package"], "1724662218")
                self.assertIn("chunked_progress_bar", manifest["conflicts"])
                self.assertNotIn("mod", manifest)
                self.assertIn("__init__.py", archive.namelist())
                self.assertIn("state_store.py", archive.namelist())
                self.assertIn("config.json", archive.namelist())
                self.assertNotIn("meta.json", archive.namelist())
                self.assertEqual(
                    [name for name in archive.namelist() if name.startswith("user_files/")],
                    ["user_files/README.txt"],
                )
                self.assertFalse(any("__pycache__" in name for name in archive.namelist()))


if __name__ == "__main__":
    unittest.main()
