## Research Problem
Many people released from state prison are rearrested within three years. Prison-based college education programs are expanding again in the United States, but the evidence on whether they reduce rearrest is mixed. Many earlier evaluations compared volunteers with non-volunteers, so differences in motivation or risk (selection bias) could explain their results.

## Theoretical Framework
- **Desistance / life-course perspective:** turning points such as stable employment can help people stop offending.
- **Human capital:** education raises skills and employability, which may increase legal earnings and reduce the appeal of crime.
- **Social bonds (informal social control):** a job and pro-social ties create "stakes in conformity".

## Research Questions and Hypotheses
- RQ1: Is completing a prison college program associated with a lower risk of rearrest within 36 months of release?
- H1: Program completers will have a lower hazard of rearrest than matched non-participants.
- RQ2: Does post-release employment partly account for (mediate) this relationship?
- H2: Being employed in the first post-release year will partly explain the lower rearrest risk among completers.

## Data
- Administrative records from the (fictional) Midland State Department of Corrections, linked to state arrest records and state unemployment-insurance wage records.
- Release cohort: all people released from Midland State prisons between 2016 and 2018, followed for 36 months.

## Design and Analytic Plan
- Treatment: completed at least one semester of the in-prison college program.
- Comparison group: built with 1:1 nearest-neighbor propensity score matching (caliper 0.1 SD) on age, sex, race/ethnicity, risk-assessment score, prior arrests, offense type, sentence length, and prior education.
- Balance checked with standardized mean differences (target < 0.10).
- Outcome: time to first rearrest (Cox proportional hazards model). Secondary: any rearrest within 36 months (logistic regression).
- Mediation: employment in the first post-release year (any quarterly UI wages), tested with the Karlson–Holm–Breen (KHB) method.
- Robustness: Rosenbaum sensitivity analysis for hidden bias; alternative caliper (0.05).

## Ethics
The study used de-identified administrative records under a data-sharing agreement and was reviewed by a university Institutional Review Board (exempt determination). No direct contact with participants.
