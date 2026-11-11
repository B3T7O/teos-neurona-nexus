"""
Analiza si el APE cambia según blockHeight.
Versión optimizada: O(n log n) con búsqueda binaria.
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from bisect import bisect_right

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"


def _parse_ts(s):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


# 1. Cargar blockHeight por timestamp
pairs = []
with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        if not ln: continue
        try:
            o = json.loads(ln)
            ts = o.get("timestamp")
            h = o.get("blockHeight")
            dt = _parse_ts(ts)
            if dt and isinstance(h, (int, float)) and h > 0:
                pairs.append((dt, h))
        except json.JSONDecodeError:
            pass

if not pairs:
    print("❌ No hay blockHeight en samples")
    raise SystemExit(1)

pairs.sort(key=lambda x: x[0])
sorted_dts = [p[0] for p in pairs]
sorted_heights = [p[1] for p in pairs]

print(f"📊 blockHeight en samples:")
print(f"   Rango: {min(sorted_heights)} → {max(sorted_heights)}")
print(f"   Span:  {max(sorted_heights) - min(sorted_heights)} bloques")
print(f"   Muestras: {len(pairs)}")
print()

# 2. Para cada outcome, encontrar height más cercano con búsqueda binaria
outcomes = []
with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        if not ln: continue
        try:
            o = json.loads(ln)
            method = o.get("method")
            src_ts = o.get("source_timestamp")
            ape = o.get("absolute_percentage_error")
            if method and src_ts and isinstance(ape, (int, float)):
                dt = _parse_ts(src_ts)
                if dt:
                    idx = bisect_right(sorted_dts, dt) - 1
                    if idx >= 0:
                        outcomes.append({
                            "method": method,
                            "ape": ape,
                            "height": sorted_heights[idx],
                        })
        except json.JSONDecodeError:
            pass

print(f"📊 Outcomes con blockHeight asignado: {len(outcomes)}")
print()

# 3. Agrupar por bin de altura
span = max(sorted_heights) - min(sorted_heights)
bin_size = max(200, span // 5)

bins = defaultdict(lambda: defaultdict(list))
for o in outcomes:
    bin_start = (o["height"] // bin_size) * bin_size
    bins[bin_start][o["method"]].append(o["ape"])

print(f"📊 APE por método por bin (bin_size={bin_size} bloques):")
print()
for bin_start in sorted(bins.keys()):
    bin_end = bin_start + bin_size
    print(f"  Bin [{bin_start} - {bin_end}):")
    for method in sorted(bins[bin_start].keys()):
        apes = bins[bin_start][method]
        if len(apes) >= 5:
            mean = sum(apes) / len(apes)
            print(f"    {method:25s} {mean:.3f}% (n={len(apes)})")
    print()

print("=" * 60)
print(" ¿EL RANKING DE MÉTODOS CAMBIA SEGÚN LA ALTURA?")
print("=" * 60)
print()
for bin_start in sorted(bins.keys()):
    bin_end = bin_start + bin_size
    ranked = []
    for method, apes in bins[bin_start].items():
        if len(apes) >= 5:
            ranked.append((sum(apes)/len(apes), method))
    ranked.sort()
    if ranked:
        top = ranked[0]
        print(f"  Bin [{bin_start}-{bin_end}): mejor = {top[1]} ({top[0]:.3f}%)")
