"""
Prueba: si elegimos el mejor método por bin de altura con datos del pasado,
¿acierta en datos futuros?
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from bisect import bisect_right
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
EPOCH = 2016
BIN_SIZE = EPOCH  # mismo tamaño de bin


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

# Ordenar por altura para simular paso del tiempo
outcomes.sort(key=lambda x: x["height"])

# Split: 70% train, 30% test
split = int(len(outcomes) * 0.7)
train = outcomes[:split]
test = outcomes[split:]

print(f"📊 Split temporal:")
print(f"   Train: {len(train)} muestras (altura {train[0]['height']} → {train[-1]['height']})")
print(f"   Test:  {len(test)} muestras (altura {test[0]['height']} → {test[-1]['height']})")
print()

# Calcular mejor método por bin en TRAIN
train_bins = defaultdict(lambda: defaultdict(list))
for o in train:
    train_bins[o["height"] // BIN_SIZE][o["method"]].append(o["ape"])

best_per_bin = {}
for b, methods in train_bins.items():
    ranked = [(mean(apes), m) for m, apes in methods.items() if len(apes) >= 10]
    ranked.sort()
    if ranked:
        best_per_bin[b] = ranked[0][1]

print(f"📊 Mejor método por bin (calculado solo con TRAIN):")
for b in sorted(best_per_bin.keys()):
    print(f"   Bin {b} [{b*BIN_SIZE}): {best_per_bin[b]}")
print()

# Evaluar en TEST usando la elección de TRAIN
correct_choices = 0
total_evals = 0
baseline_apes = []
chosen_apes = []

test_bins = defaultdict(lambda: defaultdict(list))
for o in test:
    test_bins[o["height"] // BIN_SIZE][o["method"]].append(o["ape"])

for b, methods in test_bins.items():
    if b not in best_per_bin:
        continue  # no tenemos elección para este bin
    chosen = best_per_bin[b]
    if chosen not in methods:
        continue
    apes = methods[chosen]
    if len(apes) >= 10:
        chosen_apes.extend(apes)
        total_evals += len(apes)

# Baseline: usar referencia_1h siempre
for o in test:
    if o["method"] == "referencia_1h":
        baseline_apes.append(o["ape"])

print("=" * 60)
print(" RESULTADO DE LA VALIDACIÓN TEMPORAL")
print("=" * 60)
if chosen_apes and baseline_apes:
    chosen_mean = mean(chosen_apes)
    baseline_mean = mean(baseline_apes)
    print(f"   APE del método elegido por altura: {chosen_mean:.3f}% (n={len(chosen_apes)})")
    print(f"   APE de referencia_1h (baseline):   {baseline_mean:.3f}% (n={len(baseline_apes)})")
    diff = baseline_mean - chosen_mean
    if diff > 0.1:
        print(f"   ✅ La altura AYUDA: {diff:.3f} puntos mejor que baseline")
    elif diff < -0.1:
        print(f"   ❌ La altura EMPEORA: {abs(diff):.3f} puntos peor que baseline")
    else:
        print(f"   ⚠️  La altura NO aporta: diferencia {abs(diff):.3f} puntos (ruido)")
else:
    print("   No hay datos suficientes para validar")
