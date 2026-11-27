# EXP-059 — Consejo de Expertos (MoE) vs. MLP V4

**Fecha:** 2026-11-27
**Estado:** CERRADO — RECHAZADO
**Resultado:** V4 (F1: 0.9229) superó al MoE (F1: 0.9163)

## Contexto
Inspirados por la arquitectura Mixture of Experts (MoE) de modelos como Inkling 2 Mini, se dividió la telemetría en 3 expertos (Térmico, Eléctrico, Sistema) coordinados por un Director.

## Resultados
- Experto Térmico: F1 0.916
- Experto Eléctrico: F1 0.916
- Experto de Sistema: F1 0.000 (no logró predecir nada al ver solo el error actual)
- **MoE Combinado: F1 0.9163**

## Aprendizaje
La "visión de rayos X" del MLP V4 (que procesa las 6 features en una ventana de tiempo simultánea) supera la especialización ciega del MoE. Para la física del hardware, la interacción entre temperatura, voltaje y potencia es tan fuerte que dividir los datos hace perder la señal predictiva.

El sistema rechazó automáticamente el MoE, manteniendo el V4 en producción.
