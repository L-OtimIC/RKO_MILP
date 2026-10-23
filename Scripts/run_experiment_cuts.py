#!/usr/bin/env python3
"""
Runs RKO with and without the cut pool (--cuts) on the 00Uncorrelated KP instances and
collects the results in summary.csv and runs.csv inside an experiment folder in ../Results.

Requires `debug 0` in Program/config/config_tests.conf and `make` in Program.

Examples (from the Scripts folder):
  python3 run_experiment_cuts.py
  python3 run_experiment_cuts.py --mh BRKGA --runs 30
  python3 run_experiment_cuts.py --mh BRKGA --runs 10 --cuts-time-factor 2
  python3 run_experiment_cuts.py --mh BRKGA --runs 10 --cuts-time-factor 10 --sensitivity --n 10000
  python3 run_experiment_cuts.py --resume ../Results/teste_sensibilidade_01

MAXTIME defaults to max(5, n/100) seconds. With --mh, each MH runs alone (single thread)
and the config file is temporarily rewritten with that MH and MAXRUNS = --runs.
With --sensitivity, the cuts variant runs first and the original then gets
ceil(mean time to best of the cuts variant) as MAXTIME.
"""
import argparse
import math
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
    params = {}
    for line in CONFIG_FILE.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            params[parts[0]] = int(parts[1])
    return params


def config_mhs(text):
    return [l.strip() for l in text.splitlines() if l.strip() in ALL_MHS]


def single_mh_config(text, mh, max_runs):
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
    with open(path) as f:
        return int(f.read(64).split()[0])


def read_last_result(results_file):
    """Last line of Results_RKO*.csv: instance, MHs, runs, ofv_1..ofv_k, best, avg, tBest, tTotal."""
    lines = [l for l in results_file.read_text().splitlines() if l.strip()]
    fields = lines[-1].split("\t")
    n_runs = int(fields[2])
    ofvs = [float(x) for x in fields[3:3 + n_runs]]
    return fields[0], ofvs, float(fields[-2]), float(fields[-1])


def append_csv(df, path):
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--time", type=int, help="fixed MAXTIME in seconds")
    parser.add_argument("--n", type=int, nargs="+", help="only instances with these sizes")
    parser.add_argument("--mh", nargs="+",
                        help="run each MH alone; 'all' = every MH of the config")
    parser.add_argument("--runs", type=int, help="MAXRUNS used with --mh")
    parser.add_argument("--cuts-time-factor", type=float, default=1.0,
                        help="multiplies MAXTIME of the cuts variant")
    parser.add_argument("--sensitivity", action="store_true",
                        help="original gets the mean time to best of the cuts variant")
    parser.add_argument("--out", help="name of the experiment folder in ../Results")
    parser.add_argument("--resume", type=Path, help="experiment folder to resume")
    return parser.parse_args()


