# USENIX (OSDI / NSDI / ATC) Paper Writing Guidelines

Instructions for writing the paper in the USENIX format used by OSDI, NSDI and ATC. Check the
venue's current call for papers: page limits and formatting rules differ between venues and years.

## General Setup
* **Document class:** `\documentclass[letterpaper,twocolumn,10pt]{article}`
* **Required packages:**
    ```latex
    \usepackage{usenix2019_v3}
    \microtypesetup{protrusion=false}
    \usepackage{amsmath,amssymb}
    \usepackage{graphicx}
    \usepackage{booktabs}
    ```
* `usenix2019_v3.sty` already loads Times, `url`, `cite`, `xcolor` and `hyperref`. Do not load `natbib`.
* Two columns, 10-point Times on 12-point leading, text block 7 x 9 inches. Do not change margins, fonts or spacing.

## Anonymity (double-blind)
* Author line must be exactly `\author{Paper \#XXX (anonymized)}`. No names, affiliations or acknowledgments.
* Refer to the authors' own prior work in the third person. Do not mention repository URLs or the cloud account used.

## Paper Length
* **Main text:** at most **12 pages** including figures and tables.
* **References:** unlimited, after the main text.
* Appendices are allowed after the references but reviewers need not read them; the paper must stand without them.

## Paper Type
* Follow the paper type the idea document states (for example a new system, a measurement study, or an
  experience paper). Do not invent a system name, design components or implementation details that the raw
  materials do not describe.
* State the scope of every claim (hardware, software versions, models, workloads) as the experimental log gives it.

## Abstract
* One paragraph, 150-250 words.

## Citations and References
* Use `\cite{key}` (numeric). Do not use `\citet` or `\citep`.
* Bibliography:
    ```latex
    \bibliographystyle{plain}
    \bibliography{references}
    ```

## Figures and Tables
* All figures are in the `figures` directory. Always include the prefix, e.g.
  `\includegraphics[width=\textwidth]{figures/result.png}`.
* Full-width figures use `figure*`; one-column figures use `\columnwidth`.
* Figures must be legible in black and white.
* Figure captions go below the figure; table captions go above the table.
* Use `booktabs` (`\toprule`, `\midrule`, `\bottomrule`) for tables; no vertical rules.
* Keep tables narrow enough for one column, or use `table*` for full width.

## Numbers and Honesty Rules
* Use only numbers that appear in the experimental log. Do not round in a way that changes a conclusion.
* Capacities are grid points or brackets [pass, fail), not exact values.
* Label simulator and model results as such; they are not measurements.
* Say "pre-registered" only where the log says the prediction was committed before the run.
* Respect the "Do not claim" table in the idea document.

## Important Rules
* Do not modify the text block, font sizes or column layout.
* Page numbers are on (the style file handles this).
* Do not refer to line numbers.
