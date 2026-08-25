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
- existence timing: a timestamp proves that a precise envelope existed no later
  than the timestamp's external anchor;
- portable verification: the Git host is not required once artifacts and
  receipts are downloaded.

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
`public_forecast_envelope()`. Exclude `integrity`; adding a receipt after
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
6. verifies the timestamp target and receipt.

## Timestamp workflow

Generate exact target artifacts:

```bash
python tools/build_targets.py ledger.yaml --output proofs/targets
```

For each report entry, copy the artifact path and digest into `integrity.target`.
Then create an OpenTimestamps receipt:

```bash
ots stamp proofs/targets/f-example-001.json
```

Set `integrity.status` to `pending` and record the `.ots` receipt. After Bitcoin
confirmation:

```bash
ots upgrade proofs/targets/f-example-001.json.ots
ots verify proofs/targets/f-example-001.json.ots
```

Set the OTS state to `confirmed`, record the reported upper time bound and block
height, and set integrity to `verified`. The validator rejects a verified
forecast whose confirmed timestamp does not predate a known outcome.

An RFC 3161 receipt may be stored alongside OTS for immediate independent
timestamping. OTS remains mandatory for `pending` and `verified` integrity
states in v1.

Keep target artifacts and timestamp receipts permanently and replicate them
outside the Git repository. A receipt without its exact target is insufficient.

## Test vector

`tests/vectors/forecast-seal-v1.json` is deterministic and includes a salt that
contains byte `0x1f`. It guards against delimiter-based parsing regressions.

```bash
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v1.json
```
