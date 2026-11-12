# Experimentos TEOS Neurona Nexus

## EXP-001 — Baseline de referencia
- **Fecha**: 2026-10-21
- **Hipótesis**: medias móviles simples (10m, 1h) predicen hashrate a 1 minuto.
- **Resultado**: `referencia_1h` y `referencia_10m` son competitivas (≈2.27% APE media).
- **Conclusión**: difíciles de batir. Cualquier modelo nuevo debe superarlas o
  justificar su complejidad con otra métrica (p95, robustez, etc).

## EXP-002 — Feature "bloques hasta próximo ajuste de dificultad"
- **Fecha**: 2026-11-10
- **Hipótesis**: el error de predicción varía según la fase del ciclo de 2016 bloques.
- **Método**: cuartiles + validación temporal 70/30 + intersección de timestamps
  + ventana común desde la primera predicción de `adaptativo_neurona`.
- **Resultado**: `referencia_1h` gana los 4 bins. `adaptativo_neurona` nunca gana
  (2.281–2.319% vs 2.242–2.303% de referencia_1h).
- **Conclusión**: ❌ **DESCARTADA.** No aporta información.

## EXP-003 — Feature "días hasta el próximo halving"
- **Fecha**: 2026-11-10
- **Hipótesis**: el error varía según proximidad al halving.
- **Resultado**: span de la feature en los datos = 21.5 días. Degenerada.
- **Conclusión**: ❌ **DESCARTADA.** Requiere ≥4 años de histórico para testear.

## EXP-004 — Diagnóstico de outliers y calidad de datos
- **Fecha**: 2026-11-10
- **Hallazgo**: 64 outliers (APE > 50%) concentrados el 2026-10-22 22:34–23:26.
- **Causa raíz**: 1 sample corrupto del Bitaxe (`hashRate=81806 GH/s` a 525 MHz/20 W,
  físicamente imposible). Contaminó ventanas móviles; `referencia_1h` lo arrastró 60 min.
- **Acciones**:
  - `tools/clean_invalid_samples.py` → `bitaxe_samples.clean.jsonl` (sin spikes)
  - `tools/mark_sample_quality.py` → `bitaxe_samples.marked.jsonl` (con campo `quality`)
- **Conclusión**: ✅ **Dataset saneado.** El spike no afecta a los análisis con cutoff
  ≥ 2026-10-23 05:10 (ventana común). `adaptativo_neurona` parecía robusto porque
  empezó a predecir *después* del spike, no por diseño.

## EXP-005 — Comparación honesta en ventana común
- **Fecha**: 2026-11-10
- **Método**: `tools/analyze_cycle_events.py v4`, cutoff 2026-10-23 05:10.
- **Resultado**:
  | Método | media | mediana |
  |---|---|---|
  | referencia_10m | 2.27% | 1.91% |
  | referencia_1h | 2.27% | 1.91% |
  | adaptativo_neurona | 2.30% | 1.93% |
  | media_ultimas_5 | 2.48% | 2.06% |
  | ultimo_hashrate | 3.21% | 2.72% |
- **Conclusión**: `adaptativo_neurona` **no supera** a los baselines simples en
  ventana limpia. Los baselines de referencia son el objetivo a batir.

## Próximos experimentos (no urgentes)
- Features de micro-entorno: volatilidad rolling, momentum, hora del día,
  temperatura, ratio short/long term.
- Controlador predictivo (bajar frecuencia antes de que suba temperatura).
- Baselines robustos (pasar `filter_contextual_anomalies` a todos por igual).


## EXP-006 — Detector de anomalías (Opción C)
- **Fecha**: 2026-11-10
- **Hipótesis**: es posible detectar anomalías operativas (temp alta, wifi débil,
  hashrate caído) con z-score rolling sobre el estado normal del hardware.
- **Método**: train 70% / test 30% + z-score rolling (ventana 5, umbral 3σ)
  + **piso de desviación absoluta** por feature para evitar alertas en features
  casi constantes (errorPercentage tenía std=0.02 → generaba 6713 falsas alarmas).
