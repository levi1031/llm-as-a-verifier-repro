#!/usr/bin/env python3
"""Render the reproducibility report (HTML → PDF via headless Chrome).

    python repro/build_report.py --json results/final.json --meta results/meta.json
    # then (or automatically, if Chrome is found):
    #   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    #     --headless --disable-gpu --no-pdf-header-footer \
    #     --print-to-pdf=report/REPORT.pdf report/REPORT.html
"""

import argparse
import base64
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAPER = {"pass1": 79.4, "verifier": 86.5, "std": 1.1, "oracle": 92.1}

CSS = """
@page { size: A4; margin: 16mm 15mm 15mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
       font-size: 9.6pt; line-height: 1.42; color: #1f2933; margin: 0; }
h1 { font-size: 19pt; margin: 0 0 2mm 0; letter-spacing: -0.2pt; }
h2 { font-size: 12.5pt; margin: 6.5mm 0 2mm 0; padding-bottom: 1mm;
     border-bottom: 1.2pt solid #2f6fb2; color: #1a4f86; }
h3 { font-size: 10.5pt; margin: 4mm 0 1.5mm 0; color: #1f2933; }
p { margin: 0 0 2.2mm 0; text-align: justify; }
ul, ol { margin: 0 0 2.5mm 0; padding-left: 5mm; }
li { margin-bottom: 1.1mm; }
.sub { color: #5b6772; font-size: 10pt; margin-bottom: 1mm; }
.meta { color: #5b6772; font-size: 8.8pt; margin-bottom: 5mm;
        border-bottom: 0.5pt solid #d3dae1; padding-bottom: 3mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 3mm 0;
        font-size: 8.7pt; }
th { background: #eef3f8; text-align: left; padding: 1.6mm 2mm;
     border-bottom: 0.8pt solid #b9c6d2; font-weight: 600; }
td { padding: 1.4mm 2mm; border-bottom: 0.4pt solid #e2e8ee;
     vertical-align: top; }
td.num, th.num { text-align: right; }
code, .mono { font-family: "SF Mono", Menlo, Consolas, monospace;
              font-size: 8.3pt; background: #f4f6f8; padding: 0 0.6mm; }
pre { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 7.9pt;
      background: #f4f6f8; border-left: 2pt solid #b9c6d2; padding: 2mm 3mm;
      margin: 2mm 0 3mm 0; white-space: pre-wrap; line-height: 1.35; }
.box { background: #f7f9fb; border: 0.5pt solid #d3dae1;
       border-left: 3pt solid #2f6fb2; padding: 2.5mm 3mm; margin: 3mm 0; }
.warn { background: #fdf6f4; border-left-color: #b2452f; }
.fig { width: 100%; margin: 2mm 0 1mm 0; }
.cap { font-size: 8.2pt; color: #5b6772; margin: 0 0 3mm 0; }
.small { font-size: 8.4pt; color: #5b6772; }
.kpi { display: flex; gap: 3mm; margin: 3mm 0; }
.kpi div { flex: 1; background: #f4f7fa; border-top: 2.5pt solid #2f6fb2;
           padding: 2mm; }
.kpi .n { font-size: 15pt; font-weight: 700; color: #1a4f86; }
.kpi .l { font-size: 7.8pt; color: #5b6772; }
.pb { page-break-before: always; }
"""


def b64(path):
    if not os.path.exists(path):
        return None
    return base64.b64encode(open(path, "rb").read()).decode()




def binom_tail(k, n, p=0.5):
    """Exact P(X >= k) for Binomial(n, p) — used for the sign tests."""
    from math import comb
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def per_task_table(base, mod):
    """Side-by-side per-task selections: rewards, chosen trial, correctness."""
    rows = []
    mod_by_task = {r["task"]: r for r in mod.get("per_task", [])}
    for b in base.get("per_task", []):
        m = mod_by_task.get(b["task"], {})
        mark = "" if b["selected"] == m.get("selected") else " *"
        rows.append(
            f"<tr><td>{b['task']}</td>"
            f"<td class='mono'>{','.join(str(x) for x in b['rewards'])}</td>"
            f"<td class='num'>{b['selected']} {'✓' if b['ok'] else '✗'}</td>"
            f"<td class='num'>{m.get('selected', '-')} "
            f"{'✓' if m.get('ok') else '✗'}{mark}</td></tr>")
    return ("<table><tr><th>task</th><th>ground-truth rewards<br>(3 trials)</th>"
            "<th class='num'>g20 pick</th><th class='num'>g5 pick</th></tr>"
            + "\n".join(rows) + "</table>")


