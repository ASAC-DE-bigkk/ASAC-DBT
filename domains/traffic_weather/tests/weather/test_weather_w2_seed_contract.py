from __future__ import annotations

import csv
import hashlib
import io
import json

import yaml

from tests.weather.w2_contract_fixtures import (
    BRIDGE_SEED,
    BRIDGE_SEED_CONTRACT,
    repo_path,
)


def _version_digest(blob: bytes, bridge_version: str) -> tuple[int, str]:
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig"), newline=""))
    fieldnames = tuple(reader.fieldnames or ())
    assert "bridge_version" in fieldnames
    rows = sorted(
        tuple(row[name] for name in fieldnames)
        for row in reader
        if row["bridge_version"] == bridge_version
    )
    canonical = json.dumps(
        {"fieldnames": fieldnames, "rows": rows},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return len(rows), hashlib.sha256(canonical).hexdigest()


def test_bridge_v1_seed_matches_the_versioned_repository_contract() -> None:
    contract = yaml.safe_load(
        repo_path(BRIDGE_SEED_CONTRACT).read_text(encoding="utf-8")
    )

    assert contract["fixture_version"] == 1
    assert contract["path"] == BRIDGE_SEED.as_posix()
    assert _version_digest(
        repo_path(BRIDGE_SEED).read_bytes(), contract["bridge_version"]
    ) == (contract["expected_rows"], contract["semantic_sha256"])
