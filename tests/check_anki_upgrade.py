"""Run Anki's real installer against a disposable existing installation.

Usage: python tests/check_anki_upgrade.py path/to/aqt.whl path/to/update.ankiaddon

Installer classes come from the supplied official aqt wheel. Only GUI callbacks
and moving discarded temporary files to the system trash are replaced.
"""

import __future__
import ast
import collections
import dataclasses
import json
import os
import re
import shutil
import sys
import tempfile
import types
import zipfile
from pathlib import Path


def check_upgrade(wheel, addon):
    with zipfile.ZipFile(wheel) as archive:
        source = archive.read("aqt/addons.py").decode("utf-8")
    tree = ast.parse(source)
    selected = {"AddonMeta", "InstallOk", "InstallError", "AddonManager", "package_name_valid"}
    body = [
        node for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in selected
    ]
    module = types.ModuleType("anki_upgrade_check")
    sys.modules[module.__name__] = module
    module.__dict__.update(
        dataclass=dataclasses.dataclass,
        os=os, json=json, zipfile=zipfile, ZipFile=zipfile.ZipFile, Path=Path,
        defaultdict=collections.defaultdict,
        ANKIWEB_ID_RE=re.compile(r"^\d+$"),
        _current_version=260903,
        gui_hooks=types.SimpleNamespace(
            addon_manager_will_install_addon=lambda *args: None,
            addon_manager_did_install_addon=lambda *args: None,
        ),
    )
    exec(compile(ast.Module(body=body, type_ignores=[]), "aqt/addons.py", "exec",
                 flags=__future__.annotations.compiler_flag), module.__dict__)

    for channel in ("local", "ankiweb"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            def discard_temporary(path):
                target = Path(path).resolve()
                if target.parent != root:
                    raise ValueError("Refusing to remove a path outside the test installation")
                shutil.rmtree(target)

            module.send_to_trash = discard_temporary
            manager = module.AddonManager.__new__(module.AddonManager)
            manager.mw = types.SimpleNamespace(pm=types.SimpleNamespace(addonFolder=lambda: str(root)))
            user_config = {"chunk_size": 32, "colors": {"good": "#123456"}, "unknown_user_key": [1, 2]}
            saved_state = b'{"version":1,"collections":{"test":"preserve me"}}'
            for package, config in (("1724662218", user_config), ("chunked_progress_bar", {"chunk_size": 10})):
                folder = root / package
                folder.mkdir()
                (folder / "__init__.py").write_text("# old version", encoding="utf-8")
                manager.writeAddonMeta(package, {"name": "Chunked Progress Bar", "disabled": False,
                                                "config": config, "mod": 123})
            user_files = root / "1724662218" / "user_files"
            user_files.mkdir()
            (user_files / "progress_state.json").write_bytes(saved_state)

            server_manifest = None if channel == "local" else {
                "package": "1724662218", "name": "Chunked Progress Bar", "mod": 456,
                "min_point_version": 1, "max_point_version": 0, "branch_index": 0,
            }
            result = manager.install(str(addon), manifest=server_manifest)
            assert isinstance(result, module.InstallOk), result
            assert manager.addonMeta("1724662218")["config"] == user_config
            assert manager.getConfig("1724662218")["chunk_size"] == 32
            assert manager.getConfig("1724662218")["colors"]["good"] == "#123456"
            assert (user_files / "progress_state.json").read_bytes() == saved_state
            assert manager.addon_meta("1724662218").ankiweb_id() == 1724662218
            assert manager.isEnabled("1724662218")
            assert not manager.isEnabled("chunked_progress_bar")
            assert manager.addonMeta("chunked_progress_bar")["config"] == {"chunk_size": 10}
            assert (root / "1724662218" / "__init__.py").read_text(encoding="utf-8") != "# old version"
            assert manager.addonMeta("1724662218")["mod"] == (123 if channel == "local" else 456)
            print(f"{channel}: updated existing ID; preserved config and session data; disabled duplicate")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    check_upgrade(Path(sys.argv[1]), Path(sys.argv[2]))
