#!/usr/bin/env python3
"""Validate Forecast Ledger JSON or YAML documents.

JSON Schema validates document shape. This tool adds cross-record rules that
JSON Schema cannot express portably: ID uniqueness, probability sums, option
coverage, chronological ordering, monotonic quantiles, artifact digests, and
revealed commitment verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from forecast_crypto import reveal_forecast
from jsonschema import Draft202012Validator, FormatChecker
from ruamel.yaml import YAML


class Problems:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, path: str, message: str) -> None:
        self.items.append(f"{path}: {message}")

    def unique(self, values: list[str], path: str) -> None:
        seen: set[str] = set()
        for index, value in enumerate(values):
            if value in seen:
                self.add(f"{path}[{index}]", f"duplicate id {value!r}")
            seen.add(value)


def load_document(path: Path) -> Any:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    yaml = YAML(typ="safe")
    return yaml.load(path.read_text(encoding="utf-8"))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check_schema(instance: Any, schema: dict[str, Any], problems: Problems) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path
        )
        problems.add(path, error.message)


def check_quantiles(value: dict[str, Any], path: str, problems: Problems) -> None:
    quantiles = value.get("quantiles", [])
    probabilities = [item["probability_bp"] for item in quantiles]
    if len(probabilities) != len(set(probabilities)):
        problems.add(f"{path}.quantiles", "quantile probabilities must be unique")
    if probabilities != sorted(probabilities):
        problems.add(f"{path}.quantiles", "quantiles must be ordered by probability_bp")

    values = [item["value"] for item in quantiles]
    comparable = [Decimal(item) for item in values] if value["kind"] == "numeric" else values
    if comparable != sorted(comparable):
        problems.add(f"{path}.quantiles", "quantile values must be non-decreasing")

    interval = value.get("interval")
    if interval:
        if value["kind"] == "numeric":
            lower, upper = Decimal(interval["lower"]), Decimal(interval["upper"])
        else:
            lower, upper = interval["lower"], interval["upper"]
        if lower > upper:
            problems.add(f"{path}.interval", "lower must not exceed upper")


def check_value(
    question: dict[str, Any], value: dict[str, Any], path: str, problems: Problems
) -> None:
    if value["kind"] != question["type"]:
        problems.add(path, f"value kind must match question type {question['type']!r}")
        return
    if value["kind"] == "multiple_choice":
        option_ids = [option["id"] for option in question["options"]]
        probability_ids = [item["option_id"] for item in value["probabilities"]]
        problems.unique(probability_ids, f"{path}.probabilities")
        if set(probability_ids) != set(option_ids):
            problems.add(
                f"{path}.probabilities",
                "probability entries must cover every question option exactly once",
            )
        total = sum(item["probability_bp"] for item in value["probabilities"])
        if total != 10000:
            problems.add(f"{path}.probabilities", f"probabilities sum to {total}, not 10000")
    if value["kind"] in {"numeric", "date"}:
        check_quantiles(value, path, problems)


def check_artifact(
    integrity: dict[str, Any], repository_root: Path, path: str, problems: Problems
) -> None:
    if integrity["status"] in {"unanchored", "failed"} or "target" not in integrity:
        return
    target = integrity["target"]
    artifact = repository_root / target["artifact_path"]
    if not artifact.is_file():
        problems.add(f"{path}.target.artifact_path", f"artifact does not exist: {artifact}")
        return
    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    expected = target["digest"]["value"]
    if actual != expected:
        problems.add(
            f"{path}.target.digest.value",
            f"artifact SHA-256 is {actual}, expected {expected}",
        )


def check_revealed(
    question: dict[str, Any], forecast: dict[str, Any], path: str, problems: Problems
) -> None:
    if forecast["visibility"] != "revealed":
        return
    try:
        payload = reveal_forecast(
            question_id=question["id"],
            forecast_id=forecast["id"],
            commitment=forecast["commitment"],
            key=bytes.fromhex(forecast["commitment"]["revealed_key"]),
        )
    except Exception as error:  # cryptographic APIs intentionally expose varied errors
        problems.add(f"{path}.commitment", f"reveal verification failed: {error}")
        return

    bundle = payload["bundle"]
    mirror_fields = (
        "forecasted_at",
        "recorded_at",
        "value",
        "rationale",
        "key_factors",
        "comment",
    )
    for field in mirror_fields:
        if forecast.get(field) != bundle.get(field):
            problems.add(f"{path}.{field}", "does not match the decrypted sealed bundle")


def check_semantics(
    ledger: dict[str, Any], repository_root: Path, problems: Problems
) -> None:
    try:
        ZoneInfo(ledger["default_timezone"])
    except ZoneInfoNotFoundError:
        problems.add("$.default_timezone", "is not a known IANA time zone")

    forecaster = ledger["forecaster"]
    if forecaster["kind"] == "team":
        problems.unique(
            [member["id"] for member in forecaster["members"]], "$.forecaster.members"
        )
    problems.unique(
        [key["id"] for key in forecaster.get("signing_keys", [])],
        "$.forecaster.signing_keys",
    )

    question_ids = [question["id"] for question in ledger["questions"]]
    problems.unique(question_ids, "$.questions")
    platform_ids = set(ledger["platforms"])
    global_forecast_ids: list[str] = []

    for question_index, question in enumerate(ledger["questions"]):
        qpath = f"$.questions[{question_index}]"
        window = question["forecast_window"]
        opens_at = parse_time(window.get("opens_at", question["created_at"]))
        closes_at = parse_time(window["closes_at"])
        if opens_at > closes_at:
            problems.add(f"{qpath}.forecast_window", "opens_at must not exceed closes_at")
        if parse_time(question["expected_resolution_at"]) < closes_at:
            problems.add(
                f"{qpath}.expected_resolution_at",
                "must not be earlier than forecast_window.closes_at",
            )

        for ref_index, ref in enumerate(question.get("platform_refs", [])):
            if ref["platform"] not in platform_ids:
                problems.add(
                    f"{qpath}.platform_refs[{ref_index}].platform",
                    f"unknown platform {ref['platform']!r}",
                )

        if question["type"] == "multiple_choice":
            problems.unique(
                [option["id"] for option in question["options"]], f"{qpath}.options"
            )

        local_forecast_ids: list[str] = []
        previous_recorded_at: datetime | None = None
        for forecast_index, forecast in enumerate(question["forecasts"]):
            fpath = f"{qpath}.forecasts[{forecast_index}]"
            forecast_id = forecast["id"]
            global_forecast_ids.append(forecast_id)
            forecasted_at = parse_time(forecast["forecasted_at"])
            recorded_at = parse_time(forecast["recorded_at"])
            if forecasted_at > recorded_at:
                problems.add(f"{fpath}.recorded_at", "must not precede forecasted_at")
            if not opens_at <= forecasted_at <= closes_at:
                problems.add(
                    f"{fpath}.forecasted_at",
                    "must fall inside the question forecast window",
                )
            if previous_recorded_at and recorded_at < previous_recorded_at:
                problems.add(fpath, "forecasts must be ordered by recorded_at")
            previous_recorded_at = recorded_at

            supersedes = forecast.get("supersedes_forecast_id")
            if supersedes and supersedes not in local_forecast_ids:
                problems.add(
                    f"{fpath}.supersedes_forecast_id",
                    "must reference an earlier forecast for the same question",
                )
            local_forecast_ids.append(forecast_id)

            if "value" in forecast:
                check_value(question, forecast["value"], f"{fpath}.value", problems)
            check_artifact(forecast["integrity"], repository_root, f"{fpath}.integrity", problems)
            check_revealed(question, forecast, fpath, problems)

        resolution = question.get("resolution")
        if resolution and resolution["status"] == "resolved":
            known_at = parse_time(resolution["outcome_known_at"])
            recorded_at = parse_time(resolution["recorded_at"])
            if recorded_at < known_at:
                problems.add(f"{qpath}.resolution.recorded_at", "must not precede outcome_known_at")
            if question["type"] == "multiple_choice":
                option_ids = {option["id"] for option in question["options"]}
                if resolution["outcome"] not in option_ids:
                    problems.add(
                        f"{qpath}.resolution.outcome",
                        "must reference one of the question option IDs",
                    )
            for forecast_index, forecast in enumerate(question["forecasts"]):
                integrity = forecast["integrity"]
                if integrity["status"] != "verified":
                    continue
                for proof_index, proof in enumerate(integrity["timestamps"]):
                    if (
                        proof["type"] == "opentimestamps"
                        and proof["state"] == "confirmed"
                        and parse_time(proof["anchored_before"]) >= known_at
                    ):
                        problems.add(
                            f"{qpath}.forecasts[{forecast_index}].integrity.timestamps[{proof_index}]",
                            "timestamp does not predate the known outcome",
                        )

    problems.unique(global_forecast_ids, "$.questions[*].forecasts")


def validate(path: Path, schema_path: Path, repository_root: Path) -> list[str]:
    ledger = load_document(path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    problems = Problems()
    check_schema(ledger, schema, problems)
    if not problems.items:
        check_semantics(ledger, repository_root, problems)
    return problems.items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documents", nargs="+", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("schema/forecast-ledger.schema.json"),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Base directory for proof artifact paths",
    )
    args = parser.parse_args()

    failed = False
    for document in args.documents:
        errors = validate(document, args.schema, args.repository_root)
        if errors:
            failed = True
            print(f"FAIL {document}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK   {document}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
