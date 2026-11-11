#!/usr/bin/env python3
"""Measure what the granularity ablation actually changed, vote by vote.

The task-level selection of the g=20 baseline and the g=5 ablation came out
identical, which by itself says nothing about whether the ablation did
anything. This script compares the two score caches on the *same*
comparisons and reports the local effect:

  * how often the pairwise preference (which trajectory wins) flips,
  * whether flips concentrate in uninformative comparisons (both trials end
    with the same outcome) or in the ones that actually decide a task,
  * how strongly the score values and the preference margins move.

    python repro/ablation_overlap.py
    # writes results/ablation_overlap.json
"""

import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from llm_verifier.loaders import LOADERS  # noqa: E402

BASE_TAG = "sub12_g20"
MOD_TAG = "sub12_g5"
DATA = {"agent_dir":
        "data/terminal_bench_2.1_trajs/mini-swe-agent_deepseek-v4-flash"}


def main():
    def cache(tag):
        path = os.path.join(ROOT, "cache", f"cache_tb2.1_{tag}.json")
        return json.load(open(path))

    a, b = cache(BASE_TAG), cache(MOD_TAG)
    tasks, _ = LOADERS["terminal"](DATA, ROOT)
    tasks = {k: v[:3] for k, v in tasks.items()}

    common = sorted(set(a) & set(b))
    dA = [abs(a[k]["score_A"] - b[k]["score_A"]) for k in common]
    dB = [abs(a[k]["score_B"] - b[k]["score_B"]) for k in common]
    margin_a = [abs(a[k]["score_A"] - a[k]["score_B"]) for k in common]
    margin_b = [abs(b[k]["score_A"] - b[k]["score_B"]) for k in common]

    buckets = {"informative": [0, 0], "uninformative": [0, 0]}
    for k in common:
        _crit, task, pair, _rep = k.split("|")
        i, j = (int(x) for x in pair.split(","))
        informative = tasks[task][i]["reward"] != tasks[task][j]["reward"]
        name = "informative" if informative else "uninformative"
        buckets[name][0] += 1
        if ((a[k]["score_A"] > a[k]["score_B"])
                != (b[k]["score_A"] > b[k]["score_B"])):
            buckets[name][1] += 1

    values_a = {round(v[s], 3) for v in a.values() for s in ("score_A", "score_B")}
    values_b = {round(v[s], 3) for v in b.values() for s in ("score_A", "score_B")}

    out = {
        "n_comparisons_scored_twice": len(common),
        "mean_abs_delta_score": round(statistics.mean(dA + dB), 4),
        "median_abs_delta_score": round(statistics.median(dA + dB), 4),
        "mean_abs_margin_base": round(statistics.mean(margin_a), 4),
        "mean_abs_margin_mod": round(statistics.mean(margin_b), 4),
        "distinct_values_base": len(values_a),
        "distinct_values_mod": len(values_b),
        "flip_rate_informative": round(buckets["informative"][1]
                                       / buckets["informative"][0], 4),
        "flip_n_informative": buckets["informative"][1],
        "n_informative": buckets["informative"][0],
        "flip_rate_uninformative": round(buckets["uninformative"][1]
                                         / buckets["uninformative"][0], 4),
        "flip_n_uninformative": buckets["uninformative"][1],
        "n_uninformative": buckets["uninformative"][0],
    }
    path = os.path.join(ROOT, "results", "ablation_overlap.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, "w"), indent=2)

    print(f"comparisons scored under both configurations: {len(common)}")
    print(f"  mean |delta score| = {out['mean_abs_delta_score']} "
          f"(median {out['median_abs_delta_score']})")
    print(f"  preference margin: g20 {out['mean_abs_margin_base']} -> "
          f"g5 {out['mean_abs_margin_mod']}")
    print(f"  distinct score values: {out['distinct_values_base']} -> "
          f"{out['distinct_values_mod']}")
    print(f"  flips on informative comparisons  : "
          f"{out['flip_n_informative']}/{out['n_informative']} "
          f"({100 * out['flip_rate_informative']:.1f}%)")
    print(f"  flips on uninformative comparisons: "
          f"{out['flip_n_uninformative']}/{out['n_uninformative']} "
          f"({100 * out['flip_rate_uninformative']:.1f}%)")
    print(f"\nwritten: {path}")


if __name__ == "__main__":
    main()
