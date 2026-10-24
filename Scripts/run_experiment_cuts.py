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
  python3 run_experiment_cuts.py --mh BRKGA --runs 10 --n 10000 --jobs 5 --pin
  python3 run_experiment_cuts.py --resume ../Results/teste_sensibilidade_01

MAXTIME defaults to max(5, n/100) seconds. With --mh, each MH runs alone (single thread)
and the config file is temporarily rewritten with that MH and MAXRUNS = --runs.
With --sensitivity, the cuts variant runs first and the original then gets
ceil(mean time to best of the cuts variant) as MAXTIME.
With --jobs N, N instances run at the same time (--pin binds each one to a core).
"""
import argparse
import math
import queue
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
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

lock = threading.Lock()


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


def read_result(results_file, instance):
    """Last line of Results_RKO*.csv for `instance`:
    instance, MHs, runs, ofv_1..ofv_k, best, avg, tBest, tTotal."""
    for line in reversed(results_file.read_text().splitlines()):
        fields = line.split("\t")
        if fields[0] == instance:
            n_runs = int(fields[2])
            ofvs = [float(x) for x in fields[3:3 + n_runs]]
            return ofvs, float(fields[-2]), float(fields[-1])
    raise RuntimeError(f"no result for {instance} in {results_file}")


def physical_cpus():
    """One logical CPU per physical core, so pinned jobs never share a core."""
    out = subprocess.run(["lscpu", "-p=CPU,CORE"], capture_output=True, text=True,
                         check=True).stdout
    first = {}
    for line in out.splitlines():
        if not line.startswith("#"):
            cpu, core = map(int, line.split(","))
            first.setdefault(core, cpu)
    return sorted(first.values())


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
    parser.add_argument("--jobs", type=int, default=1, help="instances run at the same time")
    parser.add_argument("--pin", action="store_true", help="bind each job to a core (taskset)")
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
        mhs = ["all"]
        max_runs = config.get("MAXRUNS", 0)
    else:
        mhs = config_mhs(original_config) if args.mh == ["all"] else args.mh
        unknown = [m for m in mhs if m not in ALL_MHS]
        if unknown:
            sys.exit(f"ERROR: unknown MH(s) {unknown}, options: {ALL_MHS}")
        max_runs = args.runs or config.get("MAXRUNS", 0)
    if args.jobs > 1 and len(mhs) > 1:
        sys.exit("ERROR: --jobs > 1 requires a single --mh")

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

    # a chain is the list of jobs of one (instance, mh), run in order by the same worker
    variants = ["cuts", "original"] if args.sensitivity else list(VARIANTS)
    chains = []
    for mh in mhs:
        for path in instances:
            n = instance_size(path)
            name = "../" + str(path.relative_to(ROOT_DIR))
            maxtime = args.time or max(5, n // 100)
            chain = []
            for variant in variants:
                if (name, mh, variant) in done:
                    continue
                if variant == "cuts":
                    t = round(maxtime * args.cuts_time_factor)
                else:
                    t = None if args.sensitivity else maxtime
                chain.append((name, n, t, mh, variant))
            if chain:
                chains.append(chain)

    seconds = []
    for chain in chains:
        cuts_t = next((j[2] for j in chain if j[4] == "cuts"), 0)
        seconds.append(sum((j[2] or cuts_t) * max_runs for j in chain))
    rounds = math.ceil(len(chains) / args.jobs)
    print(f"{sum(len(c) for c in chains)} jobs pending in {len(chains)} instances, "
          f"{args.jobs} at a time, estimated time: "
          f"{max(seconds, default=0) * rounds / 3600:.1f} h")

    cpus = list(range(args.jobs))
    if args.pin:
        cpus = physical_cpus()
        if len(cpus) < args.jobs:
            sys.exit(f"ERROR: --jobs {args.jobs} but only {len(cpus)} physical cores")
        print(f"Pinning to CPUs {cpus[:args.jobs]}")
    cores = queue.Queue()
    for cpu in cpus[:args.jobs]:
        cores.put(cpu)
    ctx = dict(max_runs=max_runs, summary_file=summary_file, runs_file=runs_file,
               original_config=original_config, cuts_time_best=cuts_time_best,
               pin=args.pin, cores=cores, per_job_config=len(mhs) > 1)

    try:
        if len(mhs) == 1 and mhs[0] != "all":
            CONFIG_FILE.write_text(single_mh_config(original_config, mhs[0], max_runs))
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run_chain, chain, ctx) for chain in chains]
            try:
                for future in futures:
                    future.result()
            except BaseException:
                pool.shutdown(cancel_futures=True)
                raise
    finally:
        CONFIG_FILE.write_text(original_config)

    print(f"\nDone: {out_dir}")


def run_chain(chain, ctx):
    core = ctx["cores"].get()
    try:
        for job in chain:
            run_job(*job, core, ctx)
    finally:
        ctx["cores"].put(core)


def run_job(name, n, maxtime, mh, variant, core, ctx):
    if maxtime is None:
        maxtime = max(1, math.ceil(ctx["cuts_time_best"][(name, mh)]))
    with lock:
        print(f"{datetime.now():%d/%m %H:%M} {name} | {mh} | {variant} | "
              f"MAXTIME {maxtime}s x {ctx['max_runs']} runs", flush=True)
        if ctx["per_job_config"] and mh != "all":
            CONFIG_FILE.write_text(single_mh_config(ctx["original_config"], mh, ctx["max_runs"]))

    cmd = ["./runRKO", name, str(maxtime)] + VARIANTS[variant]
    if ctx["pin"]:
        cmd = ["taskset", "-c", str(core)] + cmd
    if subprocess.run(cmd, cwd=PROGRAM_DIR, stdout=subprocess.DEVNULL).returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed")

    suffix = "_cuts" if variant == "cuts" else ""
    with lock:
        ofvs, time_best, time_total = read_result(RESULTS_DIR / f"Results_RKO{suffix}.csv", name)
        runs = pd.DataFrame({"instance": name, "n": n, "mh": mh, "variant": variant,
                             "maxtime": maxtime, "run": range(1, len(ofvs) + 1), "ofv": ofvs})
        append_csv(runs, ctx["runs_file"])
        append_csv(pd.DataFrame([{
            "instance": name, "n": n, "mh": mh, "variant": variant, "maxtime": maxtime,
            "runs": len(ofvs),
            "ofv_best": runs["ofv"].min(),
            "ofv_mean": runs["ofv"].mean(),
            "ofv_std": runs["ofv"].std(),
            "time_best_mean": time_best,
            "time_total_mean": time_total,
        }]), ctx["summary_file"])
        if variant == "cuts":
            ctx["cuts_time_best"][(name, mh)] = time_best


if __name__ == "__main__":
    main()