- **Resultado**:
  - Falsos positivos en test real: 17/8179 = **0.21%**
  - Test sintético (3 anomalías inyectadas): **detecta las 3**
    - temp +20°C → 9 alertas (z hasta +99)
    - wifi -95 dBm → 22 alertas (z hasta -5.75)
    - hashrate/2 → 9 alertas (z hasta -11.25)
- **Artefacto**: `data/processed/anomaly_model.json` (mean/std/abs_min por feature).
- **Conclusión**: ✅ **Detector operativo.** Listo para integrarse como guardián
  en `learning_loop_v2.py`. Evento real encontrado: caída de WiFi 2026-11-08 15:10.

## EXP-007 — Predictor de temperatura + control térmico (Opción D)
- **Fecha**: 2026-11-10
- **Hipótesis**: se puede predecir `temp(t+1)` mejor que "copiar temp(t)"
  y usar esa predicción para control térmico anticipado.
- **Método**: Ridge con features térmicas (temp_now, delta5, delta10, vrTemp,
  power, voltage, freq, hashrate, hora, día semana).
- **Resultado**:
  - baseline (copia) MAE = 0.114°C, p95 = 0.250°C
  - modelo_ridge  MAE = 0.091°C, p95 = 0.230°C
  - **Δ = +0.023°C mejor** (mejora técnica, pequeña en magnitud)
  - Simulación de control: 0 alertas reactivas y 0 predictivas (temp nunca >65°C)
  - Coeficientes casi cero → el modelo se reduce a "copia con ajuste mínimo"
- **Causa de la mejora pequeña**: inercia térmica enorme (temp ~60°C, std 0.12°C).
  `temp(t+1) ≈ temp(t)` ya es casi perfecto.
- **Artefacto**: `data/processed/temp_model.json`.
- **Conclusión**: ✅ modelo funcional pero **sin urgencia operativa hoy**.
  Guardado como componente de reserva. Se activará cuando:
  - la temperatura ambiente suba (verano),
  - se aumente frecuencia,
  - o el firmware cambie el perfil térmico.
  **Limitación honesta**: sin eventos cerca del umbral, el control no está
  validado en producción. Solo la predicción lo está.

## EXP-008 — Features de micro-entorno (descartadas)
- **Fecha**: 2026-11-10
- **Hipótesis**: temp, hora, momentum, volatilidad, ratio ayudan a predecir hashrate.
- **Resultado**: modelo_ridge (2.26% APE) ≈ h1h baseline (2.25% APE). Sin mejora.
- **Conclusión**: ❌ **DESCARTADAS.** Las features no aportan sobre `h1h` a 1 minuto.

## EXP-009 — Baselines robustos (mediana, trimmed mean)
- **Fecha**: 2026-11-10
- **Hipótesis**: mediana o trimmed mean 10% superan a media simple en referencia_10m/1h.
- **Método**: comparar tres estadísticos en ventanas de 10m y 60m, sobre samples `quality=ok`.
- **Resultado**:
  - Ventana 10m: media **2.37%**, mediana 2.43%, trimmed10 2.38% → **gana media**
  - Ventana 60m: media **2.28%**, mediana 2.28%, trimmed10 2.28% → **empate**
- **Conclusión**: ✅ **Sin cambios necesarios.** Al filtrar spikes, la media simple ya no se contamina. Mediana/trimmed solo aportan si hay outliers, y ya no los hay en `quality=ok`. Los baselines actuales son correctos.

## EXP-010 — Filtro en ingesta (collector)
- **Fecha**: 2026-11-10
- **Hipótesis**: clasificar el sample en la captura previene contaminación futura sin perder trazabilidad.
- **Método**: `core/collector.py` llama a `core.sample_quality.classify()` antes de escribir. Los `corrupt_spike` se escriben igualmente (trazabilidad) pero logean advertencia.
- **Artefacto**: `core/sample_quality.py` (módulo reutilizable).
- **Conclusión**: ✅ **Filtro aplicado en origen.** Los samples entran ya clasificados con `quality`. Cualquier análisis posterior puede confiar en `quality=ok` sin pasos extra.

