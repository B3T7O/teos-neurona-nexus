#!/usr/bin/env python3
"""
Compara modo adaptativo (choose_adaptive_method) vs modo champion (pesos ponderados)
sobre los outcomes historicos. Solo lectura. No toca produccion.
"""
import json
import sys
from pathlib import Path
from statistics import mean, median
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
CHAMPION = ROOT / "data" / "processed" / "evolve_champion.json"

METHODS = ["adaptativo_neurona", "referencia_10m", "referencia_1h",
           "media_ultimas_5", "ultimo_hashrate"]

# Cargar weights
if not CHAMPION.exists():
    print("ERROR: no existe evolve_champion.json")
    sys.exit(1)
champion = json.loads(CHAMPION.read_text())
weights = champion.get("weights", {})
print(f"Champion cargado: APE={champion.get('ape_mean')}, weights={weights}")
print()

# Cargar outcomes agrupados por target_timestamp
print("Cargando outcomes...")
by_target = defaultdict(dict)
all_outcomes = []
with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
    for ln in f:
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        t = o.get("target_timestamp")
        m = o.get("method")
        pred = o.get("predicted_hashRate_GHs")
        actual = o.get("actual_hashRate_GHs")
        if not t or not m or not isinstance(pred, (int, float)) or not isinstance(actual, (int, float)):
            continue
        by_target[t][m] = {"pred": float(pred), "actual": float(actual)}
        all_outcomes.append(o)

print(f"Targets únicos: {len(by_target)}")
print()

# Recorrer targets en orden cronologico
print("Comparando modos...")
timeline = []
for t in sorted(by_target.keys()):
    methods_here = by_target[t]
    actual = None
    for m in METHODS:
        if m in methods_here:
            actual = methods_here[m]["actual"]
            break
    if actual is None:
        continue

    preds = {m: methods_here[m]["pred"] for m in METHODS if m in methods_here}
    if len(preds) < 3:
        continue

    # Modo champion: suma ponderada (solo metodos presentes)
    pred_champion = sum(weights.get(m, 0.0) * preds[m] for m in preds) / max(1e-9, sum(weights.get(m, 0.0) for m in preds))

    # Modo adaptativo: usar solo referencia_1h como aproximacion (el mas usado por choose_adaptive_method historicamente)
    pred_adaptativo = preds.get("referencia_1h", pred_champion)

    ape_champ = 100.0 * abs(actual - pred_champion) / max(1.0, actual)
    ape_adapt = 100.0 * abs(actual - pred_adaptativo) / max(1.0, actual)

    timeline.append({
        "ts": t,
        "champion": pred_champion,
        "adaptativo": pred_adaptativo,
        "actual": actual,
        "ape_champion": ape_champ,
        "ape_adaptativo": ape_adapt,
    })

if not timeline:
    print("No hay datos suficientes para comparar.")
    sys.exit(0)

# Limitar a ventana comun ultimos N
N = min(5000, len(timeline))
sample = timeline[-N:]
print(f"Evaluando {N} timestamps recientes")
print()

apes_c = [x["ape_champion"] for x in sample]
apes_a = [x["ape_adaptativo"] for x in sample]

print("=" * 70)
print(f" {'MODO':<20} {'APE mean':>10} {'APE median':>12} {'APE p95':>10}")
print("=" * 70)
print(f" {'champion':<20} {mean(apes_c):>9.3f}% {median(apes_c):>11.3f}% {sorted(apes_c)[int(0.95*len(apes_c))]:>9.3f}%")
print(f" {'adaptativo (ref_1h)':<20} {mean(apes_a):>9.3f}% {median(apes_a):>11.3f}% {sorted(apes_a)[int(0.95*len(apes_a))]:>9.3f}%")
print()

diff_mean = mean(apes_a) - mean(apes_c)
diff_median = median(apes_a) - median(apes_c)
print(f"Diferencia (adaptativo - champion):")
print(f"  mean:   {diff_mean:+.3f} pp")
print(f"  median: {diff_median:+.3f} pp")
print()

if diff_mean > 0.05 or diff_median > 0.05:
    print("✅ Champion GANA. Vale la pena integrarlo.")
elif diff_mean < -0.05 and diff_median < -0.05:
    print("❌ Champion PIERDE. No integrar.")
else:
    print("⚠️  Sin diferencia significativa. No integrar por ahora.")
