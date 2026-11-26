# EXP-057 — Protocolo "Flecha Roja" (Proactive Drop)

**Fecha:** 2026-11-26
**Estado:** CERRADO — TÁCTICO
**Mejora:** El AI Bridge ahora actúa como un general previsor, no solo como un espectador.

## El Problema
El MLP V4 predecía inestabilidad, pero solo se usaba para *bloquear* subidas de frecuencia. Si la inestabilidad ocurría de todos modos, el sistema dependía del Watchdog (reactivo al 3% de error).

## La Solución (Flecha Roja)
Se modificó la lógica de `bitaxe_control.py` para consultar al MLP V4 antes de cualquier acción. 
Si `predict_stability() > 0.85`, el sistema ejecuta una **retirada táctica** (baja 25 MHz) de inmediato, *incluso si el error actual es bajo*.

## Resultado
El sistema tiene ahora visión prospectiva real:
1. **El MLP V4** ve los drones acercarse (patrones de telemetría).
2. **El AI Bridge** llama a la "Flecha Roja" y baja la frecuencia.
3. **El Watchdog** queda como el último escudo (Caja Negra) por si algo falla.

El soldado ya no recibe el ataque con la guardia baja.
