# EXP-039: Integración del Campeón Evolutivo y el Ojo Clínico de la IA

**Fecha:** 2026-11-15
**Objetivo:** Documentar la conexión entre el algoritmo genético (Evolve Lab), el Meta Learner y la neurona de 10 sentidos (MLP Lite), completando la arquitectura de IA de 4 capas de TEOS Neurona Nexus.

## 1. La Evolución del MLP Lite (Ojo Clínico)
El modelo de Deep Learning pasó de 7 a **10 features** (sentidos), añadiendo tasas de error específicas extraídas en tiempo real desde la API del Bitaxe:
*   `stale_rate`: Tasa de shares obsoletos (micro-cortes de red/latencia).
*   `dup_rate`: Tasa de shares duplicados (colisiones de silicio).
*   `above_rate`: Tasa de shares fuera de objetivo (cambios de dificultad del pool).
*   **Configuración final:** 12 neuronas ocultas (`HIDDEN_SIZE = 12`), 10 features (`INPUT_SIZE = 10`), 300 muestras de entrenamiento.

## 2. La Integración del Evolucionador (Genética)
El algoritmo genético (`evolve_lab.py`) fue actualizado para incluir a `mlp_lite` en su búsqueda de combinaciones. Tras 50 generaciones (población de 100), el **Campeón Evolutivo** arrojó los siguientes resultados:
*   **APE del Campeón:** 2.9201%
*   **Peso del MLP Lite:** 14.44%
*   **Peso de referencia_10m:** 48.82%
*   **Peso de referencia_1h:** 18.97%
*   **Peso de media_ultimas_5:** 12.96%
*   **Peso de ultimo_hashrate:** 3.81%
*   **Peso de adaptativo_neurona:** 0.99%

## 3. La Integración del Meta Learner
El Meta Learner (`meta_learner_lite.py`) ahora lee el archivo `evolve_champion.json` y expone los pesos del campeón en su reporte JSON. Esto permite que el sistema conozca las "fórmulas históricas" del Evolucionador, aunque la decisión en vivo siga siendo del Meta Learner.

## 4. El Estado del Hardware (Iron Man)
*   **Frecuencia:** 580 MHz (Punto dulce).
*   **Voltaje:** 1095 mV.
*   **Error Rate:** 0.38% (Nivel élite).
*   **Temperatura:** ASIC 52.8°C / VRM 67°C.
*   **Latencia:** ~1 ms (Lite Proxy local con systemd).

## Conclusión
El sistema TEOS Neurona Nexus opera con **4 capas de Inteligencia Artificial**:
1.  **Evolve Lab:** Optimización genética de pesos históricos.
2.  **Meta Learner:** Selección dinámica en ventanas de tiempo.
3.  **MLP Lite:** Predicción neuronal con 10 sentidos.
4.  **Rete Engine:** Reglas deterministas de protección.

El hardware está en su punto de máxima eficiencia térmica y energética, y la IA está lista para digerir las nuevas muestras estables.
