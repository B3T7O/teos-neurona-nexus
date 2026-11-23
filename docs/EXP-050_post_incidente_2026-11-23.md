# EXP-050 — Post-incidente: rechazo del MLP Lite y estabilización

**Fecha:** 2026-11-23
**Estado:** CERRADO
**Severidad:** Alta (pérdida de 9 días de aprendizaje del MLP)
**Causa raíz:** intervención manual sobre un modelo que el sistema ya había rechazado

## Resumen

El 2026-11-22 el sistema rechazó el MLP Lite (`improvement=-71.58%`
vs baseline persistence). El usuario, al ver una "fuga de datos" en los
pesos, intentó "arreglarlo" manualmente. Eso saturó los pesos
(`W1/W2 = ±5.0`) y dejó `X_std = 1e-08` en features 5-8 (constantes).
El modelo quedó irrecuperable sin reentrenar desde cero.

## Lo que el sistema hizo BIEN

- `mlp_lite_recovery_report.json` marcó `status: REJECTED` con evidencia.
- `original_weights_preserved: true` mantuvo los pesos previos.
- No hubo corrupción de datos de entrenamiento (`data/raw/` intacto).
- Ridge y Evolve siguieron operando sin verse afectados.

## Lo que falló

- No había un flag claro de "MLP desactivado" → el usuario creyó que
  debía "arreglarlo".
- Los pesos saturados no dispararon ninguna alarma temprana.
- No existía documentación del pipeline de rechazo.

## Cambios aplicados (2026-11-23)

1. `core/neurona_mlp_lite.py` → `MLP_ENABLED = False` (línea 14).
2. `data/processed/model_weights.json` → archivado en
   `backup/mlp_archive_20261123_075304/`.
3. `tools/overclock_watchdog.py` → reescrito con ventana móvil (v2).
4. Archivos basura en raíz (`on`, `tarts`, `tree -asp …`, etc.)
   → archivados en `backup/garbage_20261123_075332/`.

## Watchdog v2 — Qué cambió

| Antes | Ahora |
|---|---|
| `ERROR_LIMIT = 1.0` fijo | `ERROR_CRITICAL = 3.0` + ventana móvil 5 min |
| Lee `errorPercentage` instantáneo | Calcula delta de shares, promedia 10 lecturas |
| Piso `575 MHz` = freq actual → bucle `ALERT_SAFE` | Piso `525 MHz`, baja en pasos de 25 |
| Nunca bajaba | Baja 25 MHz si error sostenido > 3% |

## Reglas para no repetir

1. **Si el sistema dice REJECTED, se respeta.** No se toca el modelo.
2. **`MLP_ENABLED = False` es la primera línea a revisar** antes de
   depurar cualquier comportamiento raro del MLP.
3. **Backup antes de tocar** cualquier archivo en `data/processed/`.
4. **Documentar el experimento** en `docs/` antes de ejecutarlo.
5. **Un cambio por vez**, con `git commit` firmado, para poder revertir.

## Referencias

- `data/processed/shadow_learner_v2/mlp_lite_recovery_report.json`
- `backup/mlp_archive_20261123_075304/`
- `tools/overclock_watchdog.py` (v2, 2026-11-23)
