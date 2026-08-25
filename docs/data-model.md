# Data model

Forecast Ledger v1 stores quantitative forecasts made by one forecasting
identity. The identity may be one person or a named team, but a single ledger
never mixes independent track records.

## Design principles

1. **Record forecasts before outcomes.** `forecasted_at` is self-reported;
   cryptographic timestamps establish the stronger "existed no later than"
   bound.
2. **Append updates.** A changed probability is a new forecast with
   `supersedes_forecast_id`. Old forecast statements remain intact in Git
   history and in their timestamp targets.
3. **Separate source facts from derived metrics.** Outcomes and their evidence
   are stored. Brier scores, calibration curves, lifecycle age, and rankings are
   computed by consumers.
4. **Use exact quantitative encodings.** Probabilities are integer basis points
   and numeric quantities are exact decimal strings. Floating-point JSON values
   are not used in forecast commitments.

## Root document

| Field | Purpose |
| --- | --- |
| `schema_version` | Exact contract version. v1 requires `1.0.0`. |
| `ledger_id` | Stable identifier for this track record. |
| `forecaster` | One individual or team identity. |
| `publication` | Optional Git repository and ledger location. |
| `platforms` | Reusable platform/account registry. |
| `questions` | Questions, forecast updates, and eventual resolutions. |

## Forecaster identity

`forecaster.kind` is either `individual` or `team`. A team has at least two
members, but the team remains one scoring identity.

## Questions and lifecycle

Every question has precise resolution criteria, a forecast window, an expected
resolution time, and a self-reported status:

- `open`
- `closed`
- `awaiting_resolution`
- `resolved`
- `annulled`
- `disputed`

Resolved, annulled, and disputed questions carry a matching `resolution`
object. The Git history makes status changes auditable. A `resolved` record
separates `outcome_known_at` from `recorded_at` and requires at least one source.

## Forecast values

### Binary

`probability_bp` is the probability of YES in basis points. `6200` means 62%.

### Multiple choice

Options have stable IDs and display labels. Forecast probabilities reference
the IDs, cover every option exactly once, and sum to 10,000. The cross-record
validator enforces the coverage and sum.

### Numeric

Point estimates, intervals, and quantiles use exact decimal strings. The unit is
declared on the question. Quantile probabilities and interval credibility use
basis points.

### Date

Date forecasts use ISO `YYYY-MM-DD` values with the same point, interval, and
quantile structure as numeric forecasts.

## Visibility

- `public`: the quantitative value is present in plaintext;
- `sealed`: the value and reasoning exist only inside `forecast-seal/v1`;
- `revealed`: ciphertext is retained, the key is disclosed, and the plaintext
  mirror is checked against decryption.

See [cryptographic-verification.md](cryptographic-verification.md) for the seal
and timestamp protocols. See
[forecast-verification-workflows.md](forecast-verification-workflows.md) for
the complete author and verifier call order.
