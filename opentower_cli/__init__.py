from __future__ import annotations

from pathlib import Path

package_root = Path(__file__).resolve().parent
runtime_package = package_root.parent / "runtime" / "opentower_cli"

# Pin direct-run imports to this checkout so sibling repos with the same package
# name do not bleed into tests or `python -m opentower_cli ...`.
__path__ = [str(package_root)]
if runtime_package.exists():
    __path__.append(str(runtime_package))

from .cli import main

__all__ = ["main"]
