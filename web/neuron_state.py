"""
TEOS Neurona Nexus - Estado de ánimo de la neurona.
Modulo read-only: lee JSON, calcula estado, no modifica nada.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"


def _tail_jsonl(path, n=80):
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
    return out


def _parse(s):
    if not s:
        return None
    try:
        if isinstance(s, str) and s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, AttributeError, TypeError):
        return None


def get_state():
    now = datetime.now(timezone.utc)

    samples = _tail_jsonl(RAW / "bitaxe_samples.jsonl", 60)
    outcomes = _tail_jsonl(PROC / "learning_outcomes_v2.jsonl", 300)
    analysis = _tail_jsonl(PROC / "analysis_history.jsonl", 3)

    state = "idle"
    color = "#00c8ff"
    label = "IDLE"
    detail = "Sin actividad nueva"
    metrics = {}

    # --- APRENDIENDO: outcomes nuevos en los ultimos 120s ---
    recent_outcomes = 0
    apes = []
    for o in outcomes:
        ts = _parse(o.get("target_timestamp"))
        if ts and (now - ts).total_seconds() < 120:
            recent_outcomes += 1
            ape = o.get("absolute_percentage_error")
            if isinstance(ape, (int, float)):
                apes.append(ape)

    if recent_outcomes > 0:
        state = "learning"
        color = "#00ff9d"
        label = "APRENDIENDO"
        avg_ape = (sum(apes) / len(apes)) if apes else 0.0
        detail = f"{recent_outcomes} outcomes nuevos · APE {avg_ape:.2f}%"
        metrics["recent_outcomes"] = recent_outcomes
        metrics["ape_recent"] = round(avg_ape, 2)

    # --- ANOMALIA: temp alta o alertas ---
    if samples:
        last = samples[-1]
        temp = last.get("temp") or 0
        vr = last.get("vrTemp") or 0
        if temp > 72:
            state = "anomaly"
            color = "#ff3158"
            label = "ANOMALIA"
            detail = f"ASIC {temp}C > 72C"
        elif vr > 85:
            state = "anomaly"
            color = "#ff3158"
            label = "ANOMALIA"
            detail = f"VR {vr}C > 85C"

        if analysis:
            alerts = analysis[-1].get("latest_alerts") or []
            if alerts:
                state = "anomaly"
                color = "#ff3158"
                label = "ANOMALIA"
                detail = f"{len(alerts)} alertas: {alerts[0]}"

    # --- SALTO: hashrate 10m cambio >20% ---
    if state != "anomaly" and len(samples) >= 2:
        h1 = samples[-1].get("hashRate_10m")
        h2 = samples[-2].get("hashRate_10m")
        if h1 and h2 and h2 > 0:
            delta = abs(h1 - h2) / h2 * 100
            if delta > 20:
                state = "jump"
                color = "#ffb800"
                label = "SALTO"
                detail = f"Hashrate 10m cambio {delta:.1f}%"
                metrics["jump_pct"] = round(delta, 1)

    # --- RECORD: bestDiff subio en la ultima muestra ---
    if state not in ("anomaly",) and len(samples) >= 2:
        diffs = [s.get("bestDiff") or 0 for s in samples]
        if diffs[-1] > max(diffs[:-1]) and diffs[-1] > 0:
            state = "record"
            color = "#ffd700"
            label = "RECORD"
            detail = f"bestDiff nuevo: {diffs[-1]:,}"
            metrics["bestDiff"] = diffs[-1]

    if samples:
        metrics.update({
            "hashRate": samples[-1].get("hashRate"),
            "temp": samples[-1].get("temp"),
            "vrTemp": samples[-1].get("vrTemp"),
            "frequency": samples[-1].get("frequency"),
            "sharesAccepted": samples[-1].get("sharesAccepted"),
        })

    return {
        "state": state,
        "color": color,
        "label": label,
        "detail": detail,
        "metrics": metrics,
        "ts_utc": now.isoformat(),
    }


if __name__ == "__main__":
    print(json.dumps(get_state(), indent=2, ensure_ascii=False))
