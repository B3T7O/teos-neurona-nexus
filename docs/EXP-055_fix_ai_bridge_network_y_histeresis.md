# EXP-055 — Fix de red en AI Bridge y protección contra bucles de frecuencia

**Fecha:** 2026-11-25
**Estado:** CERRADO
**Severidad:** Alta (el AI Bridge estaba ciego por un timeout y una IP mal configurada)

## Problemas detectados
1. **Timeout prematuro:** El script esperaba solo 5s a la API del Bitaxe. Bajo carga, el ESP32 tardaba más y el script fallaba.
2. **IP por defecto incorrecta:** `BITAXE_IP` apuntaba a `192.168.1.100` (la IP de ejemplo), no a `192.168.18.45`.
3. **Guerra de frecuencias:** El AI Bridge subía a 580 MHz, el Watchdog bajaba a 555 MHz por error, y volvían a empezar (causando reinicios del ASIC).

## Soluciones aplicadas
1. `timeout=5` cambiado a `timeout=15` en `core/bitaxe_control.py`.
2. `BITAXE_IP` corregida a `192.168.18.45`.
3. **Histéresis añadida:** El AI Bridge ahora lee `logs/overclock_watchdog.log`. Si el Watchdog hizo un ROLLBACK en los últimos 45 minutos, el AI Bridge **NO** intentará subir la frecuencia.
4. **Techo de frecuencia:** El AI Bridge no subirá más de 575 MHz, incluso si la temperatura es perfecta.
5. **Umbral de subida más estricto:** Solo intenta subir si el error instantáneo es menor a 0.3% (antes 0.8%).

## Pendiente para el futuro
- El archivo `temp_model.json` (modelo predictivo térmico) no existe. El AI Bridge corre en modo reactivo. Se puede reentrenar en el futuro.
