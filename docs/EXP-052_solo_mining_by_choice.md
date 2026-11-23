# EXP-052 — Solo mining por decisión consciente

**Fecha:** 2026-11-23
**Estado:** CERRADO — DECISIÓN
**Decisor:** Luis Alberto Siguencia Andrade (B3T7O)

## Contexto

El 2026-11-23 se completó la estabilización del sistema (EXP-050, EXP-051).
Se evaluaron tres pools compartidos (Public Pool, Ocean, Braiins) frente a
la situación actual de solo mining (`solo.ckpool.org`).

## Análisis técnico

| Modo | Hashrate efectivo | Tiempo a primer sat | Probabilidad bloque |
|---|---|---|---|
| Solo (`solo.ckpool.org`) | 1.175 TH/s | Infinito (~9.500 años) | 1/5e9 por bloque |
| Public Pool | 1.175 TH/s | ~1-2 semanas | Proporcional al hash |
| Braiins | 1.175 TH/s | ~285 días | Proporcional al hash |

Con 1.175 TH/s y la red a ~600 EH/s, la probabilidad de encontrar
un bloque en solitario es estadísticamente despreciable en una vida humana.

## Decisión

**Continuar en solo mining (`solo.ckpool.org`) por convicción personal.**

Esta es una decisión consciente, no técnica. El sistema está
técnicamente preparado para cualquier modo. La wallet
`bc1q20m7sy4ks42yt67m44t3dc6tun387v5z6lykxt` es la misma en todos los modos.

## Aclaración sobre la dirección `bc1q28kkr...`

Aparece en el output 1 del coinbase de CKPool. Es la comisión del pool (2%),
NO es del usuario. Solo aparece en `data/processed/axeos_logs.json` como
metadata del bloque. La wallet del usuario (`stratumUser` del Bitaxe) es
`bc1q20m7sy4ks42yt67m44t3dc6tun387v5z6lykxt`.

## Compromisos técnicos derivados

1. **Backup de la seed de la wallet** — si se encuentra un bloque,
   perder la seed equivale a perder ~3.2 BTC (~$300k).
2. **Monitoreo pasivo** vía `tools/wallet_monitor.py` (ver EXP-053).
3. **No se toca el watchdog ni el pipeline de seguridad.**
4. **Reevaluación abierta:** el cambio a pool es 1 línea en
   `core/lite_proxy.py` (UPSTREAM_HOST + UPSTREAM_PORT).

## Referencias

- `docs/EXP-050_post_incidente_2026-11-23.md`
- `docs/EXP-051_shadow_learner_v3_rechazado.md`
- `docs/EXP-053_wallet_monitor.md`
- `core/lite_proxy.py` (líneas 10-11)
