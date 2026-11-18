# NeurIPS 2025 Paper Writing Guidelines

Below are the instructions to help you with the LaTeX paper writing process for NeurIPS 2025.

## General Setup
* **Document Class:** `\documentclass{article}`
* **Style File:** `\usepackage{neurips_2025}` — the official NeurIPS 2025 style file.
    * Default (no option): submission mode, double-blind, anonymized.
    * `[preprint]`: non-anonymous version suitable for arXiv.
    * `[final]`: camera-ready version, with author names shown.
* **Bibliography:** `natbib` is loaded by the style file, so use `\citep{}` and `\citet{}`. Author-year references are expected; `\bibliographystyle{plainnat}` is used in the template.
* **Do not** load `fullpage` or otherwise change the text area; the style file overwrites it and warns.

## Language
All manuscripts must be in English.

## Submission Policies & Anonymity
NeurIPS main-track reviewing is double-blind.

* **No Identifying Information:** Do not name authors, institutions, or funding in the submission version, including in the acknowledgments, the appendix, or figure captions.
* **Links:** Do not link to websites, repositories, or demos that identify the authors. Use an anonymized repository (e.g. anonymous.4open.science) if code must be shared.
* **Self-Citation:** Cite your own prior work in the third person, exactly as you would cite anyone else's (e.g. "Song et al. showed..." rather than "We showed...").
* **Author Block:** Always use the anonymous placeholder author information in `template.tex`.

## Paper Length
* **Main text:** at most **nine content pages**, including all figures and tables.
* **Not counted:** pages containing only references, the NeurIPS Paper Checklist, and the optional technical appendices.
* **Camera-ready:** one additional content page is allowed after acceptance.
* **Total file size:** the submission PDF must be at most 50 MB.
* Overlength papers, or papers with altered margins or font sizes, may be rejected without review.

## Required: NeurIPS Paper Checklist
* Every submission **must** end with the NeurIPS Paper Checklist, after the references and any appendix. Papers without it are desk rejected.
* The checklist does **not** count towards the page limit.
* Answer each of the 16 questions with `\answerYes{}`, `\answerNo{}`, or `\answerNA{}`, and add a 1–2 sentence justification for every answer, including NA.
* **Do not modify the questions.** Only the provided answer macros may be used.
* `\answerTODO{}` and `\justificationTODO{}` mark answers that still need to be written. They are left in the template on purpose: the answers depend on facts about the research that only the authors know, so they must not be invented.

## Formatting
* **Paper size:** US Letter. Text block is 5.5 in wide by 9 in tall, centered, with a single column.
* **Fonts:** Times 10 pt body, 11 pt leading, justified, no first-line indent; paragraphs are separated by a 5.5 pt skip.
* **Title:** 17 pt bold, centered, with a rule above and below.
* **Section headings:** flush left, bold, Arabic-numbered. References, Acknowledgments, and the Paper Checklist are unnumbered (`\section*{}`).
* **Page numbers:** the style file adds them; do not add your own.
* Do not use the `\thanks` command, and do not add a separate title page.

## Mathematics
Number displayed equations that are referred to in the text:
```latex
\begin{equation}
  \mathcal{L} = \mathbb{E}_{x \sim p}\left[\log p_\theta(x)\right]
  \label{eq:objective}
\end{equation}
```

## Figures and Tables
* Figures and tables must be readable in print. Do not rely on colour alone to distinguish curves; add line styles or markers as a second cue.
* Use `booktabs` rules in tables (no vertical rules).
* For consistent compilation across environments, all figures will reside in the `figures` directory. Always include the `figures/` prefix in your `\includegraphics` command (e.g. `figures/figure_1.pdf`).

## Optional Statements
These appear at the end of the main text, before the references, and count towards the page limit.
1. **Broader Impact:** not required as a separate section, but any discussion of societal impact must fit inside the nine pages.
2. **Limitations:** encouraged, and referenced by the checklist.

## Important Rules
* **Keep the existing packages in the template unchanged.**
* Do not change the width or length of the text rectangle or any font size.
* Do not refer to line numbers in your text; the style file adds them automatically for review.
* Use `\appendix` for supplementary material included in the same PDF.
* Always use the following author information placeholder in your writeup:
    * Ambitious AI Researcher, AI Research Institute, 123 AI Avenue, ML City, researcher@institute.ai
