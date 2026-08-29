# Forecast recording and verification workflows

This guide defines the operational order for recording, timestamping, revealing,
and independently verifying Forecast Ledger v1 records. The normative byte
formats remain defined in
[`cryptographic-verification.md`](cryptographic-verification.md).

## Evidence layers

Forecast Ledger uses independent mechanisms for different claims. Passing one
check does not imply that the other claims are true.

| Mechanism | Establishes | Does not establish |
| --- | --- | --- |
| JSON Schema and semantic validation | The ledger is structurally and internally consistent | Historical existence or truth |
| SHA-256 target digest | The committed target bytes have not changed | When they existed |
| RFC 3161 response | A TSA signed the exact target digest at its declared `genTime` | Truth of the forecast, outcome, or TSA clock |
| `forecast-seal/v1` | Hidden content is confidential and cannot be substituted at reveal | Existence before an external anchor |
| Git history | Publication history and the sequence of repository changes | An independently trusted timestamp |
| Resolution sources | Evidence for the recorded outcome | Historical existence of the forecast |

The complete public-forecast evidence chain is:

```text
forecast fields
    -> canonical forecast-envelope/v1 target
    -> SHA-256 target digest
    -> RFC 3161 request and TSA response
    -> Git commit containing ledger + target + timestamp artifacts
    -> later outcome record and resolution sources
```

For a sealed forecast, an additional chain precedes the timestamp target:

```text
private forecast bundle + random salt
    -> RFC 8785 canonical plaintext
    -> SHA-256 commitment
    -> ChaCha20-Poly1305 ciphertext
    -> canonical forecast-envelope/v1 target
```

## v1 cryptographic boundary

Forecast Ledger v1 intentionally does not use per-forecast digital signatures
or signed Git commits as part of its verification protocol. Git is the
publication history. The cryptographic timing claim comes from the external
timestamp over the exact canonical target.

A commitment hash is not a signature. It binds hidden plaintext to a later
reveal but does not identify who created it. Likewise, a Git commit hash is not
an independent timestamp and a hosting account is not a cryptographic identity
proof.

The reference verifier therefore reports content integrity, existence timing,
reveal validity, and outcome verification. It does not make a cryptographic
authorship claim.

## Artifacts that must be retained

For every anchored forecast, retain all of the following:

- the ledger file;
- `proofs/targets/<forecast-id>.json`;
- the matching `.tsq` request and `.tsr` response for every TSA;
- the CA bundle needed to verify every retained response;
- the Git commit containing the ledger, target, requests, responses, and CA bundle;
- for sealed forecasts, the original commitment and ciphertext;
- after reveal, the disclosed key and plaintext mirror.

A timestamp response without its exact request and target is insufficient. A
target without a valid TSA response proves content equality but not historical
existence.

## Public forecast: recording workflow

### 1. Add a new forecast

Create a new forecast record with `visibility: public`. Include the quantitative
value and every statement field that should be immutable. Never overwrite an
earlier forecast; append a new record and set `supersedes_forecast_id`.

The first draft may use `integrity.status: unanchored` while the timestamp is
being prepared.

### 2. Validate the ledger

```bash
python tools/validate.py ledger.yaml
```

Stop if validation fails.

### 3. Build the canonical target

```bash
python tools/build_targets.py ledger.yaml --output proofs/targets
```

The command writes one RFC 8785 canonical `forecast-envelope/v1` artifact per
forecast and prints its SHA-256 digest. Copy the reported path and digest into
`forecast.integrity.target`.

### 4. Create the timestamp request

```bash
mkdir -p proofs/timestamps
openssl ts -query \
  -data proofs/targets/<forecast-id>.json \
  -sha256 -cert \
  -out proofs/timestamps/<forecast-id>.tsq
```

The `.tsq` contains the SHA-256 message imprint and requests the TSA signing
certificate. Send it as binary data to the TSA and retain the response:

```bash
curl --fail --silent --show-error \
  -H "Content-Type: application/timestamp-query" \
  --data-binary @proofs/timestamps/<forecast-id>.tsq \
  "$TSA_URL" \
  --output proofs/timestamps/<forecast-id>.tsr
```

Before independent verification is complete, record both artifacts with
`state: pending` and set the forecast integrity status to `pending`.

