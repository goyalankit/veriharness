# E2 — Repair-Interface Factor Ablation (T=0.7, 14.7B coder)

**Verdict: the typed-repair (H4) advantage is *diagnostic*, not *typed*.**
H4 and `targeted+untyped` are statistically indistinguishable (Δ=0.000, 95% CI −0.026..+0.020,
McNemar exact p=1.000, n=540 paired instances). The mechanism is **information content —
specifically targeted diagnostic locus information — not the typing of the failure payload.**
The paper's framing should move from **"typed repair"** to **"diagnostic repair."**

---

## Setup

| | |
|---|---|
| Experiment id | `e2_repair_factor_ablation_t07_14b` |
| Model | `qwen2.5-coder:14b` (14.7B coder), local OpenAI-compatible endpoint `http://localhost:11434/v1/chat/completions` |
| Temperature | **0.7** (fair-comparison arm; T=0.0 handicaps resample/repair variants — see F1/E5) |
| Budget | `max_leaf_calls_per_task = 4`, `veriharness_k = 2` |
| Variants (7) | H3, generic-retry, natural-retry, retain+generic, targeted+untyped, typed+no-retain, H4 |
| Benchmarks (9) | boolq20, squad20, sciq20, arc_easy20, glue_sst2·20, glue_rte20, glue_mrpc20, trec_qc10, mini_workflow30 |
| Scale | 180 tasks/seed × 3 seeds = 540 instances × 7 variants = **3,780 result rows** |
| Instance key | `(benchmark, task_id, seed)`; pairing is within-instance |

`mini_workflow` is the only **multi-step** benchmark (synthetic, 30 tasks); the other 8 are
**single-step** leaf/classification benchmarks (450 instances). This stratification is decisive.

---

## [1] Per-variant summary (all strata, n=540 each)

| variant | success | wrong_claim_accepted | premature_stop | gate_pass | leaf_calls |
|---|---|---|---|---|---|
| H3 | 0.783 | 0.000 | 0.194 | 0.881 | 1.45 |
| generic-retry | 0.750 | 0.000 | 0.206 | 0.857 | 1.47 |
| natural-retry | 0.754 | 0.000 | 0.200 | 0.867 | 1.46 |
| retain+generic | 0.763 | 0.000 | 0.185 | 0.869 | 1.47 |
| targeted+untyped | **0.881** | 0.000 | 0.115 | 1.000 | 1.18 |
| typed+no-retain | **0.887** | 0.000 | 0.113 | 1.000 | 1.17 |
| H4 | **0.881** | 0.000 | 0.115 | 1.000 | 1.32 |

The three "diagnostic-locus" variants (targeted+untyped, typed+no-retain, H4) cluster at ~0.88;
the four non-diagnostic variants (H3, generic-retry, natural-retry, retain+generic) cluster at ~0.75–0.78.

## [2] Integrity — `wrong_claim_accepted` (must stay ~0)

**PASS. 0.000 for every variant.** No leaf ever decided final acceptance for a gated variant; the
external gate remained the sole acceptor. This is the core invariant of the harness and it holds
across all 3,780 rows.

## [3] 2×2 decomposition — candidate_retention × typed_failure_payload

| | typed=off | typed=on |
|---|---|---|
| **retain=off** | generic-retry 0.750 | typed+no-retain 0.887 |
| **retain=on** | retain+generic 0.763 | H4 0.881 |

- main effect (retention) = **+0.004**  (negligible)
- main effect (typing) = **+0.128**  (dominant)
- interaction = −0.019

Within this 2×2, "typing" carries essentially the entire effect and candidate retention adds
almost nothing — **but see [5]: the "typing" main effect is fully explained by diagnostic
information, which the untyped-but-targeted arm already supplies.**

## [4] *** KEY CONTRAST: H4 vs targeted+untyped *** (typing vs. diagnostic-untyped)

| stratum | H4 | targeted+untyped | Δ | 95% CI | McNemar p | n | H4_only / tgt_only |
|---|---|---|---|---|---|---|---|
| all | 0.881 | 0.881 | **0.000** | −0.026..+0.020 | **1.000** | 540 | 21 / 21 |
| single_step_leaf | 0.858 | 0.858 | 0.000 | −0.024..+0.031 | 1.000 | 450 | 21 / 21 |
| multi_step_workflow | 1.000 | 1.000 | 0.000 | 0.000..0.000 | 1.000 | 90 | 0 / 0 |

**H4 ≈ targeted+untyped at every stratum.** The 21 discordant pairs in each direction cancel
exactly — this is symmetric noise, not a hidden typing benefit. The CI brackets zero within ±3pp,
so this is a positive **equivalence** result, not merely "failure to reject."

## [5] Headline ≥80% rule — which single factor recovers the H4−generic-retry delta?

Full delta H4 − generic-retry = **+0.131** (n=540).

| factor | recovered | fraction of full delta |
|---|---|---|
| candidate_retention | +0.013 | 0.099 |
| **typed_payload** | +0.137 | **1.042 ✅** |
| **diagnostic_info (targeted+untyped − generic)** | +0.131 | **1.000 ✅** |
| natural_language_verbosity | +0.004 | 0.028 |

Two factors clear ≥80%, but they are **not independent**: `typed_payload` and
`diagnostic_info_targeted_untyped` recover the *same* delta, and [4] shows typing adds **nothing**
on top of the untyped diagnostic arm. The parsimonious mechanism claim is therefore:

> **Targeted diagnostic information about the failure locus recovers ~100% of the H4 advantage.
> Typing the payload, retaining candidates, and natural-language verbosity are each individually
> immaterial.**

## [6] Information-without-structure arms

| comparison | Δ | McNemar p | reading |
|---|---|---|---|
| natural-retry vs generic-retry | +0.004 | 0.904 | verbosity alone does nothing |
| targeted+untyped vs natural-retry | **+0.128** | 3.7e−11 | targeting the locus is the jump |
| targeted+untyped vs typed+no-retain | +0.006 | 0.749 | typing adds nothing over targeted diagnostics |

The gain appears exactly when—and only when—repair is pointed at the failing locus with actionable
content. Adding a type schema on top is inert.

## [7] Per-benchmark success — where the effect lives

| benchmark | H3 | generic | natural | retain+g | targeted+u | typed+nr | H4 | H4−tgt |
|---|---|---|---|---|---|---|---|---|
| boolq | 0.700 | 0.683 | 0.683 | 0.667 | 0.650 | 0.633 | 0.667 | +0.017 |
| squad | 0.950 | 0.950 | 0.983 | 0.983 | 0.983 | 0.983 | 0.933 | −0.050 |
| sciq | 0.967 | 0.967 | 0.950 | 0.933 | 0.950 | 0.933 | 0.950 | +0.000 |
| arc_easy | 0.900 | 0.900 | 0.900 | 0.933 | 0.917 | 0.917 | 0.867 | −0.050 |
| glue_sst2 | 0.900 | 0.967 | 0.900 | 0.917 | 0.900 | 0.917 | 0.933 | +0.033 |
| glue_rte | 0.900 | 0.833 | 0.817 | 0.833 | 0.800 | 0.850 | 0.850 | +0.050 |
| glue_mrpc | 0.867 | 0.800 | 0.800 | 0.833 | 0.800 | 0.833 | 0.800 | +0.000 |
| trec_qc | 0.867 | 0.867 | 0.900 | 0.900 | 0.867 | 0.833 | 0.867 | +0.000 |
| **mini_workflow** | **0.289** | **0.144** | **0.200** | **0.211** | **1.000** | **1.000** | **1.000** | **+0.000** |

The 8 single-step benchmarks sit near ceiling for every variant; H4−targeted deltas there are small
and mixed-sign (ceiling noise). **All separation is in `mini_workflow`**: non-diagnostic repair
collapses to 0.14–0.29 on multi-step tasks, while every diagnostic-locus variant (targeted+untyped,
typed+no-retain, H4) reaches **1.000**. Multi-step is where localization matters — and there,
untyped-targeted already saturates, leaving no room for typing to help.

## [8] Per-seed success (robustness)

| variant | seed 1 | seed 2 | seed 3 |
|---|---|---|---|
| H3 | 0.778 | 0.794 | 0.778 |
| generic-retry | 0.761 | 0.728 | 0.761 |
| natural-retry | 0.744 | 0.756 | 0.761 |
| retain+generic | 0.778 | 0.750 | 0.761 |
| targeted+untyped | 0.867 | 0.900 | 0.878 |
| typed+no-retain | 0.889 | 0.906 | 0.867 |
| H4 | 0.878 | 0.894 | 0.872 |

The H4 ≈ targeted+untyped tie and the ~+0.12 diagnostic gap over generic-retry hold on all three seeds.

---

## Paper implication

1. **Reframe H4 from "typed repair" to "diagnostic repair."** The advantage is the *information*
   (targeted failure locus + actionable content), not the *type structure* of the payload.
2. **Drop the retention and verbosity claims** as drivers — both are immaterial here.
3. **Scope the claim to multi-step tasks.** On single-step leaves there is nothing to localize and
   the mechanism is silent; the effect is a multi-step phenomenon.
4. Integrity is preserved throughout (`wrong_claim_accepted = 0`), so the gains are real acceptances,
   not the leaf leaking into the accept decision.

---

## Files

| file | contents |
|---|---|
| `README.md` | this writeup |
| `e2_analysis_report.txt` | full text report (per-variant, 2×2, key contrast, ≥80% rule, per-seed) |
| `e2_analysis.json` | machine-readable analysis (all sections) |
| `aggregate.json` | harness `aggregate` output |
| `leaderboard.csv` | per-variant success + premature-stop rates |
| `paired_policy_tests.csv` | paired McNemar tests (incl. deltas vs H4) |
| `per_seed_results.csv` | per-seed × per-variant counts |
| `per_benchmark_by_variant.csv` | per-benchmark success by variant (+ H4−targeted) |
| `failure_modes_by_benchmark.csv` | failure-reason breakdown |
| `prompt_token_overhead.csv` | prompt-token cost per variant |
| `config.yaml` | run configuration snapshot |

## Reproduction

```bash
.venv/bin/python -m veriharness.cli.main run \
  --config configs/e2/e2_repair_factor_ablation_t07_14b.yaml --backend local --concurrency 8
.venv/bin/python -m veriharness.cli.main aggregate --run-dir runs/e2_repair_factor_ablation_t07_14b
.venv/bin/python results/e2/e2_analysis.py \
  --run-dir runs/e2_repair_factor_ablation_t07_14b --json-out results/e2/e2_analysis.json
```

Run completed on 3 seeds (1,2,3) at budget 4, T=0.7; 3,780/3,780 rows; integrity clean.