## EXP-011 — Estimaciones temporales y económicas
- **Fecha**: 2026-11-10
- **Método**: `tools/estimaciones.py` calcula desde el último sample:
  bloques al ajuste, al halving, hashrate de red estimado, probabilidad de bloque solo.
- **Resultado** (último sample, altura 975357):
  - Próximo ajuste: 387 bloques → **2.69 días**
  - Próximo halving: 74,643 bloques → **518 días (1.42 años)**
  - Hashrate de red: **1,062,034 PH/s ≈ 1062 EH/s**
  - Probabilidad de bloque solo: 1.01e-9 por bloque → **18,800 años esperados**
  - Shares esperados: **900/hora** (pool diff 1000)
- **Conclusión**: estimaciones coherentes con la realidad de la red en 2026.
  Confirman matemáticamente la necesidad de minar en pool con un Bitaxe de 1 TH/s.

## EXP-012 — Coherencia de shares (test de salud pool/miner)
- **Fecha**: 2026-11-10
- **Método**: `tools/shares_coherence.py` compara `sharesAccepted` reales (delta por
  intervalo) vs esperados (`hashRate × dt / (poolDiff × 2^32)`).
- **Resultado**:
  - Ratio real/esperado (mediana): **0.982** ✅ (ideal = 1.000)
  - Media: 1.029, P05/P95: 0.507 / 1.468 (rango esperado por aleatoriedad)
  - Tasa de rechazo: mediana **0.000%**, media **0.146%** ✅ (<5% crítico)
  - Reinicios detectados: 17 en 22 días (revisable, no urgente)
  - Intervalos con d_sa=0: normales (suerte del pool en intervalos cortos)
- **Conclusión**: ✅ **Pool y miner sanos.** Rendimiento real coincide con el esperado
  matemáticamente. Rechazo prácticamente nulo. Único apunte operativo: 17 reinicios
  en 22 días, revisar si son automáticos o no.

## EXP-013 — Backfill de outcomes del ridge_live
- **Fecha**: 2026-11-11
- **Síntoma**: audit reportaba `[FAIL] Cobertura eval (ridge_live): 58.4% (14304/24479)`
- **Causa raíz**: el evaluador en vivo (`continuous_learning_evaluator.py` /
  `learning_loop_v2.py`) solo procesa las predicciones más recientes del ridge,
  no el histórico completo. Cada ciclo se acumulaban huérfanas.
- **Método**: `tools/backfill_ridge_outcomes.py` recorre predicciones sin outcome,
  empareja con la primera muestra real posterior (vía `bisect_right` sobre timestamps),
  y calcula el outcome (error, APE, etc.). Idempotente: no duplica.
- **Resultado**:
  - Huérfanas procesadas: 10,171
  - Outcomes escritos: 10,171 (0 sin match)
  - Total outcomes: 78,565 → 88,736
  - **Cobertura: 58.4% → 100.0%**
  - Audit: `CRITICO (1 fallo)` → `ADVERTENCIA (0 fallos)`
- **Conclusión**: ✅ **Fallo resuelto.** El evaluador en vivo sigue funcionando igual
  (no se tocó). Este fix solo rellena el histórico. Si en el futuro vuelven a
  acumularse huérfanas, es señal de que el evaluador necesita revisarse.

## EXP-014 — Evolve Lab v2: fitness alternativos
- **Fecha**: 2026-11-11
- **Hipótesis**: el estancamiento del GA v1 se debía a un fitness demasiado simple
  (solo APE media). Probar 3 fitness alternativos para escapar del óptimo local.
- **Modos probados**:
  - `multi_objective`: 0.6·mean + 0.4·p95 (penalizar cola alta)
  - `temporal`: solo últimos 7 días (adaptarse a datos recientes)
  - `regime_low` / `regime_high`: split por volatilidad (champion por régimen)
