
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/processed/contextual_shadow_v1_state.json"
ANOMALY_LEDGER = ROOT / "data/processed/anomaly_events.jsonl"

LEARNING_RATE = 0.05
MAX_ABS_BIAS_GHS = 50.0
MIN_CONTEXT_UPDATES = 30


def _time_seconds(value):
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    if hasattr(value, "timestamp"):
        return float(value.timestamp())
    return None


def _context_list(context_keys):
    if isinstance(context_keys, str):
        context_keys = [context_keys]
    return sorted({
        str(key).strip()
        for key in (context_keys or [])
        if key and str(key).strip()
    }) or ["normal"]


def _normalized_timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return str(value)


def _is_quarantined_target(target_timestamp):
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


def classify_samples(samples):
    """Clasifica muestras cronológicas usando únicamente información pasada."""
    intervals = []

    for i, sample in enumerate(samples):
        keys = []
        previous = samples[i - 1] if i else None
        current_time = _time_seconds(sample.get("_time"))

        if current_time is None:
            raise ValueError("Muestra sin timestamp numérico válido.")

        if previous is not None:
            previous_time = _time_seconds(previous.get("_time"))
            if previous_time is None or current_time <= previous_time:
                raise ValueError("Las muestras deben estar ordenadas cronológicamente.")

            gap = current_time - previous_time
            unusual_gap = False

            if len(intervals) >= 5:
                typical = statistics.median(intervals[-10:])
                unusual_gap = gap > max(typical * 3, typical + 120)
                if unusual_gap:
                    keys.append("brecha_telemetria")

            if not unusual_gap:
                intervals.append(gap)

            checks = (
                ("uptime_seconds", "reinicio_bitaxe", "decrease"),
                ("frequency", "cambio_frecuencia", "change"),
                ("block_height", "cambio_bloque", "change"),
                ("network_difficulty", "cambio_dificultad_red", "change"),
                ("pool_difficulty", "cambio_dificultad_pool", "change"),
            )

            for field, key, mode in checks:
                value, old = sample.get(field), previous.get(field)
                if value is not None and old is not None:
                    if (mode == "decrease" and value < old) or (
                        mode == "change" and value != old
                    ):
                        keys.append(key)

            for field, delta_field in (
                ("shares_accepted", "shares_accepted_delta"),
                ("shares_rejected", "shares_rejected_delta"),
            ):
                value, old = sample.get(field), previous.get(field)
                sample[delta_field] = (
                    value - old
                    if value is not None and old is not None and value >= old
                    else None
                )

            if (sample.get("shares_rejected_delta") or 0) > 0:
                keys.append("incremento_shares_rechazadas")

            wifi, old_wifi = sample.get("wifi_rssi"), previous.get("wifi_rssi")
            if wifi is not None and old_wifi is not None and wifi - old_wifi <= -10:
                keys.append("caida_senal_wifi")

            for field, key in (
                ("temp", "aumento_temperatura_asic"),
                ("vr_temp", "aumento_temperatura_vr"),
            ):
                value, old = sample.get(field), previous.get(field)
                if value is not None and old is not None and value - old >= 5:
                    keys.append(key)

        if sample.get("temp") is not None and sample["temp"] >= 70:
            keys.append("asic_ge_70c")
        if sample.get("vr_temp") is not None and sample["vr_temp"] >= 80:
            keys.append("vr_ge_80c")

        sample["contextual_context_keys"] = sorted(set(keys)) or ["normal"]

    return samples


def load_state():
    if not STATE.exists():
        return {
            "version": 1,
            "contexts": {},
            "total_updates": 0,
            "processed_prediction_ids": [],
            "last_update": None,
        }

    with STATE.open(encoding="utf-8") as f:
        state = json.load(f)

    if not isinstance(state, dict) or not isinstance(state.get("contexts"), dict):
        raise ValueError("Estado contextual inválido.")
    if not isinstance(state.get("processed_prediction_ids"), list):
        raise ValueError("Registro de predicciones inválido.")

    return state


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

    temporary.replace(STATE)


def predict(base_prediction_GHs, context_keys):
    base = float(base_prediction_GHs)
    if not math.isfinite(base) or base <= 0:
        raise ValueError("Predicción base no válida.")

    keys = _context_list(context_keys)
    state = load_state()
    active = []

    for key in keys:
        entry = state["contexts"].get(key, {})
        updates = int(entry.get("updates", 0))
        bias = float(entry.get("bias_GHs", 0.0))

        if not math.isfinite(bias):
            raise ValueError("Sesgo contextual no finito.")

        if updates >= MIN_CONTEXT_UPDATES:
            active.append((key, bias))

    correction = (
        sum(bias for _, bias in active) / len(active)
        if active else 0.0
    )

    return {
        "prediction_GHs": max(0.001, base + correction),
        "base_prediction_GHs": base,
        "context_keys": keys,
        "active_context_keys": [key for key, _ in active],
        "learned_bias_GHs": correction,
        "applied": bool(active),
        "updates": sum(
            int(state["contexts"].get(key, {}).get("updates", 0))
            for key in keys
        ),
    }


def learn(prediction_id, base_prediction_GHs, actual_GHs,
          target_timestamp, context_keys):
    if not prediction_id:
        raise ValueError("Falta prediction_id.")

    base = float(base_prediction_GHs)
    actual = float(actual_GHs)

    if not math.isfinite(base) or not math.isfinite(actual) or base <= 0:
        raise ValueError("Predicción o resultado no válido.")

    if _is_quarantined_target(target_timestamp):
        return {"updated": False, "reason": "objetivo_anomalo"}

    keys = _context_list(context_keys)
    state = load_state()

    if prediction_id in set(state["processed_prediction_ids"]):
        return {"updated": False, "reason": "resultado_ya_procesado"}

    # Aprende el residual respecto a la predicción base, no respecto
    # al candidato corregido, para evitar realimentación del mismo sesgo.
    error = actual - base
    changes = {}

    for key in keys:
        entry = state["contexts"].setdefault(
            key, {"bias_GHs": 0.0, "updates": 0}
        )

        old_bias = float(entry["bias_GHs"])
        new_bias = old_bias + LEARNING_RATE * (error - old_bias)
        new_bias = max(
            -MAX_ABS_BIAS_GHS,
            min(MAX_ABS_BIAS_GHS, new_bias),
        )

        entry["bias_GHs"] = new_bias
        entry["updates"] = int(entry["updates"]) + 1
        entry["last_update"] = {
            "prediction_id": str(prediction_id),
            "target_timestamp": target_timestamp,
            "error_GHs": error,
        }
        changes[key] = new_bias

    state["processed_prediction_ids"].append(str(prediction_id))
    state["total_updates"] = int(state["total_updates"]) + 1
    state["last_update"] = {
        "prediction_id": str(prediction_id),
        "context_keys": keys,
        "target_timestamp": target_timestamp,
    }

    save_state(state)

    return {
        "updated": True,
        "context_keys": keys,
        "error_GHs": error,
        "biases_after_GHs": changes,
        "total_updates": state["total_updates"],
    }
