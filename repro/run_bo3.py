#!/usr/bin/env python3
"""Best-of-3 runner with task-subset scoping and per-experiment cache tags.

This is *reproduction harness* code added for the FTEC5660 reproducibility
assignment; it does not change the method. It wraps the upstream
`scripts/run.py:run_benchmark` so that a run can be

  * scoped to a deterministic subset of the "swing" tasks (`--limit`), which
    is how the smoke test and the reduced-budget experiments are run, and
  * written to its own score cache / results file (`--tag`), so two
    configurations (e.g. baseline g20 vs. the g5 ablation) never share cached
    verifier scores.

Everything else — loaders, criteria, prompts, the Probabilistic Pivot
Tournament, the metrics — is the upstream code, unchanged.

Usage:
    python repro/run_bo3.py                          # full 89-task bo3, seed 0
    python repro/run_bo3.py --limit 3 --tag smoke     # 3 swing tasks
    LLM_VERIFIER_GRANULARITY=5 python repro/run_bo3.py --tag g5
"""

import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))

from run import report, resolve_config, run_benchmark  # noqa: E402
from llm_verifier import loaders as _loaders  # noqa: E402
from llm_verifier.fine_grained_reward import GRANULARITY, load_dotenv  # noqa: E402

N_TRIALS = 3      # best-of-3: the first 3 trials of each task
PIVOTS = 1
N_EVALUATIONS = 2


def swing_tasks(tasks):
    """Tasks whose trials disagree (from scripts/run.py:classify)."""
    swing = []
    for name, trials in tasks.items():
        rewards = [t["reward"] for t in trials]
        if not all(r == 1 for r in rewards) and not all(r == 0 for r in rewards):
            swing.append(name)
    return sorted(swing)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("benchmark", nargs="?", default="terminal_bench_2.1")
    ap.add_argument("--limit", type=int, default=None,
                    help="score only the first N swing tasks (sorted by name)")
    ap.add_argument("--tag", default="bo3",
                    help="suffix for the cache/results files (default: bo3)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-workers", type=int, default=None)
    ap.add_argument("--n-evaluations", type=int, default=N_EVALUATIONS)
    args = ap.parse_args()

    load_dotenv(ROOT_DIR)
    cfg = resolve_config(args.benchmark)

    # Deterministic scoping: truncate to best-of-3 first, then keep the first
    # N swing tasks by name. Done by wrapping the loader, so the upstream
    # pipeline (including its task classification) is untouched.
    if args.limit:
        loader = _loaders.LOADERS[cfg.loader]
        orig = loader

        def scoped(data, root, _orig=orig, _limit=args.limit):
            tasks, n_runs = _orig(data, root)
            tasks = {k: v[:N_TRIALS] for k, v in tasks.items()}
            keep = set(swing_tasks(tasks)[:_limit])
            return {k: v for k, v in tasks.items() if k in keep}, n_runs

        _loaders.LOADERS[cfg.loader] = scoped

    print(f"[repro] granularity g{GRANULARITY} | tag={args.tag} | "
          f"limit={args.limit} | seed={args.seed}")

    out = run_benchmark(
        cfg,
        pivots=PIVOTS,
        n_evaluations=args.n_evaluations,
        seed=args.seed,
        max_workers=args.max_workers,
        n_trials=N_TRIALS,
        cache_file=os.path.join(ROOT_DIR, "cache",
                                f"cache_tb2.1_{args.tag}.json"),
        results_file=os.path.join(ROOT_DIR, "results",
                                  f"terminal_bench_2.1_{args.tag}.txt"),
    )
    report(cfg, **out)


if __name__ == "__main__":
    main()
