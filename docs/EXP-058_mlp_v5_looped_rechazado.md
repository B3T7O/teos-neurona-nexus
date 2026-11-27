# EXP-058 — MLP V5 Looped (Inspiración Inkling) rechazado

**Fecha:** 2026-11-27
**Estado:** CERRADO — RECHAZADO
**Resultado:** V4 (F1: 0.9229) superó a V5 (F1: 0.9155)

## Contexto
Inspirados por la arquitectura "Looped Transformer" de Inkling 2 Mini, se intentó añadir un bucle de pensamiento a la capa oculta del MLP V4.

## Resultado
El modelo V5 obtuvo un F1 de 0.9155, ligeramente inferior al 0.9229 del V4. El sistema de validación (MIN_IMPROVEMENT = 0.005) lo rechazó automáticamente, conservando el modelo V4 en producción.

## Aprendizaje
Para redes muy pequeñas (12 neuronas ocultas) con datos ruidosos, la iteración de capas puede causar congelación del gradiente (vanishing gradient). La simplicidad del V4 es óptima para la escala actual del hardware.

El sistema demostró ser inmune a malas actualizaciones. El `mlp_evolver.py` seguirá buscando mejoras, pero siempre con red de seguridad.