```yaml
integrity:
  status: pending
  target:
    scope: forecast-envelope/v1
    canonicalization: RFC8785
    artifact_path: proofs/targets/<forecast-id>.json
    digest:
      algorithm: sha-256
      value: <64-lowercase-hex-characters>
  timestamps:
    - type: rfc3161
      request_path: proofs/timestamps/<forecast-id>.tsq
      response_path: proofs/timestamps/<forecast-id>.tsr
      tsa_url: https://tsa.example.com/
      hash_algorithm: sha256
      state: pending
```

### 5. Validate the completed pending record

```bash
python tools/validate.py ledger.yaml
```

The timestamp target deliberately excludes `integrity`, so adding the target and
timestamp metadata does not recursively change the bytes being timestamped.

### 6. Verify the TSA response

Retain the TSA trust chain in a PEM CA bundle and verify against the exact
request:

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

The `-queryfile` check binds the response to the saved request and nonce. The
`-data` check independently binds its message imprint to the exact target bytes.
Both must succeed.

Only after verification succeeds, copy `genTime`, policy OID, and serial number
from the decoded response into the timestamp object. Add `ca_bundle_path`, set
its state to `verified`, set integrity to `verified`, and record `verified_at`.

```yaml
integrity:
  status: verified
  target:
    scope: forecast-envelope/v1
    canonicalization: RFC8785
    artifact_path: proofs/targets/<forecast-id>.json
    digest:
      algorithm: sha-256
      value: <64-lowercase-hex-characters>
  timestamps:
    - type: rfc3161
      request_path: proofs/timestamps/<forecast-id>.tsq
      response_path: proofs/timestamps/<forecast-id>.tsr
      tsa_url: https://tsa.example.com/
      hash_algorithm: sha256
      state: verified
      gen_time: "2026-08-25T10:02:00Z"
      policy_oid: 1.2.3.4.1
      serial_number: "0123456789abcdef"
      ca_bundle_path: proofs/timestamps/tsa-ca.pem
  verified_at: "2026-08-25T10:03:00Z"
```

For redundancy, repeat steps 4 and 6 with other TSAs and append one timestamp
object per service. Each TSA requires its own independently retained request,
response, URL, and applicable CA bundle.

### 7. Commit and publish the complete evidence set

Stage the ledger, exact target, timestamp artifacts, and CA bundle together:

```bash
git add ledger.yaml proofs/targets/<forecast-id>.json proofs/timestamps/
git commit -m "Record forecast <forecast-id>"
git push
```

The Git commit keeps the files together in repository history. The signed RFC
3161 response, not the Git commit time, supplies the independent time claim.
Do not edit the original forecast statement or target.

## Sealed forecast: recording workflow

The sealed workflow hides `value`, `rationale`, `key_factors`, and `comment`
until reveal. The visible record still contains the forecast and recording
times, IDs, commitment, nonce, and ciphertext.

### 1. Construct and seal the private bundle

Generate a fresh key, salt, and nonce for every forecast. The reference function
call is:

```python
from secrets import token_bytes

from tools.forecast_crypto import seal_forecast

key = token_bytes(32)
commitment, canonical_plaintext = seal_forecast(
    question_id="q-example",
    forecast_id="f-example-001",
    bundle={
        "forecasted_at": "2026-08-25T10:00:00+01:00",
        "recorded_at": "2026-08-25T10:01:00+01:00",
        "value": {"kind": "binary", "probability_bp": 6500},
        "rationale": "...",
        "key_factors": ["..."],
        "comment": "Reveal after resolution.",
    },
    salt=token_bytes(32),
    key=key,
    nonce=token_bytes(12),
    key_hint="secret-manager://forecast-ledger/f-example-001",
)
```

The caller must store `key` in a secret manager before publishing anything.
`canonical_plaintext` is sensitive and must not be committed. Never reuse a
`(key, nonce)` pair.

### 2. Publish only the seal

Create the ledger record with `visibility: sealed`, the visible timestamps, and
the returned `commitment`. Do not include `value`, `rationale`, `key_factors`,
or `comment` outside the ciphertext.

### 3. Timestamp and publish

Follow public-workflow steps 2 through 7 without modification:

```text
validate
    -> build target
    -> create RFC 3161 request and obtain TSA response
    -> record pending integrity
    -> validate
    -> verify the TSA response
    -> commit ledger + target + timestamp artifacts + CA bundle
    -> push
```

Timestamp the complete sealed envelope, not the ciphertext alone.

## Sealed forecast: reveal workflow

### 1. Test the key before editing the ledger

