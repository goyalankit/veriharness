#!/usr/bin/env python
"""E2 repair-factor ablation analysis.

Computes the decisive E2 lens on a run's results.jsonl:
  1. Per-variant success + integrity (wrong_claim_accepted must stay ~0).
  2. 2x2 decomposition: candidate_retention x typed_payload
     (generic-retry / retain+generic / typed+no-retain / H4).
  3. KEY contrast: H4 vs targeted+untyped (typed vs diagnostic-but-untyped).
  4. Paired deltas vs H4 for every variant + McNemar exact p.
  5. Per-stratum (mini_workflow multi-step vs single-step leaf controls).
  6. Per-seed success rates.
  7. Headline >=80% rule: which single factor recovers >=80% of (H4 - generic-retry).

Reuses veriharness.experiments.aggregate helpers (mcnemar_exact_p, bootstrap_ci,
instance keys) so pairing/stats match the harness exactly. Tolerates partial
(in-progress) runs: pairs only over instances present for both variants.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, List, Optional

from veriharness.experiments.aggregate import (
    bootstrap_ci,
    mcnemar_exact_p,
    read_results,
)

VARIANTS = [
    "H3",
    "generic-retry",
    "natural-retry",
    "retain+generic",
    "targeted+untyped",
    "typed+no-retain",
    "H4",
]
SINGLE_STEP = {
    "boolq", "squad", "sciq", "arc_easy",
    "glue_sst2", "glue_rte", "glue_mrpc", "trec_qc",
}
MULTI_STEP = {"mini_workflow"}

Row = Dict[str, Any]
Filter = Optional[Callable[[Row], bool]]


def _instance(row: Row) -> tuple:
    return (str(row.get("benchmark", "")), str(row.get("task_id", "")), str(row.get("seed", 0)))


def _select(rows: List[Row], variant: str, flt: Filter = None) -> Dict[tuple, Row]:
    out: Dict[tuple, Row] = {}
    for r in rows:
        if r.get("variant") != variant:
            continue
        if flt and not flt(r):
            continue
        out[_instance(r)] = r
    return out


def marginal_rate(rows: List[Row], variant: str, field: str = "success", flt: Filter = None) -> Optional[float]:
    sel = _select(rows, variant, flt)
    if not sel:
        return None
    return mean(1.0 if bool(r.get(field)) else 0.0 for r in sel.values())


def paired_contrast(rows: List[Row], baseline: str, treatment: str, flt: Filter = None) -> Optional[Dict[str, Any]]:
    base = _select(rows, baseline, flt)
    treat = _select(rows, treatment, flt)
    common = sorted(set(base) & set(treat))
    if not common:
        return None
    treat_only = base_only = same_pass = same_fail = 0
    deltas: List[float] = []
    for inst in common:
        b = bool(base[inst].get("success"))
        t = bool(treat[inst].get("success"))
        deltas.append((1.0 if t else 0.0) - (1.0 if b else 0.0))
        if t and not b:
            treat_only += 1
        elif b and not t:
            base_only += 1
        elif t and b:
            same_pass += 1
        else:
            same_fail += 1
    ci = bootstrap_ci(deltas)
    return {
        "baseline": baseline,
        "treatment": treatment,
        "n_pairs": len(common),
        "baseline_success_rate": (same_pass + base_only) / len(common),
        "treatment_success_rate": (same_pass + treat_only) / len(common),
        "treatment_only": treat_only,
        "baseline_only": base_only,
        "same_pass": same_pass,
        "same_fail": same_fail,
        "delta_success_rate": mean(deltas),
        "ci_low": ci[0],
        "ci_high": ci[1],
        "mcnemar_exact_p": mcnemar_exact_p(base_only, treat_only),
    }


def per_variant_table(rows: List[Row], flt: Filter = None) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for v in VARIANTS:
        sel = _select(rows, v, flt)
        if not sel:
            out[v] = {"n": 0}
            continue
        vals = list(sel.values())
        n = len(vals)
        out[v] = {
            "n": n,
            "success_rate": mean(1.0 if r.get("success") else 0.0 for r in vals),
            "wrong_claim_accepted_rate": mean(1.0 if r.get("wrong_claim_accepted") else 0.0 for r in vals),
            "premature_stop_rate": mean(1.0 if r.get("premature_stop") else 0.0 for r in vals),
            "accepted_by_gate_rate": mean(1.0 if r.get("accepted_by_gate") else 0.0 for r in vals),
            "avg_leaf_calls": mean(float(r.get("num_leaf_calls", 0)) for r in vals),
            "avg_retries": mean(float(r.get("num_retries", 0)) for r in vals),
        }
    return out


def two_by_two(rows: List[Row], flt: Filter = None) -> Dict[str, Any]:
    """candidate_retention x typed_payload on instances common to all 4 arms."""
    arms = {
        "off_off": _select(rows, "generic-retry", flt),      # retention off, typed off
        "on_off": _select(rows, "retain+generic", flt),      # retention on,  typed off
        "off_on": _select(rows, "typed+no-retain", flt),     # retention off, typed on
        "on_on": _select(rows, "H4", flt),                   # retention on,  typed on
    }
    common = set(arms["off_off"])
    for a in arms.values():
        common &= set(a)
    common = sorted(common)
    if not common:
        return {"n_pairs": 0}

    def rate(key: str) -> float:
        return mean(1.0 if arms[key][i].get("success") else 0.0 for i in common)

    r00, r10, r01, r11 = rate("off_off"), rate("on_off"), rate("off_on"), rate("on_on")
    main_retention = ((r10 - r00) + (r11 - r01)) / 2.0
    main_typing = ((r01 - r00) + (r11 - r10)) / 2.0
    interaction = (r11 - r01) - (r10 - r00)
    return {
        "n_pairs": len(common),
        "cell_success": {
            "generic-retry (retain=off,typed=off)": r00,
            "retain+generic (retain=on,typed=off)": r10,
            "typed+no-retain (retain=off,typed=on)": r01,
            "H4 (retain=on,typed=on)": r11,
        },
        "main_effect_candidate_retention": main_retention,
        "main_effect_typed_payload": main_typing,
        "interaction": interaction,
    }


def headline(rows: List[Row], flt: Filter = None) -> Dict[str, Any]:
    """>=80% rule: which single factor recovers >=80% of (H4 - generic-retry)?

    Each factor's recovery is measured paired vs generic-retry on shared instances,
    and the fraction uses the (H4 - generic-retry) delta computed on the SAME
    baseline so numerator/denominator are comparable.
    """
    full = paired_contrast(rows, "generic-retry", "H4", flt)
    if not full or abs(full["delta_success_rate"]) < 1e-9:
        return {"delta_full": (full or {}).get("delta_success_rate"), "note": "H4-generic delta ~0; rule N/A"}
    delta_full = full["delta_success_rate"]
    factors = {
        "candidate_retention": "retain+generic",
        "typed_payload": "typed+no-retain",
        "diagnostic_info_targeted_untyped": "targeted+untyped",
        "natural_language_verbosity": "natural-retry",
    }
    recovered = {}
    for name, treat in factors.items():
        c = paired_contrast(rows, "generic-retry", treat, flt)
        if not c:
            recovered[name] = None
            continue
        frac = c["delta_success_rate"] / delta_full if delta_full else None
        recovered[name] = {
            "recovery_delta": c["delta_success_rate"],
            "fraction_of_full": frac,
            "meets_80pct": (frac is not None and frac >= 0.80),
            "mcnemar_exact_p": c["mcnemar_exact_p"],
        }
    return {"delta_full_H4_minus_generic": delta_full, "n_pairs_full": full["n_pairs"], "factors": recovered}


def per_seed(rows: List[Row]) -> Dict[str, Dict[str, Any]]:
    seeds = sorted({str(r.get("seed", 0)) for r in rows})
    out: Dict[str, Dict[str, Any]] = {}
    for s in seeds:
        flt = lambda r, s=s: str(r.get("seed", 0)) == s
        out[s] = {v: marginal_rate(rows, v, flt=flt) for v in VARIANTS}
    return out


def analyze(rows: List[Row]) -> Dict[str, Any]:
    strata = {
        "all": None,
        "single_step_leaf": lambda r: str(r.get("benchmark")) in SINGLE_STEP,
        "multi_step_workflow": lambda r: str(r.get("benchmark")) in MULTI_STEP,
    }
    report: Dict[str, Any] = {
        "n_rows": len(rows),
        "n_instances": len({_instance(r) for r in rows}),
        "per_variant": {k: per_variant_table(rows, flt) for k, flt in strata.items()},
        "two_by_two": {k: two_by_two(rows, flt) for k, flt in strata.items()},
        "H4_vs_targeted_untyped": {k: paired_contrast(rows, "targeted+untyped", "H4", flt) for k, flt in strata.items()},
        "paired_vs_H4": {
            v: paired_contrast(rows, v, "H4") for v in VARIANTS if v != "H4"
        },
        "info_without_structure": {
            "natural-retry_vs_generic-retry": paired_contrast(rows, "generic-retry", "natural-retry"),
            "targeted+untyped_vs_natural-retry": paired_contrast(rows, "natural-retry", "targeted+untyped"),
            "targeted+untyped_vs_typed+no-retain": paired_contrast(rows, "targeted+untyped", "typed+no-retain"),
        },
        "headline_80pct_rule": {k: headline(rows, flt) for k, flt in strata.items()},
        "per_seed_success": per_seed(rows),
    }
    # Integrity summary
    integrity = {}
    for v in VARIANTS:
        sel = _select(rows, v)
        if sel:
            integrity[v] = mean(1.0 if r.get("wrong_claim_accepted") else 0.0 for r in sel.values())
    report["integrity_wrong_claim_accepted_rate"] = integrity
    report["integrity_ok"] = all(x <= 0.02 for x in integrity.values()) if integrity else None
    return report


def _fmt(x: Any, nd: int = 3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def print_report(rep: Dict[str, Any]) -> None:
    print(f"\n{'='*72}\nE2 REPAIR-FACTOR ABLATION  —  {rep['n_rows']} rows, {rep['n_instances']} instances\n{'='*72}")

    print("\n[1] PER-VARIANT (all strata)")
    print(f"  {'variant':18s} {'n':>5s} {'succ':>7s} {'wrong':>7s} {'premat':>7s} {'gate':>6s} {'leaf':>5s}")
    for v in VARIANTS:
        d = rep["per_variant"]["all"].get(v, {})
        if d.get("n"):
            print(f"  {v:18s} {d['n']:>5d} {_fmt(d['success_rate']):>7s} {_fmt(d['wrong_claim_accepted_rate']):>7s} "
                  f"{_fmt(d['premature_stop_rate']):>7s} {_fmt(d['accepted_by_gate_rate']):>6s} {_fmt(d['avg_leaf_calls'],2):>5s}")
        else:
            print(f"  {v:18s} {'0':>5s}  (no rows yet)")

    print(f"\n[2] INTEGRITY  wrong_claim_accepted per variant (must be ~0): "
          f"{'OK' if rep['integrity_ok'] else 'CHECK!'}")
    for v, x in rep["integrity_wrong_claim_accepted_rate"].items():
        flag = "" if x <= 0.02 else "  <-- ELEVATED"
        print(f"  {v:18s} {_fmt(x)}{flag}")

    print("\n[3] 2x2 DECOMPOSITION  candidate_retention x typed_payload (all strata)")
    t = rep["two_by_two"]["all"]
    if t.get("n_pairs"):
        for k, val in t["cell_success"].items():
            print(f"  {k:42s} {_fmt(val)}")
        print(f"  n_pairs={t['n_pairs']}  main(retention)={_fmt(t['main_effect_candidate_retention'])}  "
              f"main(typing)={_fmt(t['main_effect_typed_payload'])}  interaction={_fmt(t['interaction'])}")
    else:
        print("  (not enough complete 4-arm instances yet)")

    print("\n[4] *** KEY CONTRAST: H4 vs targeted+untyped ***  (typed vs diagnostic-untyped)")
    for stratum in ["all", "single_step_leaf", "multi_step_workflow"]:
        c = rep["H4_vs_targeted_untyped"].get(stratum)
        if c:
            print(f"  [{stratum}] H4={_fmt(c['treatment_success_rate'])} vs targeted+untyped={_fmt(c['baseline_success_rate'])}  "
                  f"delta={_fmt(c['delta_success_rate'])} (CI {_fmt(c['ci_low'])}..{_fmt(c['ci_high'])})  "
                  f"McNemar p={_fmt(c['mcnemar_exact_p'])}  n={c['n_pairs']}  "
                  f"[H4_only={c['treatment_only']} tgt_only={c['baseline_only']}]")
        else:
            print(f"  [{stratum}] (no paired instances yet)")

    print("\n[5] PAIRED DELTAS vs H4  (treatment=H4, baseline=each variant)")
    for v, c in rep["paired_vs_H4"].items():
        if c:
            print(f"  H4 vs {v:18s} delta={_fmt(c['delta_success_rate']):>7s}  McNemar p={_fmt(c['mcnemar_exact_p']):>6s}  n={c['n_pairs']}")

    print("\n[6] INFORMATION-WITHOUT-STRUCTURE ARMS")
    for name, c in rep["info_without_structure"].items():
        if c:
            print(f"  {name:42s} delta={_fmt(c['delta_success_rate']):>7s}  McNemar p={_fmt(c['mcnemar_exact_p']):>6s}  n={c['n_pairs']}")

    print("\n[7] HEADLINE >=80% RULE  (fraction of H4-generic delta recovered by one factor)")
    for stratum in ["all", "single_step_leaf", "multi_step_workflow"]:
        h = rep["headline_80pct_rule"].get(stratum, {})
        df = h.get("delta_full_H4_minus_generic")
        print(f"  [{stratum}] delta_full(H4-generic)={_fmt(df)}  n={h.get('n_pairs_full')}")
        for name, fr in (h.get("factors") or {}).items():
            if fr:
                mark = "  <== >=80%" if fr["meets_80pct"] else ""
                print(f"      {name:34s} recov={_fmt(fr['recovery_delta']):>7s}  frac={_fmt(fr['fraction_of_full']):>7s}{mark}")

    print("\n[8] PER-SEED success rate by variant")
    seeds = sorted(rep["per_seed_success"].keys())
    print(f"  {'variant':18s} " + " ".join(f"seed{s:>2s}" for s in seeds))
    for v in VARIANTS:
        cells = " ".join(f"{_fmt(rep['per_seed_success'][s].get(v)):>6s}" for s in seeds)
        print(f"  {v:18s} {cells}")

    # Verdict
    key = rep["H4_vs_targeted_untyped"].get("all")
    print(f"\n{'='*72}\nVERDICT\n{'='*72}")
    if key:
        d = key["delta_success_rate"]
        p = key["mcnemar_exact_p"]
        lo, hi = key["ci_low"], key["ci_high"]
        print(f"  H4 vs targeted+untyped: delta={_fmt(d)} (95% CI {_fmt(lo)}..{_fmt(hi)}), "
              f"McNemar p={_fmt(p)}, n={key['n_pairs']} pairs.")
        # Equivalence read from the CI: both bounds inside +/-3pp is positive
        # evidence of a tie, not merely absence of a significant difference.
        ci_equiv = (lo is not None and hi is not None and abs(lo) < 0.03 and abs(hi) < 0.03)
        tie = p > 0.05 and abs(d) < 0.03
        if tie:
            eq = "CI supports equivalence (both bounds within +/-3pp)." if ci_equiv else \
                 "note: not significant, but CI is wide — absence of evidence, not proven equivalence."
            print("  => H4 ~= targeted+untyped. Mechanism = INFORMATION CONTENT, not typing per se.")
            print(f"     Reframe 'typed repair' -> 'diagnostic repair'. {eq}")
        else:
            print(f"  => H4 beats targeted+untyped. Typing/structure carries signal beyond diagnostic info.")
    else:
        print("  (run still warming up — insufficient paired instances for the key contrast)")

    # Headline factor (>=80% rule) on the full-population stratum
    h_all = rep["headline_80pct_rule"].get("all", {})
    df = h_all.get("delta_full_H4_minus_generic")
    if df is not None and df < 0:
        print(f"  [!] H4-generic delta is NEGATIVE ({_fmt(df)}) — H4 underperforms generic-retry; "
              f">=80% recovery fractions are not interpretable.")
    elif h_all.get("factors"):
        winners = [n for n, fr in h_all["factors"].items() if fr and fr.get("meets_80pct")]
        if winners:
            print(f"  Mechanism factor(s) recovering >=80% of the H4-generic delta: {', '.join(winners)}.")
        else:
            print("  No single factor recovers >=80% of the H4-generic delta (mechanism is multi-factor).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()
    rows = read_results(args.run_dir)
    if not rows:
        print(f"No rows in {args.run_dir}/results.jsonl yet.")
        return 0
    rep = analyze(rows)
    print_report(rep)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(rep, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nWrote JSON: {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