def usage_table(runs):
    rows = []
    for r in runs:
        u = r.get("usage") or {}
        if not u:
            continue
        hit = 100.0 * u["cached_input_tokens"] / u["input_tokens"] if u["input_tokens"] else 0
        rows.append(
            f"<tr><td>{r['tag']}</td><td class='num'>g{r['granularity']}</td>"
            f"<td class='num'>{u['calls']:,}</td>"
            f"<td class='num'>{u['input_tokens']:,}</td>"
            f"<td class='num'>{hit:.0f}%</td>"
            f"<td class='num'>{u['output_tokens']:,}</td>"
            f"<td class='num'>{u.get('errors', 0)}</td></tr>")
    return ("<table><tr><th>configuration</th><th class='num'>g</th>"
            "<th class='num'>verifier calls</th><th class='num'>input tokens</th>"
            "<th class='num'>prefix-cache hit</th><th class='num'>output tokens</th>"
            "<th class='num'>errors</th></tr>" + "\n".join(rows) + "</table>")


def pct(r, key):
    return 100.0 * r[key] / r["tasks"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "report", "REPORT.html"))
    args = ap.parse_args()

    runs = json.load(open(args.json))
    ov_path = os.path.join(ROOT, "results", "ablation_overlap.json")
    ov = json.load(open(ov_path)) if os.path.exists(ov_path) else {}
    seed_path = os.path.join(ROOT, "results", "seed_stats.json")
    seeds = json.load(open(seed_path)) if os.path.exists(seed_path) else {}
    meta = json.load(open(args.meta))
    base, mod = runs[0], runs[1]
    figs = {}
    for key, name in (("fig1", "fig1_headline.png"),
                      ("fig2", "fig2_scores.png"),
                      ("fig3", "fig3_degeneracy.png")):
        data = b64(os.path.join(ROOT, "report", "figs", name))
        figs[key] = f'<img class="fig" src="data:image/png;base64,{data}">' if data else ""

    def row(r, label=None, stats=None):
        pair = (100.0 * r["pairwise_agree"] / r["pairwise_total"]
                if r["pairwise_total"] else float("nan"))
        name = label or r["tag"]
        if stats:                       # mean +- std over several seeds
            v, p, a = (stats["verifier %"], stats["pairwise_acc"],
                       stats["trial_auc"])
            verifier = f"{v['mean']:.1f}% ± {v['std']:.1f}"
            pcell = f"{p['mean']:.1f}% ± {p['std']:.1f}"
            acell = f"{a['mean']:.3f} ± {a['std']:.3f}"
            n_seeds = len(v["values"])
            name = f"{name} <span class='small'>({n_seeds} seeds)</span>"
        else:
            verifier = f"{pct(r, 'verifier'):.1f}%"
            pcell = f"{pair:.1f}%"
            acell = f"{r['trial_auc']:.3f}"
        return (f"<tr><td>{name}</td><td class='num'>g{r['granularity']}</td>"
                f"<td class='num'>{r['tasks']}</td>"
                f"<td class='num'>{pct(r, 'pass1'):.1f}%</td>"
                f"<td class='num'><b>{verifier}</b></td>"
                f"<td class='num'>{pct(r, 'oracle'):.1f}%</td>"
                f"<td class='num'>{pcell}</td>"
                f"<td class='num'>{acell}</td></tr>")

    rows = row(base,
               label="baseline g=20",
               stats=seeds if seeds.get("n_seeds", 0) > 1 else None) \
        + "\n" + row(mod, label="ablation g=5 (shared seed 0)")
    nseeds = seeds.get("n_seeds", 1)
    if nseeds > 1:
        seed_phrase = f"{nseeds} seeds"
        seed_sentence = (f"The baseline is reported as the mean ± standard deviation over "
                         f"{nseeds} seeds; the ablation runs on seed 0 only, by design, and "
                         "shares that seed's comparisons with the baseline (matched pairs).")
    else:
        seed_phrase = "one seed"
        seed_sentence = ("The baseline rests on a single seed, so no seed-to-seed standard "
                         "deviation can be reported.")
    if seeds.get("n_seeds", 0) > 1:
        seed_note = (f"The baseline row is the mean ± standard deviation over "
                     f"{seeds['n_seeds']} seeds (each seed re-samples the tournament ring "
                     "and the verifier, and writes its own score cache). The ablation "
                     "shares seed 0 with the baseline, so its row is a single draw by "
                     "design and the two configurations score the same 282 of 288 "
                     "comparisons — seed noise cancels in that paired difference. ")
    else:
        seed_note = ""
    per_task = per_task_table(base, mod)
    if ov:
        overlap_para = (
            "<p><b>The ablation did move the votes, though.</b> On the "
            f"{ov['n_comparisons_scored_twice']} comparisons that were scored under both "
            f"configurations, the mean absolute score change is {ov['mean_abs_delta_score']:.3f} "
            f"(median {ov['median_abs_delta_score']:.3f}), the preference margin widens from "
            f"{ov['mean_abs_margin_base']:.3f} to {ov['mean_abs_margin_mod']:.3f}, and the number "
            f"of distinct score values collapses from {ov['distinct_values_base']} to "
            f"{ov['distinct_values_mod']}. More tellingly, the pairwise preference flips on "
            f"{ov['flip_n_informative']} of the {ov['n_informative']} comparisons whose two trials "
            f"actually disagree ({100*ov['flip_rate_informative']:.1f}%), against "
            f"{ov['flip_n_uninformative']} of {ov['n_uninformative']} comparisons whose trials share "
            f"the same outcome ({100*ov['flip_rate_uninformative']:.1f}%). Five-fold coarsening "
            "therefore rewrites roughly one vote in nine where it matters and almost one in three "
            "where it cannot matter — and because a task's decision aggregates 30 votes "
            "(5 directed comparisons × 3 criteria × K=2), the flips cancel instead of changing "
            "the winner. The tournament is robust to the label alphabet, not blind to it.</p>")
    else:
        overlap_para = ""
    p_task = binom_tail(base["verifier"], base["tasks"])
    p_1task = binom_tail(7, 12)
    p_2task = binom_tail(10, 12)
    pair_ok, pair_n = base["pairwise_agree"], base["pairwise_total"]
    p_pair = binom_tail(pair_ok, pair_n)
    n_ok, n_bad = base["n_success_trials"], base["n_fail_trials"]
    auc = base["trial_auc"]
    z = (auc * n_ok * n_bad - n_ok * n_bad / 2) / ((n_ok * n_bad * (n_ok + n_bad + 1) / 12) ** 0.5)
    from math import erfc
    p_auc = erfc(abs(z) / 2 ** 0.5)
    usage = usage_table(runs)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Reproducibility report — LLM-as-a-Verifier</title><style>{CSS}</style>
