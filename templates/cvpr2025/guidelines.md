# CVPR 2025 Paper Writing Guidelines

Below are the instructions to help you with the latex paper writing process for CVPR 2025.

## Language
All manuscripts must be in English.

## Submission Policies & Anonymity
CVPR reviewing is double-blind. Authors must not know the names of the reviewers, and reviewers must not know the names of the authors.

* **No Identifying Information:** Do not provide information that may identify the authors in the acknowledgments (e.g., co-workers and grant IDs) or in the supplementary material.
* **Links:** Do not provide links to websites that identify the authors.
* **GitHub:** Links to GitHub must be anonymous.
* **Self-Citation:** If you need to cite any of your own papers that are being submitted concurrently, include anonymized versions in the supplementary material and cite them as anonymous. Do not use the words "my" or "our" when citing previous work; treat your own prior work as if it were written by someone else (e.g., "Smith et al. showed..." rather than "We showed...").

## Paper length
Papers, excluding the references section, must be no longer than eight pages in length.
The references section will not be included in the page count, and there is no limit on the length of the references section.
For example, a paper of eight pages with two pages of references would have a total length of 10 pages.

Overlength papers, or papers where margins and formatting are deemed significantly altered, will simply not be reviewed.

## Mathematics
Please number all of your sections and displayed equations as in these examples:
```latex
\begin{equation}
  E = m\cdot c^2
  \label{eq:important}
\end{equation}
```
and
```latex
\begin{equation}
  v = a\cdot t.
  \label{eq:also-important}
\end{equation}
```

## Formatting your paper
All text must be in a two-column format.
The total allowable size of the text area is $6\frac78$ inches (17.46 cm) wide by $8\frac78$ inches (22.54 cm) high.
Columns are to be $3\frac14$ inches (8.25 cm) wide, with a $\frac{5}{16}$ inch (0.8 cm) space between them.
The main title (on the first page) should begin 1 inch (2.54 cm) from the top edge of the page.
The second and following pages should begin 1 inch (2.54 cm) from the top edge.
On all pages, the bottom margin should be $1\frac{1}{8}$ inches (2.86 cm) from the bottom edge of the page for $8.5 \times 11$-inch paper;
for A4 paper, approximately $1\frac{5}{8}$ inches (4.13 cm) from the bottom edge of the page.

### Type style and fonts
Wherever Times is specified, Times Roman may also be used. If neither is available on your word processor, please use the font closest in appearance to Times to which you have access.

### Main Title
Center the title $1\frac{3}{8}$ inches (3.49 cm) from the top edge of the first page. The title should be in Times 14-point, boldface type. Capitalize the first letter of nouns, pronouns, verbs, adjectives, and adverbs; do not capitalize articles, coordinate conjunctions, or prepositions (unless the title begins with such a word).

The ABSTRACT and MAIN TEXT are to be in a two-column format.

### Main Text
Type main text in 10-point Times, single-spaced.
Do NOT use double-spacing.
All paragraphs should be indented 1 pica (approx.~$\frac{1}{6}$ inch or 0.422 cm). Make sure your text is fully justified---that is, flush left and flush right. Please do not place any additional blank lines between paragraphs.

Figure and table captions should be 9-point Roman type as in \cref{fig:onecol,fig:short}. 
Short captions should be centred.

\noindent Callouts should be 9-point Helvetica, non-boldface type. Initially capitalize only the first word of section titles and first-, second-, and third-order headings.

#### First-order Headings
For example, {\large \bf 1. Introduction} should be Times 12-point boldface, initially capitalized, flush left, with one blank line before, and one blank line after.

#### Second-order Headings
For example, { \bf 1.1. Database elements} should be Times 11-point boldface, initially capitalized, flush left, with one blank line before, and one after.
If you require a third-order heading (we discourage it), use 10-point Times, boldface, initially capitalized, flush left, preceded by one blank line, followed by a period and your text on the same line.

### Footnotes
Please use \footnote{This is what a footnote looks like.
It often distracts the reader from the main flow of the argument.} sparingly.

Indeed, try to avoid footnotes altogether and include necessary peripheral observations in the text (within parentheses, if you prefer, as in this sentence). If you wish to use a footnote, place it at the bottom of the column on the page on which it is referenced.
Use Times 8-point type, single-spaced.

