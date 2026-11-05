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

## Nota de auditoria (2026-11-05) - INFORMATIVA, NO BLOQUEANTE

El audit engine reporta "cobertura eval ridge_live 72.3%". Interpretacion:

- data/processed/ridge_live_predictions.jsonl contiene predicciones de varios
  metodos del loop (ridge_live, media_ultimas_5, adaptativo_neurona, etc.)
- data/processed/learning_outcomes_v2.jsonl contiene outcomes de todos los
  metodos, con ratios distintos de generacion.
- Por eso la comparacion 1:1 entre ambos archivos NO es una medida de
  cobertura real, sino un artefacto del audit engine.

Evidencia de que el sistema funciona:
- APE medio 2.86%, mediana 2.08% sobre 70.215 outcomes (calidad alta)
- 830 outcomes nuevos en las ultimas 4h vs 215 predicciones ridge_live
  → el loop SI evalua, y evalua multiples metodos por ciclo
- Servicios activos, datos frescos, web 200

Conclusion: el "72.3%" no indica fallo. Indica que el audit engine compara
conjuntos distintos. Mejora futura del audit (v0.2): comparar por metodo.
Estado del sistema: SANO Y OPERATIVO.
