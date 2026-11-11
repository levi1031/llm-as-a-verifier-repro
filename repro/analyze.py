#!/usr/bin/env python3
"""Analysis for the FTEC5660 reproduction of LLM-as-a-Verifier (Terminal-Bench 2.1).

Reads the verifier-score caches produced by `repro/run_bo3.py` plus the
ground-truth rewards shipped in `data/`, and reports the numbers used in the
report:

  * task-level selection accuracy (Pass@1 / Verifier / Oracle) per config,
  * pairwise-preference accuracy on comparisons whose two trials disagree,
  * trial-level discrimination (AUC of the verifier reward vs. the binary
    reward), i.e. does the score separate successful from failed rollouts,
  * score-scale degeneracy, i.e. how far the logprob expectation sits from a
    pure single-letter read (the paper's "expectation over the distribution"
    component),
  * a paired McNemar-style table comparing the two configurations.

Usage:
    python repro/analyze.py --tag sub12_g20 --granularity 20
    python repro/analyze.py --tags sub12_g20:20 sub12_g5:5 --json out.json
"""

import argparse
import json
import os
import random
import statistics
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from llm_verifier.loaders import LOADERS  # noqa: E402
from llm_verifier import pivot_tournament as ppt  # noqa: E402
from llm_verifier.fine_grained_reward import cache_key, directed_reward  # noqa: E402

N_TRIALS = 3
PIVOTS = 1
CRITERIA = ["specification", "output_match", "error_signals"]
DATA = {"agent_dir": "data/terminal_bench_2.1_trajs/mini-swe-agent_deepseek-v4-flash"}
SEED = 0


def load_tasks():
    tasks, _ = LOADERS["terminal"](DATA, ROOT_DIR)
    return {k: v[:N_TRIALS] for k, v in tasks.items()}


def classify(tasks):
    all_pass, all_fail, swing = [], [], []
    for name, trials in sorted(tasks.items()):
        r = [t["reward"] for t in trials]
        if all(x == 1 for x in r):
            all_pass.append(name)
        elif all(x == 0 for x in r):
            all_fail.append(name)
        else:
            swing.append(name)
    return all_pass, all_fail, swing


def ring_of(swing, tasks, seed=SEED):
    """The same ring sampling run.py performs (sorted swing tasks, one RNG)."""
    rng = random.Random(seed)
    return {t: ppt.ring_cycle(len(tasks[t]), rng) for t in swing}


def tournament(scores, tasks, rings, k=PIVOTS, n_reps=2):
    """Replay the upstream tournament for every swing task; return
    {task: selected_index} plus the comparison pairs it used."""
    out, pairs_used = {}, {}
    for task, ring in rings.items():
        n = len(tasks[task])

        def directed(a, b, t=task):
            return directed_reward(scores, t, a, b, CRITERIA, n_reps)

        w, c = [0.0] * n, [0] * n
        ppt.accumulate(ring, lambda a, b, t=task: directed(a, b, t), w, c)
        pivots = ppt.select_pivots(w, c, k)
        pr = ppt.pivot_round_pairs(n, pivots)
        ppt.accumulate(pr, lambda a, b, t=task: directed(a, b, t), w, c)
        out[task] = max(range(n), key=lambda i: (w[i] / c[i] if c[i] else 0.0, -i))
        pairs_used[task] = list(dict.fromkeys(list(ring) + list(pr)))
    return out, pairs_used


def auc(pos, neg):
    """Rank-based AUC (ties count 1/2) of `pos` vs `neg` scores."""
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for q in neg:
            wins += 1.0 if p > q else (0.5 if p == q else 0.0)
    return wins / (len(pos) * len(neg))


def degeneracy(values, granularity):
    """Distance of each expected score from the nearest single-letter value,
    expressed in scale points (a pure mixture would be > 0.5 apart)."""
    span = granularity - 1
    dev = [abs(v * span - round(v * span)) for v in values]
    return {
        "n": len(dev),
        "median_dev": statistics.median(dev) if dev else float("nan"),
        "share_within_1e-3": (sum(1 for d in dev if d < 1e-3) / len(dev)
                              if dev else float("nan")),
        "share_within_0.01": (sum(1 for d in dev if d < 0.01) / len(dev)
                              if dev else float("nan")),
    }