### Cross-references
For the benefit of author(s) and readers, please use the
```latex
{\small\begin{verbatim}
  \cref{...}
\end{verbatim}}
```
command for cross-referencing to figures, tables, equations, or sections.

This will automatically insert the appropriate label alongside the cross-reference as in this example:
```latex
\begin{quotation}
  To see how our method outperforms previous work, please see \cref{fig:onecol} and \cref{tab:example}.
  It is also possible to refer to multiple targets as once, \eg~to \cref{fig:onecol,fig:short-a}.
  You may also return to \cref{sec:formatting} or look at \cref{eq:also-important}.
\end{quotation}
```
If you do not wish to abbreviate the label, for example at the beginning of the sentence, you can use the
```latex
{\small\begin{verbatim}
  \Cref{...}
\end{verbatim}}
command. Here is an example:
\begin{quotation}
  \Cref{fig:onecol} is also quite important.
\end{quotation}
```

## Example Code for Tables
```latex
\begin{table}
  \centering
  \begin{tabular}{@{}lc@{}}
    \toprule
    Method & Frobnability \\
    \midrule
    Theirs & Frumpy \\
    Yours & Frobbly \\
    Ours & Makes one's heart Frob\\
    \bottomrule
  \end{tabular}
  \caption{Results.   Ours is better.}
  \label{tab:example}
\end{table}
```

## Example Code for Figures
```latex
\begin{figure}[t]
  \centering
  \fbox{\rule{0pt}{2in} \rule{0.9\linewidth}{0pt}}
   %\includegraphics[width=0.8\linewidth]{egfigure.eps}

   \caption{Example of caption.
   It is set in Roman so that mathematics (always set in Roman: $B \sin A = A \sin B$) may be included without an ugly clash.}
   \label{fig:onecol}
\end{figure}

\begin{figure*}
  \centering
  \begin{subfigure}{0.68\linewidth}
    \fbox{\rule{0pt}{2in} \rule{.9\linewidth}{0pt}}
    \caption{An example of a subfigure.}
    \label{fig:short-a}
  \end{subfigure}
  \hfill
  \begin{subfigure}{0.28\linewidth}
    \fbox{\rule{0pt}{2in} \rule{.9\linewidth}{0pt}}
    \caption{Another example of a subfigure.}
    \label{fig:short-b}
  \end{subfigure}
  \caption{Example of a short caption, which should be centered.}
  \label{fig:short}
\end{figure*}
```

## Illustrations, graphs, and photographs
All graphics should be centered.
In \LaTeX, avoid using the \texttt{center} environment for this purpose, as this adds potentially unwanted whitespace.
Instead use
```latex
{\small\begin{verbatim}
  \centering
\end{verbatim}}
```
at the beginning of your figure.

Please ensure that any point you wish to make is resolvable in a printed copy of the paper. Resize fonts in figures to match the font in the body text, and choose line widths that render effectively in print.

When placing figures in \LaTeX, it's almost always best to use \verb+\includegraphics+, and to specify the figure width as a multiple of the line width as in the example below

```latex
{\small\begin{verbatim}
   \usepackage{graphicx} ...
   \includegraphics[width=0.8\linewidth]
                   {myfile.pdf}
\end{verbatim}}
```

## Color
If you use color in your plots, please keep in mind that a significant subset of reviewers and readers may have a color vision deficiency; red-green blindness is the most frequent kind.
Hence avoid relying only on color as the discriminative feature in plots (such as red \vs green lines), but add a second discriminative feature to ease disambiguation.


## Important Rules 
* DO NOT change `\usepackage[capitalize]{cleveref}` into `\usepackage[capitalize]{cleverref}`, as there's no `cleverref.sty`.
* Keep the existing packages in the template unchanged.
* For consistent compilation across environments, all figures will reside in the `figures` directory. Always include the `figures/` prefix in your `\includegraphics` command. Failing to include this prefix (e.g., using `figure_1.png` instead of `figures/figure_1.png`) will result in figure loading errors during the build process.
* Always use the following author information placeholder in your writeup:
    * Ambitious AI Researcher, AI Research Institute, 123 AI Avenue, ML City, researcher@institute.ai
