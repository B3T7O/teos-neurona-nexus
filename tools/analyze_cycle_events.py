#!/usr/bin/env python3
"""
v4: ventana comun (CUTOFF = primera prediccion de adaptativo_neurona).
Todos los metodos se evaluan solo desde ahi.
"""
import json
import time
import traceback
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, median
from bisect import bisect_right

START = time.time()
CUTOFF = "2026-10-23T05:10:18"


def log(m=""):
    print(m, flush=True)


def elapsed():
    return f"[{time.time()-START:5.1f}s]"


ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
DIFF_EPOCH = 2016
MIN_N = 30


def parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(second=0, microsecond=0)
    except Exception:
        return None


def p95(v):
    s = sorted(v)
    return s[int(0.95 * (len(s)-1))]


def stats(apes):
    return {"n": len(apes), "mean": mean(apes), "median": median(apes),
            "p95": p95(apes), "max": max(apes),
            "pct_over_5": 100.0*sum(1 for a in apes if a > 5.0)/len(apes)}


def fmt(m, st):
    return (f"{m:22s} n={st['n']:5d} mean={st['mean']:.3f}% med={st['median']:.3f}% "
            f"p95={st['p95']:.3f}% >5%={st['pct_over_5']:.1f}%")


def blocks_to_adj(h):
    return DIFF_EPOCH - (h % DIFF_EPOCH)


def main():
    log(f"{elapsed()} Cargando samples...")
    samples = []
    with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
                h = o.get("blockHeight")
                dt = parse_ts(o.get("timestamp"))
                if isinstance(h, (int, float)) and h > 0 and dt:
                    samples.append({"dt": dt, "height": int(h)})
            except Exception:
                pass
    samples.sort(key=lambda x: x["dt"])
    dts = [s["dt"] for s in samples]
    heights = [s["height"] for s in samples]
    log(f"{elapsed()} samples: {len(samples)}")

    log(f"\n{elapsed()} Cargando outcomes (cutoff={CUTOFF})...")
    outcomes = []
    dropped_before = 0
    with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
                src = o.get("source_timestamp") or ""
                if src < CUTOFF:
                    dropped_before += 1
                    continue
                m = o.get("method")
                ape = o.get("absolute_percentage_error")
                dt = parse_ts(src)
                if m and isinstance(ape, (int, float)) and dt:
                    idx = bisect_right(dts, dt) - 1
                    if idx >= 0:
                        outcomes.append({"method": m, "ape": ape, "dt": dt,
                                         "blocks": blocks_to_adj(heights[idx])})
            except Exception:
                pass
    outcomes.sort(key=lambda x: x["dt"])
    log(f"{elapsed()} outcomes en ventana: {len(outcomes)} (descartados pre-cutoff: {dropped_before})")

    # Distribucion por metodo
    per_m = defaultdict(int)
    for o in outcomes:
        per_m[o["method"]] += 1
    for m, n in sorted(per_m.items()):
        log(f"   {m:22s} {n}")

    # Cuartiles
    vals = sorted(o["blocks"] for o in outcomes)
    q25, q50, q75 = vals[len(vals)//4], vals[len(vals)//2], vals[3*len(vals)//4]
    log(f"\n{elapsed()} Cuartiles blocks_to_adj: {q25} | {q50} | {q75}")

    def bq(v):
        return "Q1" if v <= q25 else "Q2" if v <= q50 else "Q3" if v <= q75 else "Q4"

    # Agrupar por (bin, dt, metodo)
    by_bin_dt = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for o in outcomes:
        by_bin_dt[bq(o["blocks"])][o["dt"]][o["method"]].append(o["ape"])

    log(f"\n{'='*60}")
    log(" FEATURE 1 (ventana comun)")
    log(f"{'='*60}")

    for b in ["Q1", "Q2", "Q3", "Q4"]:
        bd = by_bin_dt.get(b, {})
        if not bd:
            continue
        methods = sorted({m for d in bd.values() for m in d})
        log(f"\n{b}  (metodos: {methods})")

        valid = [m for m in methods
                 if sum(len(d.get(m, [])) for d in bd.values()) >= MIN_N]
        if len(valid) < 2:
            log("  sin metodos suficientes")
            continue

        inter = defaultdict(list)
        n_common = 0
        for dt, d in bd.items():
            if all(m in d and d[m] for m in valid):
                n_common += 1
                for m in valid:
                    inter[m].append(mean(d[m]))

        log(f"  interseccion: {n_common} timestamps comunes")
        if n_common == 0:
            continue
        for m in valid:
            if inter[m]:
                log(f"    {fmt(m, stats(inter[m]))}")
        means = sorted((mean(inter[m]), m) for m in valid if inter[m])
        p95s = sorted((p95(inter[m]), m) for m in valid if inter[m])
        log(f"    Mejor media: {means[0][1]} ({means[0][0]:.3f}%)")
        log(f"    Mejor p95:   {p95s[0][1]} ({p95s[0][0]:.3f}%)")

    log(f"\n{elapsed()} OK")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