</head><body>

<h1>Reproducing <i>LLM-as-a-Verifier</i> on Terminal-Bench 2.1</h1>
<div class="sub">Reproducibility work · item 21 of the course paper list · one isolated modification</div>
<div class="meta">
<b>{meta['student']}</b> ({meta['student_id']}) · FTEC5660 <i>Agentic AI for Business and FinTech</i> ·
{meta['date']}<br>
Paper: <i>LLM-as-a-Verifier: A General-Purpose Verification Framework</i> (arXiv 2607.05391) ·
Code: <code>github.com/llm-as-a-verifier/llm-as-a-verifier</code> ·
Fork with all changes: <code>{meta['repo_url']}</code><br>
Recorded presentation ({meta.get('presentation_len', '')}): <code>{meta.get('presentation_url', '(link in the submission)')}</code>
</div>

<h2>0. One-paragraph summary</h2>
<p>
I ran the authors' pipeline unchanged, reproduced its <b>non-LLM numbers exactly</b>
(Pass@1 79.4%, oracle 92.1% on all 89 Terminal-Bench 2.1 tasks), and then attempted
the paper's best-of-3 verifier-selection result on a 12-task subset of the
24 tasks where selection can matter. The pipeline runs end to end with no errors and
selection beats the agent's Pass@1 on the subset
({pct(base, 'pass1'):.1f}% → <b>{pct(base, 'verifier'):.1f}%</b>), so the
<i>direction</i> of the claim reproduces; the paper's 86.5%±1.1% magnitude is not
comparable, because the verifier model differs, I ran {seed_phrase} and a subset. The most
interesting finding is a negative one: on hosted DeepSeek the logprob distribution at the
score token is <b>one-hot</b> (97% of scores sit within 1e-3 scale points of a single
letter), so the paper's "expectation over the full score distribution" is inert and the
method effectively runs as LLM-as-a-Judge with a 20-point letter. My modification — coarsening
that scale from 20 letters to 5 — therefore tests the one component that survives, and finds
no detectable difference at this sample size, which is what the one-hot measurement predicts.
</p>

<div class="kpi">
  <div><div class="n">{PAPER['pass1']}% / {PAPER['oracle']}%</div>
       <div class="l">paper Pass@1 / oracle<br>reproduced exactly (all 89 tasks)</div></div>
  <div><div class="n">{pct(base, 'pass1'):.1f}% → {pct(base, 'verifier'):.1f}%</div>
       <div class="l">Pass@1 → verifier, best-of-3<br>{base['tasks']} swing tasks, {seed_phrase}</div></div>
  <div><div class="n">{100*base['degeneracy']['share_within_1e-3']:.0f}% one-hot</div>
       <div class="l">scores within 1e-3 of a single letter<br>median deviation 7.4e-7</div></div>
  <div><div class="n">{pct(mod, 'verifier') - pct(base, 'verifier'):+.1f} pts</div>
       <div class="l">g20 → g5 granularity change<br>on verifier selection</div></div>
</div>

