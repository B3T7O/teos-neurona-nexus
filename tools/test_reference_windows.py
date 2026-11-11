#!/usr/bin/env python3
"""Compara ventanas de referencia: 10m, 30m, 1h, 2h sobre los mismos datos."""
import json
from pathlib import Path
from statistics import mean, median
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"


def parse_ts(s):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def p95(v):
    s = sorted(v)
    return s[int(0.95 * (len(s)-1))] if s else 0


def main():
    samples = []
    with SAMPLES.open() as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try: o = json.loads(ln)
            except: continue
            if o.get("quality") != "ok": continue
            dt = parse_ts(o.get("timestamp"))
            hr = o.get("hashRate")
            if dt and isinstance(hr, (int, float)) and hr > 0:
                samples.append({"dt": dt, "hr": float(hr)})
    samples.sort(key=lambda x: x["dt"])
    print(f"Samples: {len(samples)}")

    windows_min = {"10m": 10, "30m": 30, "60m": 60, "120m": 120}
    results = {w: [] for w in windows_min}

    # Recorrer samples y calcular medias por ventana
    split = int(len(samples) * 0.7)
    for i in range(split, len(samples) - 1):
        curr_dt = samples[i]["dt"]
        target = samples[i + 1]["hr"]
        for name, wmin in windows_min.items():
            # Samples dentro de la ventana [curr_dt - wmin, curr_dt)
            cutoff = curr_dt.timestamp() - wmin * 60
            window_vals = []
            j = i
            while j >= 0 and samples[j]["dt"].timestamp() >= cutoff:
                window_vals.append(samples[j]["hr"])
                j -= 1
            if len(window_vals) < 3: continue
            pred = mean(window_vals)
            ape = 100 * abs(pred - target) / max(1.0, target)
            results[name].append(ape)

    print()
    print(f"{'VENTANA':<10} {'n':>6} {'mean':>8} {'median':>8} {'p95':>8}")
    print("-" * 50)
    for name in windows_min:
        apes = results[name]
        if not apes: continue
        print(f"{name:<10} {len(apes):>6} {mean(apes):>7.3f}% {median(apes):>7.3f}% {p95(apes):>7.3f}%")

    # Ganador
    best = min(results.items(), key=lambda kv: mean(kv[1]) if kv[1] else 999)
    print()
    print(f"Mejor mean: {best[0]} ({mean(best[1]):.3f}%)")


if __name__ == "__main__":
    main()
