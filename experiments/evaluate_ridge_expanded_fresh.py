#!/usr/bin/env python3
"""Ridge reducido con entrenamiento ampliado y validacion nueva."""

import sys
import json
import hashlib
from pathlib import Path
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_ridge_prospective as core

SNAPSHOT = core.ROOT / "experiments/expanded_training_20261103.jsonl"
MANIFEST = core.ROOT / "experiments/expanded_training_20261103_manifest.json"
OUTPUT = core.ROOT / "experiments/ridge_expanded_fresh_report.json"

CUTOFF = core.parse_timestamp("2026-11-03T23:35:24.026790+00:00")
MIN_PAIRS = 500


def stop(message):
    raise SystemExit("EVALUACION DETENIDA: " + message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_snapshot():
    raw = SNAPSHOT.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    if sha256(raw) != manifest.get("snapshot_sha256"):
        stop("SHA-256 de fotografia incorrecto.")

    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        row["_ts"] = row["timestamp"]
        row["_dt"] = core.parse_timestamp(row["_ts"])
        row["_target"] = float(row["hashRate"])
        rows.append(row)

    if len(rows) != manifest.get("historical_records"):
        stop("Numero de registros diferente del manifiesto.")

    if rows[-1]["_dt"] != CUTOFF:
        stop("El ultimo registro no coincide con el corte.")

    return rows, manifest


def metrics(records):
    if not records:
        return {"n": 0}

    actual = [r["actual"] for r in records]
    baseline = [r["baseline"] for r in records]
    candidate = [r["candidate"] for r in records]

    ref = core.metrics(actual, baseline)
    model = core.metrics(actual, candidate)

    return {
        "n": len(records),
        "referencia_1h": ref,
        "ridge_ampliado": model,
        "delta_mae_ghs": model["mae_ghs"] - ref["mae_ghs"],
        "delta_rmse_ghs": model["rmse_ghs"] - ref["rmse_ghs"],
    }


def main():
    if OUTPUT.exists():
        stop("El informe ya existe. No se sobrescribio.")

    for path, expected in core.EXPECTED_HASHES.items():
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            stop("Integridad historica incorrecta: " + path.name)

    frozen, manifest = load_snapshot()

    candidate_report = json.loads(core.CANDIDATE.read_text())
    definition = candidate_report.get("candidate_definition", {})

    if definition.get("retained_features") != core.REDUCED_FEATURES:
        stop("Caracteristicas del Ridge reducido no verificadas.")

    # Entrenamiento ampliado: exclusivamente fotografia congelada.
    train_x = []
    train_y = []

    for i in range(2, len(frozen)):
        x = core.feature_at(frozen[i - 1], frozen[i - 2])
        y = frozen[i].get("_target")
        base = frozen[i - 1].get("hashRate_1h")
        interval = (frozen[i]["_dt"] - frozen[i - 1]["_dt"]).total_seconds()

        if (
            x is None
            or not core.valid_number(y)
            or not core.valid_number(base)
            or interval <= 0
        ):
            continue

        train_x.append(x)
        train_y.append(float(y))

    if len(train_y) != manifest.get("usable_training_pairs"):
        stop("Pares de entrenamiento no coinciden con el manifiesto.")

    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)

    # RAW: verificar continuidad con las dos ultimas muestras congeladas.
    historical, future, invalid, duplicates, raw_hash = (
        core.load_raw_future(CUTOFF)
    )

    if len(historical) < 2:
        stop("Contexto historico RAW insuficiente.")

    for old, current in zip(frozen[-2:], historical[-2:]):
        for field in ["timestamp"] + core.BASE_FIELDS:
            if old.get(field) != current.get(field):
                stop("Discontinuidad historica en campo: " + field)

    # Evaluacion exclusivamente posterior al corte.
    stream = [frozen[-2], frozen[-1]] + future

    test_x = []
    actual = []
    baseline = []
    intervals = []
    timestamps = []
    skipped = 0

    for i in range(2, len(stream)):
        previous, earlier, target = stream[i - 1], stream[i - 2], stream[i]

        if target["_dt"] <= CUTOFF:
            continue

        x = core.feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (target["_dt"] - previous["_dt"]).total_seconds()

        if (
            x is None
            or not core.valid_number(y)
            or not core.valid_number(base)
            or interval <= 0
        ):
            skipped += 1
            continue

        test_x.append(x)
        actual.append(float(y))
        baseline.append(float(base))
        intervals.append(float(interval))
        timestamps.append(target["_dt"].isoformat())

    if len(test_x) < MIN_PAIRS:
        stop(
            f"Solo hay {len(test_x)} pares nuevos validos; "
            f"se requieren {MIN_PAIRS}. No se genero informe."
        )

    test_x = np.asarray(test_x, dtype=float)
    actual = np.asarray(actual, dtype=float)
    baseline = np.asarray(baseline, dtype=float)

    selected = np.asarray([
        core.FEATURES.index(f) for f in core.REDUCED_FEATURES
    ])

    prediction = core.fit_predict(
        train_x, train_y, test_x, selected
    )

    records = [
        {
            "timestamp": timestamps[i],
            "actual": float(actual[i]),
            "baseline": float(baseline[i]),
            "candidate": float(prediction[i]),
            "interval_seconds": float(intervals[i]),
        }
        for i in range(len(actual))
    ]

    global_result = metrics(records)

    ordinary = metrics([
        r for r in records if r["interval_seconds"] <= 120
    ])
    long_gaps = metrics([
        r for r in records if r["interval_seconds"] > 120
    ])

    daily_groups = defaultdict(list)
    for r in records:
        daily_groups[r["timestamp"][:10]].append(r)

    daily = {
        day: metrics(items)
        for day, items in sorted(daily_groups.items())
    }

    ref = global_result["referencia_1h"]
    model = global_result["ridge_ampliado"]

    report = {
        "title": "TEOS NEURONA - Ridge entrenamiento ampliado",
        "integrity": {
            "snapshot_sha256": manifest["snapshot_sha256"],
            "raw_sha256": raw_hash,
            "original_files_modified": False,
        },
        "validation": {
            "training_records": len(frozen),
            "training_pairs": len(train_y),
            "training_cutoff_utc": CUTOFF.isoformat(),
            "fresh_valid_pairs": len(records),
            "future_data_used_for_training": False,
            "model_refitted_during_evaluation": False,
            "rolling_one_step_ahead": True,
            "skipped_pairs": skipped,
            "invalid_raw_records": invalid,
            "duplicate_raw_timestamps": duplicates,
            "ridge_alpha": core.ALPHA,
            "features": list(core.REDUCED_FEATURES),
            "promotion_authorized": False,
        },
        "evaluation_period_utc": {
            "first_target": timestamps[0],
            "last_target": timestamps[-1],
        },
        "global": global_result,
        "ordinary_operation_120s": ordinary,
        "long_gaps": long_gaps,
        "by_utc_day": daily,
        "conclusion": {
            "beats_reference_mae": model["mae_ghs"] < ref["mae_ghs"],
            "beats_reference_rmse": model["rmse_ghs"] < ref["rmse_ghs"],
            "ordinary_operation_mae_not_worse": (
                ordinary.get("ridge_ampliado", {}).get("mae_ghs", float("inf"))
                <= ordinary.get("referencia_1h", {}).get("mae_ghs", 0)
            ),
            "promotion_recommended": False,
        },
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - RIDGE ENTRENAMIENTO AMPLIADO")
    print("Integridad de fotografia: verificada")
    print("Entrenamiento:", len(train_y))
    print("Pares nuevos:", len(records))

    for label, result in [
        ("GLOBAL", global_result),
        ("OPERACION HABITUAL <=120s", ordinary),
        ("INTERVALOS >120s", long_gaps),
    ]:
        print("\n---", label, "---")
        if result.get("n"):
            for method in ("referencia_1h", "ridge_ampliado"):
                m = result[method]
                print(
                    f"{method}: MAE={m['mae_ghs']:.6f} | "
                    f"RMSE={m['rmse_ghs']:.6f} GH/s"
                )
        else:
            print("Sin muestras.")

    print("\nInforme:", OUTPUT.relative_to(core.ROOT))
    print("Integracion autorizada: NO")


if __name__ == "__main__":
    main()
