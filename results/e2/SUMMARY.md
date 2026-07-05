# E2 — Executive Summary

**One line:** The typed-repair (H4) advantage is **diagnostic, not typed** — the paper should say
**"diagnostic repair,"** not "typed repair."

## The decisive test
H4 ("typed repair") vs. `targeted+untyped` (same targeted failure-locus information, but no type
schema). If they tie, the win is *information*, not *typing*.

**They tie — exactly.**

| | H4 | targeted+untyped | Δ | 95% CI | McNemar p |
|---|---|---|---|---|---|
| success (n=540) | 0.881 | 0.881 | **0.000** | −0.026..+0.020 | **1.000** |

Tight CI within ±3pp ⇒ a positive **equivalence**, not merely "no significant difference."

## What actually drives the effect
Full gain over plain retry: H4 − generic-retry = **+0.131**. Attribution:

| candidate factor | recovers | verdict |
|---|---|---|
| **targeted diagnostic info** (failure locus) | **~100%** | the mechanism ✅ |
| typed payload (schema) | ~0% *on top of* targeted info (Δ=+0.006, p=0.75) | inert |
| candidate retention | ~10% | immaterial |
| natural-language verbosity | ~3% | immaterial |

## Where it lives
All separation is on the **multi-step** benchmark (`mini_workflow`): undiagnosed repair collapses to
0.14–0.29, every diagnostic-locus variant reaches **1.000**. The 8 single-step benchmarks are at
ceiling for all variants. **Scope the claim to multi-step agentic tasks.**

## Integrity
`wrong_claim_accepted = 0.000` for all 7 variants across all 3,780 rows — the external gate remained
the sole acceptor; no leaf decided final acceptance for a gated variant.

## Setup (for reference)
7 variants × 9 benchmarks × 3 seeds = **3,780 rows**; budget 4; **temperature 0.7** (the fair-comparison
arm — greedy T=0.0 handicaps resample/repair variants); model `qwen2.5-coder:14b` via a local
OpenAI-compatible endpoint (`http://localhost:11434`).

## Is this a good result?
Yes — it is a clean, robust, single-mechanism finding that **refutes the original "typed" framing** in
favor of a stronger, more defensible claim: *structured failure feedback helps because it tells the
agent **where** to look, not because it is typed.* See `README.md` for full tables and tests.
