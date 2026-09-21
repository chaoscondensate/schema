# Forecast Ledger

Forecast Ledger is an open JSON Schema and reference validator for durable,
machine-verifiable quantitative forecast records. It can preserve a forecast
made directly in a ledger or imported from a forecasting platform without
discarding the question version, probability precision, domain, or distribution
semantics needed for later verification and scoring.

One ledger represents one individual or team forecasting identity. Empty
ledgers and questions without forecasts are valid first-class states.

## Current contract

- Forecast Ledger: `2.0.0`
- JSON Schema: Draft 2020-12
- Canonicalization: RFC 8785 JCS, restricted to I-JSON without floats
- Sealed forecasts: `forecast-seal/v2`
- Timestamp target: `forecast-envelope/v2`
- External timestamp protocol: RFC 3161 with SHA-256
- Permanent schema ID:
  `https://raw.githubusercontent.com/chaoscondensate/schema/v2.0.0/schema/forecast-ledger.schema.json`

The v1.3.0 schema and cryptographic vector remain frozen at the immutable
`v1.3.0` tag. v2 is intentionally incompatible with v1 and has no implicit
conversion. See [v1 to v2 compatibility](docs/compatibility-v1-v2.md).

## What v2 records

Every question has one or more immutable revisions. A revision contains the
exact title, resolution rule, expected resolution time, outcome space, domain,
and optional source provenance that applied at that time. Every forecast binds
to one exact revision.

Outcome spaces are:

- `binary`
- `categorical`
- `ordinal`
- `numeric`
- `date`
- `datetime`

Forecast representations are independent of outcome type:

- scalar probability;
- categorical or ordinal PMF;
- binned PMF with explicit left and right tail mass;
- quantiles with declared interpolation;
- CDF with declared interpolation and explicit tails;
- point estimate with named statistic;
- credible intervals with named interval semantics.

Probabilities and numeric quantities are exact canonical decimal strings.
Categorical forecasts bind the exact option-set ID and version; binned forecasts
bind the exact bin-set ID and version.

Optional sections support question groups, conditional questions, imported
platform provenance, and append-only forecast lifecycle events. Resolutions can
be `resolved`, `ambiguous`, `void`, `disputed`, or `not_applicable`.

## Quick start

Install the development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Validate JSON or YAML:

```bash
python tools/validate.py examples/valid/individual-ledger.json
python tools/validate.py examples/valid/team-ledger.yaml
```

The validator first applies JSON Schema and then enforces the rules that cannot
be expressed portably in JSON Schema: exact probability sums, option and bin
coverage, domain bounds and discrete steps, monotonic CDFs and quantiles,
revision and provenance references, relationship acyclicity, lifecycle state
transitions, artifact digests, chronology, and sealed reveal consistency.

Run the complete conformance suite:

```bash
check-jsonschema --check-metaschema schema/forecast-ledger.schema.json
python tools/run_fixture_tests.py
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v1.json
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v2.json
python tools/verify_legacy.py
ruff check tools
```

## Minimal ledger

```yaml
$schema: https://raw.githubusercontent.com/chaoscondensate/schema/v2.0.0/schema/forecast-ledger.schema.json
schema_version: 2.0.0
ledger_id: example-forecaster
created_at: "2026-09-21T10:00:00Z"
default_timezone: UTC

forecaster:
  id: example-forecaster
  kind: individual
  name: Example Forecaster

platforms: {}
questions: []
```

A question may be added before anyone forecasts it. Supply its first revision
and use `forecasts: []`; do not invent a placeholder probability. See the
[empty ledger](examples/valid/empty-ledger.json),
[question backlog](examples/valid/question-without-forecasts.yaml),
[full JSON example](examples/valid/individual-ledger.json), and
[revealed-seal YAML example](examples/valid/team-ledger.yaml).

## Minimal binary forecast

```yaml
- id: q-example
  status: open
  created_at: "2026-09-21T10:00:00Z"
  current_revision_id: qr-example-1
  revisions:
    - id: qr-example-1
      effective_at: "2026-09-21T10:00:00Z"
      recorded_at: "2026-09-21T10:00:00Z"
      title: Will the event occur before 2027?
      resolution_criteria: Resolve YES if the event is confirmed before 2027-01-01T00:00:00Z.
      expected_resolution_at: "2027-01-01T00:00:00Z"
      outcome_space: {kind: binary}
      domain: {kind: binary}
  forecasts:
    - id: f-example-1
      question_revision_id: qr-example-1
      forecasted_at: "2026-09-21T10:05:00Z"
      recorded_at: "2026-09-21T10:05:10Z"
      visibility: public
      representations:
        - kind: probability
          outcome: true
          probability: "0.62"
      integrity:
        status: unanchored
```

## Timestamp a forecast

`forecasted_at` and `recorded_at` are ledger claims. An independently verified
RFC 3161 response supplies the stronger evidence that the exact canonical
forecast envelope existed no later than the TSA's `genTime`.

Build immutable targets:

```bash
python tools/build_targets.py ledger.yaml --output proofs/targets
```

For every target, create and retain an RFC 3161 request and response:

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

Verify both the request binding and target bytes with the retained TSA trust
chain. Multiple RFC 3161 timestamp objects are supported, so independent TSAs
can be used for redundancy.

```bash
openssl ts -verify \
  -queryfile proofs/timestamps/<forecast-id>.tsq \
  -in proofs/timestamps/<forecast-id>.tsr \
  -CAfile proofs/timestamps/tsa-ca.pem
openssl ts -verify \
  -data proofs/targets/<forecast-id>.json \
  -in proofs/timestamps/<forecast-id>.tsr \
  -CAfile proofs/timestamps/tsa-ca.pem
```

OpenTimestamps is not part of the v2 contract. Git commits are publication
history, not trusted timestamps or forecast signatures.

## Sealed forecasts

`forecast-seal/v2` encrypts the exact representations and private reasoning
with ChaCha20-Poly1305. Its commitment and associated data bind the question ID,
question revision ID, and forecast ID. The timestamp envelope includes the full
question revision, so a later reveal cannot be transplanted onto different
wording, options, bounds, or resolution criteria.

At reveal, publish the key and exact plaintext mirror while retaining the
original ciphertext. The semantic validator decrypts the bundle and rejects any
mismatch. Read the normative
[cryptographic verification specification](docs/cryptographic-verification.md)
and the [ordered operational workflows](docs/forecast-verification-workflows.md).

## Repository layout

```text
schema/                    v2 JSON Schema contract
examples/valid/            English JSON and YAML examples
tests/conformance/         Positive conformance fixtures
tests/invalid-cases.json   Mutation-based rejection cases
tests/vectors/             Frozen v1 and current v2 seal vectors
tools/validate.py          Structural and semantic validator
tools/build_targets.py     RFC 8785 timestamp-target generator
tools/forecast_crypto.py   Seal, reveal, and canonicalization reference
tools/verify_legacy.py     Byte-for-byte v1.3.0 freeze check
docs/                      Data model, compatibility, and workflows
research/                  Scope research supporting the v2 decision
```

## Versioning and publication

Release tags are immutable public contracts. A schema `$id` always points to a
tag, never a moving branch. `v2.0.0` is a major version because question shape,
probabilities, forecast representations, resolution semantics, and the
cryptographic target all changed incompatibly.

The release workflow validates both seal vectors, proves that the tagged v1.3.0
schema and vector still match their frozen SHA-256 digests, and publishes a
source archive plus `SHA256SUMS` as GitHub Release assets.

## License and contributions

The schema, documentation, examples, and reference tools are available under
the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md) before proposing changes or reporting a
cryptographic issue.
