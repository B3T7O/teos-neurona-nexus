# EXP-053 — Wallet monitor pasivo

**Fecha:** 2026-11-23
**Estado:** ACTIVO
**Autor:** TEOS Neurona Nexus

## Objetivo

Monitorear el balance de la dirección de payout
`bc1q20m7sy4ks42yt67m44t3dc6tun387v5z6lykxt` cada hora, vía API pública
de mempool.space, sin depender del dashboard de CKPool.

## Diseño

- Frecuencia: cada 3600s (1 hora).
- Fuente: `https://mempool.space/api/address/{addr}`
- Persistencia: `data/processed/wallet_state.json`
- Log: `logs/wallet_monitor.log`
- Alerta: log con prefijo `💰 CAMBIO DE BALANCE` cuando el saldo cambia.

## Por qué existe

En solo mining con 1.175 TH/s, la probabilidad de encontrar un bloque
es despreciable en una vida humana. Pero si el milagro ocurre, queremos
enterarnos en ≤1 hora, no en 1 mes.

## Aclaración sobre la dirección `bc1q28kkr5hk4gnqe3evma6runjrd2pvqyp8fpwfzu`

Esta dirección aparece en el **output 1** de los coinbase de CKPool
(comisión del 2%). **No es del usuario**, no se monitorea, no es
relevante para el balance. Es metadata del pool.

## Cómo arrancar/parar

```bash
# Arrancar
nohup python3 -u tools/wallet_monitor.py >> logs/wallet_monitor.log 2>&1 &

# Parar
pkill -f wallet_monitor.py

# Ver estado
tail -5 logs/wallet_monitor.log
