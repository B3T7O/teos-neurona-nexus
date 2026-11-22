# EXP-049: Validación predictiva, cuarentena MLP y protecciones temporales

**Fecha:** 2026-11-22
**Proyecto:** TEOS Neurona Nexus
**Hardware observado:** Bitaxe Gamma 602 (BM1370)
**Estado:** Validación parcial; no autoriza cambios automáticos de hardware.

## 1. Objetivo

Documentar las correcciones de integridad del aprendizaje, la evaluación comparativa de métodos, la cuarentena del MLP Lite y las protecciones de antigüedad de predicciones.

La prioridad es preservar la estabilidad del sistema y exigir evidencia prospectiva antes de activar modelos experimentales.

## 2. Aprendizaje V2 y calidad de muestras

Se incorporó al aprendizaje V2 una validación de calidad y de referencias de hashrate según frecuencia, utilizando los límites físicos de `core.sample_quality`:

- `HR_MIN_PER_MHZ = 0.5`.
- `HR_MAX_PER_MHZ = 5.0`.
- Se descartan muestras con etiqueta de calidad distinta de `ok` o que no superan la clasificación.
- Las referencias de 10 minutos y una hora se validan independientemente.
- La selección adaptativa solo considera métodos disponibles.
- El aprendizaje online permanece en modo sombra; no se aplica su corrección a la predicción base.

En la ejecución observada del 22 de noviembre, el scheduler registró:
- 594 muestras rechazadas por calidad.
- 10 referencias rechazadas por rango físico.
- 0 eventos nuevos registrados por la memoria de anomalías en ese ciclo.

El scheduler principal permaneció `active (running)`, PID 279133, iniciado el 22 de noviembre a las 16:26:27 (-05:00).

## 3. Corrección de Evolve Lab

Se corrigió la asignación del mejor candidato cuando todavía no existía un campeón global (`best_overall is None`).

La ejecución manual de Evolve Lab terminó con `status=0/SUCCESS` después de 50 generaciones y escribió un candidato separado:

`data/processed/evolve_champion_candidate.json`

Resultados de la evaluación comunicada:
- APE del candidato: 2.490126%.
- APE de pesos iguales: 2.576477%.
- APE del campeón anterior: 2.490179%.

La mejora respecto al campeón anterior es mínima. El candidato no se promovió ni sustituyó al campeón activo. Se requiere evaluación fuera de muestra antes de cualquier promoción.

## 4. Cuarentena del MLP Lite

El MLP Lite permanece fuera del selector adaptativo, del ensemble y de la evolución mientras sus resultados no sean fiables.

### 4.1 Anomalía histórica

Se encontró una predicción de aproximadamente 4.88 billones de GH/s para el origen `2026-11-19T17:24:39.342859+00:00`. La siguiente muestra RAW disponible tuvo un `hashRate` de 1395.779 GH/s.

La inspección de la memoria persistente disponible el 22 de noviembre mostró desviaciones estándar de `1e-08` en las entradas `share_count`, `avg_diff`, `stale_rate`, `dup_rate` y `above_rate`. Estas variables se calculaban una sola vez y se repetían en las muestras históricas.

También se identificaron problemas de diseño:
- `hashRate_10m` participaba como entrada y como objetivo de entrenamiento.
- La predicción se generaba sobre la última muestra usada en el entrenamiento, no sobre una muestra futura reservada.
- No había una separación temporal adecuada entre entrenamiento y evaluación.

La memoria inspeccionada fue modificada después de la predicción anómala. Por ello, las escalas actuales explican un mecanismo plausible de inestabilidad, pero no prueban exactamente el estado de los pesos en aquella ejecución histórica.

### 4.2 Experimento independiente

Se entrenó una red experimental únicamente en memoria, sin guardar pesos ni alterar el modelo original.

Dataset:
- 41,581 pares temporales válidos.
- Separación cronológica: 64% entrenamiento, 16% validación y 20% prueba final.
- La prueba final contenía 8,317 pares.

Resultados en la prueba final:

| Método | MAE (GH/s) | RMSE (GH/s) |
|---|---:|---:|
| MLP experimental | 70.9193 | 87.4931 |
| Último hashrate | 67.5804 | 87.4898 |
| Referencia 1m | 49.0839 | 65.8190 |
| Referencia 10m | 47.5765 | 61.9675 |
| Referencia 1h | 47.3822 | 61.8250 |