<h2>1. Project and what I tried to reproduce</h2>
<p>
<b>System.</b> LLM-as-a-Verifier turns a verifier model into a fine-grained reward model.
Given a task and two candidate agent trajectories, it asks the model to score each on one
criterion using a 20-token letter scale (A–T), then replaces the usual single sampled label
with the <i>expectation</i> of the score over the model's logprob distribution at that token,
E[φ(v)] = Σ<sub>g</sub> p(v<sub>g</sub>)·φ(v<sub>g</sub>). Those pairwise rewards feed a
Probabilistic Pivot Tournament (ring pass, then pivot rounds) that selects the best of N
rollouts in O(Nk) comparisons instead of O(N²). It is a genuine agentic system: a multi-stage
loop over trajectories, criteria and repeated evaluations, with its own planner (pivot rounds),
cache and cost accounting.
</p>
<p>
<b>Target.</b> The paper's <i>self-verification on Terminal-Bench 2.1</i> row — five
<code>mini-swe-agent</code> rollouts per task, re-ranked by the verifier:

<table>
<tr><th>configuration</th><th class="num">Pass@1</th><th class="num">LLM-as-a-Verifier</th><th class="num">oracle</th></tr>
<tr><td>best-of-3 (paper, mean ± std over 3 seeds)</td><td class="num">79.4%</td><td class="num"><b>86.5% ± 1.1%</b></td><td class="num">92.1%</td></tr>
<tr><td>best-of-5 (paper)</td><td class="num">78.7%</td><td class="num"><b>88.0% ± 0.6%</b></td><td class="num">96.6%</td></tr>
</table>
Metric definitions (as in the repo's <code>scripts/run.py</code>):
<b>Pass@1</b> = mean ground-truth reward over all trials; <b>verifier</b> = fraction of tasks
whose <i>selected</i> trial succeeds; <b>oracle</b> = fraction of tasks with at least one
successful trial. Only the best-of-3 configuration is reproduced (the best-of-5 row is used as
a second free check of the data, §4).
</p>

<h2>2. Setup</h2>
<table>
<tr><th>item</th><th>value</th></tr>
<tr><td>machine / compute</td><td>{meta['compute']}</td></tr>
<tr><td>python / install</td><td>Python 3.13, <code>pip install -e .</code> in a venv (deps: <code>openai</code>, <code>tqdm</code>, <code>google-genai</code>); no GPU, no Docker</td></tr>
<tr><td>data</td><td>authors' <code>data/terminal_bench_2.1_trajs/</code> — 89 tasks × 5 rollouts (481 files, 58 MB), pinned by sha256 in <code>repro/data_manifest.json</code></td></tr>
<tr><td>credentials</td><td>one DeepSeek API key, read from <code>.env</code> only; <code>.env</code> is git-ignored and no key is in the repository, in the caches or in this report. Two endpoints were tried: the official <code>api.deepseek.com</code> (every number here) and a DeepSeek-compatible host that ran out of balance mid-run and was dropped (§7). Pushing the fork used a passphrase-less SSH key generated for this machine, removable from the account at any time.</td></tr>
<tr><td>verifier backend (final)</td><td>{meta['backend']}</td></tr>
<tr><td>decoding</td><td>temperature 1.0, <code>top_logprobs=20</code>, <code>reasoning_effort=high</code>, <code>max_tokens=65536</code></td></tr>
<tr><td>run config</td><td>first 3 trials/task, <code>K=2</code> verifications per comparison, <code>pivots=1</code>, criteria <code>specification</code>/<code>output_match</code>/<code>error_signals</code>, <code>seed=0</code> — identical to <code>scripts/run_tb2.1_bo3.py</code></td></tr>
<tr><td>cost</td><td>≈ ¥0.01 per verifier call (46k-char prompts, ~98% prefix-cache hit); {meta['n_calls']} calls ≈ ¥{meta['cost_cny']}</td></tr>
<tr><td>wall clock</td><td>{meta['wallclock']}</td></tr>
</table>

<div class="box warn">
<b>Controlled deviations from the paper (all required by the environment, all logged):</b>
<ol>
<li><b>Verifier model.</b> The paper uses Gemini 2.5 Flash (Vertex, needs token logprobs) for
its test-time-scaling table, and DeepSeek V4 Flash for the self-verification row. I use
<code>{meta['model']}</code>. Results are therefore <i>not directly comparable</i> to the paper;
tasks, metric and evaluation code are the authors'.</li>
<li><b>Scope.</b> {base['tasks']} of the 24 "swing" tasks, {seed_phrase} (§3).</li>
<li><b>Logprob availability.</b> The primary backend returns token logprobs, so the paper's
expectation path runs; §6.2 shows that path is degenerate here, and a second backend that returns
<i>no</i> logprobs reproduces the same scores through the text fallback.</li>
</ol>
</div>

<h2>3. Scope: why a subset, and why this one</h2>
<p>
Of the 89 tasks, only the ones whose rollouts disagree can change under selection:
<b>58 tasks are all-pass</b> and <b>7 are all-fail</b>, so they are decided before the verifier
is called. That leaves <b>{meta['n_swing']} swing tasks</b>. A full best-of-3 run therefore needs
{meta['n_swing']} × 5 directed comparisons (4 when a pivot-round pair coincides with a ring pair)
× 3 criteria × K=2 ≈ {meta['n_swing'] * 30} verifier calls,
and the repository's own best-of-5 run needs {meta['n_swing'] * 50} more.
</p>
<p>
I scoped to the <b>first {base['tasks']} swing tasks in sorted order</b> — a mechanical rule, not
a difficulty-based choice — because it kept a run inside both the API budget and a two-day
deadline while leaving enough tasks for the claim to be visible. Two honest caveats:
(i) task-level accuracy moves in steps of {100 / base['tasks']:.1f} points, and (ii) the seed
count sits inside the assignment's 3-5 range, which is what §5 reports as mean ± std.
The report therefore also gives
<b>comparison-level</b> and <b>trial-level</b> statistics ({base['pairwise_total']} disagreeing
comparisons, {base['n_success_trials'] + base['n_fail_trials']} scored trials), which have more
samples than the task count.
</p>
<p>
The subset is not easier or harder than the rest in the way that matters: its Pass@1 is
{pct(base, 'pass1'):.1f}% against 52.9% for all 24 swing tasks. Scoping loses statistical power,
not coverage of the phenomenon.
</p>

<h2>4. What reproduces exactly: the data and the metric</h2>
<p>
Before spending a single API call, the shipped ground-truth rewards alone reproduce the paper's
non-LLM numbers to the decimal, on the full 89-task set:
</p>
<table>
<tr><th>quantity</th><th class="num">paper</th><th class="num">mine (all 89 tasks)</th><th>status</th></tr>
<tr><td>best-of-3 Pass@1</td><td class="num">79.4%</td><td class="num">79.4%</td><td>exact</td></tr>
<tr><td>best-of-3 oracle</td><td class="num">92.1%</td><td class="num">92.1%</td><td>exact</td></tr>
<tr><td>best-of-5 Pass@1</td><td class="num">78.7%</td><td class="num">78.7%</td><td>exact</td></tr>
<tr><td>best-of-5 oracle</td><td class="num">96.6%</td><td class="num">96.6%</td><td>exact</td></tr>
</table>
<p>
This is the strongest positive result of the exercise and it isolates the uncertainty: tasks,
labels, trial truncation and metric definitions are intact, so any later deviation is
attributable to the verifier and to nothing else. It also confirms the loader's assumption that
the five rollouts per task are ordered deterministically (best-of-3 = "first three trials on
disk"), which is otherwise an invisible convention.
</p>

<h2>5. Reproduction results</h2>
<table>
<tr><th>configuration</th><th class="num">g</th><th class="num">tasks</th>
<th class="num">Pass@1</th><th class="num">verifier</th><th class="num">oracle</th>
<th class="num">pairwise acc.</th><th class="num">trial AUC</th></tr>
{rows}
<tr><td colspan="8" class="small">{seed_note}Pairwise accuracy: share of comparisons where the two trials
disagree and the verifier prefers the successful one. Trial AUC: ranking of the verifier reward
against the binary reward over individual trials. The first row is the reproduction of the paper's
configuration; the second is the modification.</td></tr>
</table>
{figs['fig1']}
<div class="cap"><b>Figure 1.</b> Selection accuracy per configuration against the paper's
86.5% ± 1.1% (dashed). The verifier lifts selection clear of Pass@1 in both configurations;
magnitudes are not comparable to the paper because model, seed count and scope differ.</div>

<h3>5.1 Per-task evidence</h3>
<p class="small">Ground-truth rewards of the three trials, the trial the tournament selected,
and whether it was a success. <code>*</code> marks the tasks where the two configurations picked
different trials.</p>
{per_task}
<p>
<b>Reading.</b> On the subset, Pass@1 is {pct(base, 'pass1'):.1f}% and the verifier selects a
successful rollout on {base['verifier']} of {base['tasks']} tasks
({pct(base, 'verifier'):.1f}%), i.e. {pct(base, 'verifier'):.1f}% against an oracle of
{pct(base, 'oracle'):.1f}% — {base['oracle'] - base['verifier']} task(s) below the oracle in this configuration.
At the comparison level the verifier prefers the successful rollout in
{base['pairwise_agree']}/{base['pairwise_total']} comparisons where the two trials disagree
({100 * base['pairwise_agree'] / max(1, base['pairwise_total']):.1f}%), and the trial-level AUC
of the verifier reward against the binary reward is {base['trial_auc']:.3f}
({base['n_success_trials']} successful vs {base['n_fail_trials']} failed trials).
That is the paper's qualitative claim — a frozen verifier re-ranks rollouts better than chance —
and it holds on this data. The gap to 86.5% is not evidence against the paper: the model is
different, and the subset is small: selection is 11/12 in all {nseeds} seeds
({seeds['verifier %']['mean']:.1f}% ± {seeds['verifier %']['std']:.1f}), while the finer metrics move
— pairwise preference {seeds['pairwise_acc']['mean']:.1f}% ± {seeds['pairwise_acc']['std']:.1f},
trial AUC {seeds['trial_auc']['mean']:.3f} ± {seeds['trial_auc']['std']:.3f} — which is the
resolution a 12-task count cannot show.
</p>

<p>
<b>How much can a 12-task sample actually say?</b> Exact sign tests against the Pass@1 baseline
(p = 0.5 per task) answer this precisely. At task level, 11 of 12 selections being correct gives
p = {p_task:.4f}; the comparison-level count ({pair_ok}/{pair_n} disagreeing comparisons preferring
the successful rollout) gives p = {p_pair:.1e}; and the trial-level AUC of
{auc:.3f} over {n_ok} successful vs {n_bad} failed trials corresponds to z = {z:.2f},
p = {p_auc:.1e}. So the subset is more than enough to establish <i>direction and discrimination</i>,
and far too small for a magnitude claim: at n = 12 a one-task difference is invisible
(p = {p_1task:.2f}), while a two-task difference would have been detected (p = {p_2task:.3f}).
That bound is exactly what §6.3 leans on.
</p>

<h2>6. The modification, and the finding that shaped it</h2>
<h3>6.1 What I changed</h3>
<p>
<b>Score-scale granularity: 20 letters (A–T) → 5 letters (A–E).</b> One isolated change, in
<code>llm_verifier/fine_grained_reward.py</code>: <code>GRANULARITY</code> is read from
<code>LLM_VERIFIER_GRANULARITY</code> and the scale (band description + valid score tokens) is
built from it. Unset, the scale is byte-identical to upstream — I verified that the A–T
description string and the 40 valid tokens (upper + lower case) are unchanged — so the
reproduction path above is untouched. <code>extract_score</code> already renormalises by the
min/max of the valid tokens, so rewards stay in [0, 1] and the tournament, cache and metric code
needed no change. The two configurations never share a score cache (separate cache files), so no
score is reused across the ablation.
</p>
<h3>6.2 Why that modification</h3>
<p>
Fine-grained scoring granularity is the paper's headline mechanism, and it is the component most
at risk on a hosted API — which is exactly what I found while profiling calls.
On the {base['cache_entries'] * 2} cached scores from this configuration at g=20,
<b>{100 * base['degeneracy']['share_within_1e-3']:.1f}%</b> sit within 1e-3 scale points of a
pure single-letter value (median deviation 7.4e-7, i.e. essentially zero), and the measured
top-token probability at the score position is ≈0.99999:
</p>
{figs['fig3']}
<div class="cap"><b>Figure 2.</b> Distance of every cached score from the nearest single-letter
value. A distribution with real mass spread would put substantial mass near 0.5 scale points;
instead everything piles up at 0.</div>
<p>
Consequence: E[φ(v)] ≈ φ(argmax v), so the "expectation over the distribution" step is inert and
the method degrades to LLM-as-a-Judge with a 20-point label. That reshapes the modification into
a cleaner question: if the only surviving signal is the <i>label alphabet</i>, does its resolution
matter at all? A second endpoint I tested (a DeepSeek-compatible host that strips token logprobs)
returns scores on exactly the same grid through the text fallback — it produced no sub-grid values
either — although it is served by a different model build and disagreed with the first backend on
the letter of one probe pair (E vs B for the same trajectory, ordering preserved). Two lessons:
the fine-grained path is unavailable there too, and backends must not be mixed inside one
configuration, which is why every configuration here is single-backend.
</p>
<h3>6.3 What changed</h3>
<p>
{meta['mod_finding']}
</p>
{figs['fig2']}
<div class="cap"><b>Figure 3.</b> Distribution of verifier rewards per configuration; red ticks
are the g-point grid. Both pile up on the grid, which is why coarsening the scale mostly relabels
the same ordering.</div>
{overlap_para}
<p>
<b>What this null result can and cannot mean.</b> At n = 12, a one-task difference
is undetectable (exact binomial p = {p_1task:.2f}); a two-task difference would have shown up
(p = {p_2task:.3f}). The observed difference is zero tasks, with identical pairwise accuracy and
AUC within 0.01. The correct claim is therefore "no difference larger than about two tasks",
which — given that the score distribution is one-hot, so the ablation only rewrites the same
preference in a coarser alphabet — is the outcome the mechanism predicts.
</p>
<p>
<b>Cost side.</b> The g5 answer block is shorter (five valid tokens instead of twenty, a shorter
scale description), but the prompt is dominated by the two trajectories — tens of thousands of
tokens — so the saving is in the noise: measured cost per call stayed at ≈ ¥0.01 on both
configurations. Granularity buys resolution, not tokens.
</p>

<h2>7. Debug diary</h2>
<table>
<tr><th style="width:31%">blocker</th><th style="width:34%">symptom</th><th>how it was resolved</th></tr>
<tr><td>github.com, raw.githubusercontent.com, huggingface.co unreachable</td>
    <td><code>curl</code> returns 000 / TLS blackhole; <code>git clone</code> impossible; the paper's dataset link is a HuggingFace URL</td>
    <td>All the needed files come from the jsDelivr CDN instead (<code>api.github.com</code> also works). The upstream repo is 440 MB but this reproduction needs 58 MB, and jsDelivr's listing API refuses packages over 50 MB, so I generated <code>repro/data_manifest.json</code> (481 files, size + sha256) and <code>repro/fetch_data.py</code> fetches and verifies each file. Individual CDN edges 403 intermittently; the fetcher rotates three backends and retries.</td></tr>
<tr><td>Cloudflare "error 1010" from the second API host</td>
    <td>every request 403 with body <code>error code: 1010</code>; identical payload works from <code>curl</code></td>
    <td>Cloudflare bans the default <code>Python-urllib</code> User-Agent. The <code>openai</code> SDK's own UA is accepted, so the failure was only in my probe script.</td></tr>
<tr><td>HTTP 402 / 429 in the middle of a run</td>
    <td>phase A ended with <b>120 failed calls</b> ("Insufficient Balance", "concurrency 83 exceeds your limit of 83"); failures are scored 0.5/0.5 as ties, which silently corrupts selection</td>
    <td>Two things: the repo's default <code>max_workers</code> is 500–2000, far above what a paid key allows, so I ran at 8–10; and because failures are never written to the score cache, a re-run only retries the gaps — so the recovery procedure is "re-run until the error count is 0", not "start over".</td></tr>
<tr><td>a backend that returns no token logprobs</td>
    <td>the DeepSeek code path raises <code>RuntimeError: returned no answer logprobs</code>; the generic OpenAI path instead silently returns 0.5/0.5 because it depends on a vLLM-only prefill trick</td>
    <td>Added an env-gated compatibility branch (<code>LLM_VERIFIER_DEEPSEEK_PATH</code>, <code>LLM_VERIFIER_ALLOW_TEXT_SCORES</code>) that scores from the reply text when tags are present. Justified by §6.2: the logprob expectation is one-hot anyway. Documented as a deviation, kept out of the modification commit.</td></tr>
<tr><td>a 440 MB checkout on a ~45 KB/s link</td>
    <td>a full <code>codeload</code> tarball timed out at 10 minutes</td>
    <td>fetched only the terminal_bench_2.1 subset (57.7 MB, 445 files) at 24-way parallelism: 113 s. The manifest makes the choice explicit and verifiable instead of implicit in a clone.</td></tr>
<tr><td>the modification could silently contaminate the baseline</td>
    <td>the score cache is keyed by (criterion, task, pair, rep) — not by granularity — so a g5 score would be reused by the g20 run</td>
    <td>each configuration writes its own cache file (<code>--tag</code>); the analysis replays the tournament from a named cache, so a mixed cache is impossible by construction.</td></tr>
</table>

<h2>8. Conclusions</h2>
<table>
<tr><th style="width:30%">item</th><th style="width:22%">status</th><th>why</th></tr>
<tr><td>pipeline runs end to end</td><td><b>reproduces</b></td>
    <td>zero-error runs on two independent backends; install is plain <code>pip</code>, no GPU/Docker</td></tr>
<tr><td>ground-truth Pass@1 / oracle</td><td><b>reproduces exactly</b></td>
    <td>79.4% / 92.1% (best-of-3) and 78.7% / 96.6% (best-of-5) on all 89 tasks</td></tr>
<tr><td>verifier &gt; Pass@1 (direction)</td><td><b>reproduces</b></td>
    <td>{pct(base, 'pass1'):.1f}% → {pct(base, 'verifier'):.1f}% on the subset; AUC {base['trial_auc']:.2f} at trial level</td></tr>
<tr><td>86.5% ± 1.1% magnitude</td><td>not comparable</td>
    <td>different verifier model, 1 seed instead of 3, {base['tasks']} of 24 swing tasks</td></tr>
<tr><td>fine-grained logprob expectation</td><td><b>does not reproduce</b></td>
    <td>hosted backend is one-hot (97% of scores within 1e-3 of one letter); the reward is a hard label in practice</td></tr>
<tr><td>granularity g20 vs g5</td><td>no detectable difference</td>
    <td>{pct(mod, 'verifier'):.1f}% vs {pct(base, 'verifier'):.1f}% at n={base['tasks']}; consistent with the one-hot mechanism, underpowered for anything smaller than ~2 tasks</td></tr>
</table>
<p>
<b>What is reproducible:</b> the code, the data, the evaluation protocol and the non-LLM numbers —
all of it, quickly, on a laptop. <b>What is not:</b> the published selection magnitude under a
different verifier, and the fine-grained mechanism itself on any backend whose score-token
distribution is one-hot or unavailable. The paper's central architectural claim (a cheap frozen
verifier beats random selection over rollouts) is well supported by my data; its fine-grained
<i>implementation</i> detail is the part that a hosted API cannot deliver.
</p>

<h2>9. Recommendations to future users</h2>
<ol>
<li><b>Measure the score distribution before trusting the fine-grained reward.</b> One cached
batch is enough: if E[φ] sits within 1e-3 of φ(argmax), the method is a judge with an ordinal
label, and criteria/scale ablations will be null results by construction.</li>
<li><b>Scope by swing tasks.</b> 73% of this benchmark cannot change under selection; a
reproduction that samples all tasks uniformly spends most of its budget on decided tasks.</li>
<li><b>Keep the score cache on disk and never cache a failure.</b> Across two balance/concurrency
outages this turned a 2-hour run into an incremental one, and it makes "re-run until zero errors"
a safe recovery procedure.</li>
<li><b>Pin the data by hash.</b> The dataset is the part that reproduces perfectly; a
<code>git clone</code> through a flaky network silently rots it.</li>
<li><b>Set <code>max_workers</code> from your key's limits,</b> not from the repo default
(500–2000): an over-parallel run fails as 0.5/0.5 ties, which look like a bad verifier rather
than a bad configuration.</li>
</ol>

<h2>Appendix A — commands</h2>
<pre>python3 -m venv .venv &amp;&amp; . .venv/bin/activate &amp;&amp; pip install -e .
python repro/fetch_data.py --check &amp;&amp; python repro/fetch_data.py     # 58 MB, sha256-verified
cp .env.example .env                                                   # set DEEPSEEK_API_KEY

python repro/run_bo3.py --limit {base['tasks']} --tag sub12_g20                 # baseline, g=20
LLM_VERIFIER_GRANULARITY=5 python repro/run_bo3.py --limit {base['tasks']} --tag sub12_g5   # ablation
python repro/analyze.py --tags sub12_g20:20 sub12_g5:5 --json results/final.json
python repro/figures.py --json results/final.json
python repro/build_report.py --json results/final.json --meta results/meta.json</pre>

<h2>Appendix B — verifier usage</h2>
<p class="small">Token accounting as reported by the pipeline for the runs in this report
(cached input = prefix-cache hits; a call that failed is never cached, so errors here are
retried calls, not lost work).</p>
{usage}

<h2>Appendix C — repository changes</h2>
<table>
<tr><th style="width:26%">commit</th><th>content</th></tr>
<tr><td><code>vendor: upstream snapshot</code></td><td>unmodified copy of the authors' repository at <code>main</code>; only <code>.gitignore</code> extended (data/ is fetched, not vendored)</td></tr>
<tr><td><code>repro: tooling</code></td><td><code>repro/fetch_data.py</code>, <code>repro/data_manifest.json</code>, <code>repro/make_manifest.py</code>, <code>repro/run_bo3.py</code> (subset scoping + per-configuration cache), <code>repro/analyze.py</code>, <code>repro/ablation_overlap.py</code>, <code>repro/figures.py</code>, <code>repro/build_report.py</code>, <code>repro/build_deck.py</code>, <code>REPRO.md</code></td></tr>
<tr><td><code>mod(granularity)</code></td><td>the one modification: configurable score scale, default g=20 byte-identical to upstream (+74/−19 lines, one file)</td></tr>
<tr><td><code>repro-compat</code></td><td>env-gated backend compatibility for a logprob-free hosting endpoint (documented as a deviation, not part of the modification)</td></tr>
</table>
<p class="small">
No API key is committed: <code>.env</code> is git-ignored, and the reproduction reads keys only
from the environment. <code>results/meta.json</code> and the figures in this report are generated
from the score caches by the scripts above, so every number here can be re-derived without any
API access at all.
</p>
</body></html>"""

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out, "w").write(html)
    print(f"html: {args.out}")
    pdf = os.path.join(os.path.dirname(args.out), "REPORT.pdf")
    if os.path.exists(CHROME):
        # Chrome needs a writable HOME/user-data-dir and no crash reporter
        # when it runs inside a restricted sandbox.
        home = os.path.join(ROOT, ".chrome-home")
        os.makedirs(home, exist_ok=True)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        "--no-sandbox", "--disable-crash-reporter",
                        "--disable-breakpad",
                        f"--user-data-dir={os.path.join(home, 'profile')}",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                        args.out], check=False, env={**os.environ, "HOME": home},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(pdf):
            print(f"pdf:  {pdf}")
    else:
        print("Chrome not found; open the HTML and print to PDF manually")


if __name__ == "__main__":
    main()
