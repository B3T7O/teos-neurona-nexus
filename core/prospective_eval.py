#!/usr/bin/env python3
"""Evaluador prospectivo independiente para TEOS NEURONA NEXUS."""

import json
import os
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/bitaxe_samples.marked.jsonl"
OUT = ROOT / "data/processed"
STATE = OUT / "prospective_eval_state.json"
SIGNALS = OUT / "prospective_signals.jsonl"
OUTCOMES = OUT / "prospective_outcomes.jsonl"

BASELINE_N = 5
POST_N = 5
THRESHOLD_PCT = 3.0


def parse_time(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp sin zona horaria: {value}")
    return dt.astimezone(__import__("datetime").timezone.utc)


def read_rows():
    rows = []
    if not RAW.exists():
        raise SystemExit(f"No existe el archivo de muestras: {RAW}")

    with RAW.open(encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                ts = parse_time(obj["timestamp"])
                hr = float(obj["hashRate"])
                if ts.tzinfo is None or hr <= 0:
                    continue
                row = {
                    "timestamp": ts.isoformat(),
                    "hashRate": hr,
                }
                try:
                    row["hashRate_1m"] = float(obj["hashRate_1m"])
                except (KeyError, TypeError, ValueError):
                    row["hashRate_1m"] = None
                rows.append(row)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue

    # Elimina marcas de tiempo duplicadas y ordena cronológicamente.
    unique = {r["timestamp"]: r for r in rows}
    return sorted(unique.values(), key=lambda r: parse_time(r["timestamp"]))


def read_anomaly_timestamps():
    """Carga timestamps exactos de muestras en cuarentena."""
    ledger = ROOT / "data/processed/anomaly_events.jsonl"
    quarantined = set()
    if ledger.exists():
        with ledger.open(encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    ts = event.get("timestamp")
                    if ts:
                        quarantined.add(parse_time(ts).isoformat())
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    return quarantined


def read_jsonl(path):
    found = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if "signal_id" in obj:
                        found[obj["signal_id"]] = obj
                except json.JSONDecodeError:
                    continue
    return found


def append_once(path, record, existing):
    signal_id = record["signal_id"]
    if signal_id in existing:
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    existing[signal_id] = record


def save_state(state):
    temp = STATE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, STATE)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    if not rows:
        raise SystemExit("No hay muestras válidas.")

    signals = read_jsonl(SIGNALS)
    outcomes = read_jsonl(OUTCOMES)
    quarantined = read_anomaly_timestamps()

    # Primera ejecución: iniciar desde la muestra más reciente.
    # El histórico no se presenta como una predicción real.
    if not STATE.exists():
        seed = rows[-BASELINE_N:]
        state = {
            "version": 1,
            "started_at": datetime.now().astimezone().isoformat(),
            "last_processed_timestamp": rows[-1]["timestamp"],
            "history": seed,
            "pending": [],
            "bootstrap_sample_count": len(rows),
        }
        save_state(state)
        print("TEOS NEURONA — EVALUADOR PROSPECTIVO")
        print(f"Muestras históricas existentes: {len(rows)}")
        print(f"Punto inicial: {rows[-1]['timestamp']}")
        print("Modo: prospectivo; no se generan señales históricas.")
        print("Ejecuta de nuevo el módulo cuando existan nuevas muestras.")
        return

    state = json.loads(STATE.read_text(encoding="utf-8"))
    last_ts = parse_time(state["last_processed_timestamp"])
    new_rows = [
        r for r in rows if parse_time(r["timestamp"]) > last_ts
    ]

    if not new_rows:
        print("Sin muestras nuevas. No se repite ninguna evaluación.")
        print(f"Última muestra procesada: {state['last_processed_timestamp']}")
        return

    history = state.get("history", [])[-BASELINE_N:]
    pending = state.get("pending", [])
    new_signal_count = 0
    new_outcome_count = 0

    for row in new_rows:
        current_ts = parse_time(row["timestamp"])

        # Una anomalía avanza el cursor, pero no alimenta history ni post_values.
        if current_ts.isoformat() in quarantined:
            state["last_processed_timestamp"] = row["timestamp"]
            state["history"] = history
            state["pending"] = pending
            save_state(state)
            print("Muestra en cuarentena; excluida:", row["timestamp"])
            continue

        # Evaluar señales anteriores solo con esta nueva lectura.
        still_pending = []
        for event in pending:
            if current_ts > parse_time(event["timestamp"]):
                event["post_values"].append(row["hashRate"])

            if len(event["post_values"]) >= POST_N:
                post_values = event["post_values"][:POST_N]
                post_mean = mean(post_values)
                baseline = event["baseline_hashrate_GHs"]
                change = (post_mean / baseline - 1) * 100

                post_changes_pct = [
                    (value / baseline - 1) * 100
                    for value in post_values
                ]
                above_baseline = sum(
                    value > baseline for value in post_values
                )
                above_threshold = sum(
                    value > baseline * (1 + THRESHOLD_PCT / 100)
                    for value in post_values
                )

                outcome = {
                    "signal_id": event["signal_id"],
                    "signal_timestamp": event["timestamp"],
                    "evaluated_at": row["timestamp"],
                    "post_samples_required": POST_N,
                    "post_values_hashrate_GHs": [
                        round(value, 6) for value in post_values
                    ],
                    "post_mean_hashrate_GHs": round(post_mean, 6),
                    "post_min_hashrate_GHs": round(min(post_values), 6),
                    "post_max_hashrate_GHs": round(max(post_values), 6),
                    "baseline_hashrate_GHs": round(baseline, 6),
                    "post_change_pct": round(change, 4),
                    "post_min_change_pct": round(min(post_changes_pct), 4),
                    "post_max_change_pct": round(max(post_changes_pct), 4),
                    "post_samples_above_baseline": above_baseline,
                    "post_samples_above_threshold": above_threshold,
                    "all_post_above_baseline": above_baseline == POST_N,
                    "all_post_above_threshold": above_threshold == POST_N,
                    # Compatibilidad: estos dos campos describen la media,
                    # no que todas las lecturas superen el límite.
                    "remained_above_baseline": post_mean > baseline,
                    "remained_above_threshold": change > THRESHOLD_PCT,
                    "evaluation_method": "5 lecturas posteriores; comparación con la referencia inicial",
                    "note": (
                        "Resultado observado después de la señal; "
                        "no implica predicción de bloques."
                    ),
                }
                before = len(outcomes)
                append_once(OUTCOMES, outcome, outcomes)
                if len(outcomes) > before:
                    new_outcome_count += 1
            else:
                still_pending.append(event)

        pending = still_pending

        # Señal en esta lectura: solo usa las cinco lecturas anteriores.
        if len(history) >= BASELINE_N:
            baseline = mean(r["hashRate"] for r in history[-BASELINE_N:])
            change = (row["hashRate"] / baseline - 1) * 100

            if change > THRESHOLD_PCT:
                signal_id = row["timestamp"]
                one_min = row.get("hashRate_1m")
                signal = {
                    "signal_id": signal_id,
                    "timestamp": row["timestamp"],
                    "hashrate_GHs": round(row["hashRate"], 6),
                    "baseline_hashrate_GHs": round(baseline, 6),
                    "change_pct": round(change, 4),
                    "hashRate_1m_GHs": one_min,
                    "threshold_pct": THRESHOLD_PCT,
                    "baseline_samples": BASELINE_N,
                    "future_samples_required": POST_N,
                    "note": "Señal registrada sin usar lecturas futuras.",
                }
                before = len(signals)
                append_once(SIGNALS, signal, signals)
                if len(signals) > before:
                    new_signal_count += 1

                # Evita duplicar eventos pendientes si se reintenta una fila.
                if not any(p["signal_id"] == signal_id for p in pending):
                    pending.append({
                        "signal_id": signal_id,
                        "timestamp": row["timestamp"],
                        "baseline_hashrate_GHs": baseline,
                        "signal_hashrate_GHs": row["hashRate"],
                        "post_values": [],
                    })

        history.append(row)
        history = history[-BASELINE_N:]
        state["last_processed_timestamp"] = row["timestamp"]
        state["history"] = history
        state["pending"] = pending
        save_state(state)

    print("TEOS NEURONA — EVALUADOR PROSPECTIVO")
    print(f"Nuevas muestras procesadas: {len(new_rows)}")
    print(f"Nuevas señales registradas: {new_signal_count}")
    print(f"Señales evaluadas con 5 lecturas posteriores: {new_outcome_count}")
    print(f"Señales pendientes: {len(pending)}")
    print(f"Última muestra: {state['last_processed_timestamp']}")
    print(f"Registro de señales: {SIGNALS.relative_to(ROOT)}")
    print(f"Resultados: {OUTCOMES.relative_to(ROOT)}")
    print("Nota: esto evalúa cambios de hashrate, no predice bloques Bitcoin.")


if __name__ == "__main__":
    main()