def main():
    args = parse_args()

    config = read_config()
    if config.get("debug", 1) != 0:
        sys.exit(f"ERROR: set 'debug 0' in {CONFIG_FILE}")
    if not (PROGRAM_DIR / "runRKO").exists():
        sys.exit("ERROR: Program/runRKO not found, run `make` first")
    original_config = CONFIG_FILE.read_text()

    if args.mh is None:
        if args.runs is not None:
            sys.exit("ERROR: --runs requires --mh")
        mhs = [None]
        max_runs = config.get("MAXRUNS", 0)
    else:
        mhs = config_mhs(original_config) if args.mh == ["all"] else args.mh
        unknown = [m for m in mhs if m not in ALL_MHS]
        if unknown:
            sys.exit(f"ERROR: unknown MH(s) {unknown}, options: {ALL_MHS}")
        max_runs = args.runs or config.get("MAXRUNS", 0)

    if args.resume:
        out_dir = args.resume
        if not out_dir.is_dir():
            sys.exit(f"ERROR: {out_dir} not found")
    else:
        name = args.out or datetime.now().strftime("experiment_cuts_%Y-%m-%d_%H-%M-%S")
        out_dir = RESULTS_DIR / name
        if out_dir.exists():
            sys.exit(f"ERROR: {out_dir} already exists, use --resume to continue it")
        out_dir.mkdir(parents=True)
    summary_file = out_dir / "summary.csv"
    runs_file = out_dir / "runs.csv"
    print(f"Output folder: {out_dir}")

    done, cuts_time_best = set(), {}
    if summary_file.exists():
        summary = pd.read_csv(summary_file)
        for row in summary.itertuples():
            done.add((row.instance, row.mh, row.variant))
            if row.variant == "cuts":
                cuts_time_best[(row.instance, row.mh)] = row.time_best_mean

    instances = sorted(INSTANCES_DIR.glob("*/*.txt"))
    if args.n:
        instances = [p for p in instances if instance_size(p) in args.n]
    if not instances:
        sys.exit("ERROR: no instance selected")

    variants = ["cuts", "original"] if args.sensitivity else list(VARIANTS)
    jobs = []
    for mh in mhs:
        for path in instances:
            n = instance_size(path)
            name = "../" + str(path.relative_to(ROOT_DIR))
            maxtime = args.time or max(5, n // 100)
            for variant in variants:
                if (name, mh or "all", variant) in done:
                    continue
                if variant == "cuts":
                    t = round(maxtime * args.cuts_time_factor)
                else:
                    t = None if args.sensitivity else maxtime
                jobs.append((name, n, t, mh or "all", variant))

    cuts_t = {(j[0], j[3]): j[2] for j in jobs if j[4] == "cuts"}
    total = sum((j[2] or cuts_t.get((j[0], j[3]), 0)) * max_runs for j in jobs)
    print(f"{len(jobs)} jobs pending, estimated time: {total / 3600:.1f} h")

    try:
        run_jobs(jobs, max_runs, summary_file, runs_file, original_config, cuts_time_best)
    finally:
        CONFIG_FILE.write_text(original_config)

    print(f"\nDone: {out_dir}")


def run_jobs(jobs, max_runs, summary_file, runs_file, original_config, cuts_time_best):
    for k, (name, n, maxtime, mh, variant) in enumerate(jobs, 1):
        if maxtime is None:
            maxtime = max(1, math.ceil(cuts_time_best[(name, mh)]))
        print(f"[{k}/{len(jobs)}] {datetime.now():%d/%m %H:%M} {name} | {mh} | {variant} | "
              f"MAXTIME {maxtime}s x {max_runs} runs", flush=True)

        if mh != "all":
            CONFIG_FILE.write_text(single_mh_config(original_config, mh, max_runs))
        cmd = ["./runRKO", name, str(maxtime)] + VARIANTS[variant]
        if subprocess.run(cmd, cwd=PROGRAM_DIR, stdout=subprocess.DEVNULL).returncode != 0:
            sys.exit(f"ERROR: {' '.join(cmd)} failed")

        suffix = "_cuts" if variant == "cuts" else ""
        instance, ofvs, time_best, time_total = read_last_result(
            RESULTS_DIR / f"Results_RKO{suffix}.csv")
        if instance != name:
            sys.exit(f"ERROR: last result line is for {instance}, expected {name}")

        runs = pd.DataFrame({"instance": name, "n": n, "mh": mh, "variant": variant,
                             "maxtime": maxtime, "run": range(1, len(ofvs) + 1), "ofv": ofvs})
        append_csv(runs, runs_file)
        append_csv(pd.DataFrame([{
            "instance": name, "n": n, "mh": mh, "variant": variant, "maxtime": maxtime,
            "runs": len(ofvs),
            "ofv_best": runs["ofv"].min(),
            "ofv_mean": runs["ofv"].mean(),
            "ofv_std": runs["ofv"].std(),
            "time_best_mean": time_best,
            "time_total_mean": time_total,
        }]), summary_file)

        if variant == "cuts":
            cuts_time_best[(name, mh)] = time_best


if __name__ == "__main__":
    main()
