#!/usr/bin/env python3
"""Build the 15-minute presentation (PPTX, with speaker notes) and a Markdown
script, from the same numbers the report uses.

    python repro/build_deck.py --json results/final.json --meta results/meta.json
"""

import argparse
import json
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLUE = RGBColor(0x2F, 0x6F, 0xB2)
DARK = RGBColor(0x1F, 0x29, 0x33)
GREY = RGBColor(0x5B, 0x67, 0x72)
RED = RGBColor(0xB2, 0x45, 0x2F)


def add_title_slide(prs, title, sub, meta):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(8.4), Inches(1.6))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    p.font.size = Pt(30)
    p.font.bold = True
    p.font.color.rgb = DARK
    tb2 = s.shapes.add_textbox(Inches(0.8), Inches(3.6), Inches(8.4), Inches(2.0))
    tf = tb2.text_frame
    tf.word_wrap = True
    for i, line in enumerate(sub):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(13)
        p.font.color.rgb = GREY
    tb3 = s.shapes.add_textbox(Inches(0.8), Inches(6.4), Inches(8.4), Inches(0.8))
    p = tb3.text_frame.paragraphs[0]
    p.text = meta
    p.font.size = Pt(10)
    p.font.color.rgb = GREY


def add_bullets(prs, title, bullets, notes="", image=None, footnote=""):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(8.8), Inches(0.9))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = BLUE

    body = s.shapes.add_textbox(Inches(0.6), Inches(1.25),
                               Inches(5.2 if image else 8.9), Inches(4.6))
    tf = body.text_frame
    tf.word_wrap = True
    for i, (text, level) in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("• " if level == 0 else "– ") + text
        p.level = level
        p.font.size = Pt(15 if level == 0 else 12.5)
        p.font.color.rgb = DARK if level == 0 else GREY
        p.space_after = Pt(7)

    if image and os.path.exists(image):
        s.shapes.add_picture(image, Inches(5.9), Inches(1.35), width=Inches(3.7))

    if footnote:
        fb = s.shapes.add_textbox(Inches(0.6), Inches(6.0), Inches(8.8),
                                  Inches(0.9))
        ftf = fb.text_frame
        ftf.word_wrap = True
        p = ftf.paragraphs[0]
        p.text = footnote
        p.font.size = Pt(10.5)
        p.font.color.rgb = RED

    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def add_table(prs, title, header, rows, notes="", footnote=""):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(8.8), Inches(0.9))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = BLUE
    shape = s.shapes.add_table(len(rows) + 1, len(header), Inches(0.6),
                               Inches(1.35), Inches(8.8),
                               Inches(0.4) * (len(rows) + 1))
    table = shape.table
    for j, h in enumerate(header):
        cell = table.cell(0, j)
        cell.text = h
        cell.text_frame.paragraphs[0].font.size = Pt(11.5)
        cell.text_frame.paragraphs[0].font.bold = True
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            cell.text = str(val)
            cell.text_frame.paragraphs[0].font.size = Pt(11)
    if footnote:
        fb = s.shapes.add_textbox(Inches(0.6), Inches(6.1), Inches(8.8),
                                  Inches(0.8))
        ftf = fb.text_frame
        ftf.word_wrap = True
        p = ftf.paragraphs[0]
        p.text = footnote
        p.font.size = Pt(10.5)
        p.font.color.rgb = RED
    if notes:
        s.notes_slide.notes_text_frame.text = notes



