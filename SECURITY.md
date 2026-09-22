# Security policy

## Supported version

Only the latest released major version receives security fixes. Historical
v1.3.0 artifacts remain verifiable but do not receive new features. A
cryptographic protocol defect may require a new protocol identifier even when
the surrounding ledger schema remains compatible.

`v2.1.0` is an explicitly commissioned pre-adoption cutover that retains
`forecast-seal/v2` while replacing its exact private-bundle contract and test
vectors. Compatibility with v2.0.x seal bytes is intentionally not provided by
the current tools; use the immutable historical tag to verify historical data.

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
