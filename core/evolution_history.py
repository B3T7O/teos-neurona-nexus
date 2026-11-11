#!/usr/bin/env python3
"""
Historial central de evoluciones de todos los learners.
Cada learner registra aqui sus ciclos de evolucion.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "evolve" / "history.jsonl"


def record(learner, kind, detail, extra=None):
    """
    Registra un evento de evolucion.
    learner: 'evolve_lab' | 'meta_learner_lite' | 'ensemble_learner' | 'best_of_both' | 'ridge_live'
    kind: 'start' | 'ok' | 'failed' | 'champion_update'
    detail: descripcion corta
    extra: dict opcional con metadatos (weights, ape, etc.)
    """
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "learner": learner,
        "kind": kind,
        "detail": detail,
    }
    if extra:
        entry["extra"] = extra
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_all(limit=200):
    """Devuelve las ultimas `limit` entradas del historial."""
    if not HISTORY.exists():
        return []
    entries = []
    with HISTORY.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                entries.append(json.loads(ln))
            except Exception:
                continue
    return entries[-limit:]


def summarize_by_learner():
    """Resumen agrupado por learner."""
    entries = read_all(limit=10000)
    summary = {}
    for e in entries:
        learner = e.get("learner", "unknown")
        if learner not in summary:
            summary[learner] = {
                "total": 0,
                "ok": 0,
                "failed": 0,
                "last": None,
            }
        summary[learner]["total"] += 1
        kind = e.get("kind")
        if kind == "ok" or kind == "champion_update":
            summary[learner]["ok"] += 1
        elif kind == "failed":
            summary[learner]["failed"] += 1
        summary[learner]["last"] = e
    return summary
