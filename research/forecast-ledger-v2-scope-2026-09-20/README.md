# Forecast Ledger v2 Scope: Research Report

**Research Date:** 2026-09-20

**Primary Question:** Does Forecast Ledger need the proposed outcome/domain/representation redesign, and which parts belong in the next contract?

**Confidence:** HIGH for the architectural direction; MEDIUM for the exact v2 feature boundary

**Sources:** 13 sources (11 Tier 1, 2 Tier 2), plus direct review of Forecast Ledger v1.3.0

---

## Executive Summary

- Forecast Ledger v1.3.0 is coherent for its original scope: human-authored binary,
  multiple-choice, numeric, and date forecasts with cryptographic existence evidence.
  The proposal does not reveal a defect in that scope; it proposes a materially broader
  product: lossless cross-platform interchange and reproducible scoring.
- Separating the outcome space and domain from the forecast representation is the right
  core change. Hubverse and Zoltar already make essentially this separation, and their
  compatibility matrices show why the current coupling becomes restrictive.
- Versioning only the option set is insufficient. A forecast must bind to an immutable
  **question revision** containing resolution criteria, outcome space, domain, and the
  option set. Both Metaculus and Manifold permit answer sets to evolve.
- `ordered_bins` should not be an outcome-space kind. Bins are normally a representation
  of a numeric, date, or discrete domain. An actually ordinal set of labels is a distinct
  `ordinal` outcome space.
- Decimal-string probabilities are justified for lossless imports, CDFs, PMFs, and exact
  scoring, but only with a canonical lexical form and bounded precision. Otherwise
  semantically equal values such as `"0.5"` and `"0.500"` produce different commitments.
- Explicit tails and interpolation are necessary only for representations that leave the
  distribution between or beyond submitted points undefined. They should not be mandatory
  on scalar probabilities or exhaustive categorical PMFs.
- `ambiguous` is a real missing resolution state. `void` and `not_applicable` should not be
  synonyms: `void` is a no-score resolution disposition; `not_applicable` is the state of a
  conditional branch whose prerequisite did not occur.
- Withdrawal, reaffirmation, and expiry events are required if Forecast Ledger promises to
  reproduce platform scoring or standing-forecast intervals. They are optional if the
  contract remains only an immutable record of submitted forecasts.
- A structural redesign must use `forecast-envelope/v2` and `forecast-seal/v2`. Existing
  v1 vectors and the `v1.3.0` tag must remain byte-for-byte available. Deleting the old tag
  would break the permanent schema URL embedded in existing ledgers.

**Bottom Line:** Start a v2 specification phase, but do not implement the proposal literally
or as one monolithic patch. Adopt the outcome/domain/representation split, immutable question
revisions, typed resolution states, and representation-specific validation in the core;
make relationships, import provenance, and lifecycle events explicit optional profiles.

---

## Research Scope

The review addressed seven questions:

1. Which real platform question types cannot be represented faithfully by v1.3.0?
2. Is separating outcome space, domain, and representation an established design pattern?
3. When are basis points insufficient, and what does an exact decimal encoding require?
4. When are bins, tail masses, and interpolation semantics necessary?
5. Which relationship and resolution states correspond to real platform behavior?
6. Are lifecycle events and platform provenance core ledger concepts or optional profiles?
7. How can a v2 contract preserve the cryptographic meaning of v1 artifacts?

## Current Contract Assessment

Forecast Ledger v1.3.0 currently couples each question type to a limited representation:

| v1.3 question type | Allowed forecast representation | Material limitation |
| --- | --- | --- |
| `binary` | Scalar YES probability in basis points | Cannot retain higher-precision imported probabilities |
| `multiple_choice` | PMF in basis points over the question's current options | Old forecasts become incompatible when the option set changes |
| `numeric` | Point, interval, and/or quantiles | No bounds, discreteness, CDF, bins, or tail semantics |
| `date` | Point, interval, and/or quantiles | No time-of-day outcome and no distribution-grid semantics |

