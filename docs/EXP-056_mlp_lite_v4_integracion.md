# EXP-056 — Resurrección del MLP Lite (V4 Stability Predictor)

**Fecha:** 2026-11-26
**Estado:** CERRADO — ÉXITO
**Mejora:** F1-Score de 0.923 sobre el baseline.

## El Descubrimiento
Tras descartar la predicción de hashrate (puro ruido) y la detección de chips fantasma (el hardware solo reporta 1 ASIC), se encontró el nicho perfecto: **Predicción de Inestabilidad en ventanas de tiempo**.

## El Modelo
- **Input:** Ventanas deslizantes de 5 registros (temp, vrTemp, fanrpm, power, frequency, error).
- **Output:** Probabilidad de que el error supere el 1% en los próximos 5 pasos.
- **Rendimiento:** Recall de 1.000 (detecta todas las crisis) y Precision de 0.857.

## Integración
El AI Bridge (`core/bitaxe_control.py`) ahora mantiene un buffer de 5 lecturas y consulta al `stability_model.json` antes de subir la frecuencia. Si el MLP predice > 70% de probabilidad de inestabilidad, la frecuencia se bloquea en su nivel actual (previniendo el error antes de que ocurra).
