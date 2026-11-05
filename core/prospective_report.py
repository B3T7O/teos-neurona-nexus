#!/usr/bin/env python3
"""Informe de rendimiento del evaluador prospectivo TEOS NEURONA."""

import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/processed"


def read_jsonl(filename):
    path = DATA / filename
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def main():
    signals = read_jsonl("prospective_signals.jsonl")
    outcomes = read_jsonl("prospective_outcomes.jsonl")

    state_path = DATA / "prospective_eval_state.json"
    state = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    outcome_ids = {o.get("signal_id") for o in outcomes}
    pending = state.get("pending", [])
    changes = [
        float(o["post_change_pct"])
        for o in outcomes
        if isinstance(o.get("post_change_pct"), (int, float))
    ]
    sustained = [
        o for o in outcomes
        if isinstance(o.get("all_post_above_baseline"), bool)
    ]
    sustained_threshold = [
        o for o in outcomes
        if isinstance(o.get("all_post_above_threshold"), bool)
    ]
    legacy = [
        o for o in outcomes
        if "all_post_above_baseline" not in o
    ]

    print("=" * 54)
    print("TEOS NEURONA NEXUS — INFORME DE MEMORIA Y APRENDIZAJE")
    print("=" * 54)
    print(f"Señales registradas: {len(signals)}")
    print(f"Resultados registrados: {len(outcomes)}")
    print(f"Señales sin resultado registrado: "
          f"{sum(1 for s in signals if s.get('signal_id') not in outcome_ids)}")
    print(f"Señales pendientes según estado: {len(pending)}")
    print(f"Última muestra procesada: "
          f"{state.get('last_processed_timestamp', 'no disponible')}")

    print("\n--- Resultados observados ---")
    if changes:
        print(f"Cambio medio posterior medio: {mean(changes):+.4f}%")
        print(f"Resultados con cambio medio positivo: "
              f"{sum(c > 0 for c in changes)}/{len(changes)}")
        print(f"Resultados con cambio medio superior al 3%: "
              f"{sum(c > 3 for c in changes)}/{len(changes)}")
    else:
        print("Todavía no hay resultados cuantitativos suficientes.")

    print("\n--- Persistencia de la subida ---")
    print(f"Resultados con métricas individuales: "
          f"{len(sustained)}/{len(outcomes)}")
    if sustained:
        print(f"Todas las lecturas sobre la referencia: "
              f"{sum(o['all_post_above_baseline'] for o in sustained)}"
              f"/{len(sustained)}")
    if sustained_threshold:
        print(f"Todas las lecturas sobre el umbral del 3%: "
              f"{sum(o['all_post_above_threshold'] for o in sustained_threshold)}"
              f"/{len(sustained_threshold)}")
    print(f"Resultados antiguos sin métricas individuales: {len(legacy)}")

    print("\nInterpretación:")
    print("- Es un resumen descriptivo, no una prueba de capacidad predictiva.")
    print("- Los registros antiguos no se recalculan ni se modifican.")
    print("- Las señales cercanas pueden compartir contexto temporal.")
    print("- Una variación del hashrate no predice por sí sola bloques Bitcoin.")


if __name__ == "__main__":
    main()
