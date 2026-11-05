#!/usr/bin/env python3
"""Seleccion temporal Ridge mediante validacion cronologica."""

import sys
import json
import hashlib
from pathlib import Path
from datetime import timedelta

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_ridge_prospective as core

SNAPSHOT = core.ROOT / "experiments/expanded_training_20261103.jsonl"
MANIFEST = core.ROOT / "experiments/expanded_training_20261103_manifest.json"
OUTPUT = core.ROOT / "experiments/ridge_training_window_cv_report.json"

OLD_CUTOFF = core.parse_timestamp("2026-11-03T23:35:24.026790+00:00")
CUTOFF = core.parse_timestamp("2026-11-04T11:53:12.015883+00:00")
WINDOWS = {"1_dia": 1, "3_dias": 3, "7_dias": 7,
           "14_dias": 14, "historico_completo": None}
FOLDS = 5
SELECTED = np.asarray([
    core.FEATURES.index(f) for f in core.REDUCED_FEATURES
])


def stop(message):
    raise SystemExit("SELECCION DETENIDA: " + message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if OUTPUT.exists():
        stop("El informe ya existe. No se sobrescribio.")

    for path, expected in core.EXPECTED_HASHES.items():
        if not path.is_file() or digest(path.read_bytes()) != expected:
            stop("Integridad historica incorrecta: " + path.name)

    raw_snapshot = SNAPSHOT.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    if digest(raw_snapshot) != manifest.get("snapshot_sha256"):
        stop("SHA-256 de la fotografia ampliada incorrecto.")

    frozen = []
    for line in raw_snapshot.splitlines():
        row = json.loads(line)
        row["_dt"] = core.parse_timestamp(row["timestamp"])
        row["_target"] = float(row["hashRate"])
        frozen.append(row)

    if frozen[-1]["_dt"] != OLD_CUTOFF:
        stop("El corte de la fotografia no coincide.")

    historical, future, invalid, duplicates, _ = (
        core.load_raw_future(OLD_CUTOFF)
    )
    core.verify_context(frozen, historical)

    # Solo se incorpora historia hasta el corte de seleccion.
    past = [r for r in future if r["_dt"] <= CUTOFF]
    stream = frozen + past

    rows = []
    for i in range(2, len(stream)):
        previous, earlier, target = stream[i-1], stream[i-2], stream[i]
        dt = target["_dt"]

        if dt > CUTOFF:
            break

        x = core.feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (dt - previous["_dt"]).total_seconds()

        if (x is None or not core.valid_number(y)
                or not core.valid_number(base) or interval <= 0):
            continue

        rows.append({
            "dt": dt,
            "x": x,
            "y": float(y),
            "baseline": float(base),
        })

    if not rows:
        stop("No hay muestras historicas utilizables.")

    # Cinco bloques consecutivos de 24 horas antes del corte.
    cv_start = CUTOFF - timedelta(days=FOLDS)
    fold_specs = []

    for k in range(FOLDS):
        start = cv_start + timedelta(days=k)
        end = start + timedelta(days=1)
        if k == FOLDS - 1:
            end = CUTOFF + timedelta(microseconds=1)
        fold_specs.append((start, end))

    results = {}

    for name, days in WINDOWS.items():
        all_actual = []
        all_baseline = []
        all_prediction = []
        fold_results = []

        for start, end in fold_specs:
            train = [
                r for r in rows
                if r["dt"] < start
                and (days is None or r["dt"] >= start - timedelta(days=days))
            ]
            test = [r for r in rows if start <= r["dt"] < end]

            if len(train) < 100 or not test:
                stop(f"Muestras insuficientes en {name}, bloque {start.isoformat()}.")

            train_x = np.asarray([r["x"] for r in train], dtype=float)
            train_y = np.asarray([r["y"] for r in train], dtype=float)
            test_x = np.asarray([r["x"] for r in test], dtype=float)

            prediction = core.fit_predict(
                train_x, train_y, test_x, SELECTED
            )

            actual = [r["y"] for r in test]
            baseline = [r["baseline"] for r in test]

            ref_metrics = core.metrics(actual, baseline)
            model_metrics = core.metrics(actual, prediction)

            all_actual.extend(actual)
            all_baseline.extend(baseline)
            all_prediction.extend(prediction.tolist())

            fold_results.append({
                "inicio_utc": start.isoformat(),
                "fin_utc": (end - timedelta(microseconds=1)).isoformat(),
                "train_n": len(train),
                "test_n": len(test),
                "referencia_1h": ref_metrics,
                "ridge_ventana": model_metrics,
            })

        ref = core.metrics(all_actual, all_baseline)
        model = core.metrics(all_actual, all_prediction)

        wins_mae = sum(
            f["ridge_ventana"]["mae_ghs"] < f["referencia_1h"]["mae_ghs"]
            for f in fold_results
        )
        wins_rmse = sum(
            f["ridge_ventana"]["rmse_ghs"] < f["referencia_1h"]["rmse_ghs"]
            for f in fold_results
        )

        results[name] = {
            "global": {
                "n": len(all_actual),
                "referencia_1h": ref,
                "ridge_ventana": model,
                "delta_mae_ghs": model["mae_ghs"] - ref["mae_ghs"],
                "delta_rmse_ghs": model["rmse_ghs"] - ref["rmse_ghs"],
            },
            "bloques": fold_results,
            "bloques_ganados_mae": wins_mae,
            "bloques_ganados_rmse": wins_rmse,
        }

    eligible = [
        name for name, result in results.items()
        if result["global"]["delta_mae_ghs"] < 0
        and result["global"]["delta_rmse_ghs"] < 0
        and result["bloques_ganados_mae"] >= 3
        and result["bloques_ganados_rmse"] >= 3
    ]

    selected = (
        min(eligible, key=lambda n: results[n]["global"]["ridge_ventana"]["mae_ghs"])
        if eligible else None
    )

    report = {
        "title": "TEOS - Seleccion cronologica de ventana Ridge",
        "snapshot_sha256": manifest["snapshot_sha256"],
        "selection_cutoff_utc": CUTOFF.isoformat(),
        "validation_design": {
            "method": "walk-forward",
            "folds": FOLDS,
            "fold_duration_hours": 24,
            "windows": WINDOWS,
            "future_after_cutoff_used": False,
            "features": list(core.REDUCED_FEATURES),
            "ridge_alpha": core.ALPHA,
        },
        "historical_usable_pairs": len(rows),
        "invalid_raw_records": invalid,
        "duplicate_raw_timestamps": duplicates,
        "results": results,
        "eligible_windows": eligible,
        "selected_window": selected,
        "final_502_pair_holdout_used": False,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("SELECCION CRONOLOGICA DE VENTANA RIDGE")
    print("Pares historicos:", len(rows))

    for name, result in results.items():
        g = result["global"]
        print(
            f"\n{name}: train por bloque="
            f"{[f['train_n'] for f in result['bloques']]}"
        )
        print(
            f"MAE referencia={g['referencia_1h']['mae_ghs']:.5f} | "
            f"Ridge={g['ridge_ventana']['mae_ghs']:.5f}"
        )
        print(
            f"RMSE referencia={g['referencia_1h']['rmse_ghs']:.5f} | "
            f"Ridge={g['ridge_ventana']['rmse_ghs']:.5f}"
        )
        print(
            "Bloques ganados MAE/RMSE:",
            result["bloques_ganados_mae"],
            "/",
            result["bloques_ganados_rmse"],
        )

    print("\nVentana seleccionada:", selected or "NINGUNA")
    print("Holdout independiente de 502 pares: INTACTO")
    print("Informe:", OUTPUT.relative_to(core.ROOT))


if __name__ == "__main__":
    main()
