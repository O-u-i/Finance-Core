"""Build and verify the optional FRAG protocol 2 plugin archive."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plugins" / "finance-core"
ARCHIVE = ROOT / "docs" / "release" / "finance-core-frag-plugin-v1.5.0.zip"
LEGACY_ARCHIVE = ROOT / "docs" / "release" / "finance-core-frag-plugin-v1.0.0.zip"
NAMES = ("manifest.json", "adapter.py", "ui.js")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_manifest() -> dict:
    return {
        "id": "finance-core",
        "name": "Finance Core",
        "protocolVersion": 2,
        "version": "1.5.0",
        "minHostVersion": "1.12.1",
        "capabilities": ["evidence.read"],
        "fcApiVersion": "3.5.0",
        "files": {name: sha256((SOURCE / name).read_bytes()) for name in ("adapter.py", "ui.js")},
    }


def check() -> str:
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if manifest != expected_manifest():
        raise ValueError("Plugin manifest does not match source files and compatibility contract.")
    with zipfile.ZipFile(ARCHIVE) as package:
        if package.namelist() != list(NAMES):
            raise ValueError("Plugin archive must contain exactly three root files.")
        for name in NAMES:
            if package.read(name) != (SOURCE / name).read_bytes():
                raise ValueError(f"Plugin archive differs from {name}.")
    return sha256(ARCHIVE.read_bytes())


def build() -> str:
    if json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8")) != expected_manifest():
        raise ValueError("Update manifest.json hashes before building.")
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for name in NAMES:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            package.writestr(info, (SOURCE / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
    return check()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(f"FRAG plugin archive SHA-256: {check() if args.check else build()}")