The semantic validator correctly checks PMF totals and category coverage against the current
question, and checks quantile monotonicity. That same design means an option added later makes
an older multiple-choice forecast fail current coverage validation. See the
[schema](../../schema/forecast-ledger.schema.json) and
[semantic validator](../../tools/validate.py).

This is a good model for a stable, author-controlled question. It is not a lossless model for
an evolving external question or a general predictive distribution.

## Key Findings

### 1. The outcome/domain/representation separation is justified

Hubverse separates a target's statistical type from output representations such as mean,
median, quantile, CDF, PMF, and sample. It publishes an explicit compatibility matrix between
target types and output types. Zoltar similarly separates target types (`continuous`,
`discrete`, `nominal`, `binary`, and `date`) from prediction classes (`point`, `bin`,
`sample`, `named`, and `quantile`).

- **Evidence:** [Hubverse task definitions](https://docs.hubverse.io/en/latest/user-guide/tasks.html),
  [Hubverse model output](https://docs.hubverse.io/en/stable/user-guide/model-output.html),
  [Zoltar data model](https://docs.zoltardata.com/datamodel/), and
  [Zoltar validation](https://docs.zoltardata.com/validation/).
- **Confidence:** HIGH.

The proposed separation should therefore be adopted. However, use outcome-space kinds such as
`boolean`, `categorical`, `ordinal`, `numeric`, `date`, and `datetime`. A binned PMF belongs
under forecast representation and references bin definitions over the underlying domain.

### 2. Real platforms expose domain semantics absent from v1.3.0

Metaculus range questions distinguish numeric, discrete, and date outcomes, permit open or
closed bounds, and can resolve outside an open boundary. Manifold numeric markets carry
minimum, maximum, and logarithmic-scale configuration. These properties are needed to
reconstruct what the forecaster was asked and to validate a resolved value.

- **Evidence:** [Metaculus question types](https://www.metaculus.com/faq/#question-types) and
  [Manifold's official API documentation](https://github.com/manifoldmarkets/manifold/blob/main/docs/docs/api.md).
- **Confidence:** HIGH.

Bounds, bound inclusion, allowed values or a discrete step, and units belong in the domain.
`scale` needs narrower naming: a logarithmic slider or market mapping is usually an
**elicitation/display transform**, not a property of the possible outcomes themselves.

### 3. Immutable question revisions are more important than option-set versions alone

Metaculus says multiple-choice options may be added or removed as a question evolves.
Manifold permits answer addition after creation and distinguishes mutually exclusive
multiple-choice markets from independent answer sets. A forecast that merely references a
current question ID cannot prove which options, bounds, or resolution criteria were in force.

- **Evidence:** [Metaculus multiple choice and groups](https://www.metaculus.com/faq/#question-types)
  and [Manifold's create-market/API model](https://github.com/manifoldmarkets/manifold/blob/main/docs/docs/api.md).
- **Confidence:** HIGH.

The core reference should therefore be `question_revision_id`, not only
`option_set_version`. Each immutable revision should bind:

- resolution criteria;
- outcome-space kind;
- domain, including options or bins;
- units and relevant calendar/time-zone semantics;
- the revision's effective or observed time.

An option-set version may still exist as a convenience, but it must not be the only semantic
version boundary.

### 4. Decimal probabilities are useful, but basis points are not the main current defect

Basis points give 0.01 percentage-point resolution. That is already finer than Metaculus's
documented 0.1% to 99.9% binary entry range. However, Manifold's API exposes probabilities
with substantially more decimal precision, and CDF/PMF repositories operate on values in
`[0,1]` rather than basis-point integers. Lossless import and reproducible scoring therefore
justify a decimal representation.

- **Evidence:** [Metaculus forecasting guide](https://www.metaculus.com/how-to-forecast/),
  [Manifold API examples](https://github.com/manifoldmarkets/manifold/blob/main/docs/docs/api.md),
  and [Hubverse model output](https://docs.hubverse.io/en/stable/user-guide/model-output.html).
- **Confidence:** HIGH for imported forecasts; MEDIUM for manually authored forecasts.

RFC 8785 recommends strings for values needing precision beyond IEEE 754, but it also requires
string data to be preserved as-is. Consequently, decimal strings need a contract-level
canonical grammar. The v2 grammar should prohibit leading plus signs, redundant leading or
trailing zeroes, and multiple spellings of the same value, and should impose a defensible
maximum precision.

- **Evidence:** [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html).
- **Confidence:** HIGH.

For consistency, v2 should strongly consider one normalized decimal-string probability type
for all probability-bearing representations, including binary forecasts and quantile levels,
rather than mixing basis points and decimals.

### 5. Bins, tails, and interpolation need representation-specific rules

Zoltar defines bins using ordered inclusive lower bounds and well-defined interval closure.
Hubverse explicitly advises using a CDF rather than a categorical PMF when categories are a
binned discretization of an underlying continuous variable. Metaculus separately scores
probability mass below and above open range bounds.

- **Evidence:** [Zoltar target definitions](https://docs.zoltardata.com/targets/),
  [Hubverse PMF/CDF guidance](https://docs.hubverse.io/en/stable/user-guide/model-output.html),
  and [Metaculus scoring FAQ](https://www.metaculus.com/help/scores-faq/).
- **Confidence:** HIGH.

Recommended semantics:

- exhaustive categorical PMF: no tails; probabilities cover the referenced option set and sum
  exactly to one;
- binned PMF: explicit contiguous intervals with closure rules and optional underflow/overflow
  bins; no separate tail masses if tails are already bins;
- CDF grid: monotone points plus explicit behavior between points and outside the submitted
  range whenever consumers are expected to reconstruct a full CDF;
- quantiles: ordered levels and values; interpolation is required only if the contract claims
  to reconstruct unspecified quantiles or a full distribution;
- credible interval: specify whether it is equal-tailed, central, highest-density, or merely
  author-selected. Coverage alone does not determine its meaning;
- point: specify the elicited functional (`mean`, `median`, `mode`, or `best_estimate`). A bare
  point is ambiguous for scoring.

The last two requirements are missing from the proposal and should be added before designing
fixtures.

### 6. Relationships are real, but group membership and conditioning are different layers

Metaculus supports question groups and conditional pairs. A group is primarily organization
and joint presentation; a conditional relationship changes the semantics and applicability
of a forecast. Manifold also distinguishes exclusive multiple choice from sets of independent
binary answers.

- **Evidence:** [Metaculus groups and conditional pairs](https://www.metaculus.com/faq/#question-groups)
  and [Manifold API market types](https://github.com/manifoldmarkets/manifold/blob/main/docs/docs/api.md).
- **Confidence:** HIGH.

Use separate structures:

- `group_memberships`: non-scoring organization and presentation;
- `condition`: a typed reference to an immutable parent question revision and a parent outcome
  selector.

Acyclicity is necessary for the conditional dependency graph. It should not be implemented as
one generic cycle rule over every relationship kind. Initially, conditional references should
remain within one ledger; cross-ledger DAG validation creates availability and trust problems.

### 7. `ambiguous`, `void`, and `not_applicable` should remain distinct

Metaculus explicitly separates `Ambiguous` (reality is unclear) from `Annulled` (reality may be
clear, but the question is invalid or its assumptions failed). It does not score either. It
also annuls the unused branch of a conditional pair. Manifold exposes `CANCEL` as a resolution
outcome.

- **Evidence:** [Metaculus resolution rules](https://www.metaculus.com/faq/#question-resolution)
  and [Manifold resolution API](https://github.com/manifoldmarkets/manifold/blob/main/docs/docs/api.md).
- **Confidence:** HIGH for `ambiguous`; MEDIUM for a platform-neutral normalized taxonomy.

Recommended normalized model:

- `resolved`: a domain-valid outcome exists;
- `ambiguous`: the real-world outcome cannot be determined reliably;
- `void`: the question is cancelled, invalid, or unscorable, with a required reason code;
- `disputed`: a provisional or contested resolution state;
- `not_applicable`: a conditional branch did not activate. This is not a synonym for an
  intrinsically invalid question.

Preserve the platform's original resolution label in provenance while mapping it to one of
these normalized states.

### 8. Lifecycle events are necessary only when scoring standing forecasts

Metaculus predictions remain active until update or withdrawal, scores depend on how long a
prediction stands, and auto-withdrawal plus reaffirmation create intervals with no active
forecast. Forecast snapshots alone cannot reproduce that scoring history.

- **Evidence:** [Metaculus prediction withdrawal and auto-withdrawal](https://www.metaculus.com/faq/#predictions)
  and [Metaculus scoring FAQ](https://www.metaculus.com/help/scores-faq/).
- **Confidence:** HIGH for Metaculus-compatible scoring; MEDIUM as a universal core feature.

If scoring/import is in scope, add append-only events such as `submitted`, `withdrawn`,
`expired`, and `reaffirmed`, each with effective time, recorded time, actor/source, and
provenance. If scoring is out of scope, keep this as an optional `forecast-lifecycle/v1`
profile rather than burdening every private ledger.

### 9. Platform provenance must preserve evidence, not elevate platform claims to truth

The current `platform_refs` fields identify a service, remote question ID, and URL. A safe
import profile should additionally retain:

- stable provider and remote-object IDs;
- source-reported creation/update/submission times, explicitly marked as source claims;
- retrieval time;
- immutable raw snapshot path, media type, and digest;
- importer name/version and mapping profile;
- normalized question revision produced by that mapping.

Do not store API credentials, expiring authenticated URLs, or treat a platform timestamp as an
independent cryptographic timestamp. This recommendation is an architectural inference from
the ledger's evidence goals, not a claim that the surveyed platforms provide such guarantees.

**Confidence:** HIGH on the evidence boundary; MEDIUM on the exact field layout.

### 10. New semantics require new cryptographic profiles

The current envelope and seal profiles enumerate v1 fields. Adding domain revisions,
relationships, representation semantics, or lifecycle state without changing the profile
would leave security-relevant meaning outside the timestamped/committed bytes.

Use:

- `forecast-envelope/v2`;
- `forecast-seal/v2`;
- new deterministic vectors and negative fixtures;
- an explicit compatibility document.

The v1 canonicalizer, vectors, fixtures, and tagged source must not change. A revealed or sealed
v1 forecast cannot be silently "migrated" and still claim the original v2 semantics; its v1
target remains the historical evidence. A v2 document may reference that legacy evidence and
record a transparent conversion.

**Confidence:** HIGH.

## Proposal Decision Matrix

| Proposed change | Decision | Reason |
| --- | --- | --- |
| Separate outcome space, domain, representation | Adopt in v2 core | Matches mature forecast repositories and removes current coupling |
| `binary`, `categorical`, `numeric`, `date`, `datetime` | Adopt with naming review | Clear domain kinds; retain date/datetime distinction |
| `ordered_bins` as outcome space | Change | Use `ordinal` for ordered labels; bins belong to representation/domain bin definitions |
| Bounds, openness, step/allowed values, unit | Adopt in v2 core | Required for validation and faithful imports |
| `scale` in domain | Relocate or qualify | Usually elicitation/display semantics, not possible-outcome semantics |
| Scalar probability, PMF, quantiles, CDF, point, interval | Adopt as discriminated representations | Established forms; allow compatible multiple representations per forecast |
| Exact decimal-string CDF/PMF probabilities | Adopt, preferably for all v2 probabilities | Needed for lossless import; requires canonical lexical form and precision limit |
| Tail masses | Conditional | Required only where support is not exhaustive or open tails are meaningful |
| Interpolation semantics | Conditional | Required only when reconstructing unspecified points/full distributions |
| Forecast references exact option-set version | Strengthen | Reference the complete immutable question revision |
| PMF/CDF/bin/quantile/domain validation | Adopt | Necessary for semantic interoperability |
| Group and conditional relationships | Optional v2 profile or optional core section | Real use cases, but different semantic weights |
| `ambiguous` | Adopt in core | Directly maps to real platform behavior |
| `void` and `not_applicable` | Adopt as distinct concepts | Cancellation differs from an inactive conditional branch |
| Expiry/withdrawal/reaffirmation events | Adopt only with scoring/import profile | Required to reproduce standing-forecast intervals |
| Safe platform provenance | Adopt with import profile | Required for auditable mappings and raw evidence |
| New envelope/seal profile | Mandatory | New semantic fields must be cryptographically bound |
| Preserve v1 vectors byte-for-byte | Mandatory | Existing hashes and verification claims depend on exact bytes |

## Recommended v2 Architecture

### Core contract

1. **Immutable question revisions**
   - stable `question_id`;
   - immutable `question_revision_id`;
   - criteria, outcome space, domain, and option/bin definitions inside the revision;
   - forecasts and resolutions reference the revision they use.

2. **Outcome space and domain**
   - `boolean`, `categorical`, `ordinal`, `numeric`, `date`, `datetime`;
   - typed bounds and inclusion;
   - numeric discreteness via step or allowed values;
   - units and date/time-zone semantics;
   - elicitation scale separately named.

3. **Forecast representations**
   - an array of uniquely typed representations so one forecast can contain, for example,
     a point plus quantiles without pretending they are different forecasts;
   - `probability`, `pmf`, `binned_pmf`, `quantiles`, `cdf`, `point`, and
     `credible_interval`;
   - representation-specific tail, interpolation, and functional semantics.

4. **Typed resolution**
   - `resolved`, `ambiguous`, `void`, and `disputed`;
   - conditional non-applicability modeled separately;
   - outcome validated against the referenced question revision.

5. **Exact probability type**
   - normalized decimal string in `[0,1]`;
   - exact decimal arithmetic for sums and monotonicity;
   - fixed maximum precision and canonical spelling.

6. **Cryptographic profiles**
   - v2 envelope and seal;
   - domain/revision/representation semantics included in the canonical target;
   - deterministic public, sealed, reveal, and tamper vectors.

### Optional profiles

- **Relationships:** group membership and within-ledger conditional dependencies.
- **Platform import:** raw snapshots, mapping metadata, and source-reported times.
- **Forecast lifecycle:** withdrawal, expiry, and reaffirmation events.
- **Scoring:** declared scoring rule and active intervals, without storing derived aggregate
  scores as source facts.

### Defer until demanded by fixtures

- named parametric distributions;
- raw samples and joint multivariate samples;
- compositional outcomes;
- arbitrary cross-ledger conditional graphs;
- a universal scoring engine;
- free-form extension fields inside cryptographically normative objects.

## Compatibility and Release Decision

The redesign is a major contract change and should be `2.0.0`, potentially preceded by an
experimental `2.0.0-alpha.1` fixture/spec cycle. It should not be a minor update to v1.

Compatibility policy:

| Artifact | Policy |
| --- | --- |
| v1.3 schema and tagged URL | Retain permanently and never move |
| `forecast-envelope/v1` and `forecast-seal/v1` | Freeze |
| Existing v1 vectors | Re-run unchanged in every CI release |
| v1 public forecast conversion | Allow explicit one-way normalized import into v2 |
| v1 sealed forecast | Preserve as legacy evidence; do not claim a converted v2 seal existed historically |
| v2-only representations | No downgrade guarantee |

This policy conflicts with deleting every previous tag when a new release ships. A release may
be removed from the GitHub Releases list to reduce visual clutter, but a tag used in a permanent
schema `$id` must remain reachable. Otherwise existing documents lose their schema and the
published immutability promise becomes false.

## Recommended Next Step

Do not start by editing the JSON Schema. First create a small conformance corpus of real or
faithfully reconstructed cases:

- stable and evolving categorical questions;
- independent-answer sets;
- bounded numeric, open-tail numeric, discrete numeric, date, and datetime questions;
- categorical PMF, binned PMF, quantiles, CDF, point, and interval forecasts;
- ambiguous, void, and conditional-not-applicable resolutions;
- one conditional pair and one non-semantic group;
- imported forecasts with withdrawal and reaffirmation events;
- public and sealed cryptographic vectors.

For every fixture, record which platform behavior it preserves and which scoring operation it
must support. Only fields exercised by this corpus should enter v2 core. This keeps the redesign
grounded and prevents a universal schema from becoming an untestable ontology.

## Areas of Disagreement and Uncertainty

- Existing repositories disagree on supported representations: Zoltar includes named
  distributions and samples, while the proposal does not. Their omission is acceptable unless
  model-forecast hubs are an explicit target.
- Platform UI scale may affect elicited forecasts, but there is no consensus that it belongs to
  the mathematical domain rather than provenance or display metadata.
- There is no universal interpolation rule for sparse CDF or quantile grids. A contract must
  either declare one or explicitly state that unsubmitted points are undefined.
- A platform-neutral mapping among `annulled`, `cancelled`, `void`, and `not_applicable` requires
  a documented normalization table; names alone do not guarantee equivalent scoring behavior.
- The required decimal precision should be selected from the import corpus and threat model,
  not guessed in advance.

## Sources

### Tier 1 — Official and peer-reviewed

- [Metaculus FAQ](https://www.metaculus.com/faq/) — Metaculus, accessed 2026-09-20.
- [How to forecast on Metaculus](https://www.metaculus.com/how-to-forecast/) — Metaculus,
  accessed 2026-09-20.
- [Metaculus Scores FAQ](https://www.metaculus.com/help/scores-faq/) — Metaculus,
  accessed 2026-09-20.
- [Manifold API documentation](https://github.com/manifoldmarkets/manifold/blob/main/docs/docs/api.md)
  — Manifold Markets, accessed 2026-09-20.
- [Hubverse: Defining modeling tasks](https://docs.hubverse.io/en/latest/user-guide/tasks.html)
  — Consortium of Infectious Disease Modeling Hubs, accessed 2026-09-20.
- [Hubverse: Model output](https://docs.hubverse.io/en/stable/user-guide/model-output.html)
  — Consortium of Infectious Disease Modeling Hubs, accessed 2026-09-20.
- [Zoltar data model](https://docs.zoltardata.com/datamodel/) — Reich Lab,
  accessed 2026-09-20.
- [Zoltar targets and domains](https://docs.zoltardata.com/targets/) — Reich Lab,
  accessed 2026-09-20.
- [The Zoltar forecast archive](https://www.nature.com/articles/s41597-021-00839-5)
  — Reich et al., *Scientific Data*, 2021.
- [Strictly Proper Scoring Rules, Prediction, and Estimation](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf)
  — Gneiting and Raftery, *JASA*, 2007.
- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
  — RFC Editor, 2020.

### Tier 2 — Implementation documentation

- [SciPy quantile documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.quantile.html)
  — SciPy project, accessed 2026-09-20; demonstrates that interpolation conventions are not
  unique.
- [scores PIT documentation](https://scores.readthedocs.io/en/latest/tutorials/PIT.html)
  — `scores` project, accessed 2026-09-20; documents one explicit linear-interpolation choice
  for gridded CDF input.

### What was not found

- No widely adopted JSON standard that directly covers human forecasting questions,
  conditional relationships, cryptographic timestamping, and all proposed distribution
  representations in one contract.
- No evidence that every human forecasting ledger needs CDFs, explicit tails, or lifecycle
  events. Their necessity depends on the declared interchange and scoring scope.
