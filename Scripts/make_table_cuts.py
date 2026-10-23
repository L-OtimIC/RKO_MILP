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


def fmt_ofv(v, bold, decimals=1):
    s = f"{v:.{decimals}f}"
    return rf"\textbf{{{s}}}" if bold else s


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, nargs="?", default=None,
                        help="experiment folder (default: the most recent one in ../Results)")
    parser.add_argument("--sensitivity", action="store_true",
                        help="table of a --sensitivity experiment (adds the MAXTIME of each "
                             "variant), written to table_sensitivity.tex")
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

    if args.sensitivity:
        write_sensitivity_table(df, folder / "table_sensitivity.tex")
        return

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


def write_sensitivity_table(df, output):
    """Like the main table, plus the MAXTIME of each variant: the cuts variant runs with a
    large MAXTIME and the original gets the mean time to best of the cuts variant."""
    table = df.pivot(index=["n", "name"], columns="variant",
                     values=["maxtime", "ofv_best", "ofv_mean", "time_best_mean"]).sort_index()

    rows = []
    for (n, name), r in table.iterrows():
        best_o, best_c = r[("ofv_best", "original")], r[("ofv_best", "cuts")]
        orig, cuts = r[("ofv_mean", "original")], r[("ofv_mean", "cuts")]
        # the best values are integers, so they are printed without decimals to save width
        rows.append(f"{name} & {n} & "
                    f"{int(r[('maxtime', 'cuts')])} & {fmt_ofv(best_c, best_c <= best_o, 0)} & "
                    f"{fmt_ofv(cuts, cuts <= orig)} & {fmt_time(r[('time_best_mean', 'cuts')])} & "
                    f"{int(r[('maxtime', 'original')])} & {fmt_ofv(best_o, best_o <= best_c, 0)} & "
                    f"{fmt_ofv(orig, orig <= cuts)} & {fmt_time(r[('time_best_mean', 'original')])} \\\\")

    # factor of the cuts MAXTIME over the default max(5, n/100), if the same for all instances
    cuts = df[df["variant"] == "cuts"]
    factors = set(round(t / max(5, n // 100), 2) for n, t in zip(cuts["n"], cuts["maxtime"]))
    cap = f"{factors.pop():g}$\\times$ o padrão" if len(factors) == 1 else "elevado"
    mhs = df["mh"].unique() if "mh" in df else ["all"]
    method = "RKO" if list(mhs) == ["all"] else f"{mhs[0]} (1 thread)"
    runs = int(df["runs"].iloc[0])

    latex = "\n".join([
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        r"\setlength{\tabcolsep}{3pt}",
        rf"\caption{{Teste de sensibilidade -- {method}, {runs} execuções por instância "
        rf"(00Uncorrelated). A versão com cortes roda com $T_{{\max}}$ {cap}; a original recebe "
        rf"como $T_{{\max}}$ o tempo médio $\bar{{t}}$ que a versão com cortes levou para "
        rf"encontrar sua melhor solução.}}",
        r"\label{tab:sensitivity}",
        # shrinks the table only if it is still wider than the text (needs \usepackage{graphicx})
        r"\resizebox{\ifdim\width>\textwidth\textwidth\else\width\fi}{!}{%",
        r"\begin{tabular}{lrrrrrrrrr}",
        r"\toprule",
        rf" & & \multicolumn{{4}}{{c}}{{\textbf{{{method.split()[0]} + cortes}}}} & "
        rf"\multicolumn{{4}}{{c}}{{\textbf{{{method.split()[0]} original}}}} \\",
        r"\cmidrule(lr){3-6} \cmidrule(lr){7-10}",
        r"Inst. & $n$ & $T_{\max}$ (s) & Melhor & Média & $\bar{t}$ (s) & "
        r"$T_{\max}$ (s) & Melhor & Média & $\bar{t}$ (s) \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
        r"\end{table}",
    ])

    output.write_text(latex + "\n")
    print(latex)
    print(f"\n% written to {output}")


if __name__ == "__main__":
    main()
