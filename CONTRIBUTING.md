# Contributing

Contributions are welcome through GitHub issues and pull requests.

## Contract changes

Every schema change must include:

1. a clear interoperability or validation use case;
2. updated English documentation;
3. at least one valid or invalid fixture that demonstrates the behavior;
4. confirmation that existing valid fixtures still pass;
5. a versioning assessment.

Do not change released schema files in place. Backward-incompatible changes need
a new major contract and permanent `$id`. Security-sensitive changes to
canonicalization, commitment construction, encryption, or timestamp targets also
require a new protocol version and test vectors.

Before the contract has external adopters, a patch release may publish a
normative erratum that corrects reference behavior to match already documented
semantics while retaining the protocol identifier. Such an erratum must freeze
the previous tag, publish exact regression vectors, identify the byte-level
change in its release notes, and must not rewrite the previous release. Once
external evidence depends on the affected behavior, the normal major-version and
new-protocol rule applies instead.

## Development checks

```bash
python -m pip install -r requirements-dev.txt
check-jsonschema --check-metaschema schema/forecast-ledger.schema.json
python tools/run_fixture_tests.py
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v1.json
python tools/forecast_crypto.py verify-vector tests/vectors/forecast-seal-v2.json
python tools/forecast_crypto.py verify-target-vector tests/vectors/forecast-envelope-v2-public-lifecycle.json
python tools/forecast_crypto.py verify-target-vector tests/vectors/forecast-envelope-v2-sealed-lifecycle.json
python tools/run_target_tests.py
python tools/verify_legacy.py
ruff check tools
```

All public field names, code, comments, documentation, examples, issue titles,
and pull-request descriptions must be written in English.
