"""Build a clean update for the existing AnkiWeb add-on.

Usage: python tools/build_addon.py path/to/chunked-progress-bar.ankiaddon
"""

import ast
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "1724662218"


def build_addon(destination):
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("package") != PACKAGE_ID:
        raise ValueError("The package must update the existing AnkiWeb ID 1724662218")
    if "chunked_progress_bar" not in manifest.get("conflicts", []):
        raise ValueError("The legacy duplicate must be declared as a conflict")

    sources = sorted(ROOT.glob("*.py")) + [
        ROOT / "config.json",
        ROOT / "manifest.json",
        ROOT / "user_files" / "README.txt",
    ]
    # Explicitly include only shipped sources/defaults. meta.json contains the
    # user's settings; user_files/*.json contains their local session history.
    for source in sources:
        if source.suffix == ".py":
            ast.parse(source.read_bytes(), filename=str(source))
        elif source.suffix == ".json":
            json.loads(source.read_bytes())

    destination = Path(destination).resolve()
    if destination.suffix != ".ankiaddon":
        raise ValueError("The output filename must end in .ankiaddon")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sources:
            archive.write(source, source.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("The built archive failed its integrity check")
    return destination


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(build_addon(sys.argv[1]))
