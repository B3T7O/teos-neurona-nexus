#!/usr/bin/env python3
"""Diagnóstico de residuos Ridge según variación real del hashrate."""

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import evaluate_ridge_prospective as ev

SNAPSHOT = ROOT / "experiments/frozen_bitaxe_samples.marked.jsonl"
SCRIPT = ROOT / "experiments/first_learning_model.py"
ORIGINAL = ROOT / "experiments/first_learning_model_report.json"
CANDIDATE = ROOT / "experiments/ridge_reduced_candidate_report.json"
PROSPECTIVE = ROOT / "experiments/ridge_prospective_report.json"
EVENT_REPORT = ROOT / "experiments/ridge_prospective_event_impact_report.json"

OUTPUT = ROOT / "experiments/ridge_residual_conditions_report.json"

EXPECTED_HASHES = {
    SNAPSHOT: "dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5",
    SCRIPT: "b1e1a69fd272c09574a89ac866918889065fab5746ed214b98bdd6eaf8bdab7d",
    ORIGINAL: "835002b3e7720fcbf9c6d0b6ad450a86ff474d01bf5126aaf75c8d8dc9a752ba",
}

EXPECTED_PAIRS = 9922
TOLERANCE = 1e-10
TIE_EPSILON = 1e-9

METHODS = {
    "ridge_original": "ridge_original",
    "ridge_reducido": "ridge_reducido",
    "referencia_1h": "baseline_1h",
}

CHANGE_CLASSES = (
    "variacion_baja",
    "variacion_media",
    "variacion_alta",
)


def stop(message):
    raise SystemExit(f"DIAGNÓSTICO DETENIDO: {message}")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_metrics(current, reference, label):
    if current["n"] != reference["n"]:
        stop(f"{label}: cantidad de muestras diferente.")

    for key in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            current[key],
            reference[key],
            rel_tol=TOLERANCE,
            abs_tol=TOLERANCE,
        ):
            stop(f"{label}: no coincide {key}.")


def recover_original_prefix(expected_hash, last_target):
    """Recupera el prefijo exacto sin modificar el RAW actual."""

    data = ev.RAW.read_bytes()
    offset = 0

    for line in data.splitlines(keepends=True):
        offset += len(line)

        try:
            row = json.loads(line)
            timestamp = ev.parse_timestamp(row.get("timestamp"))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue

        if timestamp == last_target:
            prefix = data[:offset]

            if sha256(prefix) != expected_hash:
                stop("El prefijo RAW no coincide con el SHA-256 histórico.")

            return prefix

    stop("No se encontró el último objetivo de la evaluación original.")


def load_prefix_rows(prefix):
    """Carga y deduplica exclusivamente el prefijo verificado."""

    by_time = {}

    for line in prefix.splitlines():
        try:
            row = json.loads(line)
            timestamp = ev.parse_timestamp(row.get("timestamp"))
            hashrate = row.get("hashRate")

            if not ev.valid_number(hashrate):
                continue

            row["_dt"] = timestamp
            by_time[timestamp] = row

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue

    return [
        by_time[t] for t in sorted(by_time)
    ]


def training_change_thresholds(frozen):
    """
    Los umbrales se obtienen exclusivamente del histórico congelado.
    La variación se normaliza por minuto.
    """

    rates = []
    intervals = []

    for i in range(1, len(frozen)):
        previous = frozen[i - 1]
        current = frozen[i]

        seconds = (
            current["_dt"] - previous["_dt"]
        ).total_seconds()

        if seconds <= 0:
            continue

        before = previous["_target"]
        after = current["_target"]

        change_per_minute = (
            abs(after - before) / (seconds / 60.0)
        )

        if math.isfinite(change_per_minute):
            rates.append(change_per_minute)
            intervals.append(seconds)

    if len(rates) < 20:
        stop("Insuficientes variaciones históricas para establecer umbrales.")

    p50, p90 = np.percentile(rates, [50, 90])

    return {
        "p50_ghs_per_minute": float(p50),
        "p90_ghs_per_minute": float(p90),
        "historical_pairs": len(rates),
        "historical_median_interval_seconds": float(np.median(intervals)),
        "historical_p90_interval_seconds": float(np.percentile(intervals, 90)),
    }


def classify_change(rate, thresholds):
    if rate <= thresholds["p50_ghs_per_minute"]:
        return "variacion_baja"

    if rate <= thresholds["p90_ghs_per_minute"]:
        return "variacion_media"

    return "variacion_alta"


