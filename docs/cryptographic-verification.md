# Cryptographic verification

This document is normative for `forecast-envelope/v1` and
`forecast-seal/v1`. The reference implementation is
[`tools/forecast_crypto.py`](../tools/forecast_crypto.py).

For the end-to-end invocation order and independent verifier checklist, see
[`forecast-verification-workflows.md`](forecast-verification-workflows.md).

## Security goals

The protocol provides:

- content binding: a recorded forecast cannot be opened as another forecast;
- hiding: a sealed forecast and its reasoning remain confidential until reveal;
- existence timing: a trusted TSA signs the digest of a precise envelope and
  records its RFC 3161 `genTime`;
- portable verification: the Git host is not required once artifacts, RFC 3161
  responses, requests, and trust anchors are downloaded.

It does not prove authorship by itself, guarantee that the ledger is complete,
or prove that a self-reported `forecasted_at` is exact. Forecast Ledger v1 does
not define a cryptographic authorship protocol. A timestamp, commitment hash, or
valid decryption is not a signature.

## Canonicalization

Timestamp targets and seal plaintext use RFC 8785 JSON Canonicalization Scheme
(JCS). Forecast Ledger further restricts canonicalized values:

- no floating-point JSON numbers;
- integers must be within the I-JSON safe range;
- decimals are strings;
- duplicate object keys and lone Unicode surrogates are invalid.

This keeps implementations simple without defining a private serialization
format. `tools/forecast_crypto.py` implements the exact supported subset,
including UTF-16 property ordering required by RFC 8785.

## Public forecast envelope

For a public forecast, canonicalize this object:

```json
{
  "schema": "forecast-envelope/v1",
  "question_id": "q-example",
  "forecast": {
    "id": "f-example-001",
    "forecasted_at": "2026-08-25T10:00:00+01:00",
    "recorded_at": "2026-08-25T10:01:00+01:00",
    "visibility": "public",
    "value": { "kind": "binary", "probability_bp": 6500 },
    "rationale": "...",
    "key_factors": ["..."]
  }
}
```

Include every present immutable forecast statement field listed by
`public_forecast_envelope()`. Exclude `integrity`; adding timestamp metadata after
timestamping must not make the target recursive.

## Sealed forecast protocol

### Inputs

- 32 random bytes `salt` from a CSPRNG;
- 32 random bytes `key` from a CSPRNG;
- 12 unique random bytes `nonce`;
- bundle fields: `forecasted_at`, `recorded_at`, `value`, `rationale`,
  `key_factors`, and `comment`.

Never reuse a `(key, nonce)` pair. A fresh key per forecast is recommended.

### Plaintext and commitment

Construct and JCS-canonicalize:

```json
{
  "schema": "forecast-seal/v1",
  "question_id": "q-example",
  "forecast_id": "f-example-001",
  "bundle": { "...": "..." },
  "salt": "64 lowercase hexadecimal characters"
}
```

Then calculate:

```text
C = SHA-256(canonical_plaintext)
```

The salt is a fixed-length hex field inside canonical JSON. No delimiter is
used, so every possible 32-byte salt is decoded unambiguously.

### Encryption

Associated data is JCS-canonical JSON:

```json
{
  "scheme": "forecast-seal/v1",
  "question_id": "q-example",
  "forecast_id": "f-example-001",
  "commitment_sha256": "C"
}
```

Encrypt the canonical plaintext with ChaCha20-Poly1305. Publish `C`, algorithm,
nonce, ciphertext, and a non-secret key-manager pointer. Keep key and salt
secret; the salt is recoverable from the ciphertext.

### Timestamp target

Do not timestamp ciphertext alone. The sealed `forecast-envelope/v1` contains
the question ID, forecast ID, visible times, scheme, commitment hash, algorithm,
nonce, and ciphertext. This binds every security-relevant input and avoids
relying on properties that ordinary AEAD does not promise.

`key_hint` is intentionally excluded: it is an operational pointer that may be
rotated without changing the forecast.

### Reveal

Publish the 32-byte key as lowercase hex and set `visibility: revealed`.
Retain the original commitment and ciphertext. A verifier:

1. reconstructs associated data;
2. decrypts and authenticates the ciphertext;
3. verifies `SHA-256(plaintext) == C`;
4. checks scheme, question ID, and forecast ID;
5. checks that the public plaintext mirror equals the decrypted bundle;
6. verifies the timestamp target and RFC 3161 response.

## Timestamp workflow

Generate exact target artifacts:

```bash
python tools/build_targets.py ledger.yaml --output proofs/targets
```

For each report entry, copy the artifact path and digest into `integrity.target`.
Create an RFC 3161 request over the exact target using SHA-256:

```bash
mkdir -p proofs/timestamps
openssl ts -query \
  -data proofs/targets/f-example-001.json \
  -sha256 -cert \
  -out proofs/timestamps/f-example-001.tsq
```

Send the binary request to a Time Stamping Authority and retain its binary
response:

```bash
curl --fail --silent --show-error \
  -H "Content-Type: application/timestamp-query" \
  --data-binary @proofs/timestamps/f-example-001.tsq \
  "$TSA_URL" \
  --output proofs/timestamps/f-example-001.tsr
```

Verify the response using the exact request and a retained CA bundle, then
inspect the signed token metadata:

```bash
openssl ts -verify \
  -queryfile proofs/timestamps/f-example-001.tsq \
  -in proofs/timestamps/f-example-001.tsr \
  -CAfile proofs/timestamps/tsa-ca.pem
openssl ts -verify \
  -data proofs/targets/f-example-001.json \
  -in proofs/timestamps/f-example-001.tsr \
  -CAfile proofs/timestamps/tsa-ca.pem
openssl ts -reply -in proofs/timestamps/f-example-001.tsr -text
```

The first verification binds the response to the saved request and its nonce.
The second binds the response message imprint to the exact target bytes. Both
must succeed.

Record the request and response paths, TSA URL, CA bundle path, `gen_time`,
policy OID, and serial number. Set the timestamp state and integrity status to
`verified` only after the OpenSSL verification succeeds. The semantic validator
requires at least one verified RFC 3161 `gen_time` to predate a known outcome.
It validates the declared metadata and chronology but does not parse or verify
the binary `.tsr`; independent verification must run the command above.

RFC 3161 is the only timestamp protocol supported by `1.2.0`. Multiple timestamp
objects may retain independent responses from multiple TSAs.

Keep target artifacts and timestamp evidence permanently and replicate them
outside the Git repository. Keep the `.tsq`, `.tsr`, and CA bundle with the exact
target; none is sufficient alone for portable verification.

## Test vector

`tests/vectors/forecast-seal-v1.json` is deterministic and includes a salt that
contains byte `0x1f`. It guards against delimiter-based parsing regressions.

```bash
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v1.json
```
