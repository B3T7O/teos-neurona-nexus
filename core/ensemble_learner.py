"""
TEOS Ensemble Learner v2-B (Challenger)
=======================================
Combines predictions from the 5 methods using inverse-error weighting.
Operates in isolation (shadow mode). Does NOT affect production.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

OUTCOMES = Path("data/processed/learning_outcomes_v2.jsonl")
META_REC = Path("data/processed/meta_learner_recommendations.jsonl")
ENSEMBLE_OUT = Path("data/processed/ensemble_predictions_v2.jsonl")

def _tail_lines(path, max_bytes=50000):
    if not path.exists(): return []
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()
            data = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return []
    out = []
    for ln in data.splitlines():
        ln = ln.strip()
        if not ln: continue
        try: out.append(json.loads(ln))
        except json.JSONDecodeError: pass
    return out

def _get_weights():
    meta_lines = _tail_lines(META_REC, 5000)
    if not meta_lines:
        return None, "No hay registros del MetaLearner"
    
    last = meta_lines[-1]
    ranking = last.get("ranking", [])
    
    weights = {}
    for item in ranking:
        method = item.get("method")
        ape = item.get("median_ape", 99.0)
        if ape <= 0: ape = 0.01
        weights[method] = 1.0 / ape
    
    total = sum(weights.values())
    if total == 0: return None, "Pesos inválidos"
    for m in weights:
        weights[m] /= total
        
    return weights, "OK"

def _get_latest_predictions():
    lines = _tail_lines(OUTCOMES, 60000)
    if not lines: return None, "No hay outcomes"
    
    by_target = {}
    for r in lines:
        target = r.get("target_timestamp")
        method = r.get("method")
        pred = r.get("predicted_hashRate_GHs")
        if target and method and isinstance(pred, (int, float)):
            by_target.setdefault(target, {})[method] = pred
            
    if not by_target: return None, "No hay predicciones válidas"
    
    latest_target = max(by_target.keys())
    predictions = by_target[latest_target]
    
    if len(predictions) < 3:
        return None, f"Solo {len(predictions)} predicciones para el último timestamp"
        
    return predictions, latest_target

def compute_ensemble():
    weights, w_status = _get_weights()
    if not weights:
        return {"error": w_status}
        
    predictions, p_status = _get_latest_predictions()
    if not predictions:
        return {"error": p_status}

    ensemble_pred = 0.0
    used_methods = 0
    
    for method, pred in predictions.items():
        if method in weights:
            ensemble_pred += pred * weights[method]
            used_methods += 1

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_timestamp": p_status,
        "used_methods": used_methods,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "individual_predictions": predictions,
        "ensemble_prediction_GHs": round(ensemble_pred, 2),
        "mode": "shadow",
        "affects_production": False
    }

    ENSEMBLE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with ENSEMBLE_OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    return result

if __name__ == "__main__":
    res = compute_ensemble()
    print(json.dumps(res, indent=2, ensure_ascii=False))
