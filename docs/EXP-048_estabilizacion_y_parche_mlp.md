# EXP-048: Estabilización del Hardware (Bitaxe) y Corrección del MLP Lite

**Fecha:** 2026-11-21
**Hardware:** Bitaxe Gamma 602 (BM1370)
**Objetivo:** Diagnosticar y solucionar los reinicios intermitentes del ASIC y detener la oscilación caótica de frecuencia provocada por el AI Bridge.

---

## 1. El Problema (Síntomas)
*   El Bitaxe se reiniciaba de forma recurrente cada 40-80 minutos (HR=0, ASIC=-1°C, err 55.94%).
*   El VRM alcanzaba los 63-64°C justo antes del reinicio.
*   El AI Bridge oscilaba la frecuencia salvajemente entre 575 y 600 MHz (ej. -0.9% → -5 MHz, +0.9% → +5 MHz).
*   La tasa de error real había subido al 0.42% (191 fallos de 45,901).

## 2. El Diagnóstico (La Causa Raíz)
*   **Hardware:** El VRM del Bitaxe tiene un límite térmico real de ~105°C, por lo que apagarse a 63°C NO era un problema térmico, sino un *brownout* (caída de tensión) o un estado de fallo *latched* (bloqueado) del regulador TPS546.
*   **Software (IA):** El commit `32fc9c4` había dejado al MLP Lite sin capacidad de predecir. Al eliminar la variable del hashrate instantáneo, la red colapsó y empezó a predecir siempre el promedio estático (`1183.7377`). El AI Bridge reaccionaba a este dato falso y movía la frecuencia sin sentido.

## 3. La Solución Aplicada
1.  **Descanso de Hardware:** Se apagó el Bitaxe completamente durante 2 horas para limpiar el estado *latched* y enfriar el circuito.
2.  **Desactivación Temporal de la IA:** Se renombró `ai_bridge.py` para detener la oscilación y permitir que el hardware operara en paz.
3.  **Parche al MLP Lite:** Siguiendo la recomendación del `EXP-035` (Data > Modelo), se modificó el código en `core/neurona_mlp_lite.py` para que la variable objetivo (Y) sea el `hashRate_10m` (promedio) en lugar del `hashRate` (instantáneo).
    *   *Antes:* `Y = np.array([[s["hashRate"]] for s in samples])`
    *   *Ahora:* `Y = np.array([[s.get("hashRate_10m", s["hashRate"])] for s in samples])`
4.  **Re-entrenamiento:** Se borró `model_weights.json` y se volvió a entrenar desde cero.

## 4. Resultados Obtenidos
*   **Hardware Estable:** El Bitaxe opera a 580-585 MHz con el VRM a 66°C (completamente seguro).
*   **Cero Rechazos:** El reporte general muestra 970 shares ok y solo 1 fail (Error rate del 0.10%, bajando del 0.42%).
*   **IA Curada:** La nueva predicción del MLP Lite fue de `1196.12 GH/s` (dinámica y coherente con la realidad).
*   **AI Bridge Domado:** Al comparar la predicción real con el promedio de 10 minutos, la diferencia es mínima, por lo que la IA decide "no actuar" y mantener el Punto Dulce.

## 5. Próximos Pasos
*   Monitorear que el VRM no supere los 70°C.
*   Observar la evolución del APE (Error Porcentual Absoluto) del MLP Lite.
