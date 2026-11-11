#!/usr/bin/env python3
"""
Backfill de outcomes faltantes para predicciones de ridge_live.
Idempotente: no duplica si el outcome ya existe.
"""
import json
from pathlib import Path
from bisect import bisect_right
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
RIDGE = ROOT / "data" / "processed" / "ridge_live_predictions.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
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
    if isinstance(v, (int, float)):
        try:
            import math
            if math.isfinite(v):
                return float(v)
        except Exception:
            pass
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
            hr = num(o, "hashRate")
            if dt is None or hr is None or hr <= 0:
                continue
            samples.append({"dt": dt, "hr": hr})
    samples.sort(key=lambda x: x["dt"])
    print(f"Samples válidos: {len(samples)}")
    dts = [s["dt"] for s in samples]

    # IDs ya evaluados
    print("Cargando outcomes existentes...")
    existing = set()
    with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:
                continue
            pid = o.get("prediction_id")
            if pid:
                existing.add(pid)
    print(f"Outcomes existentes (por prediction_id): {len(existing)}")

    # Predicciones huérfanas
    print("Buscando predicciones huérfanas...")
    orphans = []
    with RIDGE.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:
                continue
            pid = o.get("prediction_id")
            if not pid or pid in existing:
                continue
            src = o.get("source_timestamp")
            pred = num(o, "predicted_hashRate_GHs")
            if not src or pred is None or pred <= 0:
                continue
            orphans.append({"pid": pid, "src": src, "pred": pred})
    print(f"Huérfanas a procesar: {len(orphans)}")

    if not orphans:
        print("Nada que hacer.")
        return

    # Emparejar con la primera muestra válida posterior
    print("Emparejando con muestras reales...")
    to_write = []
    no_match = 0
    for o in orphans:
        src_dt = parse_ts(o["src"])
        if src_dt is None:
            no_match += 1
            continue
        idx = bisect_right(dts, src_dt)
        if idx >= len(samples):
            no_match += 1
            continue
        target = samples[idx]
        actual = target["hr"]
        pred = o["pred"]
        error = actual - pred
        abs_err = abs(error)
        sq_err = error ** 2
        ape = 100.0 * abs_err / max(1.0, actual)
        to_write.append({
            "prediction_id": o["pid"],
            "method": "ridge_live",
            "source_timestamp": o["src"],
            "target_timestamp": target["dt"].isoformat(),
            "predicted_hashRate_GHs": round(pred, 6),
            "actual_hashRate_GHs": round(actual, 6),
            "error_GHs": round(error, 6),
            "absolute_error_GHs": round(abs_err, 6),
            "squared_error_GH2": round(sq_err, 6),
            "absolute_percentage_error": round(ape, 6),
            "evaluation": "backfill_ridge_live",
        })

    print(f"Outcomes a escribir: {len(to_write)}")
    print(f"Sin match (sin sample posterior): {no_match}")

    if not to_write:
        print("Nada que escribir.")
        return

    with OUTCOMES.open("a", encoding="utf-8") as f:
        for o in to_write:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    print(f"✅ Escritos {len(to_write)} outcomes nuevos")
    print(f"Total outcomes ahora: {len(existing) + len(to_write)}")


if __name__ == "__main__":
    main()
