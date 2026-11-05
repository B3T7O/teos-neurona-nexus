# TEOS NEURONA NEXUS
## Cierre de la fase de verificación del aprendizaje adaptativo

**Fecha:** 23 de octubre de 2026  
**Estado:** VERIFICACIÓN DEL MECANISMO COMPLETADA  
**Alcance:** aprendizaje online, persistencia, protección ante anomalías e integridad de registros.

---

## 1. Objetivo

Verificar que el sistema puede resolver predicciones con observaciones posteriores,
calcular el error, actualizar el sesgo del aprendiz, persistir el estado y reutilizar
ese estado al calcular una predicción adaptativa posterior.

Esta fase no certifica la rentabilidad minera ni una mejora sostenida de la precisión.

## 2. Evidencias verificadas

### 2.1 Protección de anomalías

- Archivo de memoria: `data/processed/anomaly_events.jsonl`
- Evento registrado: `f01fb7b259383f4829812733`
- Tipo: `contextual_hashrate_spike`
- Timestamp: `2026-10-22T22:35:46.909234+00:00`
- Hashrate observado: `81806.5078125 GH/s`
- Referencia de una hora registrada por el detector: `1485.9804688 GH/s`
- Estado diagnóstico: no verificado; causa desconocida.
- El detector excluyó esta muestra del cálculo sin borrar la lectura original.
- Las pruebas aisladas previas comprobaron detección idempotente y preservación
  del estado del aprendiz.

No debe atribuirse una causa física o técnica a esta anomalía sin investigación adicional.

### 2.2 Ciclo de aprendizaje

En la ejecución controlada del módulo se observó:

- Seis nuevas actualizaciones del aprendiz durante esa ejecución.
- 121 resultados adaptativos revisados.
- 121 actualizaciones persistidas al finalizar.
- 9170 predicciones registradas.
- 9165 resultados registrados.
- Cinco predicciones pendientes de una observación posterior.

En la auditoría posterior:

- Resultados adaptativos sin procesar: 0.
- Objetivos adaptativos coincidentes con el timestamp anómalo: 0.
- IDs duplicados en predicciones: 0.
- IDs duplicados en resultados: 0.
- IDs procesados únicos en el estado: 121.

### 2.3 Estado persistido

Archivo: `data/processed/online_error_learner_state.json`

Valores verificados:

- `bias_GHs`: `9.45414891000007`
- `updates`: `121`

Última actualización registrada:

- Predicción: `1069.401856 GH/s`
- Observación: `1062.575073 GH/s`
- Error observado: `-6.826783 GH/s`
- Sesgo anterior: `10.136827210000067 GH/s`
- Sesgo posterior: `9.45414891000007 GH/s`

El sesgo se ajustó en la dirección esperada para el error observado.

### 2.4 Prueba aislada de predicción

Se llamó a `online_error_learner.predict()` con una base sintética de
`1000 GH/s`.

- Sesgo persistido cargado: `9.45414891 GH/s`
- Predicción calculada: `1009.45414891 GH/s`
- Predicción esperada: `1009.45414891 GH/s`
- Sesgo cargado coincidente: verdadero.
- Contador coincidente: verdadero.
- Hash SHA-256 del archivo de estado antes y después: idéntico.

**Resultado:** prueba superada sin modificar el estado de producción.

## 3. Componentes comprobados

- `core/anomaly_memory.py`: detección y registro de anomalías contextuales.
- `core/online_error_learner.py`: carga del estado, predicción adaptativa,
  actualización del sesgo y protección de objetivos anómalos.
- `core/learning_loop_v2.py`: resolución de predicciones, aprendizaje online
  y generación de nuevas predicciones adaptativas.

La inspección confirmó que `predict()` carga el estado persistido y suma el sesgo
a la predicción base, y que el ciclo usa esa función para producir la predicción
adaptativa.

## 4. Limitaciones pendientes

No se ha demostrado todavía:

- Una mejora sostenida de la precisión frente a los métodos de referencia.
- Que el método adaptativo sea superior en distintos periodos de datos.
- La causa de la anomalía contextual.
- La estabilidad prolongada del sistema bajo operación continua.
- Que cinco predicciones pendientes ya hayan recibido su observación posterior.

Estas limitaciones no invalidan la prueba del mecanismo de persistencia y predicción,
pero impiden declarar validado el rendimiento predictivo general.

## 5. Seguridad y operación

Hasta una decisión explícita de la siguiente fase:

1. No activar los temporizadores de aprendizaje detenidos.
2. No ejecutar el ciclo de producción para repetir pruebas ya superadas.
3. No borrar ni reconstruir los archivos históricos.
4. No reindexar, reiniciar ni alterar la sincronización de Bitcoin Core.
5. Mantener el registro de anomalías y el estado persistido.
6. Hacer nuevas pruebas con copias y datos temporales siempre que sea posible.
7. Antes de cualquier ejecución de producción, verificar el alcance de sus efectos
   sobre predicciones, resultados y estado del aprendiz.

**Advertencia:** `python3 -m core.learning_loop_v2 --help` no mostró ayuda;
ejecutó `main()` y modificó los archivos de producción. No usar ese comando
como prueba inocua.

La ejecución como módulo permitió importar correctamente `core.anomaly_memory`.
No se debe asumir que cualquier invocación del programa es de solo lectura.

## 6. Copia de seguridad de referencia

Copia creada antes de la ejecución final:

`backups/controlled_learning_20261023T083025Z`

Contiene copias de las predicciones, los resultados, el estado del aprendiz y
el registro de anomalías. Es una referencia histórica; no restaurarla ni sobrescribir
los archivos actuales sin una decisión explícita.

## 7. Decisión de cierre

Se considera completada la verificación del mecanismo de aprendizaje adaptativo:
persistencia, ajuste numérico del sesgo, reutilización del estado en la predicción
y controles de integridad comprobados.

La validación de precisión predictiva y la decisión sobre operación continua
quedan fuera de este cierre.

**Próxima fase propuesta:** documentar y evaluar la calidad predictiva con un
protocolo prospectivo, sin reiniciar ni alterar el histórico y sin activar
temporizadores automáticamente.
