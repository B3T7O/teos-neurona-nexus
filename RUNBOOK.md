# TEOS NEURONA NEXUS — Manual de Operación

## Arrancar (tras reinicio del HP, hacer una vez)

    systemctl --user start teos-colector teos-scheduler teos-web

## Verificar que está sano (10 segundos)

    systemctl --user is-active teos-colector teos-scheduler teos-web
    curl -s -o /dev/null -w "web: HTTP %{http_code}\n" http://127.0.0.1:8765/
    tail -n 1 data/raw/bitaxe_samples.jsonl

Debe salir: 3 veces "active", "web: HTTP 200", y una línea con hashrate/temp.

## Parar

    systemctl --user stop teos-colector teos-scheduler teos-web

## Ver logs

    journalctl --user -u teos-scheduler -f
    tail -f logs/collector.log logs/scheduler.log logs/web-server.log

## Interpretar bitaxe_control.jsonl

    "write_attempted": false  →  sistema sano, nada que cambiar (normal)
    "write_attempted": true + "write_verified": true  →  cambio aplicado OK
    "write_attempted": true + "write_verified": false →  FALLO, revisar

## Política de seguridad (NO cambiar)

- Nunca sube frecuencia o voltaje automáticamente.
- Solo baja si hay degradación o temperatura alta.
- Verifica cada escritura con lectura posterior.
- "Sin cambios" es un resultado válido y esperado.

## Estado del proyecto

Sistema completo y operativo. Produce trabajo real:
- Observación: data/raw/bitaxe_samples.jsonl
- Análisis: data/processed/analysis_history.jsonl  
- Predicción: data/processed/ridge_live_predictions.jsonl (APE ~1.5%)
- Evaluación: data/processed/learning_outcomes_v2.jsonl
- Decisión: data/raw/bitaxe_control.jsonl

Web en http://127.0.0.1:8765

## Hallazgo abierto (audit 2026-11-05) - COBERTURA DECRECIENTE

Cobertura eval ridge_live por dia:
  2026-10-30  79.8%
  2026-10-31  79.1%
  2026-11-01  71.8%
  2026-11-02  70.2%
  2026-11-03  63.7%
  2026-11-04  62.9%
  2026-11-05  48.3% (parcial, dia en curso)

Tendencia: DECRECIENTE. El learning_loop evalua cada vez menos
proporcion de las predicciones que genera. No es un hueco historico.
Es una regresion activa. Investigacion pendiente.

Sistema sigue funcionando (sigue prediciendo y evaluando), pero
el backlog de predicciones sin evaluar crece.