def _script_html(md_lines, meta):
    """Tiny markdown -> HTML for the printable script (headings, bold, lists)."""
    import html as _html
    out, in_list = [], False
    for line in md_lines:
        if line.strip() == "---":
            if in_list:
                out.append("</ul>"); in_list = False
            out.append('<hr>')
            continue
        if line.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h2>{_html.escape(line[3:])}</h2>")
            continue
        if line.startswith("% "):
            out.append(f"<h1>{_html.escape(line[2:])}</h1>")
            continue
        if line.startswith("```"):
            continue
        if line.startswith("`") and "·" in line:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f'<p class="timing">{_html.escape(line.replace("`", ""))}</p>')
            continue
        if line.startswith("> "):
            if in_list:
                out.append("</ul>"); in_list = False
            cue = _html.escape(line[2:])
            while "**" in cue:
                cue = cue.replace("**", "<b>", 1).replace("**", "</b>", 1)
            out.append(f'<p class="cue">{cue}</p>')
            continue
        if not line.strip():
            if in_list:
                out.append("</ul>"); in_list = False
            continue
        text = _html.escape(line)
        while "**" in text:
            text = text.replace("**", "<b>", 1).replace("**", "</b>", 1)
        if line.startswith("A: "):
            out.append(f"<p>{text}</p>")
        else:
            out.append(f"<p>{text}</p>")
    if in_list:
        out.append("</ul>")
    css = """
    @page { size: A4; margin: 18mm 18mm; }
    body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
           font-size: 11pt; line-height: 1.5; color: #1f2933; }
    h1 { font-size: 17pt; margin: 0 0 2mm; }
    h2 { font-size: 13pt; color: #1a4f86; margin: 7mm 0 1.5mm; }
    p { margin: 0 0 2.4mm; }
    .timing { font-family: Menlo, monospace; font-size: 8.6pt; color: #5b6772;
              margin-bottom: 1.6mm; }
    .cue { font-size: 9.4pt; color: #b2452f; border-left: 2pt solid #e8c4ba;
           padding-left: 2mm; margin-left: 0; }
    hr { border: 0; border-top: 0.4pt solid #d3dae1; margin: 5mm 0; }
    """
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Speaker script — {meta['student']}</title>"
            f"<style>{css}</style></head><body>" + "\n".join(out) + "</body></html>")


