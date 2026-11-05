#!/usr/bin/env python3
"""Aprendiz incremental TEOS basado en errores observados."""

import json
import math
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/processed/online_error_learner_state.json"

LEARNING_RATE = 0.10
MAX_ABS_BIAS_GHS = 100.0


ANOMALY_LEDGER = ROOT / "data/processed/anomaly_events.jsonl"


def _normalized_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).isoformat()
    except (ValueError, TypeError):
        return str(value)


def _is_quarantined_target(target_timestamp):
    """Comprueba si el instante objetivo figura en la memoria de anomalías."""
    target = _normalized_timestamp(target_timestamp)
    if target is None or not ANOMALY_LEDGER.exists():
        return False

    with ANOMALY_LEDGER.open(encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if _normalized_timestamp(event.get("timestamp")) == target:
                return True

    return False


def load_state():
    if not STATE.exists():
        return {
            "version": 1,
            "bias_GHs": 0.0,
            "updates": 0,
            "processed_prediction_ids": [],
            "last_update": None,
        }

    with STATE.open(encoding="utf-8") as f:
        state = json.load(f)

    state.setdefault("bias_GHs", 0.0)
    state.setdefault("updates", 0)
    state.setdefault("processed_prediction_ids", [])
    return state


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")

    temporary.replace(STATE)


def predict(base_prediction_GHs):
    """Aplica el sesgo aprendido a una predicción base."""
    base = float(base_prediction_GHs)

    if not math.isfinite(base) or base <= 0:
        raise ValueError("La predicción base debe ser positiva y finita.")

    state = load_state()
    prediction = max(0.001, base + float(state["bias_GHs"]))

    return {
        "prediction_GHs": prediction,
        "base_prediction_GHs": base,
        "learned_bias_GHs": float(state["bias_GHs"]),
        "updates": int(state["updates"]),
    }


def learn(prediction_id, predicted_GHs, actual_GHs, target_timestamp):
    """Actualiza el sesgo una sola vez por predicción resuelta."""
    if not prediction_id:
        raise ValueError("Falta prediction_id.")

    predicted = float(predicted_GHs)
    actual = float(actual_GHs)

    if not math.isfinite(predicted) or not math.isfinite(actual):
        raise ValueError("Predicción y resultado deben ser finitos.")

    if _is_quarantined_target(target_timestamp):
        return {
            "updated": False,
            "reason": "objetivo_anomalo_en_memoria",
        }

    state = load_state()
    processed = set(state["processed_prediction_ids"])

    if prediction_id in processed:
        return {
            "updated": False,
            "reason": "resultado_ya_procesado",
            "bias_GHs": state["bias_GHs"],
            "updates": state["updates"],
        }

    error = actual - predicted
    old_bias = float(state["bias_GHs"])

    # El sesgo se acerca gradualmente al error observado.
    new_bias = old_bias + LEARNING_RATE * error
    new_bias = max(
        -MAX_ABS_BIAS_GHS,
        min(MAX_ABS_BIAS_GHS, new_bias),
    )

    state["bias_GHs"] = new_bias
    state["updates"] = int(state["updates"]) + 1
    state["processed_prediction_ids"].append(str(prediction_id))
    state["last_update"] = {
        "prediction_id": str(prediction_id),
        "target_timestamp": target_timestamp,
        "predicted_GHs": predicted,
        "actual_GHs": actual,
        "error_GHs": error,
        "bias_before_GHs": old_bias,
        "bias_after_GHs": new_bias,
    }

    save_state(state)

    return {
        "updated": True,
        "error_GHs": error,
        "bias_before_GHs": old_bias,
        "bias_after_GHs": new_bias,
        "updates": state["updates"],
    }


if __name__ == "__main__":
    state = load_state()
    print("=== ESTADO DEL APRENDIZ ONLINE ===")
    print("Actualizaciones:", state["updates"])
    print("Sesgo aprendido (GH/s):", state["bias_GHs"])
    print("Resultados procesados:", len(state["processed_prediction_ids"]))
    print("Estado:", STATE.relative_to(ROOT))
