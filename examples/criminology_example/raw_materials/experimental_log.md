## Sample
- Full release cohort 2016-2018: N = 14,862.
- Program completers: n = 1,209. Eligible non-participants: n = 13,653.
- After 1:1 matching: 1,209 completers and 1,209 matched comparisons (analytic N = 2,418). 0 completers dropped for lack of common support.
- Missing data: 3.1% missing on prior education; handled with multiple imputation (20 imputations) before matching.

## Balance After Matching (standardized mean difference, before -> after)
| Covariate | Before | After |
|---|---|---|
| Age at release | 0.31 | 0.02 |
| Risk-assessment score | -0.44 | -0.03 |
| Prior arrests | -0.38 | 0.04 |
| Violent offense | 0.12 | 0.01 |
| High school diploma/GED at admission | 0.52 | 0.05 |
All post-matching SMDs < 0.10.

## Descriptive Statistics (matched sample, N = 2,418)
| Variable | Completers | Comparison |
|---|---|---|
| Age at release, M (SD) | 34.8 (9.7) | 34.6 (10.1) |
| Male, % | 88.4 | 88.9 |
| Black, % | 41.2 | 40.7 |
| Hispanic, % | 14.6 | 15.0 |
| White, % | 41.9 | 42.0 |
| Prior arrests, M (SD) | 6.2 (4.9) | 6.4 (5.1) |
| Employed in first year after release, % | 61.3 | 48.7 |
| Rearrested within 36 months, % | 33.5 | 42.6 |

## Main Results
### Cox proportional hazards model: time to first rearrest (N = 2,418)
- Program completion: HR = 0.74, 95% CI [0.66, 0.83], p < .001.
- Age at release (per year): HR = 0.97, 95% CI [0.96, 0.98], p < .001.
- Prior arrests (per arrest): HR = 1.05, 95% CI [1.04, 1.06], p < .001.
- Proportional hazards assumption: Schoenfeld residual global test p = .21.

### Logistic regression: any rearrest within 36 months (N = 2,418)
- Program completion: b = -0.39, SE = 0.08, OR = 0.68, 95% CI [0.58, 0.80], p < .001.
- Average marginal effect of completion: -8.9 percentage points.
- Nagelkerke pseudo-R² = .11.

## Mediation (KHB method)
- Total effect of completion (log-odds): -0.39.
- Direct effect controlling for first-year employment: -0.31.
- Indirect effect through employment: -0.08 (p = .002); about 21% of the total association.

## Robustness Checks
- Caliper 0.05 SD: n = 1,174 pairs; HR = 0.75, 95% CI [0.67, 0.85].
- Rosenbaum sensitivity analysis: result stays significant at p < .05 up to Gamma = 1.35.

## Subgroups (HR for completion)
- Under 30 at release: HR = 0.69, 95% CI [0.57, 0.83].
- 30 and older: HR = 0.79, 95% CI [0.68, 0.91].
- Interaction test: p = .27 (difference not statistically significant).