def _print_pdf(html_path, pdf_path):
    import subprocess
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not os.path.exists(chrome):
        return
    home = os.path.join(ROOT, ".chrome-home")
    os.makedirs(home, exist_ok=True)
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--disable-crash-reporter", "--disable-breakpad",
                    f"--user-data-dir={os.path.join(home, 'profile')}",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}",
                    html_path], check=False, env={**os.environ, "HOME": home},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "report",
                                                  "presentation.pptx"))
    ap.add_argument("--brief", action="store_true",
                    help="short reminder notes only, no speaker script "
                         "(used for the deck committed to the public repo)")
    ap.add_argument("--variant", choices=("full", "short"), default="full",
                    help="full ≈15 min script, or the short cut ≈8 min")

    args = ap.parse_args()

    # The full speaker script is deliberately *not* part of the repository:
    # it lives only in the local, git-ignored repro/presentation_script.py.
    # Without that file (or with --brief) the deck keeps the short reminder
    # notes and no script is generated.
    SCRIPT = QA = None
    if not args.brief:
        sys.path.insert(0, ROOT)
        try:
            from repro.presentation_script import QA as _QA
            from repro.presentation_script import SCRIPT as _FULL
            from repro.presentation_script import SHORT as _SHORT
            SCRIPT, QA = (_SHORT if args.variant == "short" else _FULL), _QA
        except ImportError:
            SCRIPT = QA = None
    runs = json.load(open(args.json))
    seed_path = os.path.join(ROOT, "results", "seed_stats.json")
    seeds = json.load(open(seed_path)) if os.path.exists(seed_path) else {}
    nseeds = seeds.get("n_seeds", 1)
    meta = json.load(open(args.meta))
    figs = os.path.join(ROOT, "report", "figs")
    by_tag = {r["tag"]: r for r in runs}
    base = runs[0]
    mod = runs[1] if len(runs) > 1 else runs[0]

    def pct(r, key):
        return 100.0 * r[key] / r["tasks"]

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(7.5)
    script = []

    add_title_slide(
        prs,
        "Reproducing LLM-as-a-Verifier",
        ["Paper 21 · *LLM-as-a-Verifier: A General-Purpose Verification Framework* (arXiv 2607.05391)",
         "Target: Terminal-Bench 2.1 self-verification, best-of-3",
         "Reproduction + one isolated modification (score granularity g20 → g5)"],
        f"{meta['student']} · {meta['student_id']} · FTEC5660 Agentic AI for Business and FinTech")
    script.append(("1. Title", "Introduce the paper, the target result, and that the talk has three parts: what reproduces, what I changed, and what broke."))

    add_bullets(
        prs,
        "The claim under test",
        [("The repo re-ranks N agent rollouts with a fine-grained verifier; "
          "selection should beat the agent's own Pass@1", 0),
         ("Terminal-Bench 2.1, 5 mini-swe-agent rollouts per task (paper)", 0),
         ("Paper, mean ± std over 3 seeds:", 0),
         ("Best-of-3: 79.4% Pass@1 → 86.5% ± 1.1% (oracle 92.1%)", 1),
         ("Best-of-5: 78.7% Pass@1 → 88.0% ± 0.6% (oracle 96.6%)", 1),
         ("Mechanism: pairwise tournament over rollouts; each pair scored on 3 criteria; "
          "score = expectation over the logprob distribution of a 20-point letter", 0)],
        "State the claim precisely: this is not a training result, it is a selection result. "
        "Emphasise the two ingredients the paper says matter: fine-grained scoring, and taking "
        "the expectation over the model's full score-token distribution.")
    script.append(("2. Claim", "The target is a table row: best-of-3 selection accuracy on Terminal-Bench 2.1, plus its two ablations in spirit (granularity, K)."))

    add_table(
        prs,
        "Setup: what I actually ran",
        ["item", "paper", "this reproduction"],
        [["verifier model", "gemini-2.5-flash / deepseek-v4-flash", meta["model"]],
         ["backend", "Vertex AI / DeepSeek", meta["backend"]],
         ["decoding", "T=1.0, logprobs", "T=1.0, thinking=high, text fallback"],
         ["scope", "66 tasks × 5 rollouts, 3 seeds",
          f"{base['tasks']} swing tasks, {nseeds} seed" + ("s" if nseeds > 1 else "") + " baseline"],
         ["config", "K=2, pivots=1, 3 criteria", "identical"],
         ["compute", "—", meta["compute"]]],
        "Two controlled deviations, both forced by the environment: the verifier model "
        "and the fact that the final backend strips token logprobs.",
        footnote=meta["deviation_note"])
    script.append(("3. Setup", "Be explicit: results are NOT directly comparable to the paper because the verifier model and the logprob availability differ. Everything else — tasks, metric, evaluation code — is the authors' code."))

    add_bullets(
        prs,
        "Step 0: the dataset and the metric check out exactly",
        [("Pass@1 and Oracle are computed from the shipped ground-truth rewards — no API calls", 0),
         ("My numbers on all 89 tasks, best-of-3: Pass@1 79.4%, Oracle 92.1%", 0),
         ("Paper: Pass@1 79.4%, Oracle 92.1% → identical to the decimal", 1),
         ("Best-of-5: 78.7% / 96.6% — also identical", 1),
         ("So: the trajectories, the pass/fail labels and the metric definitions are intact", 0),
         ("What remains uncertain is only the verifier itself", 0)],
        "This is the strongest positive result of the whole exercise and it costs nothing: the "
        "released data reproduces the paper's non-LLM numbers exactly, which means any deviation "
        "later is attributable to the verifier, not the data.")
    script.append(("4. Data validates", "Point out that Pass@1/Oracle are exact — this isolates the verifier as the only source of divergence."))

    add_bullets(
        prs,
        "Scope: a defensible subset, not cherry-picking",
        [("Of 89 tasks, only the 24 'swing' tasks (rollouts disagree) can change under selection", 0),
         ("58 all-pass + 7 all-fail tasks are decided before the verifier runs", 1),
         ("24 swing × 30 verifier calls = 720 calls for a full best-of-3 run", 0),
         ("Budget + wall-clock forced a subset: first 6 swing tasks by name", 0),
         ("Subset Pass@1 50.0% vs full swing Pass@1 52.9% → same difficulty band", 1),
         ("Caveat: n=6 tasks, 1 seed ⇒ ±1 task ≈ ±17 pts; treat as directional", 0)],
        "Quantify the caveat honestly. The task-level number is coarse; the report therefore also "
        "reports comparison-level and trial-level metrics, which have 30-60 samples.",
        footnote="All-pass / all-fail tasks contribute no selection decision, so the subset loses statistical power, not coverage of the phenomenon.")
    script.append(("5. Scope", "Explain why swing tasks are the only interesting ones, and that the subset is chosen by sorted name — a mechanical rule, not by difficulty."))

    add_bullets(
        prs,
        "Result: does selection beat Pass@1?",
        [(f"Pass@1 {pct(base,'pass1'):.1f}% → verifier {pct(base,'verifier'):.1f}% "
          f"(oracle {pct(base,'oracle'):.1f}%) on {base['tasks']} tasks", 0),
         (f"Paper's best-of-3 verifier: 86.5% ± 1.1% on its own scope", 0),
         ("Direction reproduces: the verifier lifts selection clear of Pass@1", 0),
         ("Magnitude does not transfer: different model, 1 seed, 6 tasks", 1),
         ("Cost: ~40-80k input tokens and ~10-15k output tokens per comparison", 1)],
        "Answer the headline question directly, then immediately bound it. Direction yes, magnitude no.",
        image=os.path.join(figs, "fig1_headline.png"))
    script.append(("6. Result", "Say what reproduces (direction) and what does not (magnitude), and why the comparison is not apples-to-apples."))

    add_bullets(
        prs,
        "The surprise: the 'expectation over the distribution' is inert",
        [("The paper's reward is E[score letter] over the logprob distribution", 0),
         ("Measured on api.deepseek.com (225 cached scores at g=20):", 0),
         (f"{100*base['degeneracy']['share_within_1e-3']:.1f}% of scores sit within 1e-3 "
          f"scale points of a single letter", 1),
         ("median deviation from a pure single-letter read is 7.4e-7", 1),
         ("I.e. the distribution is one-hot: expectation ≈ argmax ≈ hard label", 0),
         ("Consequence: on hosted DeepSeek the method runs as LLM-as-a-Judge with a letter label", 0),
         ("The second backend does not even return logprobs — and that changes nothing", 1)],
        "This is the most useful finding for future users: the fine-grained machinery is dormant "
        "on this backend. It also justifies running the final experiment on a backend without logprobs.",
        image=os.path.join(figs, "fig3_degeneracy.png"))
    script.append(("7. One-hot finding", "Show the measurement, state the consequence: the 'fine-grained' reward degenerates to a hard label, so the two backends are equivalent."))

    add_table(
        prs,
        "Modification: score granularity g20 → g5",
        ["config", "Pass@1", "verifier", "oracle", "pairwise acc.", "trial AUC"],
        [[r["tag"],
          f"{pct(r,'pass1'):.1f}%",
          (f"{seeds['verifier %']['mean']:.1f}% ± {seeds['verifier %']['std']:.1f}"
           if (i == 0 and nseeds > 1) else f"{pct(r,'verifier'):.1f}%"),
          f"{pct(r,'oracle'):.1f}%",
          (f"{seeds['pairwise_acc']['mean']:.1f}%"
           if (i == 0 and nseeds > 1) else
           f"{100*r['pairwise_agree']/max(1,r['pairwise_total']):.1f}%"),
          (f"{seeds['trial_auc']['mean']:.3f} ± {seeds['trial_auc']['std']:.3f}"
           if (i == 0 and nseeds > 1) else f"{r['trial_auc']:.3f}")]
         for i, r in enumerate(runs)],
        "One change, isolated in the scale definition: 20 letters (A-T) → 5 letters (A-E). "
        "Unset, the code is byte-identical to upstream. Caches are separate per configuration.",
        footnote=(meta["mod_note"] +
                  (f" Baseline is the mean ± std over {nseeds} seeds; the ablation "
                   "shares seed 0 with it (matched pairs)." if nseeds > 1 else "")))
    script.append(("8. Modification", "Explain what was changed (one scale function), that the default is untouched, and read the delta off the table."))

    add_bullets(
        prs,
        "What changed, and what that means",
        [(meta["mod_finding"], 0),
         ("Reading: with a one-hot distribution, coarse vs fine scales differ only in label "
          "resolution, and the verifier's ranking is robust to it", 0),
         ("On a backend with genuine logprob mass, the same ablation is the sharp test of the "
          "paper's granularity claim", 1),
         ("Cost implication: g5 shortens the answer block by a few dozen tokens; no measurable "
          "saving next to the trajectory prompt", 1)],
        "Do not overclaim: with n=6 the difference is within noise, and the honest statement is "
        "'no detectable effect at this sample size', which is what the report says.",
        image=os.path.join(figs, "fig2_scores.png"))
    script.append(("9. Meaning", "Frame the modification result carefully: at this sample size it is a null result, and explain why that is the expected outcome given the one-hot finding."))

    add_table(
        prs,
        "Debug diary: five real blockers",
        ["blocker", "resolution"],
        [["github.com / raw / HuggingFace unreachable from the shell",
          "pinned 481-file sha256 manifest + jsDelivr fetch script"],
         ["440 MB upstream data, wanted 58 MB", "per-file CDN fetch, verified, git-ignored"],
         ["Cloudflare 1010 on the API host", "browser-like User-Agent; Python urllib default is banned"],
         ["HTTP 402 + 429 mid-run (balance / concurrency)",
          "lower max_workers to 8; failures are never cached, so re-runs only retry gaps"],
         ["backend returns no token logprobs",
          "text-tag fallback path, justified by the one-hot measurement"]],
        "Each of these is a lesson for the next user; the report has the full table with symptoms "
        "and the exact fix.",
        footnote="Wall-clock: a 30-comparison run takes 1.5-2.5 h at 1-2 effective concurrent verifier calls.")
    script.append(("10. Debug diary", "Walk two or three of these quickly; the point is that reproducibility work is mostly environment archaeology."))

    add_table(
        prs,
        "Verdict: what reproduces",
        ["item", "status", "why"],
        [["ground-truth Pass@1 / Oracle", "reproduces exactly", "shipped labels, same metric code"],
         ["pipeline runs end to end", "yes", "0-error runs on two backends"],
         ["direction of the verifier gain", "reproduces", "verifier > Pass@1 on the subset"],
         ["86.5% ± 1.1% magnitude", "not comparable", "model, seed count, scope differ"],
         ["fine-grained logprob expectation", "does not reproduce", "hosted backend is one-hot"],
         ["g20 vs g5 granularity effect", "no detectable difference", "null at n=6, consistent with one-hot"]],
        "Close the loop: separate 'the code works' from 'the number transfers' from 'the mechanism is real'.",
        footnote="Recommendation for future users: budget for the 24 swing tasks and 3 seeds on a logprob-capable backend; measure the score distribution before trusting the fine-grained claim.")
    script.append(("11. Verdict", "Three-way split is the honest summary: code yes, magnitude no, mechanism unavailable."))

    add_bullets(
        prs,
        "Lessons + what I'd recommend",
        [("Read the evaluation path, not just the README: the fine-grained reward silently "
          "degrades to a hard label when the backend is one-hot or logprob-free", 0),
         ("Cache verifier scores to disk by (criterion, task, pair, rep) — that is what made a "
          "2-hour run survivable across 402/429 outages", 0),
         ("Failures must never be cached: retries then become incremental, not full re-runs", 1),
         ("Scope by swing tasks: 3/4 of the task list cannot change under selection", 0),
         ("Pin data by hash; the benchmark data is the part that reproduces perfectly", 0)],
        "End with the two or three things a future student should copy.",
        footnote="")
    script.append(("12. Lessons", "Close on transferable practice: hash-pinned data, on-disk score cache, swing-task scoping, and distrust of 'fine-grained' claims until you measure the distribution."))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # The speaker notes become the full script, so Presenters View while
    # recording shows exactly what to say, with its clock and the Chinese cue.
    def flatten(t):
        return " ".join(t.split())

    if SCRIPT:
        by_num = {entry[0]: entry for entry in SCRIPT}
        for idx, sl in enumerate(prs.slides, start=1):
            entry = by_num.get(idx)
            if not entry:
                continue        # slide not used in this variant: keep brief note
            _num, title, clock, secs, en, cue = entry
            sl.notes_slide.notes_text_frame.text = (
                f"[{clock} · {secs}s · slide {_num}] {title}\n\n"
                f"{flatten(en)}\n\n"
                f"中文提示：{cue}")
    prs.save(args.out)
    if not SCRIPT:
        print(f"deck: {args.out} (brief notes; no speaker script written)")
        return

    # ---- markdown + printable PDF of the same script ----
    total_words = sum(len(flatten(en).split()) for *_, en, _c in SCRIPT)
    total_secs = sum(secs for *_x, secs, _en, _c in SCRIPT)
    suffix = "" if args.variant == "full" else "_SHORT"
    md = [f"% Reproducing LLM-as-a-Verifier — speaker script"
          f"{'' if args.variant == 'full' else ' (short cut)'}",
          "",
          f"{meta['student']} · {meta['student_id']} · FTEC5660",
          "",
          f"**Timing:** {len(SCRIPT)} slides, {total_secs // 60}:{total_secs % 60:02d} "
          f"of speech, {total_words} words "
          f"(≈{total_words / max(1, total_secs / 60):.0f} words per minute — comfortable).",
          "",
          "The same text is in each slide's **speaker notes**, so you can record "
          "from Presenters View. The 中文提示 line is a one-sentence reminder of "
          "what the slide is for; do not read it out.",
          ""]
    if args.variant == "short":
        md += ["---", "",
               "## 四个必答问题 → 对应幻灯片", "",
               "| 作业要求 | 幻灯片 | 时间 |", "|---|---|---|",
               "| 你尝试复现了什么 | 1 标题、2 论文声称、5 范围 | 0:00-2:25 |",
               "| 你的修改及其可量化影响 | 8 修改、9 投票级影响 | 5:10-6:55 |",
               "| 哪些成功 / 哪些没成功 | 4 数据一致、6 结果、7 one-hot、11 判定 | 1:50-5:10, 6:55-7:35 |",
               "| 关键经验 + 给后续使用者的建议 | 12 三条建议 | 7:35-8:10 |",
               "",
               "Slides 3 (setup) and 10 (debug diary) are optional in the short "
               "cut: 3 is worth including if the audience needs the deviation "
               "context, and 10 adds 80 seconds if you have time.", ""]
    for num, title, clock, secs, en, cue in SCRIPT:
        words = len(flatten(en).split())
        md += [f"---", "",
               f"## Slide {num} — {title}",
               "",
               f"`{clock}` · {secs}s · {words} words",
               "",
               flatten(en),
               "",
               f"> **中文提示**：{cue}",
               ""]
    md += ["---", "", "## Q&A 预案", ""]
    for q, a in QA:
        md += [f"**Q: {q}**", "", f"A: {flatten(a)}", ""]
    md += ["---", "",
           "Recorded demo you can add after slide 10 (no API cost):",
           "",
           "```bash",
           "cd ~/Desktop/repro/_repos/llm-as-a-verifier_llm-as-a-verifier",
           "./.venv/bin/python repro/analyze.py --tags sub12_g20:20 sub12_g5:5",
           "```",
           "",
           "It replays the tournament from the checked-in caches and prints the "
           "table, in about two seconds.", ""]
    md_path = os.path.join(os.path.dirname(args.out),
                           f"PRESENTATION_SCRIPT{suffix}.md")
    open(md_path, "w").write("\n".join(md))

    html = _script_html(md, meta)
    html_path = md_path.replace(".md", ".html")
    open(html_path, "w").write(html)
    pdf_path = md_path.replace(".md", ".pdf")
    _print_pdf(html_path, pdf_path)
    print(f"deck: {args.out}\nscript: {md_path}\nscript pdf: {pdf_path}")


if __name__ == "__main__":
    main()
