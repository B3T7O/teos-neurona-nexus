# EXP-036: Integración de Regex y 10k Nonces al MLP Lite

**Fecha:** 2026-11-14
**Objetivo:** Enriquecer el modelo predictivo (MLP Lite) con datos exactos extraídos de los logs del ASIC y estadísticas históricas de la blockchain.

## Cambios Realizados
1. **Feature Engineering (8 Features):** El modelo pasó de 5 a 8 variables de entrada.
2. **Parser Regex en Logs:** Se implementó un Regex para leer `axeos_logs.json`, extrayendo la cantidad de shares y la dificultad real de los últimos 500 eventos.
3. **Análisis de 10k Nonces:** Se calcularon la media y desviación estándar de los nonces históricos para inyectar un `Z-Score` (rareza del nonce) al modelo.

## Resultados de la Prueba
*   Shares extraídos: 72
*   Dificultad media: 1641.29
*   Rareza Z-Score: 0.2807 (Nonces dentro del rango normal histórico)

## Conclusión
La IA ahora no solo predice en base a telemetría, sino que "ve" la suerte estadística de la red y los shares encontrados en tiempo real.
