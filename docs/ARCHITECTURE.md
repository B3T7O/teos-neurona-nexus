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


---

## Procesos autonomos (v1.1, 2026-11-11)

### tools/auto_healer.py
- Funcion: reinicia servicios systemd caidos cada 5 minutos.
- Verifica: 3 servicios (collector, scheduler, api), Bitaxe en 192.168.18.45,
  y que el collector escriba muestras frescas (<300s).
- Modo por defecto: simulacion (solo reporta).
- Modo real: --execute (reinicia via systemctl restart).
- Log: data/healer/healer_log.jsonl.
- Estado: corriendo con --execute desde 2026-11-11.

### tools/evolve_runner.py
- Funcion: ejecuta core/evolve_lab.py (algoritmo genetico) cada 6 horas.
- Encuentra pesos optimos de los 5 metodos de prediccion.
- Guarda campeon en data/processed/evolve_champion.json.
- Modo real: --execute.
- Log: data/evolve/evolve_log.jsonl.
- Estado: corriendo con --execute desde 2026-11-11.

### core/evolution_history.py
- Funcion: historial central de evoluciones de todos los learners.
- API:
  - record(learner, kind, detail, extra=None)
  - read_all(limit=200)
  - summarize_by_learner()
- Log: data/evolve/history.jsonl (append-only).
- Quien registra:
  - core/scheduler.py registra 7 learners cada ciclo:
    learning_loop_v2, ridge_live, bitaxe_control, prospective_eval,
    meta_learner_lite, best_of_both, ensemble_learner.
  - tools/evolve_runner.py registra evolve_lab.
- Herramientas:
  - tools/show_evolution_history.py (CLI)
  - tools/backfill_evolution_history.py (rellenar historico)

## Flujo del sistema

    Bitaxe --HTTP--> collector --> data/raw/bitaxe_samples.marked.jsonl
                                          |
                                          v
                              scheduler (cada 5 min)
                                          |
              +----------+----------+-----+-----+----------+
              |          |          |           |          |
              v          v          v           v          v
        learning   ridge_live  meta_learner  ensemble  best_of_both
              |          |          |           |          |
              +----------+----------+-----+-----+----------+
                                          |
                                          v
                            core/evolution_history.py
                                          |
                                          v
                            data/evolve/history.jsonl

    auto_healer (5 min)  --> vigila 3 servicios + Bitaxe
    evolve_runner (6 h)  --> evolve_lab.py --> evolve_champion.json
