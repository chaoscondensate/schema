#!/usr/bin/env python3
"""Build immutable RFC 8785 forecast-envelope targets for timestamping."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forecast_crypto import (
    canonicalize,
    public_forecast_envelope,
    sealed_forecast_envelope,
    sha256_ref,
)
from validate import load_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--output", type=Path, default=Path("proofs/targets"))
    args = parser.parse_args()

    ledger = load_document(args.ledger)
    args.output.mkdir(parents=True, exist_ok=True)
    report = []

    for question in ledger["questions"]:
        revisions = {revision["id"]: revision for revision in question["revisions"]}
        for forecast in question["forecasts"]:
            revision = revisions[forecast["question_revision_id"]]
            if forecast["visibility"] == "public":
                envelope = public_forecast_envelope(question["id"], forecast, revision)
            else:
                envelope = sealed_forecast_envelope(question["id"], forecast, revision)
            data = canonicalize(envelope)
            path = args.output / f"{forecast['id']}.json"
            path.write_bytes(data)
            report.append(
                {
                    "question_id": question["id"],
                    "forecast_id": forecast["id"],
                    "artifact_path": path.as_posix(),
                    "digest": sha256_ref(data),
                }
            )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
