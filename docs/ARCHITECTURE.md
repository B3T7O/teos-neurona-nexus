# TEOS Neurona Nexus — Arquitectura

## Qué es
Prototipo funcional de capa AI para minería Bitcoin con Bitaxe Gamma 602.
Predice hashrate, detecta anomalías, y (cuando puede) ajusta frecuencia/voltaje.

## Servicios (systemd, el mecanismo PRINCIPAL)
| Servicio | Función | Estado esperado |
|---|---|---|
| `teos-neurona-api.service` | Dashboard web (puerto 8765) | ✅ Running |
| `teos-neurona-scheduler.service` | Orquesta: analyze + learning_loop + ridge + control + meta_learners cada 5min | ✅ Running |
| `teos-nexus-collector.service` | Captura Bitaxe cada 60s → `bitaxe_samples.marked.jsonl` | ✅ Running |

## Mecanismos de arranque secundarios (red de seguridad)
- **`start_teos.sh`**: script manual que mata TODO y arranca 4 procesos con setsid.
- **`.bashrc` línea 130-131`**: si abres terminal y no detecta scheduler, ejecuta `start_teos.sh`.
- **RIESGO**: estos dos compiten con systemd y pueden crear duplicados. No tocar sin entender.

## Estructura de `core/` (30 módulos)
### Captura
- `collector.py` → Bitaxe API → `bitaxe_samples.marked.jsonl`
- `sample_quality.py` → clasifica cada sample (ok/idle/corrupt_spike/bad_zero)

### Aprendizaje (corriendo en paralelo, shadow mode)
- `learning_loop.py` (v1)
- `learning_loop_v2.py` (v2, principal)
- `neurona_ridge_live.py` (Ridge)
- `meta_learner_lite.py` + `best_of_both.py` + `ensemble_learner.py` (meta)
- `online_error_learner.py` + `contextual_error_learner.py` + `contextual_adaptation.py` (aprendices secundarios)

### Guardian / auditoría
- `guardian.py` → watchdog que puede pausar learning
- `audit_reader.py` → lee auditoría para dashboard
- `reference_guard.py` → protege baseline
- `validation.py` → valida esquema de samples

### Control
- `bitaxe_control.py` → ajusta frecuencia/voltaje (solo reduce, nunca sube)

## Estructura de `tools/` (21 scripts de diagnóstico)
Scripts one-shot para análisis, no producción. Los nuevos de hoy:
- `anomaly_detector.py` → detector de anomalías
- `temp_predictor_control.py` → predicción térmica
- `robust_baselines.py`, `shares_coherence.py`, `estimaciones.py`, etc.

## Archivos de datos
| Path | Contenido |
|---|---|
| `data/raw/bitaxe_samples.marked.jsonl` | Samples del Bitaxe con `quality` |
| `data/raw/bitaxe_samples.jsonl` | Legacy (no se usa, migramos) |
| `data/processed/learning_outcomes_v2.jsonl` | Predicciones + errores |
| `data/processed/anomaly_model.json` | Modelo detector anomalías |
| `data/processed/temp_model.json` | Modelo térmico |
| `data/guardian/PAUSE_LEARNING` | Si existe, pausa learning_loop |

## Convención de trabajo
- Un solo scheduler debe correr. Si hay dos → RAM + CPU consumidas.
- Un solo collector debe correr. Si hay dos → ambos escriben al mismo archivo.
- Un solo web server. Si hay dos → el segundo falla en bucle.
- El audit exige frescura <300s en `marked.jsonl`.

## Regla de oro
**Si systemd tiene los servicios enabled, NO usar `start_teos.sh`**.
El script es solo para arranque manual cuando systemd NO está configurado.
