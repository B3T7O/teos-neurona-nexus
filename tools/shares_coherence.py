#!/usr/bin/env python3
"""
Test de coherencia de shares:
  compara sharesAccepted reales (delta entre muestras) vs esperados
  dada tu hashrate y la pool_difficulty.

Si la mediana del ratio (real/esperado) esta entre 0.8 y 1.2 -> sano.
Si <0.8 o >1.2 -> revisar conexion, pool, firmware o uptime.
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


def num(o, k):
    v = o.get(k)
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


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
            sa = num(o, "sharesAccepted")
            sr = num(o, "sharesRejected")
            hr = num(o, "hashRate")
            pd = num(o, "poolDifficulty")
            up = num(o, "uptimeSeconds")
            if dt is None or sa is None or sr is None or hr is None or pd is None or pd <= 0:
                continue
            samples.append({
                "_dt": dt, "ts": o.get("timestamp"),
                "sa": sa, "sr": sr, "hr": hr, "pd": pd, "up": up,
            })
    samples.sort(key=lambda x: x["_dt"])
    print(f"Samples validos: {len(samples)}")
    if len(samples) < 50:
        print("Pocos samples.")
        return

    # --- Detectar reinicios por reset de contadores o caida de uptime ---
    deltas = []
    resets = 0
    for i in range(1, len(samples)):
        prev, cur = samples[i - 1], samples[i]
        if cur["up"] is not None and prev["up"] is not None:
            if cur["up"] < prev["up"]:
                resets += 1
                continue
        d_sa = cur["sa"] - prev["sa"]
        d_sr = cur["sr"] - prev["sr"]
        dt_sec = (cur["_dt"] - prev["_dt"]).total_seconds()
        if dt_sec <= 0 or dt_sec > 300 or d_sa < 0 or d_sr < 0:
            continue
        deltas.append({
            "d_sa": d_sa, "d_sr": d_sr, "dt_sec": dt_sec,
            "hr": cur["hr"], "pd": cur["pd"],
        })

    print(f"Reinicios detectados (uptime cae): {resets}")
    print(f"Intervalos validos: {len(deltas)}")
    if not deltas:
        print("Sin intervalos validos.")
        return

    # --- Comparar por bloque de tamano variable: usar mediana de 100 intervalos ---
    # Calcular ratio real/esperado por intervalo
    ratios = []
    rejects_ratios = []
    for d in deltas:
        hr_hs = d["hr"] * 1e9
        expected_shares = hr_hs / (d["pd"] * (2**32)) * d["dt_sec"]
        if expected_shares < 0.01:  # ruido muy bajo, ignorar
            continue
        ratio = d["d_sa"] / expected_shares
        ratios.append(ratio)
        total = d["d_sa"] + d["d_sr"]
        if total > 0:
            rejects_ratios.append(d["d_sr"] / total)

    if not ratios:
        print("Sin ratios calculables (intervalos muy cortos).")
        return

    r = np.array(ratios)
    print()
    print("=" * 60)
    print(" COHERENCIA DE SHARES")
    print("=" * 60)
    print(f"  Intervalos evaluados: {len(r)}")
    print(f"  Ratio real/esperado (mediana):  {np.median(r):.3f}")
    print(f"  Media:                          {np.mean(r):.3f}")
    print(f"  P05 / P95:                      {np.percentile(r,5):.3f} / {np.percentile(r,95):.3f}")
    print(f"  Min / Max:                      {r.min():.3f} / {r.max():.3f}")

    med = float(np.median(r))
    if 0.8 <= med <= 1.2:
        print(f"  ✅ Sano: ratio mediano {med:.2f} dentro de [0.8, 1.2]")
    elif 0.6 <= med < 0.8:
        print(f"  ⚠️  Bajo: ratio {med:.2f} -> revisar conexion al pool")
    elif 1.2 < med <= 1.4:
        print(f"  ⚠️  Alto: ratio {med:.2f} -> posible pool diff desactualizada")
    else:
        print(f"  ❌ Fuera de rango: {med:.2f} -> revisar urgente")

    if rejects_ratios:
        print()
        print(f"  Tasa de rechazo:")
        print(f"    Mediana: {np.median(rejects_ratios)*100:.3f}%")
        print(f"    Media:   {np.mean(rejects_ratios)*100:.3f}%")
        if np.median(rejects_ratios) > 0.05:
            print("  ⚠️  Rechazo alto (>5%). Revisar conexion / pool.")
        else:
            print("  ✅ Rechazo normal (<5%).")

    # Top 5 peores intervalos
    print()
    print("  Peores 5 intervalos (ratio mas bajo):")
    indexed = sorted(enumerate(ratios), key=lambda x: x[1])[:5]
    for idx, val in indexed:
        d = deltas[idx] if idx < len(deltas) else None
        if d:
            ts = samples[idx + 1]["ts"] if idx + 1 < len(samples) else "?"
            print(f"    {ts}  ratio={val:.3f}  dt={d['dt_sec']:.0f}s  "
                  f"d_sa={d['d_sa']:.0f}  hr={d['hr']:.0f}")

    print("=" * 60)


if __name__ == "__main__":
    main()
