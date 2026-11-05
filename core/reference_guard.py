"""Protección experimental de referencias temporales de NEURONA.

No modifica los datos originales ni los archivos de producción.
Recibe muestras previamente filtradas y ordenadas cronológicamente.
"""

from statistics import median
from numbers import Real
import math


def _positive_finite(value):
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0
    )


def guard_references(samples, factor=3.0, window=10, min_history=5):
    """Añade marcas de validez sin sobrescribir las referencias originales."""
    if factor <= 1 or window < 1 or min_history < 1:
        raise ValueError("Parámetros de protección inválidos")

    result = []
    accepted_history = []

    for sample in samples:
        item = dict(sample)
        history = accepted_history[-window:]
        actuals = [
            float(s["actual"])
            for s in history
            if _positive_finite(s.get("actual"))
        ]

        baseline = (
            median(actuals)
            if len(actuals) >= min_history
            else None
        )

        item["reference_guard_baseline_GHs"] = baseline

        for field in ("rate_10m", "rate_1h"):
            value = item.get(field)
            valid = _positive_finite(value)
            reason = "validada"

            if not valid:
                reason = "referencia_ausente_o_invalida"
            elif baseline is None:
                valid = False
                reason = "historial_insuficiente"
            elif float(value) > factor * baseline:
                valid = False
                reason = "referencia_supera_limite_contextual"

            item[f"{field}_valid"] = bool(valid)
            item[f"{field}_guard_reason"] = reason

        result.append(item)

        # El guard no decide qué observaciones son anómalas.
        # La lista recibida debe haber pasado antes el filtro de muestras.
        if _positive_finite(item.get("actual")):
            accepted_history.append(item)

    return result


def build_safe_forecasts(guarded_samples):
    """Construye referencias predictivas solo con campos validados."""
    if not guarded_samples:
        raise ValueError("No hay muestras para construir predicciones")

    latest = guarded_samples[-1]
    actual = latest.get("actual")
    if not _positive_finite(actual):
        raise ValueError("Hashrate actual inválido")

    forecasts = {"ultimo_hashrate": float(actual)}

    history = [
        float(s["actual"])
        for s in guarded_samples[-5:]
        if _positive_finite(s.get("actual"))
    ]
    if len(history) == 5:
        forecasts["media_ultimas_5"] = sum(history) / 5

    for field, method in (
        ("rate_10m", "referencia_10m"),
        ("rate_1h", "referencia_1h"),
    ):
        if latest.get(f"{field}_valid") is True:
            value = latest.get(field)
            if _positive_finite(value):
                forecasts[method] = float(value)

    return forecasts


def select_available_method(preferred_method, forecasts):
    """Usa el método preferido si existe; si no, busca una base segura."""
    if preferred_method in forecasts:
        return preferred_method

    for method in (
        "ultimo_hashrate",
        "media_ultimas_5",
        "referencia_10m",
        "referencia_1h",
    ):
        if method in forecasts:
            return method

    return None
