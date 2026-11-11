# Reproduction notes — LLM-as-a-Verifier (FTEC5660)

Reproducibility work for **item 21** of the course paper list:
[LLM-as-a-Verifier: A General-Purpose Verification Framework](https://arxiv.org/abs/2607.05391)
([code](https://github.com/llm-as-a-verifier/llm-as-a-verifier)).

**Student:** 李尚益 (Li Shangyi) · **ID:** 1155270838 · FTEC5660 *Agentic AI for Business and FinTech*

---

## 1. What is reproduced

The paper's **Terminal-Bench 2.1 self-verification** result: five
`mini-swe-agent` trajectories per task are re-ranked by the fine-grained
verifier, and selection should land well above the agent's own Pass@1.

| Config | Pass@1 | LLM-as-a-Verifier | Oracle |
|---|---|---|---|
| Best-of-3 (paper, mean ± std over 3 seeds) | 79.4% | **86.5% ± 1.1%** | 92.1% |
| Best-of-5 (paper) | 78.7% | **88.0% ± 0.6%** | 96.6% |

Only the **best-of-3** configuration is reproduced, on a deterministic
**12-task subset of the 24 "swing" tasks** (see §4). `Pass@1` and `Oracle` are
computed from the shipped ground-truth rewards and reproduce the paper's
numbers exactly on the full data (79.4% / 92.1%), which validates the dataset
and the metric definitions before any verifier call is made.

## 2. Install

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# 58 MB of package code + Terminal-Bench 2.1 trajectories (see §3)
python repro/fetch_data.py --check     # verify against pinned sha256
python repro/fetch_data.py             # download what is missing

cp .env.example .env                   # then set DEEPSEEK_API_KEY=...
```

`.env` is git-ignored; no key is ever committed. `data/` (58 MB) and the
runtime `cache/`, `results/`, `logs/` trees are git-ignored as well.

## 3. Why a CDN fetcher instead of `git clone`

On this machine `github.com`, `raw.githubusercontent.com` and
`huggingface.co` are unreachable from the shell, while the jsDelivr CDN is
not. The upstream repository is 440 MB, but this reproduction needs 58 MB
(package, criteria, scripts, Terminal-Bench 2.1 trajectories). jsDelivr still
serves individual files even though its listing API refuses packages over
50 MB, so `repro/data_manifest.json` pins the 481 needed files by path, size
and sha256, and `repro/fetch_data.py` pulls and verifies them.

## 4. Run

```bash
# the paper's configuration, scoped to the 12-task subset
python repro/run_bo3.py --limit 12 --tag sub12_g20

# the ablation: same everything, score scale g=5 (letters A-E)
LLM_VERIFIER_GRANULARITY=5 python repro/run_bo3.py --limit 12 --tag sub12_g5

# the paper's full-data best-of-3 (all 24 swing tasks, ~720 verifier calls)
python repro/run_bo3.py

# two more seeds of the reproduction target (stochastic pipeline: each seed
# re-samples the tournament ring and the verifier, own score cache)
python repro/run_bo3.py --limit 12 --tag sub12_g20_s1 --seed 1
python repro/run_bo3.py --limit 12 --tag sub12_g20_s2 --seed 2

# metrics tables from the score caches (no API calls)
python repro/analyze.py --tags sub12_g20:20 sub12_g5:5 --json results/final.json
python repro/seed_stats.py            # mean +- std over seeds 0,1,2
python repro/ablation_overlap.py      # what the ablation changed, vote by vote
```

Config pinned by `repro/run_bo3.py` (identical to `scripts/run_tb2.1_bo3.py`):
first 3 trials per task, `K=2` verifications per comparison, `pivots=1`,
criteria `specification`/`output_match`/`error_signals`, `seed=0`.
Verifier backend: `deepseek-flash` (DeepSeek V4.1 Flash), `temperature=1.0`,
`top_logprobs=20`, `reasoning_effort=high`, `max_tokens=65536`.

Subset definition: swing tasks sorted by name, first 12. It is not
cherry-picked; its Pass@1 (50.0%) is within 3 points of the full swing-task
Pass@1 (52.9%).

### Results (423 verifier calls, ≈¥4, ≈30 min)

| configuration | Pass@1 | LLM-as-a-Verifier | oracle | pairwise acc. | trial AUC |
|---|---|---|---|---|---|
| g=20 baseline, 3 seeds | 50.0% | **mean ± std, see `results/seed_stats.json`** | 100% | — | — |
| g=5 ablation, seed 0 | 50.0% | **91.7%** (11/12) | 100% | 90.6% | 0.852 |
| paper, best-of-3 | 79.4% | 86.5% ± 1.1% | 92.1% | — | — |

The non-LLM half of the paper's table reproduces **exactly** on all 89 tasks
(Pass@1 79.4% / oracle 92.1% for best-of-3; 78.7% / 96.6% for best-of-5). The
verifier gain reproduces in direction on the subset; the magnitude is not
comparable (different verifier model, one seed, 12 of 24 swing tasks). The
coarsening ablation changes nothing detectable — which is what the one-hot
measurement below predicts.

## 5. Modification

**Score-scale granularity: g=20 (A-T) → g=5 (A-E).** Isolated in
`llm_verifier/fine_grained_reward.py`, driven by `LLM_VERIFIER_GRANULARITY`;
unset, the scale is byte-identical to upstream, so the reproduction path is
unchanged. Two configurations never share a score cache (`--tag`).

Motivation, and the finding that shaped it: on this backend the logprob
distribution at the score token is effectively **one-hot** (97.2% of scores
are within 1e-3 scale points of a pure single-letter read, median deviation
7.4e-7), so the paper's "expectation over the full score distribution"
collapses into a hard label. If the fine-grained scale still mattered, it
would have to show up as a selection-accuracy difference on its own.

## 6. Layout of this fork

```
repro/               reproduction harness, data fetcher, analysis, report
                     and deck builders (added)
llm_verifier/        upstream package; fine_grained_reward.py carries the mod
scripts/  criteria/  upstream
report/              REPORT.pdf, presentation.pptx (brief speaker notes), figs
results/             final.json (all metrics), meta.json, result tables
cache/               the two score caches behind every number (checked in)
data/  logs/         fetched on demand / runtime, git-ignored
```

See `report/REPORT.pdf` for the write-up (targets, numbers, debug diary,
conclusions) and `report/presentation.pptx` for the 15-minute talk. The
slide deck ships with short reminder notes only: the word-for-word speaker
script is deliberately kept out of this repository and lives locally.
