#!/usr/bin/env python3
"""
Generates a LaTeX table (booktabs) comparing RKO with and without the cut pool,
from the summary.csv of an experiment folder (produced by run_experiment_cuts.py).
The table is written to table_cuts.tex in the same folder.

Melhor is the best (lowest) objective value over the runs and Média the mean one
(as reported by RKO, minimization); in each row the lower Melhor and the lower Média
are in bold. Tempo is the mean time to find the best solution.

Usage (from the Scripts folder):
  python3 make_table_cuts.py                  # most recent ../Results/experiment_cuts_* folder
  python3 make_table_cuts.py ../Results/experiment_cuts_2026-10-07_14-30-00
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent.parent / "Results"


def fmt_time(t):
    return r"$\leq 0.01$" if t < 0.01 else f"{t:.2f}"


def fmt_ofv(v, bold):
    s = f"{v:.1f}"
    return rf"\textbf{{{s}}}" if bold else s


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, nargs="?", default=None,
                        help="experiment folder (default: the most recent one in ../Results)")
    args = parser.parse_args()

    folder = args.folder
    if folder is None:
        # names carry the date and time, so the lexicographic max is the most recent
        folders = sorted(RESULTS_DIR.glob("experiment_cuts_*/"))
        if not folders:
            sys.exit(f"ERROR: no experiment_cuts_* folder in {RESULTS_DIR}")
        folder = folders[-1]
    output = folder / "table_cuts.tex"

    df = pd.read_csv(folder / "summary.csv")
    df["name"] = df["instance"].map(lambda p: Path(p).stem.replace("_", r"\_"))

    table = df.pivot(index=["n", "name"], columns="variant",
                     values=["ofv_best", "ofv_mean", "time_best_mean"]).sort_index()

    rows = []
    for (n, name), r in table.iterrows():
        best_o, best_c = r[("ofv_best", "original")], r[("ofv_best", "cuts")]
        orig, cuts = r[("ofv_mean", "original")], r[("ofv_mean", "cuts")]
        rows.append(f"{name} & {n} & {fmt_ofv(best_o, best_o <= best_c)} & "
                    f"{fmt_ofv(orig, orig <= cuts)} & "
                    f"{fmt_time(r[('time_best_mean', 'original')])} & "
                    f"{fmt_ofv(best_c, best_c <= best_o)} & "
                    f"{fmt_ofv(cuts, cuts <= orig)} & "
                    f"{fmt_time(r[('time_best_mean', 'cuts')])} \\\\")

    latex = "\n".join([
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Resultados -- RKO com e sem pool de cortes (instâncias 00Uncorrelated)}",
        r"\label{tab:cuts}",
        r"\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r" & & \multicolumn{3}{c}{\textbf{RKO original}} & \multicolumn{3}{c}{\textbf{RKO + cortes}} \\",
        r"\cmidrule(lr){3-5} \cmidrule(lr){6-8}",
        r"Instância & $n$ & Melhor & Média & Tempo (s) & Melhor & Média & Tempo (s) \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    output.write_text(latex + "\n")
    print(latex)
    print(f"\n% written to {output}")


if __name__ == "__main__":
    main()
