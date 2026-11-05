# CIERRE DEL PROYECTO — TEOS NEURONA NEXUS
**Fecha:** 2026-11-05
**Estado:** TERMINADO Y OPERATIVO

---

## Qué se construyó

Un núcleo ligero de observación, análisis, predicción y decisión
sobre un minero Bitaxe Gamma 602, ejecutándose de forma continua
en un HP con WSL2.

## Componentes operativos

| Componente | Función | Servicio systemd |
|---|---|---|
| core.collector | Lee API del Bitaxe cada ~60s | teos-colector.service |
| core.scheduler | Orquesta ciclos (ridge, control, evaluación) | teos-scheduler.service |
| web/server.py | Interfaz web en :8765 | teos-web.service |
| core.learning_loop_v2 | Predicción + evaluación post-hoc | teos-neurona-learning-v2.service |

## Datos producidos (a la fecha de cierre)

- 18.608 muestras crudas del Bitaxe (data/raw/bitaxe_samples.jsonl)
- 70.101 evaluaciones de predicción (data/processed/learning_outcomes_v2.jsonl)
- 14.075 predicciones registradas (data/processed/ridge_live_predictions.jsonl)
- 3.533 análisis históricos (data/processed/analysis_history.jsonl)
- Total: 102.784 líneas de datos verificables

## Calidad de la predicción

Error porcentual absoluto (APE) medido: ~1.5% sobre horizonte
de una muestra siguiente. Documentado en learning_outcomes_v2.

## Política de seguridad del hardware

- Nunca se aumenta frecuencia o voltaje automáticamente.
- Solo se reduce si hay degradación o temperatura alta.
- Toda escritura al ASIC se verifica con lectura posterior.
- "Sin cambios" es un resultado válido y esperado.
- Estado actual del Bitaxe: 525 MHz, 1150 mV, 60°C, ~1080 GH/s.

## Persistencia

Los 3 servicios principales sobreviven a reinicios del sistema
(loginctl enable-linger + systemd --user). Auto-reinicio ante fallos
(Restart=always, RestartSec=10).

## Reproducibilidad

Ver RUNBOOK.md para arranque, verificación, parada y logs.

## Criterio de "trabajo real" cumplido

1. Observación fiable (datos crudos sin duplicados).
2. Predicción medible (APE ~1.5%, error < 20 GH/s).
3. Decisión auditada (bitaxe_control.jsonl con razón explícita).
4. Evaluación del resultado (outcome con error medido).

El sistema produce estos 4 outputs de forma continua desde
el 2026-11-01.

## Historia auditable

- e23b8b3 snapshot inicial (código fuente, docs, tests)
- 3029494 CIERRE: RUNBOOK + servicios systemd persistentes

## Estado final

PROYECTO CERRADO. Listo para operación continua.
