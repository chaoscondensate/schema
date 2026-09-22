# v1.3.0 to v2 compatibility

## Decision

Forecast Ledger v2 is a new incompatible contract. v1.3.0 documents remain
valid only against the v1.3.0 schema URL. Consumers must not relabel a v1
document as v2 or infer missing v2 semantics.

The `v1.3.0` Git tag, schema bytes, and seal vector are permanent. The current
repository tools verify historical `forecast-seal/v1` vectors but generate v2
envelopes for v2 ledgers.

## Why a major version was required

| Area | v1.3.0 | v2.0.x | Compatibility |
| --- | --- | --- | --- |
| Question definition | Mutable fields on question | Ordered immutable revisions | Breaking |
| Forecast binding | Question ID | Exact question revision | Breaking |
| Outcome kinds | Binary, multiple choice, numeric, date | Binary, categorical, ordinal, numeric, date, datetime | Breaking |
| Probability | Integer basis points | Canonical decimal string | Breaking |
| Forecast value | Type-specific `value` object | Array of independent representations | Breaking |
| Option identity | Unversioned question options | Versioned option set referenced by PMF | Breaking |
| Bins and tails | Not represented | Versioned bins plus explicit tail mass | New semantics |
| Distribution semantics | Point/interval/quantiles | PMF, bins, quantiles, CDF, point, credible intervals | Breaking |
| Resolution | Resolved, annulled, disputed | Resolved, ambiguous, void, disputed, not applicable | Breaking |
| Provenance | Loose platform references | Versioned object provenance and optional snapshot digest | Breaking |
| Relationships | None | Groups and acyclic conditional dependencies | New semantics |
| Seal | `forecast-seal/v1` | `forecast-seal/v2` with revision binding | Breaking |
| Timestamp target | `forecast-envelope/v1` | `forecast-envelope/v2` with full revision | Breaking |

## Migration rules

Migration is explicit and should produce a new v2 file. Keep the original v1
file and its timestamp artifacts unchanged.

1. Create one v2 question revision from the v1 question fields.
2. Preserve v1 `created_at` as the revision's `effective_at` and use a truthful
   migration time for `recorded_at` unless original recording time is known.
3. Convert binary basis points exactly: `6200` becomes `"0.62"`.
4. Convert multiple-choice probabilities to a PMF and create option-set version
   1. Preserve option IDs and order.
5. Convert numeric/date point, interval, and quantile fields into separate v2
   representations. Record the interval semantic explicitly; if it cannot be
   inferred, use `author_selected` and document the migration decision.
6. Bind every migrated forecast to the created revision.
7. Map `annulled` to `void` only when that matches the original reason; otherwise
   require human review.
8. Preserve source URLs and outcome evidence.
9. Do not convert a v1 seal or target into v2. It remains verifiable under v1.
10. If migrated v2 content needs a v2 timestamp, create a new v2 envelope and
    timestamp it; never imply that this new token dates the original v1 forecast.

## Loss indicators requiring human review

An automated migration must stop or emit an explicit review item when:

- the historical question wording or options changed without preserved versions;
- a numeric interval's meaning is unknown;
- source probability precision was already rounded to basis points;
- a platform option cannot be mapped to one stable option ID;
- date/time timezone semantics are missing;
- `annulled` does not clearly mean `void`;
- a forecast refers to a question state that cannot be reconstructed.

## Consumer support policy

Consumers should select behavior from `schema_version`, not feature detection.
Supporting v1.3.0 and v2.1.0 means validating each document against its own
permanent schema and using the matching envelope/seal profile. There is no
mixed-version ledger and no v2 envelope around a v1 forecast.

## v2.0.1 normative erratum

v2.0.1 corrects the `forecast-envelope/v2` projection so append-only
`lifecycle_events` are outside both public and sealed timestamp targets. The
events change derived active state, not the recorded belief. No ledger field or
`forecast-seal/v2` byte changes.

The v2.0.0 tag remains immutable. Verification of an artifact explicitly
created under v2.0.0 uses that exact tagged contract. The current reference
tools implement only the corrected v2.0.1 projection; they do not add a dual
projection or automatic conversion path.

## v2.1.0 pre-adoption cutover

v2.1.0 is intentionally incompatible with v2.0.x and provides no converter or
compatibility bundle. A client importing v2.1.0 must update schema, semantic
validator, target builder, crypto implementation, vectors, and diagnostics as
one exact contract release.

The cutover adds `forecast-lifecycle/v1`, forecast activity checkpoints, and
forecast-relative lifecycle chronology. It also changes the closed
`forecast-seal/v2` private bundle: only non-empty `representations` is required;
`rationale`, `key_factors`, and `comment` are independently optional and their
presence is authenticated. Earlier `forecast-seal/v2` ciphertext is verified
only with its exact v2.0.x tagged implementation.

All prior tags remain immutable. Do not relabel a v2.0.x document, seal,
envelope, or evidence package as v2.1.0.

## Frozen legacy verification

The legacy manifests record expected hashes for v1.3.0, v2.0.0, and v2.0.1
schema, vector, and reference implementation artifacts. Run:

```bash
python tools/verify_legacy.py
```

The command reads those files directly from their Git tags and rejects any byte
change or tag loss. The release workflow runs this check before publication.