- **Método**: 4 GAs independientes (60 individuos × 40 generaciones cada uno),
  evaluados sobre **los mismos 5000 targets** recientes.
- **Resultado** (mean / p95 / max):
  | Champion | mean | p95 | max |
  |---|---|---|---|
  | v1_original | 2.251% | 5.504% | 12.24% |
  | multi_obj | 2.256% | **5.466%** | 12.12% |
  | regime_high | 2.256% | 5.478% | **12.10%** |
  | regime_low | 2.251% | 5.504% | 12.30% |
  | temporal | 2.251% | 5.480% | 12.21% |
- **Conclusión**: ❌ **Los 3 modos nuevos no superan al v1.** Variaciones de
  décimas de punto = ruido. El "estancamiento" no es un problema de fitness:
  es que el óptimo real es **trivial** (referencia_1h con 82% de peso).
  Cualquier combinación que lo respete da casi lo mismo. El GA no puede
  escapar de ese óptimo porque **no hay otro mejor**.
- **Artefactos**: `data/processed/evolve_champion_v2_{multi_obj,temporal,regime_low,regime_high}.json`
  (documentación del experimento, NO usados en producción).
- **Lección**: antes de optimizar el optimizador, verificar que el problema
  tiene margen de mejora. Aquí no lo tiene.


## EXP-014 — Evolve Lab v2: fitness alternativos
- **Fecha**: 2026-11-11
- **Hipotesis**: el estancamiento del GA v1 se debia a un fitness demasiado simple
  (solo APE media). Probar 3 fitness alternativos para escapar del optimo local.
- **Modos probados**:
  - multi_objective: 0.6*mean + 0.4*p95 (penalizar cola alta)
  - temporal: solo ultimos 7 dias (adaptarse a datos recientes)
  - regime_low / regime_high: split por volatilidad (champion por regimen)
- **Metodo**: 4 GAs independientes (60 individuos x 40 generaciones cada uno),
  evaluados sobre los mismos 5000 targets recientes.
- **Resultado** (mean / p95 / max):
  | Champion | mean | p95 | max |
  |---|---|---|---|
  | v1_original | 2.251% | 5.504% | 12.24% |
  | multi_obj | 2.256% | 5.466% | 12.12% |
  | regime_high | 2.256% | 5.478% | 12.10% |
  | regime_low | 2.251% | 5.504% | 12.30% |
  | temporal | 2.251% | 5.480% | 12.21% |
- **Conclusion**: Los 3 modos nuevos NO superan al v1. Variaciones de decimas
  de punto = ruido. El estancamiento no es un problema de fitness: el optimo
  real es trivial (referencia_1h con 82% de peso). Cualquier combinacion que
  lo respete da casi lo mismo.
- **Artefactos**: data/processed/evolve_champion_v2_*.json (documentacion, NO en produccion)
- **Leccion**: antes de optimizar el optimizador, verificar que el problema
  tiene margen de mejora. Aqui no lo tiene.


## EXP-015 — Control termico predictivo
- **Fecha**: 2026-11-11
- **Hipotesis**: usar prediccion de temp(t+1) para bajar frecuencia ANTES de
  que la temperatura cruce el umbral reactivo (70C), reduciendo riesgo termico.
- **Metodo**: bitaxe_control.py extendido con flag --predictive (default OFF).
  Cuando esta activo:
  - Carga temp_model.json (MAE 0.091C)
  - Lee ultimas 10 muestras, construye features, predice temp(t+1)
  - Si temp_pred >= 68C (margen 2C) -> baja frecuencia
  - Regla de oro intacta: NUNCA sube frecuencia/voltaje automaticamente
- **Tests**:
  - Sin --predictive: comportamiento actual intacto (predictive_mode=false)
  - Con --predictive real: predijo 60.029C, sin cambios (temp estable)
  - Forzado 69.5C: dispara reduccion de frecuencia correctamente
  - Forzado 62.0C: no actua, sin falsas alarmas
