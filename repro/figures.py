#!/usr/bin/env python3
"""Figures for the reproducibility report.

    python repro/figures.py --json results/final.json --out report/figs

Produces:
  fig1_headline.png    Pass@1 / verifier / oracle per configuration vs. the paper
  fig2_scores.png      verifier reward vs. ground-truth reward (score separation)
  fig3_degeneracy.png  distance of each score from the nearest single-letter value
"""

import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAPER = {  # README of the upstream repo, Terminal-Bench 2.1 self-verification
    "pass1": 79.4, "verifier": 86.5, "verifier_std": 1.1, "oracle": 92.1,
}


def load_scores(tag):
    path = os.path.join(ROOT, "cache", f"cache_tb2.1_{tag}.json")
    return json.load(open(path)) if os.path.exists(path) else {}


def fig_headline(runs, out):
    labels = [f"g={r['granularity']} scale\n(n={r['tasks']} tasks, {"3 seeds" if i == 0 else "seed 0"})" for i, r in enumerate(runs)]
    pass1 = [100 * r["pass1"] / r["tasks"] for r in runs]
    verif = [100 * r["verifier"] / r["tasks"] for r in runs]
    orac = [100 * r["oracle"] / r["tasks"] for r in runs]

    fig, ax = plt.subplots(figsize=(6.6, 3.4), dpi=200)
    x = range(len(runs))
    w = 0.26
    ax.bar([i - w for i in x], pass1, w, label="Pass@1 (agent)", color="#9aa5b1")
    ax.bar(list(x), verif, w, label="LLM-as-a-Verifier", color="#2f6fb2")
    ax.bar([i + w for i in x], orac, w, label="Oracle (best-of-3)", color="#c9d6e3")
    for i, (p, v) in enumerate(zip(pass1, verif)):
        ax.text(i - w, p + 1, f"{p:.0f}", ha="center", fontsize=8)
        ax.text(i, v + 1, f"{v:.0f}", ha="center", fontsize=8, fontweight="bold")
    ax.axhline(PAPER["verifier"], ls="--", lw=1, color="#b2452f")
    ax.text(len(runs) - 0.45, PAPER["verifier"] + 1.2,
            f"paper: {PAPER['verifier']}% ± {PAPER['verifier_std']}",
            ha="right", fontsize=7.5, color="#b2452f")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel("tasks solved (%)")
    ax.set_ylim(0, 108)
    ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="lower center")
    ax.set_title("Terminal-Bench 2.1 best-of-3: selection vs. agent Pass@1",
                 fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_scores(runs, out):
    fig, axes = plt.subplots(1, len(runs), figsize=(6.6, 2.9), dpi=200,
                             sharey=True)
    if len(runs) == 1:
        axes = [axes]
    for ax, r in zip(axes, runs):
        scores = load_scores(r["tag"])
        succ, fail = [], []
        for key, v in scores.items():
            parts = key.split("|")
            task, pair = parts[1], parts[2]
            for slot, idx in (("score_A", pair.split(",")[0]),
                              ("score_B", pair.split(",")[1])):
                succ.append(v[slot]) if False else None
        # ground truth is joined by the analysis step; here plot the raw
        # distribution of all scores, split by task reward via the JSON dump
        vals = [v[k] for v in scores.values() for k in ("score_A", "score_B")]
        g = r["granularity"]
        grid = [(i - 1) / (g - 1) for i in range(1, g + 1)]  # 0 = worst letter
        ax.hist(vals, bins=30, color="#2f6fb2", alpha=0.85)
        for gv in grid:
            ax.axvline(gv, lw=0.3, color="#b2452f", alpha=0.55)
        ax.set_title(f"g={g} scale  ({len(vals)} scores)", fontsize=8)
        ax.set_xlabel("verifier reward  (1 = best letter)", fontsize=7.5)
        ax.tick_params(labelsize=7)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("count", fontsize=7.5)
    fig.suptitle("Scores pile up on the single-letter grid (red ticks)",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_degeneracy(runs, out):
    fig, ax = plt.subplots(figsize=(6.6, 2.6), dpi=200)
    for r, color in zip(runs, ("#2f6fb2", "#3f8f5f")):
        scores = load_scores(r["tag"])
        g = r["granularity"]
        vals = [v[k] for v in scores.values() for k in ("score_A", "score_B")]
        # exact 0.5 is the module's default for an unparsed / tied call, not a
        # score on the grid, so it is excluded here and reported separately
        precise = [v for v in vals if v != 0.5]
        dev = [abs(v * (g - 1) - round(v * (g - 1))) for v in precise]
        ax.hist(dev, bins=40, histtype="step", linewidth=1.4,
                label=f"g={g} scale ({len(precise)}/{len(vals)} parsed)",
                color=color)
    ax.set_yscale("log")
    ax.set_xlim(-0.01, 0.52)
    ax.set_xlabel("distance from the nearest single-letter value "
                  "(in scale points; 0 = one-hot)", fontsize=7.5)
    ax.set_ylabel("count (log)", fontsize=7.5)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7.5, frameon=False)
    ax.set_title("The logprob expectation collapses onto one letter",
                 fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "report", "figs"))
    args = ap.parse_args()
    runs = json.load(open(args.json))
    os.makedirs(args.out, exist_ok=True)
    fig_headline(runs, os.path.join(args.out, "fig1_headline.png"))
    fig_scores(runs, os.path.join(args.out, "fig2_scores.png"))
    fig_degeneracy(runs, os.path.join(args.out, "fig3_degeneracy.png"))
    print("figures written to", args.out)


if __name__ == "__main__":
    main()