Use `reveal_forecast()` with the original IDs, commitment, and 32-byte key:

```python
from tools.forecast_crypto import reveal_forecast

payload = reveal_forecast(
    question_id="q-example",
    forecast_id="f-example-001",
    commitment=commitment,
    key=bytes.fromhex(revealed_key_hex),
)
```

Stop if decryption, AEAD authentication, commitment verification, ID binding, or
canonicalization fails.

### 2. Change the record to `revealed`

Retain the original commitment hash, nonce, ciphertext, and `key_hint`. Add:

- `revealed_at`;
- `revealed_key`;
- the exact decrypted `value`, `rationale`, `key_factors`, and `comment` as the
  public plaintext mirror.

### 3. Validate and compare the original target

```bash
python tools/validate.py ledger.yaml
python tools/build_targets.py ledger.yaml --output proofs/rebuilt-targets
cmp proofs/targets/<forecast-id>.json proofs/rebuilt-targets/<forecast-id>.json
```

The semantic validator decrypts the ciphertext and compares every public mirror
field with the private bundle. The rebuilt target for a revealed forecast must
be byte-for-byte identical to the original sealed target; revealing a forecast
does not require a new timestamp.

### 4. Commit the reveal

Commit and push the revealed ledger. The old sealed commit, target, and timestamp
response remain the evidence that the hidden content existed before the reveal
and, when applicable, before the outcome.

## Independent verifier workflow

Verification should start from an exact Git revision, never from an unpinned
branch view.

### 1. Select the containing commit

Identify the first commit containing the forecast record, target, timestamp
artifacts, and CA bundle:

```bash
git log --follow -- ledger.yaml
git show <commit>:ledger.yaml
```

### 2. Validate the ledger

Check out the exact commit and run:

```bash
python tools/validate.py ledger.yaml
```

This checks JSON Schema, chronology, IDs, probability constraints, local target
digests, and revealed sealed bundles. It does not parse or cryptographically
verify binary `.tsr` files.

### 3. Rebuild and compare the target

```bash
python tools/build_targets.py ledger.yaml --output proofs/rebuilt-targets
cmp proofs/targets/<forecast-id>.json proofs/rebuilt-targets/<forecast-id>.json
```

Also compare the SHA-256 digest with `integrity.target.digest.value`. Any byte or
digest mismatch invalidates the content-binding claim.

### 4. Verify the external timestamp

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

The response must validate against the exact committed request, exact target,
and trusted TSA chain. Inspect it with
`openssl ts -reply -in <response>.tsr -text` and compare
its message imprint, `genTime`, policy OID, and serial number with the ledger.
For a resolved forecast, at least one verified `genTime` must precede
`resolution.outcome_known_at`; otherwise the evidence does not rule out hindsight.

### 5. Verify a reveal, when present

Run the ledger validator or call `reveal_forecast()` directly. Confirm that:

1. ChaCha20-Poly1305 authentication succeeds;
2. the plaintext SHA-256 equals `commitment_hash`;
3. the sealed question and forecast IDs match the ledger;
4. the decrypted bytes are canonical RFC 8785 JSON;
5. the public mirror equals the decrypted bundle;
6. the rebuilt sealed target still matches the originally timestamped target.

### 6. Verify the outcome independently

Open each resolution source, check that it supports the declared resolution
criteria, and confirm the reported publication and retrieval times. Cryptography
can preserve a false outcome record perfectly; source evaluation remains a
separate verification step.

## Failure handling

| Failure | Required conclusion |
| --- | --- |
| Ledger validation fails | The record is invalid |
| Rebuilt target differs | Forecast content binding is invalid |
| RFC 3161 response is pending | Historical existence is not yet independently confirmed |
| RFC 3161 signature, request, or trust-chain check fails | Historical existence claim is invalid |
| Timestamp is not earlier than the known outcome | The response does not exclude hindsight |
| Reveal decryption or hash check fails | The reveal is invalid |
| Public mirror differs from decrypted content | The reveal is invalid |
| Resolution sources do not support the criteria | The recorded outcome is unverified |

Do not collapse these results into a single generic `verified` label. Report
content integrity, existence timing, reveal validity, and outcome verification
separately.

## External reference

- [RFC 3161: Internet X.509 Public Key Infrastructure Time-Stamp Protocol](https://www.rfc-editor.org/rfc/rfc3161)
- [OpenSSL `ts` command](https://docs.openssl.org/master/man1/openssl-ts/)