- **Estado**: implementado y testeado. NO activado en produccion por defecto.
  - Para activar manualmente: python3 -m core.bitaxe_control --predictive --apply
  - Para activar en systemd: editar ExecStart del servicio
- **Limitacion conocida**: con temp estable a 60C, el predictivo se comporta
  igual que el reactivo (porque temp(t+1) ~= temp(t)). Su valor aparece cuando
  la temperatura empiece a subir (verano, cambio de frecuencia, mas carga).
- **Conclusion**: disponible como red de seguridad. No urgente activarlo hoy.


## EXP-016 — Ventanas de referencia (10m / 30m / 60m / 120m)
- **Fecha**: 2026-11-11
- **Hipotesis**: una ventana mas corta (30m) podria mejorar la referencia
  al adaptarse mas rapido a cambios recientes.
- **Metodo**: calcular media movil de 10, 30, 60, 120 min sobre los mismos
  samples, evaluar APE contra el siguiente valor real.
- **Resultado**:
  | Ventana | mean | median | p95 |
  |---|---|---|---|
  | 10m | 2.353% | 2.004% | 5.669% |
  | 30m | 2.300% | 1.982% | 5.545% |
  | 60m | 2.282% | 1.962% | 5.514% |
  | 120m | 2.275% | 1.959% | 5.467% |
- **Conclusion**: La hipotesis era incorrecta. Ventanas mas largas ganan porque
  el hashrate es muy estable y promediar mas tiempo cancela mas ruido del pool.
  La diferencia 60m vs 120m (0.007pp) es ruido, no mejora real. 120m tarda 2h
  en reaccionar a cambios. **60m se mantiene como el equilibrio optimo.**
- **Leccion**: en hardware estable, la reactividad no ayuda. El ruido se combate
  con promediado, no con velocidad de respuesta.


## EXP-017 — Crypto Audit Autónomo
- **Fecha**: 2026-11-11
- **Hipotesis**: integrar la verificacion criptografica de Bitcoin (Merkle Root y ECDSA) 
  en el scheduler para asegurar la integridad de la base de datos local y de la red.
- **Implementacion**: 
  - `tools/crypto_audit.py`: descarga el ultimo bloque de Bitcoin, verifica su firma 
    ECDSA y calcula el Merkle Root de los 89,841 outcomes locales.
  - Integrado en `core/scheduler.py` para ejecutarse cada 5 minutos.
