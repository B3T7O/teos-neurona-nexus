#!/usr/bin/env python3
"""
Precomputa data/processed/neuron_flow.json para el panel neuron_center.html.
Lee de learning_outcomes_v2.jsonl, history.jsonl y evolve_champion.json.
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from statistics import mean, median

ROOT = Path(__file__).resolve().parent.parent
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
HISTORY = ROOT / "data" / "evolve" / "history.jsonl"
CHAMPION = ROOT / "data" / "processed" / "evolve_champion.json"
OUTPUT = ROOT / "data" / "processed" / "neuron_flow.json"

METHODS = [
    "adaptativo_neurona",
    "referencia_10m",
    "referencia_1h",
    "media_ultimas_5",
    "ultimo_hashrate",
    "ridge_live",
]

ROLL_WINDOW = 100  # ultimas N predicciones por metodo
SERIES_LEN = 60    # ultimos N puntos para la serie temporal


def tail_jsonl(path, n):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [json.loads(l) for l in lines[-n:] if l.strip()]


def main():
    # 1. Ultimas N por metodo
    rows = []
    with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue

    # Agrupar por metodo
    by_method = {m: [] for m in METHODS}
    by_method_ts = {m: [] for m in METHODS}
    for r in rows:
        m = r.get("method")
        ape = r.get("absolute_percentage_error")
        ts = r.get("target_timestamp") or r.get("source_timestamp")
        if m in by_method and isinstance(ape, (int, float)) and ts:
            by_method[m].append(float(ape))
            by_method_ts[m].append(ts)

    # 2. Champion
    champion = {}
    if CHAMPION.exists():
        try:
            champion = json.loads(CHAMPION.read_text())
        except Exception:
            pass
    weights = champion.get("weights", {})

    # 3. Resumen por learner
    learners = []
    winner = None
    for m in METHODS:
        vals = by_method[m][-ROLL_WINDOW:]
        if not vals:
            continue
        info = {
            "method": m,
            "n_recent": len(vals),
            "ape_mean_recent": round(mean(vals), 4),
            "ape_median_recent": round(median(vals), 4),
            "is_champion_weight": round(float(weights.get(m, 0.0)), 4),
        }
        learners.append(info)
    if learners:
        winner = min(learners, key=lambda x: x["ape_mean_recent"])["method"]
        for l in learners:
            l["is_winner"] = (l["method"] == winner)

    # 4. Ultima prediccion vs real
    last_pred = None
    valid_rows = [
        r for r in rows
        if isinstance(r.get("absolute_percentage_error"), (int, float))
        and isinstance(r.get("predicted_hashRate_GHs"), (int, float))
        and isinstance(r.get("actual_hashRate_GHs"), (int, float))
    ]
    if valid_rows:
        r = valid_rows[-1]
        last_pred = {
            "method": r.get("method"),
            "predicted": round(float(r["predicted_hashRate_GHs"]), 2),
            "actual": round(float(r["actual_hashRate_GHs"]), 2),
            "ape": round(float(r["absolute_percentage_error"]), 4),
            "target_timestamp": r.get("target_timestamp"),
        }

    # 5. Ultimas evoluciones
    evolutions = []
    for e in tail_jsonl(HISTORY, 20):
        evolutions.append({
            "ts": e.get("ts"),
            "learner": e.get("learner"),
            "kind": e.get("kind"),
            "detail": (e.get("detail") or "")[:80],
        })

    # 6. Series temporales (ultimos N timestamps comunes)
    series = {}
    common_ts = None
    per_method_map = {}
    for m in METHODS:
        mp = {}
        for ts, ape in zip(by_method_ts[m], by_method[m]):
            mp[ts] = ape
        per_method_map[m] = mp
        ts_set = set(mp.keys())
        common_ts = ts_set if common_ts is None else (common_ts & ts_set)
    ordered_ts = sorted(common_ts or [])[-SERIES_LEN:]
    if ordered_ts:
        for m in METHODS:
            series[m] = [
                round(per_method_map[m].get(ts, 0.0), 3) for ts in ordered_ts
            ]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "champion": {
            "ape_mean": champion.get("ape_mean"),
            "weights": weights,
            "timestamp": champion.get("timestamp"),
        },
        "learners": learners,
        "winner": winner,
        "last_prediction": last_pred,
        "evolutions": evolutions,
        "series": {
            "timestamps": ordered_ts,
            "series": series,
        },
    }

    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {OUTPUT} generado")


if __name__ == "__main__":
    main()
