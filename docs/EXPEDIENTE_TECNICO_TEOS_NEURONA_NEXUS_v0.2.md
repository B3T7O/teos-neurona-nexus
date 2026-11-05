# TEOS NEURONA NEXUS
## Expediente técnico — Versión 0.2

- Fecha de corte: 2026-10-21
- Estado: documento técnico inicial
- Proyecto: TEOS — Tecnología Electrónica, Optimización y Sistemas
- Lema: Optimizar. Distribuir. Evolucionar.
- Entorno observado: Linux bajo WSL
- Aplicación inicial: observación y análisis de métricas de Bitaxe

> Este documento distingue entre código existente, pruebas ejecutadas,
> resultados experimentales y capacidades todavía no demostradas.
> No constituye una certificación independiente ni un registro legal
> de propiedad intelectual.

## Índice

- [1. Propósito](#1-propósito)
- [2. Estructura técnica observada](#2-estructura-técnica-observada)
- [3. Datos e integridad](#3-datos-e-integridad)
- [4. Experimentos registrados](#4-experimentos-registrados)
  - [4.1 Benchmark de referencias congeladas](#41-benchmark-de-referencias-congeladas)
  - [4.2 Validación walk-forward](#42-validación-walk-forward-de-referencias)
  - [4.3 Primer experimento de aprendizaje](#43-primer-experimento-de-aprendizaje)
  - [4.4 Auditoría de calidad](#44-auditoría-de-calidad-de-hashrate)
  - [4.5 Memoria de tendencias](#45-memoria-de-tendencias)
- [5. Pruebas automatizadas](#5-pruebas-automatizadas)
- [6. Reproducibilidad y control de cambios](#6-reproducibilidad-y-control-de-cambios)
- [7. Limitaciones actuales](#7-limitaciones-actuales)
- [8. Hoja de ruta propuesta](#8-hoja-de-ruta-propuesta)
- [9. Protección del conocimiento](#9-protección-del-conocimiento-del-proyecto)
- [10. Registro de esta versión](#10-registro-de-esta-versión)
- [11. Matriz de trazabilidad](#11-matriz-de-trazabilidad)
- [12. Diferencias entre conjuntos de evaluación](#12-diferencias-entre-conjuntos-de-evaluación)
- [13. Historial de versiones](#13-historial-de-versiones)

## 1. Propósito

TEOS NEURONA NEXUS busca construir un núcleo modular y ligero para
observar, analizar y, posteriormente, optimizar sistemas de computación
distribuida. La primera aplicación observada es la minería de Bitcoin
mediante un dispositivo Bitaxe.

Principios documentados en el README:
- Mantener una arquitectura modular.
- Separar datos originales, procesamiento y resultados.
- Evitar alterar o eliminar el histórico original.
- Validar datos y evitar predicciones duplicadas.
- Registrar errores y decisiones.
- No afirmar que una optimización funciona sin medirla.

## 2. Estructura técnica observada

- `core/`: validación, análisis, historial, adaptación, aprendizaje,
  evaluación prospectiva y memoria de tendencias.
- `experiments/`: scripts de comparación, auditoría y evaluación.
- `data/raw/`: capturas originales de Bitaxe.
- `data/processed/`: historial analítico y registros de predicciones.
- `tests/`: pruebas automatizadas.
- `web/`: interfaz y servidor web.
- `docs/`: documentación técnica.

La presencia de un módulo o archivo no demuestra por sí sola que esté
activo, integrado o validado en ejecución.

## 3. Datos e integridad

Archivos identificados durante la inspección:

- `data/raw/bitaxe_samples.jsonl`
- `data/processed/analysis_history.jsonl`
- `data/processed/learning_predictions.jsonl`
- `data/processed/learning_predictions_v2.jsonl`
- `experiments/frozen_bitaxe_samples.jsonl`
- `experiments/frozen_evaluation_manifest.json`

Los recuentos iniciales observados fueron 1.997 líneas en las capturas
raw, 68 en el historial analítico, 949 en las predicciones antiguas,
3.768 en las predicciones V2 y 846 en el conjunto congelado. Son
recuentos de líneas, no necesariamente de observaciones únicas válidas.

El manifiesto del conjunto congelado registra:
- 846 registros en la comprobación básica.
- SHA-256:
  `dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5`
- Propósito: comparar referencias y modelos sobre un conjunto fijo.
- Declaración de que el conjunto original no fue modificado por esa
  operación de congelación.

Los scripts de benchmark y Ridge verifican el SHA-256 del conjunto
congelado antes de utilizarlo. Esto ayuda a detectar cambios en el
archivo evaluado.

### Diferencias entre informes

Los informes inspeccionados no usan necesariamente exactamente las
mismas filas:
- Auditoría de calidad: 843 muestras únicas válidas.
- Comparación de ventanas: 845 muestras únicas válidas.
- Conjunto congelado: 846 registros básicos válidos declarados.

Estas diferencias deben investigarse y documentarse antes de combinar
métricas. No se asume que los recuentos sean intercambiables.

## 4. Experimentos registrados

### 4.1 Benchmark de referencias congeladas

Script:
`experiments/benchmark_frozen_baselines.py`

Informe:
`experiments/frozen_baseline_benchmark.json`

Evalúa cuatro referencias sobre 254 objetivos de prueba comunes.
El objetivo es el `hashRate` de la siguiente muestra. No entrena un
modelo.

| Método | MAE (GH/s) | RMSE (GH/s) |
|---|---:|---:|
| Último hashRate | 35,0032 | 42,6056 |
| Media de las últimas cinco muestras | 28,1452 | 34,4867 |
| hashRate_10m previo | 25,1184 | 31,0454 |
| hashRate_1h previo | 24,9858 | 30,8140 |

La referencia `hashRate_1h` obtuvo el menor MAE en este benchmark.
El resultado no demuestra capacidad para predecir bloques de Bitcoin.

### 4.2 Validación walk-forward de referencias

Script:
`experiments/walkforward_baselines.py`

Informe:
`experiments/walkforward_baseline_report.json`

El informe registra cinco tramos cronológicos y 423 objetivos en el
resultado global.

| Método | MAE (GH/s) | RMSE (GH/s) |
|---|---:|---:|
| hashRate_1h previo | 25,1672 | 31,2474 |
| hashRate_10m previo | 25,2316 | 31,3610 |
| Media de las últimas cinco muestras | 27,3646 | 34,2981 |
| Último hashRate | 34,7602 | 43,2562 |

En el conjunto evaluado, la referencia de una hora obtuvo el menor MAE
global. Los resultados por tramo varían; no se presume superioridad
universal de un método.

### 4.3 Primer experimento de aprendizaje

Script:
`experiments/first_learning_model.py`

Informe:
`experiments/first_learning_model_report.json`

Método: regresión Ridge con alpha = 10. Utiliza 16 características
relacionadas con métricas, sensores y diferencias entre muestras.
Las características se calculan con datos anteriores al objetivo.
El escalado se ajusta usando únicamente los datos de entrenamiento
de cada tramo.

El informe declara 846 registros válidos únicos y 844 muestras
utilizables, con cinco tramos cronológicos.

| Método | MAE (GH/s) | RMSE (GH/s) |
|---|---:|---:|
| Ridge | 25,5797 | 31,6702 |
| Referencia hashRate_1h | 25,2175 | 31,2838 |

El MAE de Ridge fue aproximadamente 1,44 % mayor que el de la
referencia. Ridge mejoró el MAE en dos de los cinco tramos.

Conclusión: en esta evaluación, el modelo no superó a la referencia
sencilla. Es un resultado válido que orienta futuras pruebas; no
demuestra que todos los componentes de NEURONA sean ineficaces.

El informe declara que no modificó el sistema en vivo y que no realiza
predicción de bloques de Bitcoin.

### 4.4 Auditoría de calidad de hashrate

Script:
`experiments/audit_hashrate_quality.py`

Informe:
`experiments/hashrate_audit_report.json`

El informe registra 843 muestras únicas válidas, cero líneas inválidas
y cero marcas temporales duplicadas según los criterios de ese script.
Utiliza una división cronológica de 590 muestras históricas y 253 de
prueba.

| Segmento | Muestras | MAE (GH/s) | RMSE (GH/s) |
|---|---:|---:|---:|
| Estable | 226 | 25,0728 | 30,1157 |
| Cambio brusco | 27 | 54,5806 | 60,1332 |

Los segmentos se clasifican retrospectivamente según un umbral calculado
a partir de cambios históricos. Por tanto, estas cifras describen
diferencias de error en el histórico; no demuestran detección anticipada
en tiempo real.

El script también identifica errores atípicos usando una regla basada
en la mediana y la desviación absoluta mediana (MAD).

### 4.5 Memoria de tendencias

Módulo:
`core/trend_memory.py`

Informe:
`data/processed/trend_memory_report.json`

El informe declara que utiliza condiciones de origen, exige un mínimo
de diez observaciones por grupo y no modifica los archivos raw ni las
predicciones V2.

Registra 2.392 resultados asociados a capturas de origen, sin marcas
temporales de origen sin correspondencia según el informe.

En sus resultados históricos, las referencias de 10 minutos y una hora
tienen MAE cercano a 24,88 GH/s. La media de las últimas cinco muestras
registra aproximadamente 27,69 GH/s y la referencia al último valor,
33,82 GH/s.

El propio informe advierte que los grupos históricos no demuestran
causalidad ni garantizan rendimiento futuro. Estas cifras no deben
compararse directamente con otros informes sin verificar las filas,
los objetivos y los períodos utilizados.

## 5. Pruebas automatizadas

Comando ejecutado:

`python3 -m unittest discover -s tests -v`

Resultado observado: 17 pruebas aprobadas; salida final `OK`.

Los casos cubren:
- Rechazo de entradas no válidas.
- Timestamp ausente.
- Hashrate negativo o booleano.
- Interpretación de sensores no disponibles.
- Interpretación de cero RPM reportadas.
- Umbrales térmicos normal, warning, critical y unknown.
- No modificación del registro por ciertas funciones de validación
  y evaluación térmica.

Estas pruebas verifican los casos implementados; no equivalen a una
validación completa de toda la aplicación.

## 6. Reproducibilidad y control de cambios

En la inspección del 2026-10-21, `git rev-parse` y `git status`
indicaron que el directorio no es un repositorio Git.

Los informes y scripts ya existentes deben preservarse. Antes de
repetir experimentos, comprobar si el script sobrescribe su informe:
algunos scripts se detienen si la salida ya existe, mientras otros
escriben directamente en el archivo de informe.

Procedimiento recomendado para futuras pruebas:
1. Registrar fecha, versión del código y archivo de datos.
2. Verificar la integridad del conjunto utilizado.
3. Guardar configuración y criterios de evaluación.
4. Separar predicciones, mediciones reales y conclusiones.
5. Conservar el informe original y documentar cualquier nueva versión.
6. Ejecutar las pruebas automatizadas después de cambios relevantes.

## 7. Limitaciones actuales

- Los resultados son experimentales y se refieren al hashrate de la
  siguiente muestra, no a la probabilidad de encontrar un bloque.
- El primer modelo Ridge no superó a la referencia de una hora en el
  resultado global informado.
- Los cambios bruscos tienen mayor error histórico, pero su clasificación
  en la auditoría es retrospectiva.
- Los recuentos difieren entre informes y requieren una explicación
  basada en sus criterios de validación.
- La existencia de código no prueba que todos los módulos estén activos
  o integrados en el sistema en vivo.
- No se ha confirmado aquí una mejora operativa causada por una
  optimización de NEURONA.

## 8. Hoja de ruta propuesta

1. Explicar las diferencias de validación y deduplicación entre informes.
2. Establecer un protocolo común de evaluación y métricas.
3. Comparar cada modelo nuevo con las referencias en objetivos y
   muestras idénticos.
4. Evaluar cambios de régimen con criterios disponibles en tiempo real.
5. Añadir pruebas para módulos de aprendizaje, historial y predicciones.
6. Registrar versión de código, configuración y hashes de datos por
   experimento.
7. Documentar la integración real de la API, la interfaz y los módulos
   de NEURONA mediante comprobaciones reproducibles.
8. Mantener un registro de decisiones técnicas, hipótesis, resultados
   negativos y cambios aceptados.

## 9. Protección del conocimiento del proyecto

Este expediente organiza evidencia técnica y ayuda a mantener
trazabilidad. Por sí solo no concede una patente, no registra una marca
y no garantiza derechos exclusivos sobre una idea.

Para evaluar protección formal se deberá identificar qué elementos son
software, documentación, marca, diseño o una posible invención técnica,
y consultar los mecanismos aplicables en Ecuador antes de divulgar
información que pudiera ser sensible.

## 10. Registro de esta versión

- Versión: 0.2
- Fecha: 2026-10-21
- Base: inspección de scripts e informes existentes y ejecución de
  las 17 pruebas automatizadas.
- Pendiente: revisión de discrepancias entre conjuntos, comprobación
  de integración en vivo y establecimiento de control de versiones.
## 11. Matriz de trazabilidad

La siguiente matriz indica dónde revisar los resultados citados en este
expediente. Los JSON son informes existentes; sus valores deben contrastarse
con el contenido de cada archivo si se realizan nuevas revisiones.

| Tema | Script o prueba | Informe o evidencia |
|---|---|---|
| Benchmark de referencias congeladas | `experiments/benchmark_frozen_baselines.py` | `experiments/frozen_baseline_benchmark.json` |
| Evaluación walk-forward | `experiments/walkforward_baselines.py` | `experiments/walkforward_baseline_report.json` |
| Primer modelo Ridge | `experiments/first_learning_model.py` | `experiments/first_learning_model_report.json` |
| Auditoría de calidad | `experiments/audit_hashrate_quality.py` | `experiments/hashrate_audit_report.json` |
| Comparación de ventanas | `experiments/compare_hashrate_windows.py` | `experiments/hashrate_window_comparison.json` |
| Memoria de tendencias | Módulo de memoria de tendencias y proceso que generó el informe | `data/processed/trend_memory_report.json` |
| Pruebas automatizadas | `python3 -m unittest discover -s tests -v` | Salida de consola de la ejecución; no se presupone un informe persistente |
| Integridad de muestra congelada | Manifiesto de evaluación congelada | `experiments/frozen_evaluation_manifest.json` |
| Datos de entrada | Registros históricos del dispositivo | `data/raw/bitaxe_samples.jsonl` |

Los nombres y rutas identifican evidencia local. Su inclusión en esta tabla
no demuestra por sí sola que cada módulo esté integrado en producción, que
todos los informes procedan de la misma muestra ni que el resultado pueda
reproducirse sin verificar el estado actual del código y los datos.

## 12. Diferencias entre conjuntos de evaluación

Los recuentos registrados en los informes no deben tratarse como si
representaran el mismo conjunto estadístico.

| Informe o proceso | Recuento informado | Qué representa |
|---|---:|---|
| Manifiesto de muestra congelada | 846 | Registros válidos de la muestra congelada |
| Auditoría de calidad de hashrate | 843 | Muestras válidas únicas bajo los criterios de esa auditoría |
| Comparación de ventanas | 845 | Muestras únicas bajo los criterios de ese proceso |
| Primer modelo Ridge | 844 | Muestras utilizables para el modelo, a partir de un conjunto informado de 846 registros válidos únicos |
| Benchmark congelado | 254 | Objetivos de prueba comunes comparados por los métodos del benchmark |
| Walk-forward de referencias | 423 | Objetivos evaluados en el resultado global de cinco tramos |
| Memoria de tendencias | 598 por método | Resultados contabilizados para cada método en ese informe |

Los recuentos proceden de informes distintos y no son directamente
intercambiables. Las diferencias pueden depender de filtros de validez,
deduplicación, disponibilidad de características, construcción de objetivos,
particiones cronológicas y reglas particulares de cada evaluación.

Esta tabla registra la discrepancia; no determina por sí sola su causa exacta.
Antes de comparar o combinar resultados, hay que revisar el código de cada
proceso y establecer un protocolo común de inclusión, deduplicación y
partición temporal.

Las métricas de los informes son evidencia histórica. No garantizan el
rendimiento futuro ni prueban que una predicción haya causado una mejora
operativa.

## 13. Historial de versiones

| Versión | Descripción | Identificación |
|---|---|---|
| 0.1 | Expediente técnico inicial, basado en la inspección del código, los informes existentes y las pruebas registradas. | SHA-256: `e0c6f3948a6a009b6b72addc3da69c1e06de51785369cac99656c216f4819f6b` |
| 0.2 | Añade índice navegable, matriz de trazabilidad, explicación de los recuentos y registro de versiones. No vuelve a ejecutar experimentos ni modifica sus informes. | Huella SHA-256 registrada externamente tras la validación final. |

La versión 0.2 es una revisión documental. No representa por sí misma una
nueva versión del código de NEURONA ni una validación independiente del
sistema. La huella SHA-256 permite identificar los bytes de un archivo, pero
no constituye por sí sola una certificación de autoría o una prueba legal
concluyente.