- **Resultado**: 
  - El scheduler reporta `crypto_audit: ok` en el historial central cada 5 minutos.
  - Merkle Root local: 22c491f5bc13f63caad53b289a40abfd...
  - El bloque actual de Bitcoin (#975,490) tiene firma ECDSA valida.
- **Conclusion**: ✅ TEOS ahora es un auditor criptografico autonomo. 
  Garantiza que los datos de entrenamiento no han sido alterados y que el nodo 
  tiene conexion con la red Bitcoin real.


## EXP-018 — Blindaje de Datos contra Apagones (Critical Guardian)
- **Fecha**: 2026-11-11
- **Hipotesis**: proteger los datos críticos de entrenamiento (89k+ outcomes) contra
  corrupcion por cortes de energia electrica repentinos.
- **Implementacion**: 
  - `tools/critical_guardian.py`: crea un backup rotativo (max 5) cada vez que se ejecuta.
  - Valida la integridad de archivos JSON (objetos) y JSONL (lineas).
  - Restaura automaticamente el backup mas reciente si detecta corrupcion.
  - Integrado en `core/scheduler.py` (backup cada 5 min).
  - Integrado en `~/.bashrc` (restauracion automatica al encender la PC).
- **Resultado**: 
  - Primer backup manual: `backup_20261111_191245`.
  - El scheduler registrara `critical_backup: ok` en el historial.
- **Conclusion**: ✅ El sistema ahora es resiliente a cortes de luz. En el peor
  de los casos, se pierden maximo 5 minutos de datos, no toda la base historica.


## EXP-019 — Block Explorer (Nonce, Merkle y ECDSA en vivo)
- **Fecha**: 2026-11-11
- **Hipotesis**: integrar un explorador de bloques de Bitcoin en el scheduler
  para extraer datos criptograficos en tiempo real y verificar la autenticidad de la red.
- **Implementacion**: 
  - `tools/block_explorer.py`: descarga el ultimo bloque, extrae Nonce, Merkle Root,
    cuenta transacciones y verifica una firma ECDSA (soporta Legacy y SegWit).
  - Integrado en `core/scheduler.py` (cada 5 min).
  - Guarda los datos en `data/processed/block_explorer.json`.
- **Resultado**: 
  - Bloque verificado: #975,504.
  - Nonce: 402,790,069.
  - Merkle Root: cb34b5ad... 
  - Firma ECDSA: ✅ VALIDA.
- **Conclusion**: ✅ TEOS ahora no solo predice el hashrate de tu Bitaxe, sino que
  audita la red Bitcoin en tiempo real. El sistema es un nodo de observacion criptografica.


## EXP-020 — Panel visual con Block Explorer integrado
- **Fecha**: 2026-11-11
- **Hipotesis**: mostrar los datos criptograficos del bloque de Bitcoin en vivo
  dentro del panel neuron_center.html.
- **Implementacion**: 
  - Endpoint /api/block-explorer en web/server.py.
  - Nueva tarjeta en web/neuron_center.html con Altura, Nonce, Transacciones, 
    Merkle Root y estado de firma ECDSA.
  - Consumo asincrono cada 30 segundos.
- **Resultado**: Panel mostrando Bloque #975,507 con firma ECDSA VALIDA en vivo.
- **Conclusion**: ✅ El sistema es un centro de comando criptografico. Integra
  prediccion de hardware (IA), infraestructura (scheduler) y criptografia Bitcoin.


## EXP-021 — Network Context (Estado de la Red Bitcoin)
- **Fecha**: 2026-11-11
- **Hipotesis**: mostrar el contexto operativo de la red Bitcoin (dificultad, mempool, comisiones) para entender el entorno de minado.
- **Implementacion**: 
  - `tools/network_context.py`: analiza proyeccion de dificultad, mempool, comisiones y tiempos de bloques.
  - Endpoint /api/network-context en el servidor web.
  - Tarjeta visual en neuron_center.html con colores dinamicos (verde si la dificultad baja).
- **Resultado**: Panel mostrando -6.96% de cambio de dificultad, congestion ALTA y comisiones de 3 sat/vB.
- **Conclusion**: ✅ El panel ahora muestra tanto el estado del hardware (Bitaxe) como el contexto de la red (Bitcoin).


## EXP-022 — Monitor ECG en Vivo, Drift de Nonces y Crypto Lab
- **Fecha**: 2026-11-12
- **Hipotesis**: integrar la salud de la red Bitcoin y el analisis criptografico en un solo panel unificado.
- **Implementacion**: 
  - `tools/pulse_series.py`: captura append-only de tiempos de bloque.
  - `tools/live_pulse.py`: estado del epoch actual para el panel.
  - `tools/nonce_drift.py`: test KS de distribucion de nonces (Capa 1: red).
  - `tools/nonce_drift_bitaxe.py`: detector para pool API (Capa 2: MOCK/LIVE).
  - `web/server.py`: endpoints para live-pulse, pulse-series y nonce-drift.
  - `web/neuron_center.html`: 
    - Monitor ECG animado en canvas (latido en vivo).
    - Crypto Lab unificado (Campana de Gauss + 10k Nonces + Conclusiones).
    - Eliminacion de graficos estaticos y fantasmas de DOM.
- **Resultado**: 
  - El panel muestra el pulso de la red en tiempo real (Promedio 10.28 min, NORMAL).
  - Detector de deriva (Capa 1) indica KS=0.0753 (ATENCION: ligera desviacion).
  - La dificultad va a bajar -7.66% en 1.3 dias.
- **Conclusion**: ✅ El sistema es un centro de comando criptografico completo y visual.
