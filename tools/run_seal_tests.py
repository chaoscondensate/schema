#!/usr/bin/env python3
"""Verify forecast-seal/v2 optional-field presence and reveal semantics."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from forecast_crypto import (
    PRIVATE_BUNDLE_V2_FIELDS,
    SEAL_SCHEME_V2,
    reveal_forecast,
    reveal_into_forecast,
    seal_forecast,
    verify_presence_vector,
)
from validate import Problems, check_revealed

ROOT = Path(__file__).resolve().parents[1]
VECTOR = ROOT / "tests/vectors/forecast-seal-v2-presence.json"


def main() -> int:
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    verify_presence_vector(vector)
    material = vector["material"]
    key = bytes.fromhex(material["key_hex"])
    cases = {case["name"]: case for case in vector["cases"]}

    for name, case in cases.items():
        commitment, _ = seal_forecast(
            question_id=vector["question_id"],
            question_revision_id=vector["question_revision_id"],
            forecast_id=vector["forecast_id"],
            bundle=case["bundle"],
            salt=bytes.fromhex(material["salt_hex"]),
            key=key,
            nonce=bytes.fromhex(material["nonce_hex"]),
            key_hint=vector["key_hint"],
            scheme=SEAL_SCHEME_V2,
        )
        payload = reveal_forecast(
            question_id=vector["question_id"],
            question_revision_id=vector["question_revision_id"],
            forecast_id=vector["forecast_id"],
            commitment=commitment,
            key=key,
        )
        revealed_commitment = {
            **commitment,
            "revealed_at": "2026-09-03T10:00:00Z",
            "revealed_key": material["key_hex"],
        }
        sealed = {
            "id": vector["forecast_id"],
            "question_revision_id": vector["question_revision_id"],
            "forecasted_at": "2026-09-02T10:00:00Z",
            "recorded_at": "2026-09-02T10:00:05Z",
            "visibility": "sealed",
            "commitment": commitment,
            "integrity": {"status": "unanchored"},
        }
        revealed = reveal_into_forecast(sealed, payload, revealed_commitment)
        actual_private = set(revealed) & PRIVATE_BUNDLE_V2_FIELDS
        if actual_private != set(case["bundle"]):
            raise AssertionError(f"{name}: reveal invented or omitted a private field")

    absent_hash = cases["representation-only"]["expected"]["commitment_sha256"]
    empty_hash = cases["explicit-empty-optionals"]["expected"]["commitment_sha256"]
    if absent_hash == empty_hash:
        raise AssertionError("absent and explicitly empty private fields have the same commitment")

    for reveal_case in vector["reveal_cases"]:
        source = cases[reveal_case["sealed_case"]]
        commitment, _ = seal_forecast(
            question_id=vector["question_id"],
            question_revision_id=vector["question_revision_id"],
            forecast_id=vector["forecast_id"],
            bundle=source["bundle"],
            salt=bytes.fromhex(material["salt_hex"]),
            key=key,
            nonce=bytes.fromhex(material["nonce_hex"]),
            key_hint=vector["key_hint"],
            scheme=SEAL_SCHEME_V2,
        )
        altered = {
            "id": vector["forecast_id"],
            "question_revision_id": vector["question_revision_id"],
            "forecasted_at": "2026-09-02T10:00:00Z",
            "recorded_at": "2026-09-02T10:00:05Z",
            "visibility": "revealed",
            **copy.deepcopy(reveal_case["revealed_private_fields"]),
            "commitment": {
                **commitment,
                "revealed_at": "2026-09-03T10:00:00Z",
                "revealed_key": material["key_hex"],
            },
            "integrity": {"status": "unanchored"},
        }
        problems = Problems()
        check_revealed({"id": vector["question_id"]}, altered, "$.forecast", problems)
        if reveal_case["expected_error"] not in problems.items:
            raise AssertionError(f"{reveal_case['name']}: altered presence was not rejected")

    print("OK   all forecast-seal/v2 optional-field presence combinations")
    print("OK   absence differs from explicitly empty values")
    print("OK   reveal adds only authenticated private fields")
    print("OK   altered optional-field presence is rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
