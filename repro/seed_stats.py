#!/usr/bin/env python3
"""Seed statistics for the reproduction target.

The graded reproduction requirement asks for 3-5 trials of a stochastic
pipeline and a mean/variance report. The verifier runs at temperature 1.0, so
each seed is a different draw: a different Hamiltonian ring for the tournament
*and* different verifier samples (each seed writes its own score cache).

    python repro/seed_stats.py                      # seeds 0,1,2 of the baseline
    python repro/seed_stats.py --tags sub12_g20 sub12_g20_s1 sub12_g20_s2

Note on the ablation: the g=5 configuration is deliberately *not* given extra
seeds. It shares seed 0 with the baseline, so the two configurations score the
same 282 of 288 comparisons — a matched-pair design in which seed-to-seed
noise cancels in the paired difference (see repro/ablation_overlap.py). Its
evidence is those 282 paired comparisons, not a count of 12 tasks.
"""

import argparse
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from repro.analyze import analyse, load_tasks  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", nargs="+",
                    default=["sub12_g20", "sub12_g20_s1", "sub12_g20_s2"])
    ap.add_argument("--granularity", type=int, default=20)
    ap.add_argument("--json", default=os.path.join(ROOT, "results",
                                                   "seed_stats.json"))
    args = ap.parse_args()

    tasks = load_tasks()
    rows = []
    for s, tag in enumerate(args.tags):
        print(f"\n== seed {s} ({tag}) ==")
        r = analyse(tag, args.granularity, tasks, seed=s)
        rows.append(r)

    def agg(key):
        vals = [100.0 * r[key] / r["tasks"] for r in rows]
        return statistics.mean(vals), (statistics.stdev(vals) if len(vals) > 1 else 0.0), vals

    print("\n" + "=" * 68)
    print(f"{'metric':<22}" + "".join(f"seed{s:<8}" for s in range(len(rows)))
          + f"{'mean':>8}{'std':>8}")
    print("-" * 68)
    out = {"n_seeds": len(rows), "tasks": rows[0]["tasks"], "per_seed": []}
    for r in rows:
        out["per_seed"].append({
            "seed": r["seed"], "tag": r["tag"],
            "pass1": 100.0 * r["pass1"] / r["tasks"],
            "verifier": 100.0 * r["verifier"] / r["tasks"],
            "oracle": 100.0 * r["oracle"] / r["tasks"],
            "pairwise_acc": (100.0 * r["pairwise_agree"] / r["pairwise_total"]
                             if r["pairwise_total"] else None),
            "trial_auc": r["trial_auc"],
            "verifier_tasks": r["verifier"],
        })
    for label, key in (("Pass@1 %", "pass1"), ("verifier %", "verifier"),
                       ("oracle %", "oracle")):
        m, sd, vals = agg(key)
        print(f"{label:<22}" + "".join(f"{v:<12.1f}" for v in vals)
              + f"{m:>8.1f}{sd:>8.1f}")
        out[label] = {"mean": round(m, 2), "std": round(sd, 2),
                      "values": [round(v, 2) for v in vals]}
    aucs = [r["trial_auc"] for r in rows]
    pairs = [100.0 * r["pairwise_agree"] / r["pairwise_total"] for r in rows]
    print(f"{'pairwise acc %':<22}" + "".join(f"{v:<12.1f}" for v in pairs)
          + f"{statistics.mean(pairs):>8.1f}"
          f"{(statistics.stdev(pairs) if len(pairs) > 1 else 0):>8.1f}")
    print(f"{'trial AUC':<22}" + "".join(f"{v:<12.3f}" for v in aucs)
          + f"{statistics.mean(aucs):>8.3f}"
          f"{(statistics.stdev(aucs) if len(aucs) > 1 else 0):>8.3f}")
    out["pairwise_acc"] = {"mean": round(statistics.mean(pairs), 2),
                           "std": round(statistics.stdev(pairs) if len(pairs) > 1 else 0, 2),
                           "values": [round(v, 2) for v in pairs]}
    out["trial_auc"] = {"mean": round(statistics.mean(aucs), 3),
                        "std": round(statistics.stdev(aucs) if len(aucs) > 1 else 0, 3),
                        "values": [round(v, 3) for v in aucs]}
    json.dump(out, open(args.json, "w"), indent=2)
    print(f"\nwritten: {args.json}")


if __name__ == "__main__":
    main()
