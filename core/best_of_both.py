"""
TEOS Best-of-Both Selector v1.0
================================
Shadow-mode selector that chooses between:
- v1 Panoramic (method recommendation)
- v2-B Ensemble (weighted prediction)

Based on which one had lower APE in the last 30 minutes.
Does NOT affect production.

Author: Luis Alberto Siguencia Andrade (B3T7O)
License: Apache 2.0
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
try:
    from core.evolution_history import record as _evo_record
except Exception:
    def _evo_record(*a, **k): pass

import json
import statistics
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "data" / "processed" / "meta_learner_recommendations.jsonl"
ENSEMBLE = ROOT / "data" / "processed" / "ensemble_predictions_v2.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"
OUTPUT = ROOT / "data" / "processed" / "best_of_both_predictions.jsonl"

WINDOW_MINUTES = 30
MIN_SAMPLES = 3


def _parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _load(path):
    out = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    return out


def _v1_predictions_for_window(outcomes, metas, window_start):
    """Devuelve {target_timestamp: ape} para v1 en la ventana."""
    # Indexar outcomes por método
    outcomes_by_method = defaultdict(list)
    for o in outcomes:
        method = o.get("method")
        src_ts = o.get("source_timestamp")
        tgt = o.get("target_timestamp")
        pred = o.get("predicted_hashRate_GHs")
        actual = o.get("actual_hashRate_GHs")
        if method and src_ts and isinstance(pred, (int, float)) and isinstance(actual, (int, float)):
            dt = _parse_ts(src_ts)
            if dt:
                outcomes_by_method[method].append({
                    "dt": dt,
                    "pred": pred,
                    "actual": actual,
                    "target": tgt,
                })
    for m in outcomes_by_method:
        outcomes_by_method[m].sort(key=lambda x: x["dt"])

    result = {}
    for meta in metas:
        rec_ts = _parse_ts(meta.get("timestamp"))
        method = meta.get("recommended_method")
        if not rec_ts or rec_ts < window_start or not method:
            continue
        if method not in outcomes_by_method:
            continue
        for o in outcomes_by_method[method]:
            if o["dt"] >= rec_ts and o["actual"] > 0:
                ape = abs(o["pred"] - o["actual"]) / o["actual"] * 100
                result[o["target"]] = ape
                break
    return result


def _v2_predictions_for_window(outcomes, ensembles, window_start):
    """Devuelve {target_timestamp: ape} para v2-B en la ventana."""
    actual_by_target = {}
    for o in outcomes:
        tgt = o.get("target_timestamp")
        actual = o.get("actual_hashRate_GHs")
        if tgt and isinstance(actual, (int, float)) and actual > 0:
            actual_by_target[tgt] = actual

    result = {}
    for e in ensembles:
        ts = _parse_ts(e.get("timestamp"))
        if not ts or ts < window_start:
            continue
        tgt = e.get("target_timestamp")
        pred = e.get("ensemble_prediction_GHs")
        if tgt and tgt in actual_by_target and isinstance(pred, (int, float)):
            actual = actual_by_target[tgt]
            if actual > 0:
                ape = abs(pred - actual) / actual * 100
                result[tgt] = ape
    return result


def compute_best_of_both():
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=WINDOW_MINUTES)

    outcomes = _load(OUTCOMES)
    metas = _load(META)
    ensembles = _load(ENSEMBLE)

    v1_apes = _v1_predictions_for_window(outcomes, metas, window_start)
    v2_apes = _v2_predictions_for_window(outcomes, ensembles, window_start)

    v1_mean = statistics.mean(v1_apes.values()) if v1_apes else None
    v2_mean = statistics.mean(v2_apes.values()) if v2_apes else None

    if v1_mean is None and v2_mean is None:
        chosen = "NONE"
        confidence = "NULA"
        reason = "Sin datos en la ventana"
    elif v1_mean is None:
        chosen = "v2-B"
        confidence = "BAJA"
        reason = f"Solo v2-B disponible (APE {v2_mean:.2f}%)"
    elif v2_mean is None:
        chosen = "v1"
        confidence = "BAJA"
        reason = f"Solo v1 disponible (APE {v1_mean:.2f}%)"
    elif len(v1_apes) < MIN_SAMPLES or len(v2_apes) < MIN_SAMPLES:
        chosen = "v1" if (v1_mean or 99) < (v2_mean or 99) else "v2-B"
        confidence = "BAJA"
        reason = f"Pocas muestras (v1={len(v1_apes)}, v2={len(v2_apes)})"
    else:
        diff = v1_mean - v2_mean
        if abs(diff) < 0.1:
            chosen = "BOTH (avg)"
            confidence = "MEDIA"
            reason = f"Empate técnico (v1={v1_mean:.2f}%, v2={v2_mean:.2f}%)"
        elif diff > 0:
            chosen = "v2-B"
            confidence = "ALTA"
            reason = f"v2-B mejor por {diff:.2f} pts (v1={v1_mean:.2f}%, v2={v2_mean:.2f}%)"
        else:
            chosen = "v1"
            confidence = "ALTA"
            reason = f"v1 mejor por {abs(diff):.2f} pts (v1={v1_mean:.2f}%, v2={v2_mean:.2f}%)"

    result = {
        "version": "TEOS Best-of-Both v1.0",
        "timestamp": now.isoformat(),
        "window_minutes": WINDOW_MINUTES,
        "v1_samples": len(v1_apes),
        "v2_samples": len(v2_apes),
        "v1_mean_ape": round(v1_mean, 3) if v1_mean is not None else None,
        "v2_mean_ape": round(v2_mean, 3) if v2_mean is not None else None,
        "chosen": chosen,
        "confidence": confidence,
        "reason": reason,
        "mode": "shadow",
        "affects_production": False,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    return result


if __name__ == "__main__":
    print(json.dumps(compute_best_of_both(), indent=2, ensure_ascii=False))
