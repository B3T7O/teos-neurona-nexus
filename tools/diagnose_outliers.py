#!/usr/bin/env python3
"""
Diagnostico de outliers masivos (APE > threshold).
Cruza outcomes con samples para entender si son datos reales o bugs.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "raw" / "bitaxe_samples.marked.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"

APE_THRESHOLD = 50.0  # %


def log(msg=""):
    print(msg, flush=True)


def parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(second=0, microsecond=0)
    except Exception:
        return None


def main():
    # ---- 1. Cargar samples indexados por minuto ----
    log("Cargando samples...")
    samples_by_min = defaultdict(list)
    sample_keys = set()
    with SAMPLES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
                sample_keys.update(o.keys())
                dt = parse_ts(o.get("timestamp"))
                if dt:
                    samples_by_min[dt].append(o)
            except Exception:
                pass
    log(f"  samples: {sum(len(v) for v in samples_by_min.values())} en {len(samples_by_min)} minutos")
    log(f"  campos en samples: {sorted(sample_keys)}")

    # ---- 2. Cargar outcomes, filtrar outliers ----
    log("\nCargando outcomes...")
    outcomes = []
    outcome_keys = set()
    with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
                outcome_keys.update(o.keys())
                ape = o.get("absolute_percentage_error")
                if isinstance(ape, (int, float)) and ape > APE_THRESHOLD:
                    outcomes.append(o)
            except Exception:
                pass
    log(f"  outliers APE > {APE_THRESHOLD}%: {len(outcomes)}")
    log(f"  campos en outcomes: {sorted(outcome_keys)}")

    if not outcomes:
        log("Sin outliers con ese umbral. Prueba APE_THRESHOLD mas bajo.")
        return

    # ---- 3. Agrupaciones ----
    by_method = Counter(o.get("method") for o in outcomes)
    by_min = Counter(parse_ts(o.get("source_timestamp")) for o in outcomes)

    log(f"\n=== Outliers por metodo ===")
    for m, n in by_method.most_common():
        log(f"  {m:22s} {n}")

    log(f"\n=== Outliers por minuto (top 15) ===")
    for dt, n in by_min.most_common(15):
        log(f"  {dt}  ->  {n} outliers")

    # ---- 4. Detalle de los 20 peores ----
    log(f"\n=== Detalle de los 20 peores ===")
    worst = sorted(outcomes, key=lambda o: o.get("absolute_percentage_error", 0), reverse=True)[:20]

    for i, o in enumerate(worst, 1):
        dt = parse_ts(o.get("source_timestamp"))
        ape = o.get("absolute_percentage_error")
        method = o.get("method")
        pred = o.get("predicted_value", o.get("prediction", o.get("predicted")))
        actual = o.get("actual_value", o.get("actual", o.get("target")))
        log(f"\n[{i}] method={method}  APE={ape:.2f}%  ts={dt}")
        log(f"    predicted={pred}  actual={actual}")

        # Cruzar con samples
        if dt and dt in samples_by_min:
            sample = samples_by_min[dt][0]
            log(f"    sample en ese minuto:")
            for k in ["blockHeight", "hashrate", "hashRate", "hashrate_ths",
                      "temperature", "power", "frequency", "voltage"]:
                if k in sample:
                    log(f"      {k} = {sample[k]}")
        elif dt:
            # Buscar el minuto mas cercano
            log(f"    SIN sample exacto en {dt}")
            nearby = [s for s in samples_by_min if abs((s - dt).total_seconds()) < 600]
            if nearby:
                log(f"    minutos cercanos con sample: {nearby[:3]}")

    # ---- 5. Distribucion de APE ----
    log(f"\n=== Distribucion APE (todos los outliers) ===")
    ranges = [(50, 100), (100, 500), (500, 1000), (1000, 10000), (10000, float("inf"))]
    for lo, hi in ranges:
        n = sum(1 for o in outcomes if lo <= o.get("absolute_percentage_error", 0) < hi)
        if n:
            log(f"  [{lo:>6} - {hi:>6})% : {n}")

    # ---- 6. Cuantos son de "adaptativo_neurona" ----
    log(f"\n=== Outliers por metodo Y si adaptativo predijo en ese minuto ===")
    dts_adapt = {parse_ts(o.get("source_timestamp")) for o in outcomes
                 if o.get("method") == "adaptativo_neurona"}
    log(f"  minutos donde adaptativo TAMBIEN tuvo outlier: {len(dts_adapt)}")
    log(f"  minutos donde adaptativo NO tuvo outlier:      {len(by_min) - len(dts_adapt)}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
