from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from finance_core.release_artifact import check as check_release_artifacts


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = "3.1.0"


def main() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    init_text = (ROOT / "backend" / "finance_core" / "__init__.py").read_text(encoding="utf-8")
    index_text = (ROOT / "index.html").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    values = {
        "package.json": package["version"],
        "package-lock.json": package_lock["version"],
        "package-lock root": package_lock["packages"][""]["version"],
        "backend/pyproject.toml": pyproject["project"]["version"],
        "finance_core.__version__": re.search(r'__version__\s*=\s*"([^"]+)"', init_text).group(1),  # type: ignore[union-attr]
    }
    mismatches = {name: value for name, value in values.items() if value != EXPECTED}
    if mismatches:
        raise SystemExit(f"Version mismatch: {mismatches}")
    for name, text in (("index.html", index_text), ("README.md", readme)):
        if EXPECTED not in text:
            raise SystemExit(f"{name} does not display {EXPECTED}.")
    major_horizon = f"{EXPECTED.split('.', 1)[0]}.0.0"
    horizon = ROOT / "docs" / "pdf" / f"finance-core-v{major_horizon}-horizon.pdf"
    if not horizon.is_file() or horizon.stat().st_size < 10_000:
        raise SystemExit(f"Major release Horizon PDF is missing or unexpectedly small: {horizon.name}")
    check_release_artifacts()
    print(f"Finance Core version surfaces are synchronized at {EXPECTED}; Horizon baseline is {major_horizon}.")


if __name__ == "__main__":
    main()
