#!/usr/bin/env python3
"""
Paso 1: Diagnostico de senales para deteccion de anomalias.
No modela. Solo describe los datos.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"

# Umbrales tipicos de un Bitaxe (ajustar si es otro modelo)
TEMP_WARN = 65.0
TEMP_CRIT = 75.0
VRTEMP_WARN = 80.0
ERROR_PCT_WARN = 5.0
REJECT_RATIO_WARN = 0.10
WIFI_WEAK = -70.0
HASHRATE_DROP = 0.50  # fraccion del expected


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


def num(o, k):
    v = o.get(k)
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


def find_windows(samples, cond, min_gap_sec=120, min_size=2):
    """Agrupa muestras consecutivas que cumplen `cond`."""
    windows = []
    cur = []
    prev_dt = None
    for s in samples:
        dt = s["_dt"]
        if cond(s):
            if prev_dt is None or (dt - prev_dt).total_seconds() <= min_gap_sec:
                cur.append(s)
            else:
                if len(cur) >= min_size:
                    windows.append(cur)
                cur = [s]
            prev_dt = dt
        else:
            if len(cur) >= min_size:
                windows.append(cur)
            cur = []
            prev_dt = None
    if len(cur) >= min_size:
        windows.append(cur)
    return windows


def describe(label, vals):
    if not vals:
        print(f"  {label:20s} sin datos")
        return
    a = np.array(vals)
    print(f"  {label:20s} n={len(a):6d}  "
          f"min={a.min():8.2f}  med={np.median(a):8.2f}  "
          f"p95={np.percentile(a, 95):8.2f}  max={a.max():8.2f}")


def main():
    print("Cargando samples...")
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
            if dt is None:
                continue
            o["_dt"] = dt
            samples.append(o)
    samples.sort(key=lambda x: x["_dt"])
    print(f"Samples: {len(samples)}")
    if len(samples) < 100:
        print("Pocos samples.")
        return
    print(f"Rango: {samples[0]['timestamp']} -> {samples[-1]['timestamp']}")
    dur = (samples[-1]["_dt"] - samples[0]["_dt"]).total_seconds() / 86400
    print(f"Duracion: {dur:.1f} dias")

    print("\n=== Distribuciones ===")
    for k in ["hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h",
              "expectedHashrate", "temp", "vrTemp", "power", "voltage",
              "frequency", "errorPercentage", "wifiRSSI",
              "sharesAccepted", "sharesRejected"]:
        vals = [num(s, k) for s in samples]
        vals = [v for v in vals if v is not None]
        describe(k, vals)

    print("\n=== Frecuencia de eventos ===")
    events = {
        f"temp > {TEMP_WARN}C": lambda s: (num(s, "temp") or 0) > TEMP_WARN,
        f"temp > {TEMP_CRIT}C": lambda s: (num(s, "temp") or 0) > TEMP_CRIT,
        f"vrTemp > {VRTEMP_WARN}C": lambda s: (num(s, "vrTemp") or 0) > VRTEMP_WARN,
        f"error% > {ERROR_PCT_WARN}": lambda s: (num(s, "errorPercentage") or 0) > ERROR_PCT_WARN,
        "rechazo > 10%": lambda s: (
            (num(s, "sharesRejected") or 0) /
            max(1.0, (num(s, "sharesAccepted") or 0) + (num(s, "sharesRejected") or 0))
        ) > REJECT_RATIO_WARN,
        f"wifi < {WIFI_WEAK}dBm": lambda s: (num(s, "wifiRSSI") or 0) < WIFI_WEAK,
        f"hashRate < 50% expected": lambda s: (
            (num(s, "hashRate") or 0) < HASHRATE_DROP * (num(s, "expectedHashrate") or float("inf"))
        ),
    }
    for name, cond in events.items():
        n = sum(1 for s in samples if cond(s))
        pct = 100.0 * n / len(samples)
        print(f"  {name:30s} {n:6d} muestras ({pct:5.2f}%)")

    print("\n=== Ventanas continuas (>=2 muestras seguidas) ===")
    for name, cond in events.items():
        windows = find_windows(samples, cond, min_gap_sec=120, min_size=2)
        if not windows:
            continue
        print(f"\n  {name}: {len(windows)} ventanas")
        for w in windows[:5]:
            start = w[0]["timestamp"]
            end = w[-1]["timestamp"]
            dur_min = (w[-1]["_dt"] - w[0]["_dt"]).total_seconds() / 60
            print(f"    {start} -> {end}  ({len(w)} muestras, {dur_min:.0f} min)")
        if len(windows) > 5:
            print(f"    ... y {len(windows)-5} ventanas mas")

    print("\n=== Correlacion con hashrate (Pearson) ===")
    hr_vals = []
    feature_names = ["temp", "vrTemp", "power", "voltage", "frequency",
                     "errorPercentage", "wifiRSSI", "sharesRejected",
                     "hashRate_1m", "hashRate_10m", "hashRate_1h"]
    feat_rows = []
    for s in samples:
        hr = num(s, "hashRate")
        if hr is None:
            continue
        row = {k: num(s, k) for k in feature_names}
        if any(v is None for v in row.values()):
            continue
        row["_hr"] = hr
        feat_rows.append(row)

    if feat_rows:
        hr_arr = np.array([r["_hr"] for r in feat_rows])
        for k in feature_names:
            x = np.array([r[k] for r in feat_rows])
            if x.std() == 0:
                print(f"  {k:15s} constante, corr indefinida")
                continue
            corr = float(np.corrcoef(x, hr_arr)[0, 1])
            print(f"  {k:15s} corr={corr:+.3f}")

    print("\nDiagnostico completo.")


if __name__ == "__main__":
    main()
