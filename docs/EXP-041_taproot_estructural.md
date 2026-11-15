# EXP-041: Auditoría Taproot Estructural (P2TR)

**Fecha:** 2026-11-15
**Objetivo:** Crear un Scheduler independiente para auditar transacciones Taproot sin afectar la auditoría principal (P2PKH).

## Arquitectura
- **Script aislado:** `tools/crypto_audit_taproot.py`
- **Entorno virtual:** `.venv_taproot` con `btclib` (instalado con `--user` en venv para evitar conflictos PEP 668).
- **Scheduler systemd:** `teos-taproot-audit.timer` (cada 6 horas).
- **Reporte:** `data/audit/taproot_audit.json`

## Resultados de la Prueba
- **Bloque auditado:** #975889
- **Transacciones totales:** 7,415
- **Transacciones Taproot (P2TR) encontradas:** 22
- **Estado:** `structural_ok`

## Diferencia con la Auditoría Principal
La auditoría principal (`crypto_audit.py`) verifica P2PKH y el Master Merkle Root.
La auditoría Taproot es **estructural** (verifica el formato OP_1 <32 bytes>).
La verificación criptográfica completa (BIP341) queda pendiente para una próxima sesión.

## Conclusión
El sistema ahora detecta transacciones Taproot de forma aislada y segura, sin riesgo de romper la auditoría principal.
