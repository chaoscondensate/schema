#!/usr/bin/env python3
"""Verify v2 target vectors and lifecycle-event projection invariants."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from build_targets import build_targets
from forecast_crypto import (
    canonicalize,
    envelope_from_target_vector,
    verify_target_vector,
)

ROOT = Path(__file__).resolve().parents[1]
VECTOR_PATHS = (
    ROOT / "tests/vectors/forecast-envelope-v2-public-lifecycle.json",
    ROOT / "tests/vectors/forecast-envelope-v2-sealed-lifecycle.json",
)

LIFECYCLE_CASES: dict[str, list[dict[str, Any]]] = {
    "withdrawn": [
        {
            "id": "event-withdrawn",
            "type": "withdrawn",
            "effective_at": "2026-09-05T10:00:00Z",
            "recorded_at": "2026-09-05T10:00:05Z",
        }
    ],
    "expired": [
        {
            "id": "event-expired",
            "type": "expired",
            "effective_at": "2026-09-05T10:00:00Z",
            "recorded_at": "2026-09-05T10:00:05Z",
        }
    ],
    "reaffirmed": [
        {
            "id": "event-withdrawn-before-reaffirmation",
            "type": "withdrawn",
            "effective_at": "2026-09-05T10:00:00Z",
            "recorded_at": "2026-09-05T10:00:05Z",
        },
        {
            "id": "event-reaffirmed",
            "type": "reaffirmed",
            "effective_at": "2026-09-06T10:00:00Z",
            "recorded_at": "2026-09-06T10:00:05Z",
        },
    ],
}


def vector_ledger(vector: dict[str, Any]) -> dict[str, Any]:
    return {
        "questions": [
            {
                "id": vector["question_id"],
                "revisions": [vector["question_revision"]],
                "forecasts": [vector["forecast"]],
            }
        ]
    }


def check_vector(path: Path) -> list[str]:
    vector = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    try:
        expected = verify_target_vector(vector)
    except Exception as error:
        return [str(error)]

    envelope = envelope_from_target_vector(vector)
    projected = envelope["forecast"]
    for field in vector["expected_included_forecast_fields"]:
        if field not in projected:
            errors.append(f"allowed field {field!r} is missing from the projection")
    for field in vector["expected_excluded_forecast_fields"]:
        if field in projected:
            errors.append(f"excluded field {field!r} is present in the projection")

    baseline_vector = copy.deepcopy(vector)
    baseline_vector["forecast"].pop("lifecycle_events", None)
    baseline = canonicalize(envelope_from_target_vector(baseline_vector))
    if baseline != expected:
        errors.append("target with lifecycle events differs from the target before events")

    for name, events in LIFECYCLE_CASES.items():
        event_vector = copy.deepcopy(baseline_vector)
        event_vector["forecast"]["lifecycle_events"] = events
        candidate = canonicalize(envelope_from_target_vector(event_vector))
        if candidate != baseline:
            errors.append(f"{name} changes the canonical target")

    with TemporaryDirectory() as directory:
        output = Path(directory)
        report = build_targets(vector_ledger(vector), output)
        built = (output / f"{vector['forecast']['id']}.json").read_bytes()
        if built != expected:
            errors.append("reference builder does not reproduce the published target bytes")
        if report[0]["digest"]["value"] != vector["expected"]["sha256"]:
            errors.append("reference builder does not reproduce the published target digest")
    return errors


def main() -> int:
    failed = False
    for path in VECTOR_PATHS:
        errors = check_vector(path)
        if errors:
            failed = True
            print(f"FAIL target vector {path.relative_to(ROOT)}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK   target vector {path.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
