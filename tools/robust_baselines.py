#!/usr/bin/env python3
"""
Pendiente B: calcular baselines robustos y comparar con version actual.
Sobre los samples limpios (quality=ok), comparar:
  media simple  vs  mediana  vs  trimmed mean 10%
Para ventanas de 10m y 1h.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from statistics import mean, median
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"


def parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def safe(x):
    if isinstance(x, (int, float)) and math.isfinite(x):
        return float(x)
    return None


def trimmed_mean(vals, trim=0.10):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    k = int(n * trim)
    if n - 2 * k < 1:
        return mean(s)
    return mean(s[k:n - k])


def main():
    print("Cargando samples (quality=ok)...")
    samples = []
    with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if o.get("quality") != "ok":
                continue
            dt = parse_ts(o.get("timestamp"))
            hr = safe(o.get("hashRate"))
            if dt is None or hr is None or hr <= 0:
                continue
            samples.append({"dt": dt, "hashRate": hr})
    samples.sort(key=lambda x: x["dt"])
    print(f"Samples validos: {len(samples)}")

    # Evaluar tres versiones para cada ventana, sobre el test final (30%)
    split = int(len(samples) * 0.7)
    train, test = samples[:split], samples[split:]
    print(f"Train: {len(train)} | Test: {len(test)}")

    # Index de entrenamiento para cada posicion de test
    all_samples = train + test
    test_start = len(train)

    for window_min in [10, 60]:
        print(f"\n=== Ventana {window_min}m ===")
        results = {"media": [], "mediana": [], "trimmed10": []}

        for i in range(test_start + window_min, len(all_samples) - 1):
            # samples en la ventana [i-window_min, i)
            window = [all_samples[j]["hashRate"]
                      for j in range(i - window_min, i)]
            target = all_samples[i + 1]["hashRate"] if i + 1 < len(all_samples) else None
            if target is None or not window:
                continue

            pred_media = mean(window)
            pred_mediana = median(window)
            pred_trimmed = trimmed_mean(window, 0.10)

            for name, pred in [("media", pred_media),
                               ("mediana", pred_mediana),
                               ("trimmed10", pred_trimmed)]:
                if pred is None:
                    continue
                ape = 100.0 * abs(target - pred) / max(1.0, target)
                results[name].append(ape)

        for name, apes in results.items():
            if not apes:
                print(f"  {name:12s} sin datos")
                continue
            arr = np.array(apes)
            print(f"  {name:12s} n={len(arr):5d}  "
                  f"APE mean={arr.mean():5.2f}%  median={np.median(arr):5.2f}%  "
                  f"p95={np.percentile(arr, 95):5.2f}%")

        # Ganador
        best = min(results.items(), key=lambda kv: mean(kv[1]) if kv[1] else 999)
        print(f"  🏆 Ganador por media: {best[0]}")

    print("\n=== Conclusion ===")
    print("Si media simple gana o empata, los baselines actuales son correctos.")
    print("Si mediana o trimmed mean ganan, hay que actualizar referencia_1h/10m.")


if __name__ == "__main__":
    main()
