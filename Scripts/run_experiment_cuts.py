#!/usr/bin/env python3
"""
Experiment: RKO with and without the cut pool (--cuts) on the 00Uncorrelated KP instances.

For each instance and variant, runs ./runRKO once (MAXRUNS runs inside, each with its own
clock-based seed) and reads the line RKO appends to ../Results/Results_RKO[_cuts].csv.

Outputs (in a new folder ../Results/experiment_cuts_YYYY-MM-DD_HH-MM-SS):
  summary.csv : one line per (instance, variant) with mean/std of the FO
  runs.csv    : one line per run with the individual FO values

Requirements in config/config_tests.conf: debug 0 and MAXRUNS 30.
An interrupted experiment can be resumed with --resume <folder>: (instance, mh, variant)
triples already in its summary.csv are skipped.

With --mh, each listed metaheuristic is run alone (RKO uses one thread per MH in the
config, so this is the single-thread setting): the config file is rewritten for each
job with only that MH (and MAXRUNS from --runs) and restored at the end.

Usage (from the Scripts folder, after `make clean && make` in Program):
  python3 run_experiment_cuts.py              # MAXTIME = max(5, n/100) seconds
  python3 run_experiment_cuts.py --time 30    # fixed MAXTIME
  python3 run_experiment_cuts.py --resume ../Results/experiment_cuts_2026-10-07_14-30-00
  python3 run_experiment_cuts.py --mh all --runs 10   # each MH of the config alone
  python3 run_experiment_cuts.py --mh BRKGA SA --runs 10
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
PROGRAM_DIR = ROOT_DIR / "Program"
INSTANCES_DIR = ROOT_DIR / "Instances" / "KP" / "00Uncorrelated"
RESULTS_DIR = ROOT_DIR / "Results"
CONFIG_FILE = PROGRAM_DIR / "config" / "config_tests.conf"

VARIANTS = {"original": [], "cuts": ["--cuts"]}
ALL_MHS = ["BRKGA", "SA", "GRASP", "ILS", "VNS", "PSO", "GA", "LNS", "BRKGA-CS",
           "MultiStart", "IPR"]


def read_config():
    """Returns the integer parameters (MAXRUNS, debug, ...) of the RKO config file."""
    params = {}
    for line in CONFIG_FILE.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            params[parts[0]] = int(parts[1])
    return params


def config_mhs(text):
    """Metaheuristics listed in the config file, in order."""
    return [l.strip() for l in text.splitlines() if l.strip() in ALL_MHS]


def single_mh_config(text, mh, max_runs):
    """Config text with only `mh` as metaheuristic and MAXRUNS = max_runs."""
    out, inserted = [], False
    for line in text.splitlines():
        if line.strip() in ALL_MHS:
            if not inserted:
                out.append(mh)
                inserted = True
        elif line.split()[:1] == ["MAXRUNS"]:
            out.append(f"MAXRUNS {max_runs}")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def instance_size(path):
    # first token of the file (some instances start with a blank line)
    with open(path) as f:
        return int(f.read(64).split()[0])


def read_last_result(results_file):
    """Parses the last line of Results_RKO*.csv:
    instance \t MHs \t nRuns \t ofv_1..ofv_n \t best \t avg \t timeBest \t timeTotal"""
    lines = [l for l in results_file.read_text().splitlines() if l.strip()]
    fields = lines[-1].split("\t")
    n_runs = int(fields[2])
    ofvs = [float(x) for x in fields[3:3 + n_runs]]
    return fields[0], ofvs, float(fields[-2]), float(fields[-1])


def append_csv(df, path):
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--time", type=int, default=None,
                        help="fixed MAXTIME in seconds (default: max(5, n/100))")
    parser.add_argument("--resume", type=Path, default=None,
                        help="experiment folder to resume (default: create a new one)")
    parser.add_argument("--mh", nargs="+", default=None,
                        help="run each of these MHs alone (single thread); 'all' = every MH "
                             "in the config (default: all MHs of the config together)")
    parser.add_argument("--runs", type=int, default=None,
                        help="MAXRUNS used with --mh (default: MAXRUNS of the config)")
    args = parser.parse_args()

    config = read_config()
    if config.get("debug", 1) != 0:
        sys.exit(f"ERROR: set 'debug 0' in {CONFIG_FILE} (debug 1 fixes the seed and writes no results)")
    original_config = CONFIG_FILE.read_text()

    if args.mh is None:
        if args.runs is not None:
            sys.exit("ERROR: --runs requires --mh")
        mhs = [None]   # all MHs of the config, in parallel
        max_runs = config.get("MAXRUNS", 0)
        if max_runs != 30:
            print(f"WARNING: MAXRUNS = {max_runs} in {CONFIG_FILE} (expected 30)")
    else:
        mhs = config_mhs(original_config) if args.mh == ["all"] else args.mh
        unknown = [m for m in mhs if m not in ALL_MHS]
        if unknown:
            sys.exit(f"ERROR: unknown MH(s) {unknown}, options: {ALL_MHS}")
        max_runs = args.runs if args.runs is not None else config.get("MAXRUNS", 0)

    if not (PROGRAM_DIR / "runRKO").exists():
        sys.exit("ERROR: ./runRKO not found, run `make` first")

    if args.resume is not None:
        out_dir = args.resume
        if not out_dir.is_dir():
            sys.exit(f"ERROR: {out_dir} not found")
    else:
        out_dir = RESULTS_DIR / datetime.now().strftime("experiment_cuts_%Y-%m-%d_%H-%M-%S")
        out_dir.mkdir(parents=True)
    summary_file = out_dir / "summary.csv"
    runs_file = out_dir / "runs.csv"
    print(f"Output folder: {out_dir}")

    done = set()
    if summary_file.exists():
        summary = pd.read_csv(summary_file)
        mh_col = summary["mh"] if "mh" in summary else ["all"] * len(summary)
        done = set(zip(summary["instance"], mh_col, summary["variant"]))

    jobs = []
    for mh in mhs:
        for inst in sorted(INSTANCES_DIR.glob("*/*.txt")):
            n = instance_size(inst)
            maxtime = args.time if args.time is not None else max(5, n // 100)
            name = "../" + str(inst.relative_to(ROOT_DIR))
            for variant in VARIANTS:
                if (name, mh or "all", variant) not in done:
                    jobs.append((name, n, maxtime, mh, variant))

    total_sec = sum(job[2] * max_runs for job in jobs)
    print(f"{len(jobs)} jobs pending, estimated time: {total_sec / 3600:.1f} h")

    try:
        run_jobs(jobs, max_runs, summary_file, runs_file, original_config)
    finally:
        CONFIG_FILE.write_text(original_config)

    print(f"\nDone.\nSummary: {summary_file}\nRuns:    {runs_file}"
          f"\nTable:   python3 make_table_cuts.py {out_dir}")


def run_jobs(jobs, max_runs, summary_file, runs_file, original_config):
    for k, (name, n, maxtime, mh, variant) in enumerate(jobs, 1):
        print(f"[{k}/{len(jobs)}] {name} | {mh or 'all MHs'} | {variant} | "
              f"MAXTIME {maxtime}s x {max_runs} runs", flush=True)
        if mh is not None:
            CONFIG_FILE.write_text(single_mh_config(original_config, mh, max_runs))
        cmd = ["./runRKO", name, str(maxtime)] + VARIANTS[variant]
        proc = subprocess.run(cmd, cwd=PROGRAM_DIR, stdout=subprocess.DEVNULL)
        if proc.returncode != 0:
            sys.exit(f"ERROR: {' '.join(cmd)} returned {proc.returncode}")

        suffix = "_cuts" if variant == "cuts" else ""
        instance, ofvs, time_best, time_total = read_last_result(
            RESULTS_DIR / f"Results_RKO{suffix}.csv")
        if instance != name:
            sys.exit(f"ERROR: last result line is for {instance}, expected {name}")

        runs = pd.DataFrame({"instance": name, "n": n, "mh": mh or "all", "variant": variant,
                             "maxtime": maxtime, "run": range(1, len(ofvs) + 1), "ofv": ofvs})
        append_csv(runs, runs_file)

        append_csv(pd.DataFrame([{
            "instance": name, "n": n, "mh": mh or "all", "variant": variant, "maxtime": maxtime,
            "runs": len(ofvs),
            "ofv_best": runs["ofv"].min(),
            "ofv_mean": runs["ofv"].mean(),
            "ofv_std": runs["ofv"].std(),          # sample standard deviation
            "time_best_mean": time_best,
            "time_total_mean": time_total,
        }]), summary_file)


if __name__ == "__main__":
    main()
