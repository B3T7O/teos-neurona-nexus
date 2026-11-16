# EXP-046: Latency Sniper - Medición de Tiempo de Reacción en Tiempo Real

**Fecha:** 2026-11-16
**Objetivo:** Medir la latencia exacta entre el momento en que un bloque es minado en la red de Bitcoin y el momento en que el Bitaxe recibe la nueva tarea (`mining.notify`).

## Implementación
Se creó un script (`latency_sniper_rt.py`) que:
1. Monitorea la altura de la blockchain cada 3 segundos.
2. Cuando detecta un bloque nuevo, obtiene su timestamp desde mempool.space.
3. Busca en los logs del Bitaxe (`axeos_logs.json`) la tarea `mining.notify` correspondiente.
4. Calcula el delta de tiempo entre ambos eventos.

## Resultados
* **Bloque capturado:** #976069
* **Timestamp del bloque:** 2026-11-16T04:03:35Z
* **Tarea recibida:** 2026-11-16T04:03:39.624949Z
* **Latencia medida:** 4.6249 segundos (4625 ms)

## Análisis
La latencia de ~4.6 segundos es consistente con el tiempo de propagación de un bloque en la red P2P de Bitcoin hasta los servidores de solo.ckpool.org. El Lite Proxy (1 ms) añade una latencia insignificante en comparación con el tiempo de propagación global. El sistema demuestra ser capaz de monitorear eventos de red en tiempo real con precisión de milisegundos.
