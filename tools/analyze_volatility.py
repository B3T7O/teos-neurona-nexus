"""
Analiza si el APE cambia según la volatilidad del hashrate.
Versión optimizada: O(n log n) con búsqueda binaria.
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from statistics import mean, stdev
from bisect import bisect_right

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
WINDOW = 12


def _parse_ts(s):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


# 1. Cargar samples
samples = []
with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        if not ln: continue
        try:
            o = json.loads(ln)
            h = o.get("hashRate")
            ts = o.get("timestamp")
            if isinstance(h, (int, float)) and h > 0:
                dt = _parse_ts(ts)
                if dt:
                    samples.append({"dt": dt, "hashrate": h})
        except json.JSONDecodeError:
            pass

samples.sort(key=lambda x: x["dt"])
if len(samples) < WINDOW * 2:
    print("❌ Muy pocos samples")
    raise SystemExit(1)

# 2. Volatilidad por índice (CV)
vol_by_idx = []
for i in range(WINDOW, len(samples)):
    window = samples[i-WINDOW:i]
    hrs = [s["hashrate"] for s in window]
    m = mean(hrs)
    vol_by_idx.append(stdev(hrs) / m if m > 0 else 0.0)

# Alinear: vol_by_idx[j] corresponde a samples[WINDOW + j]
sorted_dts = [s["dt"] for s in samples]

vols_sorted = sorted(vol_by_idx)
p33 = vols_sorted[len(vols_sorted)//3]
p66 = vols_sorted[2*len(vols_sorted)//3]

print(f"📊 Samples: {len(samples)}")
print(f"   Volatilidad (CV):")
print(f"     Baja   (< {p33:.4f})")
print(f"     Media  ({p33:.4f} - {p66:.4f})")
print(f"     Alta   (> {p66:.4f})")
print()

# 3. Outcomes con volatilidad por búsqueda binaria
outcomes = []
with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        if not ln: continue
        try:
            o = json.loads(ln)
            m = o.get("method")
            src = o.get("source_timestamp")
            ape = o.get("absolute_percentage_error")
            if m and src and isinstance(ape, (int, float)):
                dt = _parse_ts(src)
                if dt:
                    idx = bisect_right(sorted_dts, dt) - 1
                    if idx >= WINDOW:
                        vol = vol_by_idx[idx - WINDOW]
                        outcomes.append({"method": m, "ape": ape, "vol": vol})
        except json.JSONDecodeError:
            pass

print(f"📊 Outcomes con volatilidad asignada: {len(outcomes)}")
print()


def regimen(v):
    if v < p33: return "BAJA"
    elif v < p66: return "MEDIA"
    else: return "ALTA"


bins = defaultdict(lambda: defaultdict(list))
for o in outcomes:
    bins[regimen(o["vol"])][o["method"]].append(o["ape"])

for reg in ["BAJA", "MEDIA", "ALTA"]:
    print(f"📊 Régimen {reg}:")
    for method in sorted(bins[reg].keys()):
        apes = bins[reg][method]
        if len(apes) >= 30:
            print(f"    {method:25s} {mean(apes):.3f}% (n={len(apes)})")
    print()

print("=" * 60)
print(" GANADOR POR RÉGIMEN DE VOLATILIDAD")
print("=" * 60)
for reg in ["BAJA", "MEDIA", "ALTA"]:
    ranked = [(mean(apes), m) for m, apes in bins[reg].items() if len(apes) >= 30]
    ranked.sort()
    if ranked:
        print(f"  {reg}: mejor = {ranked[0][1]} ({ranked[0][0]:.3f}%)")
