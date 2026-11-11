"""
Validación temporal: ¿el "mejor por régimen de volatilidad" del pasado
predice el mejor en el futuro?
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


# 1. Samples y volatilidad
samples = []
with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        if not ln: continue
        try:
            o = json.loads(ln)
            h = o.get("hashRate")
            dt = _parse_ts(o.get("timestamp"))
            if isinstance(h, (int, float)) and h > 0 and dt:
                samples.append({"dt": dt, "hashrate": h})
        except json.JSONDecodeError:
            pass

samples.sort(key=lambda x: x["dt"])
vol_by_idx = []
for i in range(WINDOW, len(samples)):
    hrs = [s["hashrate"] for s in samples[i-WINDOW:i]]
    m = mean(hrs)
    vol_by_idx.append(stdev(hrs) / m if m > 0 else 0.0)

sorted_dts = [s["dt"] for s in samples]

# 2. Outcomes con volatilidad
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
                        outcomes.append({
                            "method": m,
                            "ape": ape,
                            "vol": vol_by_idx[idx - WINDOW],
                            "dt": dt,
                        })
        except json.JSONDecodeError:
            pass

# Ordenar por tiempo
outcomes.sort(key=lambda x: x["dt"])

# Split temporal
split = int(len(outcomes) * 0.7)
train = outcomes[:split]
test = outcomes[split:]

# Calcular regímenes con percentiles de TRAIN
train_vols = sorted([o["vol"] for o in train])
p33_train = train_vols[len(train_vols)//3]
p66_train = train_vols[2*len(train_vols)//3]


def regimen(v):
    if v < p33_train: return "BAJA"
    elif v < p66_train: return "MEDIA"
    else: return "ALTA"


# Mejor método por régimen en TRAIN
train_bins = defaultdict(lambda: defaultdict(list))
for o in train:
    train_bins[regimen(o["vol"])][o["method"]].append(o["ape"])

best_per_reg = {}
for reg, methods in train_bins.items():
    ranked = [(mean(apes), m) for m, apes in methods.items() if len(apes) >= 30]
    ranked.sort()
    if ranked:
        best_per_reg[reg] = ranked[0][1]

print("📊 Mejor método por régimen (calculado solo con TRAIN):")
for reg in ["BAJA", "MEDIA", "ALTA"]:
    print(f"   {reg}: {best_per_reg.get(reg, 'N/A')}")
print()

# Evaluar en TEST
test_bins = defaultdict(lambda: defaultdict(list))
for o in test:
    test_bins[regimen(o["vol"])][o["method"]].append(o["ape"])

chosen_apes = []
baseline_apes = []

for reg, methods in test_bins.items():
    if reg not in best_per_reg:
        continue
    chosen = best_per_reg[reg]
    if chosen in methods and len(methods[chosen]) >= 30:
        chosen_apes.extend(methods[chosen])

for o in test:
    if o["method"] == "referencia_1h":
        baseline_apes.append(o["ape"])

print("=" * 60)
print(" RESULTADO DE LA VALIDACIÓN TEMPORAL")
print("=" * 60)
if chosen_apes and baseline_apes:
    chosen_mean = mean(chosen_apes)
    baseline_mean = mean(baseline_apes)
    print(f"   APE del método elegido por volatilidad: {chosen_mean:.3f}% (n={len(chosen_apes)})")
    print(f"   APE de referencia_1h (baseline):        {baseline_mean:.3f}% (n={len(baseline_apes)})")
    diff = baseline_mean - chosen_mean
    if diff > 0.1:
        print(f"   ✅ La volatilidad AYUDA: {diff:.3f} puntos mejor que baseline")
    elif diff < -0.1:
        print(f"   ❌ La volatilidad EMPEORA: {abs(diff):.3f} puntos peor que baseline")
    else:
        print(f"   ⚠️  La volatilidad NO aporta: diferencia {abs(diff):.3f} puntos (ruido)")
