#!/usr/bin/env python3
# Copyright (c) 2026 Luis Alberto Siguencia Andrade (B3T7O)
# SPDX-License-Identifier: Apache-2.0
#
# TEOS Neurona Nexus - Reference Implementation
# https://github.com/[TU_USUARIO]/teos-neurona-nexus

"""
Analisis de predicciones validadas.
Compara los metodos de prediccion y mide si superan al baseline ingenuo.
Solo lectura. No modifica datos.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

OUTCOMES = Path("data/processed/learning_outcomes_v2.jsonl")
REPORT = Path("data/processed/validation_report.json")


def percentile(sorted_list, p):
    """Calcula percentil p (0-100) de una lista ya ordenada."""
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(sorted_list) - 1)
    if f == c:
        return sorted_list[f]
    return sorted_list[f] + (sorted_list[c] - sorted_list[f]) * (k - f)


def main():
    # Recolectar datos por metodo
    by_method = defaultdict(list)
    total_lines = 0
    parse_errors = 0

    with OUTCOMES.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total_lines += 1
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue

            method = d.get("method", "desconocido")
            ape = d.get("absolute_percentage_error")
            ae = d.get("absolute_error_GHs")
            se = d.get("squared_error_GH2")

            if isinstance(ape, (int, float)) and isinstance(ae, (int, float)):
                by_method[method].append({
                    "ape": ape,
                    "ae": ae,
                    "se": se if isinstance(se, (int, float)) else 0.0,
                })

    print("=" * 70)
    print(" ANALISIS DE PREDICCIONES VALIDADAS")
    print("=" * 70)
    print(f"Lineas procesadas: {total_lines:,}")
    print(f"Lineas corruptas:  {parse_errors}")
    print(f"Metodos distintos: {len(by_method)}")
    print()

    # Baseline ingenuo: predecir que el proximo = ultimo
    # En este dataset, 'ultimo_hashrate' es exactamente eso.
    baseline_method = "ultimo_hashrate"
    baseline_ape = None
    if baseline_method in by_method and by_method[baseline_method]:
        apes = sorted(x["ape"] for x in by_method[baseline_method])
        baseline_ape = statistics.mean(apes)

    # Resumen por metodo
    print(f"{'Metodo':<25} {'N':>8} {'APE_med':>9} {'APE_mediana':>12} {'APE_p95':>9} {'MAE_GHs':>10} {'RMSE_GHs':>10}")
    print("-" * 90)

    results = {}
    for method in sorted(by_method.keys()):
        rows = by_method[method]
        n = len(rows)
        if n == 0:
            continue

        apes = sorted(x["ape"] for x in rows)
        aes = [x["ae"] for x in rows]
        ses = [x["se"] for x in rows]

        ape_mean = statistics.mean(apes)
        ape_median = statistics.median(apes)
        ape_p95 = percentile(apes, 95)
        mae = statistics.mean(aes)
        rmse = (sum(ses) / n) ** 0.5

        results[method] = {
            "n": n,
            "ape_mean": round(ape_mean, 4),
            "ape_median": round(ape_median, 4),
            "ape_p95": round(ape_p95, 4),
            "mae_ghs": round(mae, 4),
            "rmse_ghs": round(rmse, 4),
        }

        marca = ""
        if baseline_ape is not None and method != baseline_method:
            diff = baseline_ape - ape_mean
            if diff > 0:
                marca = f" ✅ -{diff:.2f}pp vs baseline"
            elif diff < 0:
                marca = f" ⚠️ +{abs(diff):.2f}pp vs baseline"

        print(f"{method:<25} {n:>8} {ape_mean:>8.2f}% {ape_median:>11.2f}% {ape_p95:>8.2f}% {mae:>9.1f} {rmse:>9.1f}{marca}")

    # Conclusiones
    print()
    print("=" * 70)
    print(" CONCLUSIONES")
    print("=" * 70)

    if baseline_ape is not None:
        print(f"Baseline ingenuo (ultimo_hashrate): APE medio {baseline_ape:.2f}%")
        print()
        best_method = min(
            (m for m in results if m != baseline_method),
            key=lambda m: results[m]["ape_mean"],
            default=None,
        )
        if best_method:
            best_ape = results[best_method]["ape_mean"]
            mejora = baseline_ape - best_ape
            print(f"Mejor metodo: {best_method}")
            print(f"  APE medio: {best_ape:.2f}%")
            if mejora > 0:
                print(f"  Mejora vs baseline: {mejora:.2f} puntos porcentuales ({mejora/baseline_ape*100:.1f}%)")
                print(f"  ✅ El modelo SUPERA al baseline ingenuo.")
            else:
                print(f"  ⚠️ El modelo NO supera al baseline. Vale mas predecir el ultimo valor.")
    else:
        print("No hay baseline (ultimo_hashrate) en los datos.")

    # Guardar reporte
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", encoding="utf-8") as f:
        json.dump({
            "total_lines": total_lines,
            "parse_errors": parse_errors,
            "baseline_method": baseline_method,
            "baseline_ape_mean": round(baseline_ape, 4) if baseline_ape else None,
            "methods": results,
        }, f, indent=2, ensure_ascii=False)
    print()
    print(f"📁 Reporte guardado en: {REPORT}")


if __name__ == "__main__":
    main()
