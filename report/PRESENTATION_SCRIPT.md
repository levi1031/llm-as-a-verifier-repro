# Presentation script (≈15 min)

## 1. Title

Introduce the paper, the target result, and that the talk has three parts: what reproduces, what I changed, and what broke.

## 2. Claim

The target is a table row: best-of-3 selection accuracy on Terminal-Bench 2.1, plus its two ablations in spirit (granularity, K).

## 3. Setup

Be explicit: results are NOT directly comparable to the paper because the verifier model and the logprob availability differ. Everything else — tasks, metric, evaluation code — is the authors' code.

## 4. Data validates

Point out that Pass@1/Oracle are exact — this isolates the verifier as the only source of divergence.

## 5. Scope

Explain why swing tasks are the only interesting ones, and that the subset is chosen by sorted name — a mechanical rule, not by difficulty.

## 6. Result

Say what reproduces (direction) and what does not (magnitude), and why the comparison is not apples-to-apples.

## 7. One-hot finding

Show the measurement, state the consequence: the 'fine-grained' reward degenerates to a hard label, so the two backends are equivalent.

## 8. Modification

Explain what was changed (one scale function), that the default is untouched, and read the delta off the table.

## 9. Meaning

Frame the modification result carefully: at this sample size it is a null result, and explain why that is the expected outcome given the one-hot finding.

## 10. Debug diary

Walk two or three of these quickly; the point is that reproducibility work is mostly environment archaeology.

## 11. Verdict

Three-way split is the honest summary: code yes, magnitude no, mechanism unavailable.

## 12. Lessons

Close on transferable practice: hash-pinned data, on-disk score cache, swing-task scoping, and distrust of 'fine-grained' claims until you measure the distribution.