def operational_context(timestamp, event_windows):
    for name, (start, end) in event_windows.items():
        if start <= timestamp <= end:
            return name

    return "funcionamiento_habitual"


def detailed_metrics(records, field):
    actual = np.asarray(
        [r["actual"] for r in records],
        dtype=float,
    )

    predicted = np.asarray(
        [r[field] for r in records],
        dtype=float,
    )

    residual = predicted - actual
    absolute = np.abs(residual)

    return {
        "n": len(records),
        "mae_ghs": float(np.mean(absolute)),
        "rmse_ghs": float(np.sqrt(np.mean(residual ** 2))),
        "bias_prediccion_menos_real_ghs": float(np.mean(residual)),
        "mediana_error_absoluto_ghs": float(np.median(absolute)),
        "p90_error_absoluto_ghs": float(np.percentile(absolute, 90)),
    }


def summarize(records):
    if not records:
        return {"n": 0}

    methods = {
        name: detailed_metrics(records, field)
        for name, field in METHODS.items()
    }

    reduced_errors = np.asarray([
        abs(r["actual"] - r["ridge_reducido"])
        for r in records
    ])

    baseline_errors = np.asarray([
        abs(r["actual"] - r["baseline_1h"])
        for r in records
    ])

    differences = reduced_errors - baseline_errors

    wins = int(np.sum(differences < -TIE_EPSILON))
    losses = int(np.sum(differences > TIE_EPSILON))
    ties = len(records) - wins - losses

    intervals = np.asarray(
        [r["interval_seconds"] for r in records],
        dtype=float,
    )

    changes = np.asarray(
        [r["absolute_change_ghs"] for r in records],
        dtype=float,
    )

    return {
        "n": len(records),
        "methods": methods,
        "ridge_reducido_vs_referencia_1h": {
            "gana_por_error_absoluto": wins,
            "pierde_por_error_absoluto": losses,
            "empata": ties,
            "porcentaje_de_victorias": wins / len(records) * 100,
            "diferencia_media_error_absoluto_ghs": float(
                np.mean(differences)
            ),
        },
        "interval_seconds": {
            "median": float(np.median(intervals)),
            "p90": float(np.percentile(intervals, 90)),
        },
        "absolute_change_ghs": {
            "median": float(np.median(changes)),
            "p90": float(np.percentile(changes, 90)),
            "maximum": float(np.max(changes)),
        },
    }


