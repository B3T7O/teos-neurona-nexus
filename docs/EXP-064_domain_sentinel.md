# EXP-064 — Centinela de Dominios (Truco de Feynman)

**Fecha:** 2026-11-28
**Estado:** CERRADO — ÉXITO
**Hito:** TEOS ahora tiene visión interna del ASIC.

## El Descubrimiento
Los dominios internos del ASIC (los 4 clústeres que forman el BM1370) no están en la raíz de la API de AxeOS. Están profundamente anidados en `hashrateMonitor -> asics -> [0] -> domains`. 

## La Solución (Truco de Feynman)
Se implementó una búsqueda recursiva (`find_domains_recursive`) que encuentra la llave "domains" sin importar dónde se esconda el firmware. 
Se creó el script `tools/domain_sentinel.py` que calcula el Coeficiente de Variación (CV) entre los 4 dominios.
Se integró esta visión al Gemelo Digital (`shadow_evaluator.py`) para registrar el CV en cada predicción.

## Estado Actual
El hardware muestra un CV de ~8.47% (Advertencia). Esto es normal por la varianza del silicio, pero ahora tenemos la telemetría para monitorearlo. Si un dominio se degrada en el futuro, el sistema lo sabrá antes de que falle.
