# EXP-051 — Shadow Learner V3: ambas opciones rechazadas honestamente

**Fecha:** 2026-11-23
**Estado:** CERRADO — NEGATIVO
**Severidad:** N/A (el sistema rechazó los modelos, no hubo daño)
**Causa:** features insuficientes para predecir errores/hashrate con antelación

## Objetivo

Tras el rechazo del MLP Lite (EXP-049) y el incidente (EXP-050),
se intentó reentrenar con dos enfoques nuevos:

- **Opción 1:** clasificador binario "¿habrá error > 1% en los próximos 5 samples?"
- **Opción 2:** MLP residual que predice delta de hashrate (no valor absoluto)

## Metodología

- Split **temporal** 70/15/15 (no aleatorio, evita leakage)
- **v3**: evaluación naïve (baseline = 0.05) → falso ACCEPTED
- **v3.1**: evaluación honesta
  * Opción 1 entrena SOLO con samples pre-error (error < 1%)
  * Compara contra **null model** (mayoría trivial)
  * Rechaza si `f1_test <= null_f1_test + 0.05`

## Resultados (v3.1 honesta)


## Conclusiones

1. **Los errores no son predecibles** con features instantáneas
   (temp, VRM, errorPercentage, RSSI, power, frequency).
2. **El delta de hashrate es esencialmente ruido** (std=156 GH/s,
   mean=0.002). Ningún modelo lineal o MLP pequeño lo supera.
3. **El baseline persistence es muy fuerte** para series de tiempo
   con mean-reversion. No es trivial de superar.
4. **93% del test pre-error fue seguido de error** en los próximos
   5 samples → el período reciente fue inestable. Los errores son
   eventos correlacionados, no independientes.

## Aprendizajes clave

- **El sistema rechaza honestamente cuando no hay señal.** Esto es
  una fortaleza, no una debilidad. Mejor no desplegar nada que
  desplegar un modelo que empeora las decisiones.
- **"Datos crudos" ≠ "datos útiles".** 43k samples no bastan si
  las features no contienen información predictiva.
- **Antes de intentar un cuarto modelo MLP, considerar:**
  * ¿Hay features nuevas que aportar? (e.g., difficulty del pool,
    tiempo desde último share, historial de cambios de freq)
  * ¿O el problema es fundamentalmente no-predecible y hay que
    aceptar el watchdog reactivo (que ya funciona)?

## Cambios aplicados

- `core/shadow_learner_v2/train_v3.py` → descartado (falso ACCEPTED)
- `core/shadow_learner_v2/train_v3_1.py` → conservado (evaluación honesta)
- `data/processed/shadow_learner_v3/training_report_v3_1.json` → evidencia

## Recomendación

**No intentar más variantes del MLP.** El sistema actual
(Ridge + Evolve + Watchdog v2 reactivo) es suficiente. El MLP queda
permanentemente desactivado (`MLP_ENABLED = False`).

Si en el futuro se quiere retomar:
- Primero añadir features exógenas (pool difficulty, blockchain state)
- Segundo, split temporal más fino (walk-forward validation)
- Tercero, comparar siempre contra null y persistence, no contra 0.05

## Referencias

- `docs/EXP-049_mlp_rejection.md` (implícito en commit anterior)
- `docs/EXP-050_post_incidente_2026-11-23.md`
- `data/processed/shadow_learner_v3/training_report_v3_1.json`
- `core/shadow_learner_v2/train_v3_1.py`
