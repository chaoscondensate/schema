# Security policy

## Supported version

Only the latest released major version receives security fixes. Historical
v1.3.0 artifacts remain verifiable but do not receive new features. A
cryptographic protocol defect may require a new protocol identifier even when
the surrounding ledger schema remains compatible.

`v2.2.0` is an explicitly commissioned pre-adoption cutover that introduces
`forecast-seal/v3`, `forecast-key/v3`, `forecast-envelope/v3`, and
`forecast-lifecycle/v2`. Compatibility with earlier ledger, key, seal, target,
or package bytes is intentionally absent; use the exact immutable historical
tag and historical tools to inspect historical data.

Protected key files, raw keys, salts, plaintext, credentials, and protected
paths must never enter logs, normal output, evidence indexes, publication
packages, or unrestricted diagnostics. A public `key_hint` is only an opaque
logical hint and must not contain a credential or filesystem location.

Validator diagnostics expose JSON Pointers and bounded source locations only.
They must not include protected values, surrounding source text, credentials,
keys, salts, decrypted plaintext, or unrestricted local filesystem paths.

Lifecycle checkpoints prove integrity and external timing only for the retained
prefix and evidence package. They cannot prove that a deleted event existed if
all ledger records, checkpoints, target artifacts, packages, and external
copies have also been deleted.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could permit a forecast to
be altered, opened ambiguously, revealed early, falsely timestamped, or accepted
without valid evidence. Use the repository's private GitHub Security Advisory
flow and include:

- the affected schema or protocol version;
- a minimal reproducer or test vector;
- the claimed and actual security behavior;
- any known affected published ledgers.

No cryptographic reference code in this repository has undergone an independent
security audit. Treat it as an interoperability reference, not a substitute for
a reviewed production key-management system.
