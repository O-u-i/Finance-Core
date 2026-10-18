from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from finance_core import __version__
from finance_core.app_v3 import create_app, public_commit


ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIR = ROOT / "docs" / "release"
OPENAPI_PATH = RELEASE_DIR / f"finance-core-v{__version__}-openapi.json"
MANIFEST_PATH = RELEASE_DIR / f"finance-core-v{__version__}-release.json"


def canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def expected_artifacts() -> tuple[bytes, bytes, str]:
    schema = create_app(data_root=ROOT / ".tmp" / "release-contract", admin_token="").openapi()
    openapi_bytes = canonical_json(schema)
    openapi_sha256 = hashlib.sha256(openapi_bytes).hexdigest()
    manifest = {
        "apiVersion": "3.10.0",
        "buildCommit": public_commit(os.environ.get("FINANCE_CORE_BUILD_COMMIT")),
        "openapiArtifact": OPENAPI_PATH.name,
        "openapiSha256": openapi_sha256,
        "releaseCommit": public_commit(os.environ.get("FINANCE_CORE_RELEASE_COMMIT")),
        "service": "finance-core",
        "serviceVersion": __version__,
    }
    return openapi_bytes, canonical_json(manifest), openapi_sha256


def write() -> str:
    openapi_bytes, manifest_bytes, digest = expected_artifacts()
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_bytes(openapi_bytes)
    MANIFEST_PATH.write_bytes(manifest_bytes)
    return digest


def check() -> str:
    openapi_bytes, manifest_bytes, digest = expected_artifacts()
    mismatches = []
    if not OPENAPI_PATH.is_file() or OPENAPI_PATH.read_bytes() != openapi_bytes:
        mismatches.append(OPENAPI_PATH.name)
    if not MANIFEST_PATH.is_file() or MANIFEST_PATH.read_bytes() != manifest_bytes:
        mismatches.append(MANIFEST_PATH.name)
    if mismatches:
        raise SystemExit(f"Release artifacts are stale or missing: {', '.join(mismatches)}")
    print(f"Finance Core {__version__} OpenAPI SHA-256: {digest}")
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or verify Finance Core release contract artifacts.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        print(f"Finance Core {__version__} OpenAPI SHA-256: {write()}")


if __name__ == "__main__":
    main()