def main():
    required = [
        SNAPSHOT,
        SCRIPT,
        ORIGINAL,
        CANDIDATE,
        PROSPECTIVE,
        EVENT_REPORT,
        ev.MANIFEST,
        ev.RAW,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta el archivo {path.name}.")

    if OUTPUT.exists():
        stop(f"El informe ya existe. No se sobrescribió: {OUTPUT.name}")

    # 1. Integridad de los archivos históricos.
    for path, expected in EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    prospective = json.loads(
        PROSPECTIVE.read_text(encoding="utf-8")
    )
    original = json.loads(
        ORIGINAL.read_text(encoding="utf-8")
    )
    candidate = json.loads(
        CANDIDATE.read_text(encoding="utf-8")
    )
    event_report = json.loads(
        EVENT_REPORT.read_text(encoding="utf-8")
    )
    manifest = json.loads(
        ev.MANIFEST.read_text(encoding="utf-8")
    )

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original no corresponde a la fotografía.")

    if candidate.get("integrity", {}).get("snapshot_sha256") != snapshot_hash:
        stop("El candidato reducido no corresponde a la fotografía.")

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("La evaluación prospectiva usa otra fotografía.")

    if event_report.get("snapshot_sha256") != snapshot_hash:
        stop("El informe de eventos usa otra fotografía.")

    if event_report.get("validation", {}).get(
        "original_prospective_metrics_reproduced"
    ) is not True:
        stop("El análisis previo de eventos no está validado.")

    # 2. Recuperar el RAW original exacto.
    expected_raw_hash = prospective["integrity"]["raw_sha256"]

    if event_report.get("raw_sha256") != expected_raw_hash:
        stop("Los informes prospectivos no comparten el mismo RAW.")

    last_target = ev.parse_timestamp(
        prospective["evaluation_period_utc"]["last_target"]
    )

    prefix = recover_original_prefix(
        expected_raw_hash,
        last_target,
    )

    prefix_rows = load_prefix_rows(prefix)
    cutoff = frozen[-1]["_dt"]

    historical = [
        r for r in prefix_rows if r["_dt"] <= cutoff
    ]

    future = [
        r for r in prefix_rows if r["_dt"] > cutoff
    ]

    ev.verify_context(frozen, historical)

    if len(future) != prospective["validation"]["future_raw_rows"]:
        stop("No coincide el número de muestras futuras originales.")

    # 3. Reconstruir exactamente el conjunto de entrenamiento congelado.
    train_x = []
    train_y = []

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

    if len(train_y) != original["usable_samples"]:
        stop("No coincide el entrenamiento histórico.")

    if len(train_y) != prospective["validation"]["training_samples"]:
        stop("No coincide el número de muestras de entrenamiento.")

    # 4. Umbrales de variación aprendidos únicamente del histórico congelado.
    thresholds = training_change_thresholds(frozen)

    event_windows = {}

    for name, window in event_report["event_windows_utc"].items():
        event_windows[name] = (
            ev.parse_timestamp(window["start"]),
            ev.parse_timestamp(window["end"]),
        )

    # 5. Reconstruir la secuencia prospectiva sin excluir observaciones.
    stream = [frozen[-2], frozen[-1]] + future

    test_x = []
    records = []
    skipped = 0

    for i in range(2, len(stream)):
        previous = stream[i - 1]
        earlier = stream[i - 2]
        target = stream[i]

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

        previous_actual = previous.get("hashRate")

        if not ev.valid_number(previous_actual):
            skipped += 1
            continue

        absolute_change = abs(float(actual) - float(previous_actual))
        change_per_minute = absolute_change / (interval / 60.0)

        test_x.append(x)

        records.append({
            "timestamp": target["_dt"],
            "actual": float(actual),
            "baseline_1h": float(baseline),
            "interval_seconds": float(interval),
            "absolute_change_ghs": absolute_change,
            "change_per_minute_ghs": change_per_minute,
            "change_class": classify_change(
                change_per_minute,
                thresholds,
            ),
            "operational_context": operational_context(
                target["_dt"],
                event_windows,
            ),
        })

    if skipped != prospective["validation"]["future_pairs_skipped"]:
        stop("La cantidad de pares omitidos no coincide.")

    if len(records) != EXPECTED_PAIRS:
        stop(f"Se esperaban {EXPECTED_PAIRS} pares y hay {len(records)}.")

    test_x = np.asarray(test_x, dtype=float)

    # 6. Recuperar los mismos modelos fijos: no se aprende con datos futuros.
    full_indices = np.arange(len(ev.FEATURES))

    reduced_indices = np.asarray([
        ev.FEATURES.index(f)
        for f in ev.REDUCED_FEATURES
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

    # 7. Reproducir las métricas prospectivas oficiales.
    global_methods = ev.compare_methods(records)

    for method in METHODS:
        verify_metrics(
            global_methods[method],
            prospective["global"][method],
            f"Global {method}",
        )

    # 8. Agrupar todas las observaciones sin descartarlas.
    by_change = defaultdict(list)
    by_context = defaultdict(list)
    habitual_by_change = defaultdict(list)
    context_by_change = defaultdict(list)

    for record in records:
        change_class = record["change_class"]
        context = record["operational_context"]

        by_change[change_class].append(record)
        by_context[context].append(record)
        context_by_change[(context, change_class)].append(record)

        if context == "funcionamiento_habitual":
            habitual_by_change[change_class].append(record)

    if sum(len(group) for group in by_change.values()) != len(records):
        stop("La clasificación por variación perdió observaciones.")

    if sum(len(group) for group in by_context.values()) != len(records):
        stop("La clasificación por contexto perdió observaciones.")

    if sum(len(group) for group in habitual_by_change.values()) != len(
        by_context["funcionamiento_habitual"]
    ):
        stop("La clasificación del funcionamiento habitual está incompleta.")

    # 9. Métricas globales, por variación y por contexto operativo.
    global_summary = summarize(records)

    change_summary = {
        name: summarize(by_change.get(name, []))
        for name in CHANGE_CLASSES
    }

    context_summary = {
        name: summarize(group)
        for name, group in sorted(by_context.items())
    }

    habitual_summary = {
        name: summarize(habitual_by_change.get(name, []))
        for name in CHANGE_CLASSES
    }

    context_change_summary = {
        context: {
            change_class: summarize(
                context_by_change.get((context, change_class), [])
            )
            for change_class in CHANGE_CLASSES
        }
        for context in sorted(by_context)
    }

    # 10. Guardar un informe nuevo.
    report = {
        "title": "TEOS NEURONA — Residuos Ridge por condiciones operativas",
        "snapshot_sha256": snapshot_hash,
        "raw_prefix_sha256": expected_raw_hash,
        "validation": {
            "official_prospective_metrics_reproduced": True,
            "future_pairs": len(records),
            "training_samples": len(train_y),
            "same_targets_for_all_methods": True,
            "future_data_used_for_training": False,
            "model_weights_fixed_during_evaluation": True,
            "all_valid_observations_preserved": True,
            "group_partitions_cover_all_observations": True,
            "original_files_modified": False,
        },
        "movement_classification": {
            "measurement": (
                "Cambio absoluto de hashRate real entre dos muestras "
                "consecutivas, dividido por los minutos transcurridos."
            ),
            "threshold_source": "Conjunto histórico congelado",
            "thresholds": thresholds,
            "classes": {
                "variacion_baja": "<= percentil 50 histórico",
                "variacion_media": "> percentil 50 y <= percentil 90 histórico",
                "variacion_alta": "> percentil 90 histórico",
            },
            "classification_is_post_hoc": True,
        },
        "global_all_observations": global_summary,
        "by_change_class_all_contexts": change_summary,
        "by_operational_context": context_summary,
        "habitual_operation_by_change_class": habitual_summary,
        "cross_classification_context_and_change": context_change_summary,
        "counts": {
            "all": len(records),
            "by_change_class": {
                name: len(group) for name, group in by_change.items()
            },
            "by_operational_context": {
                name: len(group) for name, group in by_context.items()
            },
        },
        "interpretation": {
            "positive_mean_error_delta": (
                "Ridge reducido tiene mayor error absoluto medio "
                "que la referencia 1h en ese grupo."
            ),
            "negative_mean_error_delta": (
                "Ridge reducido tiene menor error absoluto medio "
                "que la referencia 1h en ese grupo."
            ),
            "bias_convention": (
                "Predicción menos valor real; positivo indica "
                "sobreestimación y negativo indica subestimación."
            ),
        },
        "warning": (
            "La clasificación por variación utiliza el hashrate real "
            "del objetivo y es retrospectiva; no es una característica "
            "disponible para predecir ese mismo objetivo. Los resultados "
            "por grupo son diagnósticos descriptivos. El global conserva "
            "todas las observaciones, incluidos los eventos identificados."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — RESIDUOS RIDGE")
    print("Integridad y métricas oficiales: verificadas")
    print("Pares prospectivos conservados:", len(records))
    print("Entrenamiento histórico:", len(train_y))
    print("Reentrenamiento con datos futuros: NO")

    print("\n--- COMPARACIÓN GLOBAL ---")

    for name in METHODS:
        item = global_summary["methods"][name]
        print(
            f"{name}: MAE={item['mae_ghs']:.4f} | "
            f"RMSE={item['rmse_ghs']:.4f} GH/s"
        )

    print("\n--- FUNCIONAMIENTO HABITUAL POR VARIACIÓN ---")

    for name in CHANGE_CLASSES:
        group = habitual_summary[name]
        print(f"\n{name}: n={group['n']}")

        if not group["n"]:
            continue

        reduced = group["methods"]["ridge_reducido"]
        baseline = group["methods"]["referencia_1h"]
        comparison = group["ridge_reducido_vs_referencia_1h"]

        print(f"Ridge reducido MAE: {reduced['mae_ghs']:.4f} GH/s")
        print(f"Referencia 1h MAE: {baseline['mae_ghs']:.4f} GH/s")
        print(
            "Diferencia MAE reducido - referencia:",
            f"{reduced['mae_ghs'] - baseline['mae_ghs']:+.4f} GH/s",
        )
        print(
            "Victorias individuales del reducido:",
            f"{comparison['gana_por_error_absoluto']}/"
            f"{group['n']}",
        )

    print("\n--- CONTEXTOS OPERATIVOS ---")

    for name, group in context_summary.items():
        print(f"{name}: n={group['n']}")

        if group["n"]:
            reduced = group["methods"]["ridge_reducido"]
            baseline = group["methods"]["referencia_1h"]
            print(
                f"  MAE reducido={reduced['mae_ghs']:.4f} | "
                f"MAE referencia={baseline['mae_ghs']:.4f} GH/s"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos originales y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
