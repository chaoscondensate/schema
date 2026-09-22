# Forecast Ledger

Forecast Ledger is an open JSON Schema and reference validator for durable,
machine-verifiable quantitative forecast records. It can preserve a forecast
made directly in a ledger or imported from a forecasting platform without
discarding the question version, probability precision, domain, or distribution
semantics needed for later verification and scoring.

One ledger represents one individual or team forecasting identity. Empty
ledgers and questions without forecasts are valid first-class states.

## Current contract

- Forecast Ledger: `2.2.0`
- JSON Schema: Draft 2020-12
- Canonicalization: RFC 8785 JCS, restricted to I-JSON without floats
- Sealed forecasts: `forecast-seal/v3`
- Protected key file: `forecast-key/v3`
- Timestamp target: `forecast-envelope/v3`
- Lifecycle target: `forecast-lifecycle/v2`
- Evidence index: `forecast-evidence-index/v1`
- Publication manifest: `forecast-ledger-publication/v3`
- External timestamp protocol: RFC 3161 with SHA-256
- Permanent schema ID:
  `https://raw.githubusercontent.com/chaoscondensate/schema/v2.2.0/schema/forecast-ledger.schema.json`

This runtime contract accepts only v2.2.0 and its named profiles. Historical
material remains attributable through its immutable tag and historical tools;
v2.2.0 has no converter, dual parser, compatibility bundle, or fallback.

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
check-jsonschema --check-metaschema schema/*.schema.json
python tools/run_fixture_tests.py
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v3.json
python tools/forecast_crypto.py verify-key-vector tests/vectors/forecast-key-v3.json
python tools/forecast_crypto.py verify-target-vector tests/vectors/forecast-envelope-v3-public-lifecycle.json
python tools/forecast_crypto.py verify-target-vector tests/vectors/forecast-envelope-v3-sealed-lifecycle.json
python tools/forecast_crypto.py verify-lifecycle-vector tests/vectors/forecast-lifecycle-v2.json
python tools/forecast_crypto.py verify-presence-vector tests/vectors/forecast-seal-v3-presence.json
python tools/sidecar_contracts.py tests/vectors/forecast-evidence-index-v1*.json tests/vectors/forecast-ledger-publication-v3*.json
python tools/run_target_tests.py
python tools/run_seal_tests.py
python tools/run_sidecar_tests.py
python tools/run_transition_tests.py
python tools/run_diagnostic_tests.py
ruff check tools
```

## Minimal ledger

```yaml
$schema: https://raw.githubusercontent.com/chaoscondensate/schema/v2.2.0/schema/forecast-ledger.schema.json
schema_version: 2.2.0
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

`forecast-seal/v3` encrypts the exact representations and private reasoning
with ChaCha20-Poly1305. Its commitment and associated data bind the question ID,
question revision ID, and forecast ID. The timestamp envelope includes the full
question revision, so a later reveal cannot be transplanted onto different
wording, options, bounds, or resolution criteria.

Lifecycle events are append-only activity metadata. They change derived active
state but are excluded from both public and sealed immutable timestamp targets,
so withdrawal, expiry, and reaffirmation do not invalidate existing evidence.
Optional activity checkpoints bind an ordered lifecycle prefix to the original
forecast-envelope digest under `forecast-lifecycle/v2`. Later events leave an
earlier checkpoint valid and make its coverage partial until a new checkpoint
is retained and timestamped.

The `forecast-seal/v3` private bundle requires only non-empty
`representations`. `rationale`, `key_factors`, and `comment` are independently
optional. Their absence is authenticated and differs from an explicitly empty
string or empty array; reveal tooling never invents missing fields.

The protected `forecast-key/v3` file binds the question, revision, forecast, and
commitment digest. It is exact canonical JSON followed by one LF and is never a
publication artifact. At reveal, retain the original ciphertext and publish the
revealed key only inside the ledger commitment. The semantic validator decrypts
the bundle and rejects any mismatch. Read the normative
[cryptographic verification specification](docs/cryptographic-verification.md)
the [ordered operational workflows](docs/forecast-verification-workflows.md),
and the normative [evidence and publication contract](docs/evidence-and-publication.md).

## Repository layout

```text
schema/                    Ledger, key, evidence-index, and publication schemas
examples/valid/            English JSON and YAML examples
tests/conformance/         Positive conformance fixtures
tests/invalid-cases.json   Mutation-based rejection cases
tests/vectors/             Seal, key, target, sidecar, and publication vectors
tools/validate.py          Structural and semantic validator
tools/build_targets.py     RFC 8785 timestamp-target generator
tools/forecast_crypto.py   Seal, reveal, and canonicalization reference
tools/sidecar_contracts.py Evidence-index and publication reference
tools/run_target_tests.py  Envelope projection conformance tests
docs/                      Data model, compatibility, and workflows
research/                  Scope research supporting the v2 decision
```

## Versioning and publication

Release tags are immutable public contracts. A schema `$id` always points to a
tag, never a moving branch. `v2.2.0` is an explicitly breaking pre-adoption
cutover. It assigns new identities to every changed byte profile, adds retained
target states and closed evidence/publication sidecars, and accepts no earlier
contract or profile. Compatibility and conversion are deliberately out of
scope. Frozen older tags remain the exact sources for historical evidence.

The release workflow validates schema, seal, key, envelope, lifecycle, sidecar,
diagnostic, and conformance vectors and publishes a deterministic source archive,
standalone schemas, examples, and `SHA256SUMS` as GitHub Release assets.

## License and contributions

The schema, documentation, examples, and reference tools are available under
the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md) before proposing changes or reporting a
cryptographic issue.
