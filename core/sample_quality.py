#!/usr/bin/env python3
"""
Modulo reutilizable de clasificacion de calidad de samples.
Uso:
    from core.sample_quality import classify, is_valid, is_trainable
"""
HR_MIN_PER_MHZ = 0.5
HR_MAX_PER_MHZ = 5.0
IDLE_THRESHOLD = 50.0


def classify(o):
    """Devuelve 'ok' | 'corrupt_spike' | 'idle' | 'bad_zero'."""
    hr = o.get("hashRate")
    if hr is None:
        hr = o.get("hashRate_1m")
    pw = o.get("power")
    fr = o.get("frequency")

    if hr is None or pw is None or fr is None:
        return "ok"

    if pw <= 0.5 or fr <= 0:
        return "bad_zero"
    if hr < IDLE_THRESHOLD:
        return "idle"
    if hr < fr * HR_MIN_PER_MHZ or hr > fr * HR_MAX_PER_MHZ:
        return "corrupt_spike"
    return "ok"


def is_valid(o):
    """True si el sample no es fisicamente imposible."""
    return classify(o) != "corrupt_spike"


def is_trainable(o):
    """True si el sample es apto para entrenamiento (no corrupto, no idle)."""
    return classify(o) == "ok"