El MLP no superó las referencias. No se aprobó ni se guardaron sus pesos.

**Decisión:** mantener MLP Lite en cuarentena. No borrar sus predicciones, resultados ni históricos.

## 5. Comparación de referencias

En una comparación independiente con muestras comunes:
- 41,573 pares válidos.
- 8,315 pares en la prueba final.
- `referencia_1h`: MAE 47.3914 GH/s.
- `referencia_10m`: MAE 47.5865 GH/s.
- `media_ultimas_5`: no fue la mejor referencia global.
- `ultimo_hashrate`: obtuvo el mayor error entre los cuatro métodos.

En el análisis por día, `referencia_1h` ganó 6 de 7 días y `referencia_10m` ganó 1 de 7.

En otra comparación de los mismos 50 targets históricos:
- `referencia_1h`: MAE 44.54957 GH/s.
- `referencia_10m`: MAE 49.26224 GH/s.
- `media_ultimas_5`: MAE 57.68721 GH/s.
- `ultimo_hashrate`: MAE 76.53965 GH/s.

El selector adaptativo eligió `referencia_1h`, con 50 resultados y MAE de 44.54956554 GH/s.

Estas comparaciones son evidencia histórica y de selección, pero no constituyen por sí solas una prueba independiente de rendimiento futuro, porque los resultados recientes participan en la selección.

## 6. Validación prospectiva pendiente

Se fijó como corte inicial:

`2026-11-22T22:01:22.037201+00:00`

En la última comprobación disponible solo había un target posterior común a los cuatro métodos:

`2026-11-22T22:06:48.791399+00:00`

Un target no es suficiente para concluir que la ventaja de `referencia_1h` se mantiene prospectivamente.

La siguiente evaluación debe comparar los cuatro métodos sobre exactamente los mismos targets nuevos. Se estableció un mínimo operativo de 20 targets comunes para una primera revisión, no como garantía estadística definitiva.

## 7. Protecciones temporales de predicciones

Se reforzaron las comprobaciones de antigüedad en:
- `core.ai_bridge`: campeón de menos de 15 minutos.
- `core.evolve_predictor`: predicciones de origen de menos de 20 minutos.

Ambos componentes rechazan fechas futuras y predicciones antiguas.

Las pruebas sintéticas realizadas con archivos temporales comprobaron, en ambos componentes:
- Predicción de 5 minutos: aceptada.
- Predicción de 30 minutos: rechazada.
- Predicción fechada 5 minutos en el futuro: rechazada.

Las seis comprobaciones pasaron. No se modificaron archivos de producción durante esas pruebas.

## 8. Observación operativa

En los registros consultados del scheduler:
- Estado del servicio: `active (running)`.
- Estado térmico reportado: normal.
- Muestras térmicas clasificadas como normal: 42,321.
- Warning: 0; critical: 0.
- Hashrate observado en el reporte: 1218.197 GH/s.
- Temperatura ASIC: 51.125 °C.
- Temperatura del regulador: 63 °C.

El sensor `temp2` reportó -1 y `fan2rpm` reportó 0 RPM. Estos datos aislados no demuestran por sí solos una avería.

No se autoriza ningún cambio de frecuencia, voltaje u overclock como parte de este experimento.

## 9. Decisiones y próximos pasos

1. Mantener `referencia_1h` como ganador observado del selector, sin fijarlo permanentemente.
2. Mantener el aprendizaje V2 y el aprendizaje experimental en sombra según su configuración actual.
3. Mantener MLP Lite en cuarentena.
4. No promover el candidato de Evolve Lab.
5. Continuar la evaluación prospectiva con targets comunes.
6. No modificar el Bitaxe ni sus parámetros de protección en esta etapa.
7. Mantener separados los respaldos, entornos virtuales, datos RAW y resultados operativos del control de versiones.

## 10. Alcance de las conclusiones

Este expediente registra pruebas y observaciones realizadas al 22 de noviembre de 2026. No declara validado el rendimiento futuro del selector, no certifica la superioridad estadística de `referencia_1h` y no aprueba la activación del MLP Lite ni del candidato evolutivo.
