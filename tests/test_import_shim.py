from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import opentower_cli


def test_direct_run_shim_stays_inside_current_checkout() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    package_paths = {str(Path(path).resolve()) for path in opentower_cli.__path__}
    expected_paths = {
        str((repo_root / "opentower_cli").resolve()),
        str((repo_root / "runtime" / "opentower_cli").resolve()),
    }

    assert package_paths == expected_paths

    cli_mod = importlib.import_module("opentower_cli.cli")
    assert Path(cli_mod.__file__).resolve() == (repo_root / "runtime" / "opentower_cli" / "cli.py").resolve()


def test_runtime_path_shim_stays_inside_current_checkout() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str((repo_root / "runtime").resolve())
    code = """
import importlib
import json
from pathlib import Path
import opentower_cli

cli_mod = importlib.import_module("opentower_cli.cli")
print(json.dumps({
    "package_paths": [str(Path(path).resolve()) for path in opentower_cli.__path__],
    "cli_file": str(Path(cli_mod.__file__).resolve()),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=env,
    )
    payload = json.loads(completed.stdout)
    expected_paths = {
        str((repo_root / "opentower_cli").resolve()),
        str((repo_root / "runtime" / "opentower_cli").resolve()),
    }

    assert set(payload["package_paths"]) == expected_paths
    assert Path(payload["cli_file"]).resolve() == (repo_root / "runtime" / "opentower_cli" / "cli.py").resolve()
