#!/usr/bin/env python3
"""Impacto de extrapolaciones temporales sobre el error prospectivo."""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import evaluate_ridge_prospective as ev
import audit_ridge_residual_conditions as audit

OUTPUT = ROOT / "experiments/ridge_extrapolation_impact_report.json"
FEATURES = ("delta_hashRate", "delta_hashRate_10m", "delta_hashRate_1h")

EXPECTED_OUTSIDE = {
    "delta_hashRate": 21,
    "delta_hashRate_10m": 14,
    "delta_hashRate_1h": 66,
}
EXPECTED_EXTREME = {
    "delta_hashRate": 27,
    "delta_hashRate_10m": 26,
    "delta_hashRate_1h": 128,
}


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def metrics(records, global_error_sum):
    if not records:
        return {"n": 0}

    actual = np.asarray([r["actual"] for r in records])
    reduced = np.asarray([r["ridge_reducido"] for r in records])
    baseline = np.asarray([r["baseline_1h"] for r in records])

    er = np.abs(reduced - actual)
    eb = np.abs(baseline - actual)
    difference = er - eb

    wins = int(np.sum(difference < -1e-9))
    losses = int(np.sum(difference > 1e-9))

    return {
        "n": len(records),
        "porcentaje_muestras": len(records) / EXPECTED_PAIRS * 100,
        "ridge_reducido_mae_ghs": float(np.mean(er)),
        "referencia_1h_mae_ghs": float(np.mean(eb)),
        "diferencia_mae_ghs": float(np.mean(er) - np.mean(eb)),
        "ridge_reducido_rmse_ghs": float(
            np.sqrt(np.mean((reduced - actual) ** 2))
        ),
        "ridge_reducido_sesgo_ghs": float(np.mean(reduced - actual)),
        "victorias_reducido": wins,
        "derrotas_reducido": losses,
        "suma_error_absoluto_reducido_ghs": float(np.sum(er)),
        "porcentaje_error_global_reducido": (
            float(np.sum(er) / global_error_sum * 100)
            if global_error_sum else 0.0
        ),
        "diferencia_acumulada_error_vs_referencia_ghs": float(
            np.sum(difference)
        ),
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    required = [
        audit.SNAPSHOT, audit.SCRIPT, audit.ORIGINAL,
        audit.CANDIDATE, audit.PROSPECTIVE,
        audit.EVENT_REPORT, ev.MANIFEST, ev.RAW,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta {path.name}")

    for path, expected in audit.EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    prospective = json.loads(
        audit.PROSPECTIVE.read_text(encoding="utf-8")
    )
    events = json.loads(
        audit.EVENT_REPORT.read_text(encoding="utf-8")
    )
    manifest = json.loads(
        ev.MANIFEST.read_text(encoding="utf-8")
    )

    if manifest.get("sha256") != snapshot_hash:
        stop("El manifiesto no coincide.")

    raw_hash = prospective["integrity"]["raw_sha256"]

    if (
        prospective["integrity"]["snapshot_sha256"] != snapshot_hash
        or events.get("snapshot_sha256") != snapshot_hash
        or events.get("raw_sha256") != raw_hash
    ):
        stop("Los informes no comparten la misma evidencia.")

    last_target = ev.parse_timestamp(
        prospective["evaluation_period_utc"]["last_target"]
    )

    prefix = audit.recover_original_prefix(raw_hash, last_target)
    rows = audit.load_prefix_rows(prefix)

    cutoff = frozen[-1]["_dt"]
    historical = [r for r in rows if r["_dt"] <= cutoff]
    future = [r for r in rows if r["_dt"] > cutoff]

    ev.verify_context(frozen, historical)

    if len(future) != prospective["validation"]["future_raw_rows"]:
        stop("No coincide la cantidad de muestras futuras.")

    # Entrenamiento congelado.
    train_x, train_y = [], []

    for i in range(2, len(frozen)):
        x = ev.feature_at(frozen[i - 1], frozen[i - 2])
        target = frozen[i]["_target"]
        baseline = frozen[i - 1].get("hashRate_1h")

        if (
            x is None
            or not math.isfinite(target)
            or not ev.valid_number(baseline)
        ):
            continue

        train_x.append(x)
        train_y.append(target)

    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)

    if len(train_y) != 844:
        stop("El entrenamiento congelado no contiene 844 muestras.")

    # Reconstrucción prospectiva.
    stream = [frozen[-2], frozen[-1]] + future
    test_x, records = [], []
    skipped = 0

    event_windows = {
        name: (
            ev.parse_timestamp(window["start"]),
            ev.parse_timestamp(window["end"]),
        )
        for name, window in events["event_windows_utc"].items()
    }

    for i in range(2, len(stream)):
        previous, earlier, target = (
            stream[i - 1], stream[i - 2], stream[i]
        )

        x = ev.feature_at(previous, earlier)
        actual = target.get("hashRate")
        baseline = previous.get("hashRate_1h")
        interval = (
            target["_dt"] - previous["_dt"]
        ).total_seconds()

        if (
            x is None
            or not ev.valid_number(actual)
            or not ev.valid_number(baseline)
            or interval <= 0
        ):
            skipped += 1
            continue

        test_x.append(x)
        records.append({
            "timestamp": target["_dt"].isoformat(),
            "actual": float(actual),
            "baseline_1h": float(baseline),
            "context": audit.operational_context(
                target["_dt"], event_windows
            ),
        })

    if len(records) != 9922:
        stop(f"Se reconstruyeron {len(records)} pares, no 9922.")

    if skipped != prospective["validation"]["future_pairs_skipped"]:
        stop("No coincide el número de pares omitidos.")

    test_x = np.asarray(test_x, dtype=float)

    # Rango y estandarización definidos exclusivamente por entrenamiento.
    feature_flags = {}
    thresholds = {}

    for name in FEATURES:
        j = ev.FEATURES.index(name)
        training = train_x[:, j]
        values = test_x[:, j]

        mean = float(np.mean(training))
        std = float(np.std(training))
        if std < 1e-9:
            std = 1.0

        z = (values - mean) / std
        outside = (values < np.min(training)) | (
            values > np.max(training)
        )
        extreme = np.abs(z) > 3.0

        feature_flags[name] = {
            "outside": outside,
            "extreme": extreme,
        }

        thresholds[name] = {
            "minimum_training": float(np.min(training)),
            "maximum_training": float(np.max(training)),
            "mean_training": mean,
            "std_training": std,
            "outside_count": int(np.sum(outside)),
            "extreme_count": int(np.sum(extreme)),
        }

        if int(np.sum(outside)) != EXPECTED_OUTSIDE[name]:
            stop(f"No coincide el conteo fuera de rango: {name}")

        if int(np.sum(extreme)) != EXPECTED_EXTREME[name]:
            stop(f"No coincide el conteo de 3 desviaciones: {name}")

    any_outside = np.zeros(len(records), dtype=bool)
    any_extreme = np.zeros(len(records), dtype=bool)

    for flags in feature_flags.values():
        any_outside |= flags["outside"]
        any_extreme |= flags["extreme"]

    for i, record in enumerate(records):
        record["outside_training_range"] = bool(any_outside[i])
        record["above_3_std"] = bool(any_extreme[i])

    # Reconstrucción de los mismos modelos fijos.
    full_indices = np.arange(len(ev.FEATURES))
    reduced_indices = np.asarray([
        ev.FEATURES.index(name) for name in ev.REDUCED_FEATURES
    ])

    original_predictions = ev.fit_predict(
        train_x, train_y, test_x, full_indices
    )
    reduced_predictions = ev.fit_predict(
        train_x, train_y, test_x, reduced_indices
    )

    for i, record in enumerate(records):
        record["ridge_original"] = float(original_predictions[i])
        record["ridge_reducido"] = float(reduced_predictions[i])

    # Reproducir métricas oficiales antes de analizar grupos.
    global_methods = ev.compare_methods(records)

    for method in audit.METHODS:
        audit.verify_metrics(
            global_methods[method],
            prospective["global"][method],
            method,
        )

    global_error_sum = sum(
        abs(r["ridge_reducido"] - r["actual"])
        for r in records
    )

    groups = {
        "global": records,
        "al_menos_una_caracteristica_fuera_rango": [
            r for r in records if r["outside_training_range"]
        ],
        "todas_dentro_rango": [
            r for r in records if not r["outside_training_range"]
        ],
        "al_menos_una_caracteristica_mayor_3_std": [
            r for r in records if r["above_3_std"]
        ],
        "todas_dentro_3_std": [
            r for r in records if not r["above_3_std"]
        ],
        "funcionamiento_habitual": [
            r for r in records
            if r["context"] == "funcionamiento_habitual"
        ],
    }

    by_context = defaultdict(list)
    for r in records:
        by_context[r["context"]].append(r)

    context_groups = {
        context: metrics(group, global_error_sum)
        for context, group in sorted(by_context.items())
    }

    feature_groups = {}

    for name, flags in feature_flags.items():
        feature_groups[name] = {
            "fuera_rango": metrics(
                [
                    records[i] for i in range(len(records))
                    if flags["outside"][i]
                ],
                global_error_sum,
            ),
            "mayor_3_std": metrics(
                [
                    records[i] for i in range(len(records))
                    if flags["extreme"][i]
                ],
                global_error_sum,
            ),
        }

    report = {
        "title": "TEOS NEURONA - Impacto de extrapolaciones temporales",
        "snapshot_sha256": snapshot_hash,
        "raw_prefix_sha256": raw_hash,
        "validation": {
            "prospective_metrics_reproduced": True,
            "training_samples": len(train_y),
            "prospective_pairs": len(records),
            "future_data_used_for_training": False,
            "model_weights_fixed": True,
            "original_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "training_ranges": thresholds,
        "groups": {
            name: metrics(group, global_error_sum)
            for name, group in groups.items()
        },
        "by_operational_context": context_groups,
        "by_individual_feature": feature_groups,
        "warning": (
            "Las agrupaciones identifican asociación entre extrapolación "
            "y error. No demuestran causalidad ni justifican excluir "
            "observaciones."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - IMPACTO DE EXTRAPOLACIONES")
    print("Integridad y métricas prospectivas: verificadas")
    print("Pares:", len(records))
    print("Entrenamiento:", len(train_y))

    print("\n--- COMPARACIÓN DE GRUPOS ---")

    for name, group in groups.items():
        result = metrics(group, global_error_sum)
        if result["n"] == 0:
            print(f"{name}: n=0")
            continue

        print(
            f"{name}: n={result['n']} | "
            f"MAE reducido={result['ridge_reducido_mae_ghs']:.4f} | "
            f"MAE referencia={result['referencia_1h_mae_ghs']:.4f} | "
            f"diferencia={result['diferencia_mae_ghs']:+.4f} GH/s | "
            f"aporte al error global={result['porcentaje_error_global_reducido']:.2f}%"
        )

    print("\n--- POR CONTEXTO OPERATIVO ---")

    for name, result in context_groups.items():
        print(
            f"{name}: n={result['n']} | "
            f"MAE reducido={result['ridge_reducido_mae_ghs']:.4f} | "
            f"MAE referencia={result['referencia_1h_mae_ghs']:.4f} | "
            f"diferencia={result['diferencia_mae_ghs']:+.4f} GH/s"
        )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos y Bitaxe: intactos.")


EXPECTED_PAIRS = 9922

if __name__ == "__main__":
    main()
