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
    verify_lifecycle_vector,
    verify_target_vector,
)
from validate import load_document

ROOT = Path(__file__).resolve().parents[1]
VECTOR_PATHS = (
    ROOT / "tests/vectors/forecast-envelope-v2-public-lifecycle.json",
    ROOT / "tests/vectors/forecast-envelope-v2-sealed-lifecycle.json",
)
LIFECYCLE_VECTOR_PATH = ROOT / "tests/vectors/forecast-lifecycle-v1.json"
LIFECYCLE_FIXTURE_PATH = ROOT / "tests/conformance/valid/lifecycle-checkpoints.json"

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

    checkpoint_vector = copy.deepcopy(vector)
    checkpoint_vector["forecast"]["activity_checkpoints"] = [
        {
            "id": "checkpoint-excluded-from-envelope",
            "head_event_id": "event-excluded-from-envelope",
            "recorded_at": "2026-09-30T00:00:00Z",
            "integrity": {"status": "failed"},
        }
    ]
    if canonicalize(envelope_from_target_vector(checkpoint_vector)) != expected:
        errors.append("activity checkpoints change the canonical envelope target")

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
    lifecycle_vector = json.loads(LIFECYCLE_VECTOR_PATH.read_text(encoding="utf-8"))
    try:
        verify_lifecycle_vector(lifecycle_vector)
        expected = {
            checkpoint["head_event_id"]: checkpoint["expected"]
            for checkpoint in lifecycle_vector["checkpoints"]
        }
        with TemporaryDirectory() as directory:
            output = Path(directory)
            report = build_targets(load_document(LIFECYCLE_FIXTURE_PATH), output)
            lifecycle_reports = [
                item for item in report if item["scope"] == "forecast-lifecycle/v1"
            ]
            if len(lifecycle_reports) != 2:
                raise AssertionError("reference builder did not produce both lifecycle checkpoints")
            for item in lifecycle_reports:
                published = expected[item["head_event_id"]]
                built = Path(item["artifact_path"]).read_bytes()
                if built.decode("utf-8") != published["canonical_target"]:
                    raise AssertionError("reference builder lifecycle bytes differ from vector")
                if item["digest"]["value"] != published["sha256"]:
                    raise AssertionError("reference builder lifecycle digest differs from vector")
    except Exception as error:
        failed = True
        print(f"FAIL lifecycle vector {LIFECYCLE_VECTOR_PATH.relative_to(ROOT)}")
        print(f"  - {error}")
    else:
        print(f"OK   lifecycle vector {LIFECYCLE_VECTOR_PATH.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
