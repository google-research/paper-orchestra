# Criminology Journal Manuscript Guidelines (APA 7th Edition)

These instructions guide the LaTeX writing process for a manuscript submitted to a peer-reviewed criminology or criminal justice journal that uses APA 7th edition style. They describe common requirements across such journals. **Authors must check their target journal's "Instructions for Authors" and edit this file to match** (word limit, abstract length, blinding rules, and table placement differ between journals).

## Language
All manuscripts must be in English (American spelling by default).

## Peer Review and Anonymity
Review is double-blind (masked). Neither authors nor reviewers know each other's identities.

* The template uses the apa7 `mask` option, which hides author names and affiliations. Do not remove it.
* Do not include names, institutions, grant numbers, data-sharing agreement numbers, or acknowledgments that could identify the authors.
* Refer to the authors' own earlier work in the third person ("Smith (2021) found...", not "In our earlier work...").
* If the data come from a specific agency that would identify the authors, describe it generically (e.g., "a large Midwestern police department").

## Length
* **Total length: about 8,000–10,000 words**, including the abstract, references, tables, and notes (a common limit for full-length criminology articles; check your journal).
* **Abstract: no more than 250 words**, one paragraph, covering Objectives, Methods, Results, and Conclusions.
* **Keywords: 3–5.**
* Page count is not a limit in this format, because the manuscript is double-spaced. Do not shrink fonts, margins, or line spacing to save space; shorten the text instead.

## Required Structure
1. Title page (generated automatically by `\maketitle`; masked for review).
2. Abstract and keywords (in the preamble: `\abstract{...}` and `\keywords{...}`).
3. Introduction (no heading; the title is repeated above it automatically).
4. Literature Review (theory, prior research, and a final subsection "The Current Study" with research questions / hypotheses).
5. Data and Methods (Data; Sample; Measures; Analytic Strategy). Qualitative studies: Data Collection; Analytic Approach.
6. Results.
7. Discussion (including a "Limitations and Future Research" subsection).
8. Conclusion.
9. References (`\printbibliography`; generated automatically in APA 7 style).
10. Appendices (optional, after the references, starting with `\appendix`).

## Formatting (APA 7 manuscript style, handled by the template)
The apa7 class in `man` mode automatically produces the correct layout. Do NOT change it:
* Letter-size page, 1-inch margins on all sides.
* 12-point Times-style font.
* **Double-spaced text throughout** (this is correct and must not be flagged as a formatting problem).
* Paragraphs indented 0.5 inch; left-aligned text with a ragged right margin (not justified).
* Running head with the short title and page numbers in the top margin.
* Headings: Level 1 centered bold; Level 2 flush-left bold; Level 3 flush-left bold italic. Use `\section`, `\subsection`, `\subsubsection`. Headings are NOT numbered.

## Citations and References
* Author–date citations in APA 7 style, using biblatex:
  * Parenthetical: `\parencite{key}` gives (Smith, 2020). Several works: `\parencite{keyA,keyB}` gives (Jones, 2019; Smith, 2020).
  * Narrative: `\textcite{key}` gives Smith (2020).
  * With a page number for a direct quotation: `\parencite[p.~45]{key}`.
* Do not use `\cite{}`, numbered citations, or footnote citations.
* Only cite works that appear in the reference library you are given.
* Direct quotations from published works should be rare; paraphrase instead.

## Tables (APA 7)
* Number tables in the order they are first mentioned and refer to every table in the text (e.g., "Table~\ref{tab:descriptives}").
* The table number and title go **above** the table; the title is italic and in title case (the class does this automatically from `\caption`).
* Use horizontal rules only (`booktabs`); no vertical lines.
* Notes go **below** the table with `\tablenote{...}` inside a `threeparttable`. Explain abbreviations, what the numbers are (b, SE, OR, 95% CI), and significance markers: \* *p* < .05. \*\* *p* < .01. \*\*\* *p* < .001.
* Table 1 normally presents descriptive statistics for all study variables.

```latex
\begin{table}[htbp]
  \caption{Logistic Regression Predicting Rearrest Within 3 Years}
  \label{tab:logit}
  \begin{threeparttable}
  \begin{tabular}{@{}lrrr@{}}
    \toprule
    Variable & \textit{b} & \textit{SE} & \textit{OR} \\
    \midrule
    Program completion & -0.42*** & 0.09 & 0.66 \\
    Age at release & -0.03*** & 0.01 & 0.97 \\
    \bottomrule
  \end{tabular}
  \tablenote{\textit{N} = 2,418. \textit{OR} = odds ratio. *\textit{p} < .05. **\textit{p} < .01. ***\textit{p} < .001.}
  \end{threeparttable}
\end{table}
```

## Figures (APA 7)
* Number and title go **above** the figure (from `\caption`); an optional note goes below with `\figurenote{...}`.
* Figures must be readable in black and white: do not rely on color alone; use line styles or markers too.
* Label axes clearly, with units.
* Use `\includegraphics[width=\linewidth]{figures/...}`. All figures live in the `figures` directory; always include the `figures/` prefix.

```latex
\begin{figure}[htbp]
  \caption{Predicted Probability of Rearrest by Program Participation}
  \label{fig:predicted}
  \includegraphics[width=\linewidth]{figures/fig_predicted_probability.png}
  \figurenote{Shaded areas show 95\% confidence intervals.}
\end{figure}
```

## Statistics (APA 7)
* Italicize statistical symbols: *N*, *n*, *M*, *SD*, *b*, *SE*, *t*, *F*, χ², *p*, *r*, *OR*, *IRR*.
* No leading zero for numbers that cannot exceed 1 (*p* = .032; *r* = .21); use a leading zero otherwise (0.42 years).
* Report exact *p* values to two or three decimals (*p* = .006), except *p* < .001.
* Report confidence intervals as 95% CI [0.52, 0.81].

## Ethics
* State the ethics / Institutional Review Board (IRB) review status, informed consent, and how participants' confidentiality was protected, if the inputs provide this.
* Do not include any information that could identify research participants.

## Language
* Use person-first, non-stigmatizing language ("people in prison", "individuals with a criminal record", "youth involved in the justice system") rather than labels ("inmates", "offenders", "criminals"), unless quoting a legal category or a measure's official name.
* Describe racial, ethnic, and gender differences as observed patterns; do not suggest they reflect inherent traits.

## Important Rules
* Keep the existing document class options and packages unchanged.
* Keep `\printbibliography` at the end of the main text, before any appendix.
* Escape special characters in text: `\%`, `\&`, `\$`, `\#`, `\_`.
* Do not add author names; the manuscript must stay masked.
