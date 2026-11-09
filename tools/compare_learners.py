"""
TEOS Compare Learners (v1 vs v2-B)
==================================
Compares the accuracy of:
- v1 Panoramic: uses the recommended method per timestamp
- v2-B Ensemble: uses the weighted prediction per timestamp

Both against the real outcomes in learning_outcomes_v2.jsonl.
"""
import json
import statistics
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "data" / "processed" / "meta_learner_recommendations.jsonl"
ENSEMBLE = ROOT / "data" / "processed" / "ensemble_predictions_v2.jsonl"
OUTCOMES = ROOT / "data" / "processed" / "learning_outcomes_v2.jsonl"


def load_jsonl(path):
    out = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    return out


def main():
    outcomes = load_jsonl(OUTCOMES)
    metas = load_jsonl(META)
    ensembles = load_jsonl(ENSEMBLE)

    # Mapa: target_timestamp -> {method: {predicted, actual}}
    by_target = defaultdict(dict)
    for o in outcomes:
        target = o.get("target_timestamp")
        method = o.get("method")
        pred = o.get("predicted_hashRate_GHs")
        actual = o.get("actual_hashRate_GHs")
        if target and method and isinstance(pred, (int, float)) and isinstance(actual, (int, float)):
            by_target[target][method] = {"pred": pred, "actual": actual}

    # Filtrar solo recomendaciones del v1 Panorámico (excluir v1 miope anterior)
    metas = [m for m in metas if "Panoramic" in (m.get("version") or "")]
    print(f"v1 Panorámico puro: {len(metas)} recomendaciones (después de filtrar v1 miope)")

    # Para cada meta-recommendation: buscar el PRÓXIMO outcome de ese método
    from datetime import datetime
    def _parse_ts(s):
        if not s: return None
        try:
            if s.endswith("Z"): s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except Exception:
            return None

    # Indexar outcomes por método con source_timestamp parseado
    outcomes_by_method = defaultdict(list)
    for o in outcomes:
        method = o.get("method")
        src_ts = o.get("source_timestamp")
        tgt = o.get("target_timestamp")
        pred = o.get("predicted_hashRate_GHs")
        actual = o.get("actual_hashRate_GHs")
        if method and src_ts and isinstance(pred, (int, float)) and isinstance(actual, (int, float)):
            dt = _parse_ts(src_ts)
            if dt:
                outcomes_by_method[method].append({
                    "dt": dt,
                    "pred": pred,
                    "actual": actual,
                    "target": tgt,
                })
    for m in outcomes_by_method:
        outcomes_by_method[m].sort(key=lambda x: x["dt"])

    v1_apes = []
    v1_details = []
    for m in metas:
        rec_ts = _parse_ts(m.get("timestamp"))
        method = m.get("recommended_method")
        if not rec_ts or not method or method not in outcomes_by_method:
            continue
        # Buscar el outcome más cercano DESPUÉS del timestamp de la recomendación
        best = None
        for o in outcomes_by_method[method]:
            if o["dt"] >= rec_ts:
                best = o
                break
        if best and best["actual"] > 0:
            ape = abs(best["pred"] - best["actual"]) / best["actual"] * 100
            v1_apes.append(ape)
            v1_details.append({
                "timestamp": best["target"],
                "method": method,
                "ape": ape,
            })

    # Para cada ensemble: predecir = ensemble_prediction_GHs
    v2_apes = []
    v2_details = []
    for e in ensembles:
        target = e.get("target_timestamp")
        pred = e.get("ensemble_prediction_GHs")
        if target in by_target and isinstance(pred, (int, float)):
            actual = None
            for d in by_target[target].values():
                actual = d["actual"]
                break
            if actual and actual > 0:
                ape = abs(pred - actual) / actual * 100
                v2_apes.append(ape)
                v2_details.append({"timestamp": target, "ape": ape})

    print("=" * 60)
    print(" ANÁLISIS COMPARATIVO: v1 PANORÁMICO vs v2-B ENSEMBLE")
    print("=" * 60)
    print(f"v1: {len(v1_apes)} predicciones evaluadas")
    print(f"v2-B: {len(v2_apes)} predicciones evaluadas")
    print()

    if v1_apes:
        print(f"📊 v1 PANORÁMICO:")
        print(f"   Media APE:   {statistics.mean(v1_apes):.2f}%")
        print(f"   Mediana APE: {statistics.median(v1_apes):.2f}%")
        print(f"   Mejor:       {min(v1_apes):.2f}%")
        print(f"   Peor:        {max(v1_apes):.2f}%")
        print()

    if v2_apes:
        print(f"📊 v2-B ENSEMBLE:")
        print(f"   Media APE:   {statistics.mean(v2_apes):.2f}%")
        print(f"   Mediana APE: {statistics.median(v2_apes):.2f}%")
        print(f"   Mejor:       {min(v2_apes):.2f}%")
        print(f"   Peor:        {max(v2_apes):.2f}%")
        print()

    # Comparación directa sobre los mismos timestamps
    v1_by_ts = {d["timestamp"]: d["ape"] for d in v1_details}
    v2_by_ts = {d["timestamp"]: d["ape"] for d in v2_details}
    common = set(v1_by_ts) & set(v2_by_ts)
    if common:
        v1_common = [v1_by_ts[t] for t in common]
        v2_common = [v2_by_ts[t] for t in common]
        print(f"⚖️  COMPARACIÓN DIRECTA ({len(common)} timestamps comunes):")
        print(f"   v1 media:   {statistics.mean(v1_common):.2f}%")
        print(f"   v2-B media: {statistics.mean(v2_common):.2f}%")
        winner = "v2-B" if statistics.mean(v2_common) < statistics.mean(v1_common) else "v1"
        diff = abs(statistics.mean(v1_common) - statistics.mean(v2_common))
        print(f"   🏆 GANADOR: {winner} por {diff:.2f} puntos")
    else:
        print("⚠️  No hay timestamps comunes para comparar directamente.")
        print("    Espera a que ambos acumulen más datos solapados.")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
