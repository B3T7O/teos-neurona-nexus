# Copyright (c) 2026 Luis Alberto Siguencia Andrade (B3T7O)
# SPDX-License-Identifier: Apache-2.0
#
# TEOS Neurona Nexus - Reference Implementation
# https://github.com/[TU_USUARIO]/teos-neurona-nexus

"""
TEOS Neurona Nexus - Estado de animo de la neurona.
Modulo read-only. Lectura optimizada (seek al final del archivo) + cache 2s.
"""
import json
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

_cache = {"ts": 0.0, "state": None}
_lock = threading.Lock()
_CACHE_TTL = 2.0


def _tail_bytes(path, max_bytes=80_000):
    """Lee solo los ultimos max_bytes del archivo. No carga archivos grandes."""
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # descartar linea parcial
            data = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return []
    out = []
    for ln in data.splitlines():
        ln = ln.strip()
        if not ln:
            continue
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


def _compute_state():
    now = datetime.now(timezone.utc)

    samples = _tail_bytes(RAW / "bitaxe_samples.marked.jsonl", 30_000)[-60:]
    outcomes = _tail_bytes(PROC / "learning_outcomes_v2.jsonl", 60_000)[-400:]
    analysis = _tail_bytes(PROC / "analysis_history.jsonl", 20_000)[-3:]

    state, color, label, detail = "idle", "#00c8ff", "IDLE", "Sin actividad nueva"
    metrics = {}

    # APRENDIENDO
    recent_outcomes, apes = 0, []
    for o in outcomes:
        ts = _parse(o.get("target_timestamp"))
        if ts and (now - ts).total_seconds() < 3600:
            recent_outcomes += 1
            ape = o.get("absolute_percentage_error")
            if isinstance(ape, (int, float)):
                apes.append(ape)
    if recent_outcomes > 0:
        state, color, label = "learning", "#00ff9d", "APRENDIENDO"
        avg = (sum(apes) / len(apes)) if apes else 0.0
        detail = f"{recent_outcomes} outcomes nuevos · APE {avg:.2f}%"
        metrics["recent_outcomes"] = recent_outcomes
        metrics["ape_recent"] = round(avg, 2)

    # ANOMALIA
    if samples:
        last = samples[-1]
        temp = last.get("temp") or 0
        vr = last.get("vrTemp") or 0
        if temp > 72:
            state, color, label = "anomaly", "#ff3158", "ANOMALIA"
            detail = f"ASIC {temp}C > 72C"
        elif vr > 85:
            state, color, label = "anomaly", "#ff3158", "ANOMALIA"
            detail = f"VR {vr}C > 85C"
        if analysis:
            alerts = analysis[-1].get("latest_alerts") or []
            if alerts:
                state, color, label = "anomaly", "#ff3158", "ANOMALIA"
                detail = f"{len(alerts)} alertas"

    # SALTO
    if state != "anomaly" and len(samples) >= 2:
        h1 = samples[-1].get("hashRate_10m")
        h2 = samples[-2].get("hashRate_10m")
        if h1 and h2 and h2 > 0:
            delta = abs(h1 - h2) / h2 * 100
            if delta > 20:
                state, color, label = "jump", "#ffb800", "SALTO"
                detail = f"Hashrate 10m cambio {delta:.1f}%"
                metrics["jump_pct"] = round(delta, 1)

    # RECORD
    if state not in ("anomaly",) and len(samples) >= 2:
        diffs = [s.get("bestDiff") or 0 for s in samples]
        if diffs[-1] > max(diffs[:-1]) and diffs[-1] > 0:
            state, color, label = "record", "#ffd700", "RECORD"
            detail = f"bestDiff nuevo: {diffs[-1]:,}"
            metrics["bestDiff"] = diffs[-1]

    if samples:
        s = samples[-1]
        metrics.update({
            "hashRate": s.get("hashRate"),
            "temp": s.get("temp"),
            "vrTemp": s.get("vrTemp"),
            "frequency": s.get("frequency"),
            "sharesAccepted": s.get("sharesAccepted"),
        })

    return {
        "state": state, "color": color, "label": label, "detail": detail,
        "metrics": metrics, "ts_utc": now.isoformat(),
    }


def get_state():
    with _lock:
        if _cache["state"] and (time.time() - _cache["ts"]) < _CACHE_TTL:
            return _cache["state"]
        result = _compute_state()
        _cache["ts"] = time.time()
        _cache["state"] = result
        return result


if __name__ == "__main__":
    print(json.dumps(get_state(), indent=2, ensure_ascii=False))
