# Forecast Ledger

Forecast Ledger is an open JSON Schema for recording quantitative forecasts as
a durable, independently verifiable track record. It supports one individual or
team forecasting identity, forecast updates, outcome evidence, Git history,
RFC 3161 timestamp responses, and encrypted forecasts that can be revealed later.

The project exists because a useful forecasting record must answer more than
"what probability do you remember assigning?" It should make the original
number, the question, the timing, later updates, the resolution rule, and the
outcome evidence inspectable by another person or tool.

## What it guarantees

When the documented workflow is followed, a verifier can establish:

- exactly what quantitative forecast was recorded;
- that later updates did not silently replace earlier statements;
- that a TSA signed the exact forecast digest at the recorded RFC 3161
  `genTime`;
- that a revealed private forecast matches its original sealed commitment;
- how the question resolved and which external sources support the outcome.

## Current contract

- Forecast Ledger: `1.3.0`
- JSON Schema dialect: Draft 2020-12
- Canonicalization: RFC 8785 JCS, restricted to I-JSON values without floats
- Sealed forecasts: `forecast-seal/v1`
- Timestamp target: `forecast-envelope/v1`
- Timestamp protocol: RFC 3161 with SHA-256
- Permanent schema ID:
  `https://raw.githubusercontent.com/chaoscondensate/schema/v1.3.0/schema/forecast-ledger.schema.json`

The schema ID points to the immutable `v1.3.0` Git tag in this repository. Never
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
$schema: https://raw.githubusercontent.com/chaoscondensate/schema/v1.3.0/schema/forecast-ledger.schema.json
schema_version: 1.3.0
ledger_id: example-forecaster
created_at: "2026-08-25T10:00:00+01:00"
default_timezone: Europe/London

forecaster:
  id: example-forecaster
  kind: individual
  name: Example Forecaster

platforms: {}
questions: []
```

Questions may also exist before a forecast is available. Keep the required
question metadata and use `forecasts: []`; no placeholder probability is needed.

See the [empty ledger](examples/valid/empty-ledger.json),
[question backlog](examples/valid/question-without-forecasts.yaml), complete
[JSON example](examples/valid/individual-ledger.json), and complete
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
and an expected resolution time. An optional `forecast_window.opens_at` records
a lower bound; platform closing times are not duplicated in the ledger. A
resolved question stores the outcome, the time it became knowable, the ledger
recording time, and at least one evidence source.

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
5. Create an RFC 3161 request and obtain a response from a Time Stamping
   Authority (TSA):

   ```bash
   openssl ts -query \
     -data proofs/targets/<forecast-id>.json \
     -sha256 -cert \
     -out proofs/timestamps/<forecast-id>.tsq

   curl --fail --silent --show-error \
     -H "Content-Type: application/timestamp-query" \
     --data-binary @proofs/timestamps/<forecast-id>.tsq \
     "$TSA_URL" \
     --output proofs/timestamps/<forecast-id>.tsr
   ```

6. Verify the response against the exact request and a retained CA bundle:

   ```bash
   openssl ts -verify \
     -queryfile proofs/timestamps/<forecast-id>.tsq \
     -in proofs/timestamps/<forecast-id>.tsr \
     -CAfile proofs/timestamps/tsa-ca.pem
   openssl ts -verify \
     -data proofs/targets/<forecast-id>.json \
     -in proofs/timestamps/<forecast-id>.tsr \
     -CAfile proofs/timestamps/tsa-ca.pem
   openssl ts -reply -in proofs/timestamps/<forecast-id>.tsr -text
   ```

7. Record the request, response, TSA URL, CA bundle, `gen_time`, policy OID, and
   serial number; set the proof and integrity states to `verified`; then commit
   the complete evidence set.

RFC 3161 is the only timestamp protocol supported by `1.3.0`. Add one timestamp
object per TSA when using redundant services.

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

The current and only supported release is tagged `v1.3.0`. Release assets
include the schema, examples, documentation, and a checksum manifest. The
schema `$id` resolves directly to the tagged source file.

Each released schema requires its exact `schema_version`. This pre-adoption
phase permits breaking changes in a minor version because no clients depend on
the contract yet. Once the contract has adopters, breaking changes receive a new
major version and permanent URL. Released files are never overwritten; Git
provides development history, while release tags define immutable public
contracts.

## License and contributions

The schema, documentation, examples, and reference tools are available under the
[MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md) before proposing changes or reporting a cryptographic
issue.
