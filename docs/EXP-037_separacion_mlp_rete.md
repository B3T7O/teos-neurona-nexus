# EXP-037: Separación de Responsabilidades (MLP Lite vs Rete Engine)

**Fecha:** 2026-11-14
**Objetivo:** Definir la arquitectura de decisión del sistema TEOS Neurona Nexus, separando la lógica probabilística (IA) de la lógica determinista (Reglas).

## Contexto
Con la integración del Motor de Reglas (Rete Engine) y la actualización del modelo de Deep Learning (MLP Lite), surgió la duda de si los 10,000 nonces históricos debían usarse también en el motor de reglas.

## Decisión Arquitectónica
Se establece una separación estricta de responsabilidades:

1. **MLP Lite (El Analista Probabilístico):**
   *   **Entradas:** Temperaturas, Hashrate, Shares (Regex), Dificultad y **Rareza de Nonces (Z-Score)**.
   *   **Función:** Predecir el hashrate futuro y detectar patrones complejos.
   *   **Justificación:** Los nonces son "ruido blanco". Solo un modelo estadístico/neuronal puede intentar aproximarse a su comportamiento sin romper la lógica del sistema.

2. **Rete Engine (El Guardián Determinista):**
   *   **Entradas:** Temperatura (ASIC/VRM), Tasa de Error, Frecuencia actual.
   *   **Función:** Ejecutar acciones inmediatas de protección y optimización (Subir/Bajar MHz, cambiar ventilador).
   *   **Justificación:** Las reglas de Rete son `If-Then`. Introducir la aleatoriedad de los nonces aquí provocaría que el minero cambie de frecuencia basándose en el azar.

## Integración Futura
Aunque Rete no calcula nonces, puede consumir las predicciones del MLP Lite en el futuro.

## Conclusión
El sistema tiene 4 cerebros especializados: Regex, MLP Lite, Rete y Scheduler.
