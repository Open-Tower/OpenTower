from __future__ import annotations

from pathlib import Path

package_root = Path(__file__).resolve().parent
checkout_package = package_root.parents[1] / "opentower_cli"

# Mirror the repo-root shim so `PYTHONPATH=runtime ...` keeps imports pinned to
# this checkout instead of leaking to sibling repos with the same package name.
__path__ = [str(package_root)]
if checkout_package.exists():
    __path__.insert(0, str(checkout_package))

from .cli import main

__all__ = ["main"]