def usage_from_logs(tag):
    """Token accounting for a run, parsed from the run's log if present."""
    import glob
    import re as _re
    path = os.path.join(ROOT_DIR, "logs", f"{tag}.log")
    if not os.path.exists(path):
        return {}
    text = open(path, errors="ignore").read()
    calls = _re.findall(r"Tokens: ([\d,]+) calls  input ([\d,]+) \(cached ([\d,]+),", text)
    out = _re.findall(r"output ([\d,]+)", text)
    if not calls:
        return {}
    c = sum(int(x[0].replace(",", "")) for x in calls)
    i = sum(int(x[1].replace(",", "")) for x in calls)
    ca = sum(int(x[2].replace(",", "")) for x in calls)
    o = sum(int(x.replace(",", "")) for x in out)
    return {"calls": c, "input_tokens": i, "cached_input_tokens": ca,
            "output_tokens": o,
            "errors": text.count("\n  Error: ")}


def analyse(tag, granularity, tasks, seed=SEED):
    path = os.path.join(ROOT_DIR, "cache", f"cache_tb2.1_{tag}.json")
    scores = json.load(open(path))
    all_pass, all_fail, _swing_all = classify(tasks)
    # Only tasks whose *every* comparison is cached may enter the tournament:
    # a missing entry defaults to a 0.5/0.5 tie, which would silently decide
    # the ranking by index order. The number of distinct comparisons per task
    # is 4 or 5 (a pivot-round pair can coincide with a ring pair), so the
    # check walks the actual pairs the tournament will use.
    per_task = {}
    for k in scores:
        per_task[k.split("|")[1]] = per_task.get(k.split("|")[1], 0) + 1
    candidates = sorted(per_task)
    all_rings = ring_of(candidates, tasks, seed=seed)
    scored_tasks, incomplete = [], {}
    for t in candidates:
        ring = all_rings[t]
        missing = [cache_key(c, t, a, b, r) for c, a, b, r in
                   ((c, a, b, r) for a, b in ring for c in CRITERIA
                    for r in range(2))
                   if cache_key(c, t, a, b, r) not in scores]
        if missing:
            incomplete[t] = f"{len(missing)} ring comparisons missing"
            continue
        w, c = [0.0] * len(tasks[t]), [0] * len(tasks[t])
        ppt.accumulate(ring, lambda a, b, t=t: directed_reward(
            scores, t, a, b, CRITERIA, 2), w, c)
        pr = ppt.pivot_round_pairs(len(tasks[t]), ppt.select_pivots(w, c, PIVOTS))
        missing = [cache_key(cr, t, a, b, r) for cr, a, b, r in
                   ((cr, a, b, r) for a, b in pr for cr in CRITERIA
                    for r in range(2))
                   if cache_key(cr, t, a, b, r) not in scores]
        if missing:
            incomplete[t] = f"{len(missing)} pivot comparisons missing"
            continue
        scored_tasks.append(t)
    if incomplete:
        print(f"  [warn] {tag}: {len(incomplete)} task(s) skipped, "
              f"cache incomplete (e.g. {list(incomplete.items())[:2]})")
    if not scored_tasks:
        raise SystemExit(f"{tag}: no completely scored task in the cache")
    print(f"  {tag}: {len(scored_tasks)} completely scored tasks "
          f"({len(scores)} cached entries)")
    sub = {t: tasks[t] for t in scored_tasks}
    rings = ring_of(scored_tasks, sub, seed=seed)
    selected, pairs_used = tournament(scores, sub, rings)

    n = len(scored_tasks)
    pass1 = sum(sum(t["reward"] for t in sub[t]) / len(sub[t]) for t in sub)
    verifier = sum(1 for t, i in selected.items() if sub[t][i]["reward"] == 1)
    oracle = sum(1 for t in sub if any(x["reward"] == 1 for x in sub[t]))

    # pairwise preference accuracy on comparisons whose trials disagree
    agree = total_disagree = 0
    for task, pairs in pairs_used.items():
        for a, b in pairs:
            ra, rb = sub[task][a]["reward"], sub[task][b]["reward"]
            if ra == rb:
                continue
            total_disagree += 1
            va, vb = directed_reward(scores, task, a, b, CRITERIA, 2)
            if (va > vb and ra == 1) or (vb > va and rb == 1):
                agree += 1

    # trial-level discrimination: mean verifier reward per trial vs its reward
    per_trial = {}
    for a in range(N_TRIALS):
        vals = []
        for task in scored_tasks:
            acc = [v["score_A"] for k, v in scores.items()
                   if k.split("|")[1] == task and k.split("|")[2].split(",")[0] == str(a)]
            acc += [v["score_B"] for k, v in scores.items()
                    if k.split("|")[1] == task and k.split("|")[2].split(",")[1] == str(a)]
            if acc:
                vals.append((statistics.mean(acc), sub[task][a]["reward"]))
        per_trial[a] = vals
    pos = [s for vals in per_trial.values() for s, r in vals if r == 1]
    neg = [s for vals in per_trial.values() for s, r in vals if r == 0]

    values = [v[k] for v in scores.values() for k in ("score_A", "score_B")]
    return {
        "tag": tag,
        "granularity": granularity,
        "seed": seed,
        "tasks": n,
        "pass1": pass1,
        "verifier": verifier,
        "oracle": oracle,
        "selected": selected,
        "pairwise_agree": agree,
        "pairwise_total": total_disagree,
        "trial_auc": auc(pos, neg),
        "n_success_trials": len(pos),
        "n_fail_trials": len(neg),
        "mean_reward_success": statistics.mean(pos) if pos else float("nan"),
        "mean_reward_fail": statistics.mean(neg) if neg else float("nan"),
        "degeneracy": degeneracy(values, granularity),
        "cache_entries": len(scores),
        # per-task evidence: rewards of the (first three) trials, which trial
        # the tournament selected, and whether that trial succeeded
        "per_task": [
            {"task": t,
             "rewards": [x["reward"] for x in sub[t]],
             "selected": selected[t],
             "ok": sub[t][selected[t]]["reward"] == 1}
            for t in sorted(sub)],
        "usage": usage_from_logs(tag),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", required=True,
                    help="tag:granularity pairs, e.g. sub12_g20:20 sub12_g5:5")
    ap.add_argument("--json", default=None, help="write the results as JSON")
    args = ap.parse_args()

    tasks = load_tasks()
    all_pass, all_fail, swing = classify(tasks)
    print(f"full bo3 data: tasks={len(tasks)} all-pass={len(all_pass)} "
          f"all-fail={len(all_fail)} swing={len(swing)}")
    full_pass1 = (len(all_pass) + sum(sum(t["reward"] for t in tasks[k]) / N_TRIALS
                                      for k in swing)) / len(tasks)
    print(f"full-data reference: Pass@1={full_pass1:.3f} "
          f"Oracle={(len(all_pass) + len(swing)) / len(tasks):.3f}\n")

    runs = []
    for spec in args.tags:
        tag, gran = spec.split(":")
        runs.append(analyse(tag, int(gran), tasks))

    hdr = (f"{'config':<12}{'g':>4}{'tasks':>7}{'Pass@1':>9}{'Verifier':>10}"
           f"{'Oracle':>8}{'pairAcc':>9}{'trialAUC':>10}{'deg<1e-3':>10}")
    print(hdr)
    print("-" * len(hdr))
    for r in runs:
        pa = r["pairwise_agree"] / r["pairwise_total"] if r["pairwise_total"] else float("nan")
        print(f"{r['tag']:<12}{r['granularity']:>4}{r['tasks']:>7}"
              f"{r['pass1'] / r['tasks']:>9.1%}{r['verifier'] / r['tasks']:>10.1%}"
              f"{r['oracle'] / r['tasks']:>8.1%}{pa:>9.1%}{r['trial_auc']:>10.3f}"
              f"{r['degeneracy']['share_within_1e-3']:>10.1%}")

    if len(runs) == 2:
        a, b = runs
        both = sum(1 for t in a["selected"] if t in b["selected"]
                   and a["selected"][t] == b["selected"][t])
        same_ok = sum(1 for t in a["selected"] if t in b["selected"]
                      and a["selected"][t] == b["selected"][t]
                      and tasks[t][a["selected"][t]]["reward"] == 1)
        print(f"\nidentical selection on {both}/{a['tasks']} tasks "
              f"({same_ok} of those correct)")
        print(f"per-task selection (g20 vs g5):")
        for t in sorted(a["selected"]):
            ia, ib = a["selected"][t], b["selected"][t]
            r = [x["reward"] for x in tasks[t]]
            mark = "  " if ia == ib else "≠ "
            print(f"  {mark}{t:42} rewards={r} g20->{ia}({r[ia]}) "
                  f"g5->{ib}({r[ib]})")

    if args.json:
        json.dump(runs, open(args.json, "w"), indent=2)
        print(f"\nwritten: {args.json}")


if __name__ == "__main__":
    main()
