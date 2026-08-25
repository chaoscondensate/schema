# Security policy

## Supported version

Only the latest released major version receives security fixes. A cryptographic
protocol defect may require a new protocol identifier even when the surrounding
ledger schema remains compatible.

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
