# Forecast Ledger

Forecast Ledger is an open JSON Schema for recording quantitative forecasts as
a durable, independently verifiable track record. It supports one individual or
team forecasting identity, forecast updates, outcome evidence, Git history,
OpenTimestamps receipts, and encrypted forecasts that can be revealed later.

The project exists because a useful forecasting record must answer more than
"what probability do you remember assigning?" It should make the original
number, the question, the timing, later updates, the resolution rule, and the
outcome evidence inspectable by another person or tool.

## What it guarantees

When the documented workflow is followed, a verifier can establish:

- exactly what quantitative forecast was recorded;
- that later updates did not silently replace earlier statements;
- that a cryptographically timestamped forecast existed no later than an
  external anchor;
- that a revealed private forecast matches its original sealed commitment;
- how the question resolved and which external sources support the outcome.

## Current contract

- Forecast Ledger: `1.0.0`
- JSON Schema dialect: Draft 2020-12
- Canonicalization: RFC 8785 JCS, restricted to I-JSON values without floats
- Sealed forecasts: `forecast-seal/v1`
- Timestamp target: `forecast-envelope/v1`
- Permanent schema ID:
  `https://raw.githubusercontent.com/chaoscondensate/schema/v1.0.0/schema/forecast-ledger.schema.json`

The schema ID points to the immutable `v1.0.0` Git tag in this repository. Never
move a release tag or change a released schema in place.

## Quick start

Create a virtual environment and install the validation dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Validate either JSON or YAML:

```bash
python tools/validate.py examples/valid/individual-ledger.json
python tools/validate.py examples/valid/team-ledger.yaml
```

The validator runs Draft 2020-12 with format assertions and then checks semantic
rules that JSON Schema cannot express portably: ID uniqueness, probability sums,
option coverage, chronology, monotonic quantiles, artifact digests, and sealed
reveal consistency.

Run the complete test suite:

```bash
check-jsonschema --check-metaschema schema/forecast-ledger.schema.json
python tools/run_fixture_tests.py
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v1.json
```

## Minimal structure

```yaml
$schema: https://raw.githubusercontent.com/chaoscondensate/schema/v1.0.0/schema/forecast-ledger.schema.json
schema_version: 1.0.0
ledger_id: example-forecaster
created_at: "2026-08-25T10:00:00+01:00"
default_timezone: Europe/London

forecaster:
  id: example-forecaster
  kind: individual
  name: Example Forecaster

publication:
  history: git
  repository_url: https://github.com/chaoscondensate/schema
  default_branch: main
  ledger_path: ledger.yaml

platforms: {}
questions:
  - id: q-example
    title: Will the example event occur by 2026-12-31?
    type: binary
    status: open
    resolution_criteria: Resolve YES if the event is publicly confirmed before 2027-01-01T00:00:00Z.
    created_at: "2026-08-25T10:00:00+01:00"
    forecast_window:
      closes_at: "2026-12-01T00:00:00Z"
    expected_resolution_at: "2027-01-01T00:00:00Z"
    forecasts:
      - id: f-example-001
        forecasted_at: "2026-08-25T10:05:00+01:00"
        recorded_at: "2026-08-25T10:06:00+01:00"
        visibility: public
        value:
          kind: binary
          probability_bp: 6500
        integrity:
          status: unanchored
```

See the complete [JSON example](examples/valid/individual-ledger.json) and
[YAML example](examples/valid/team-ledger.yaml).

## Data model

One ledger represents one forecasting identity. A team may list multiple
members, but it is scored and published as one forecaster.

Questions support four measurable types:

- binary probability;
- multiple-choice probability distribution;
- numeric point, interval, and quantile forecasts;
- date point, interval, and quantile forecasts.

Probabilities are integer basis points (`6200` = 62%). Exact numeric quantities
are decimal strings. Qualitative phrases and inferred probabilities are outside
the v1 contract.

Every question has self-reported lifecycle status, explicit resolution criteria,
a forecast window, and an expected resolution time. A resolved question stores
the outcome, the time it became knowable, the ledger recording time, and at
least one evidence source.

Read the full [data model guide](docs/data-model.md).

## Record and timestamp a forecast

1. Add a new forecast record. Never edit an old probability; use
   `supersedes_forecast_id` on the new record.
2. Validate the ledger.
3. Generate the exact canonical timestamp target:

   ```bash
   python tools/build_targets.py ledger.yaml --output proofs/targets
   ```

4. Put the reported artifact path and SHA-256 into `integrity.target`.
5. Timestamp the artifact:

   ```bash
   ots stamp proofs/targets/<forecast-id>.json
   ```

6. Record the `.ots` path with integrity `pending`; commit and push the ledger,
   target, and receipt together.
7. Run `ots upgrade` and `ots verify` after confirmation, then record the verified
   upper time bound and Bitcoin block height.

RFC 3161 receipts may be added as an immediate second witness. OTS is mandatory
for anchored v1 records because it provides a long-lived Bitcoin-backed proof.

## Sealed forecasts

`forecast-seal/v1` encrypts the value, rationale, key factors, and comment with
ChaCha20-Poly1305. A separate SHA-256 commitment binds the canonical plaintext.
The timestamp target binds the full public seal envelope, not ciphertext alone.

At reveal time, publish the key and plaintext mirror while retaining the original
ciphertext. The semantic validator decrypts the bundle and rejects any mismatch.

The deterministic test vector deliberately includes the byte that broke the old
delimiter-based design. See the complete
[cryptographic verification specification](docs/cryptographic-verification.md).

For the exact public, sealed, reveal, and independent-verifier call order, read
the [forecast recording and verification workflows](docs/forecast-verification-workflows.md).

## Repository layout

```text
schema/                    JSON Schema contract
examples/valid/            English JSON and YAML ledgers
docs/                      Data-model and cryptographic specifications
tests/                     Negative mutations and cryptographic vectors
tools/validate.py          Structural and semantic validator
tools/build_targets.py     RFC 8785 timestamp-target generator
tools/forecast_crypto.py   Seal, reveal, and canonicalization reference
.github/workflows/         Continuous validation
```

## Publishing and versioning

The first public release is tagged `v1.0.0` and published as an immutable GitHub
release. Release assets include the schema, examples, documentation, and a
checksum manifest. The schema `$id` resolves directly to the tagged source file.

Each released schema requires its exact `schema_version`. A breaking contract
change receives a new major version and a new permanent URL. Released files are
never overwritten; Git provides development history, while release tags define
immutable public contracts.

## License and contributions

The schema, documentation, examples, and reference tools are available under the
[MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md) before proposing changes or reporting a cryptographic
issue.
