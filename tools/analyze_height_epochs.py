"""
Análisis por épocas de dificultad (cada 2016 bloques).
También reporta significancia estadística por bin.
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from bisect import bisect_right
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"

EPOCH = 2016  # bloques por época de dificultad


def _parse_ts(s):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


pairs = []
with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        if not ln: continue
        try:
            o = json.loads(ln)
            dt = _parse_ts(o.get("timestamp"))
            h = o.get("blockHeight")
            if dt and isinstance(h, (int, float)) and h > 0:
                pairs.append((dt, int(h)))
        except json.JSONDecodeError:
            pass

pairs.sort(key=lambda x: x[0])
sorted_dts = [p[0] for p in pairs]
sorted_heights = [p[1] for p in pairs]

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
                    if idx >= 0:
                        outcomes.append({"method": m, "ape": ape, "height": sorted_heights[idx]})
        except json.JSONDecodeError:
            pass

# Agrupar por época de dificultad
bins = defaultdict(lambda: defaultdict(list))
for o in outcomes:
    epoch = o["height"] // EPOCH
    bins[epoch][o["method"]].append(o["ape"])

print(f"📊 Épocas de dificultad (cada {EPOCH} bloques):")
print()
for ep in sorted(bins.keys()):
    lo = ep * EPOCH
    hi = lo + EPOCH
    total_n = sum(len(v) for v in bins[ep].values())
    print(f"  Época {ep} [{lo} - {hi})   muestras totales: {total_n}")
    for method in sorted(bins[ep].keys()):
        apes = bins[ep][method]
        if len(apes) >= 30:
            m = mean(apes)
            sd = stdev(apes) if len(apes) > 1 else 0
            # IC 95% aproximado
            ci = 1.96 * sd / (len(apes) ** 0.5)
            print(f"    {method:25s} {m:.3f}% ± {ci:.3f} (n={len(apes)})")
    print()

# ¿El ganador cambia por época?
print("=" * 60)
print(" GANADOR POR ÉPOCA (solo bins con n≥30 por método)")
print("=" * 60)
for ep in sorted(bins.keys()):
    ranked = []
    for method, apes in bins[ep].items():
        if len(apes) >= 30:
            ranked.append((mean(apes), method))
    ranked.sort()
    if ranked:
        lo = ep * EPOCH
        print(f"  Época {ep} [{lo}): mejor = {ranked[0][1]} ({ranked[0][0]:.3f}%)")
