# TEOS NEURONA NEXUS

## Propósito
Construir desde cero un núcleo ligero para observar, analizar y optimizar
sistemas de computación distribuida, comenzando con la minería Bitcoin
mediante Bitaxe.

## Principios
1. Arquitectura modular y mínima.
2. Compatibilidad con equipos de recursos limitados.
3. Separación entre datos originales, procesamiento y resultados.
4. No modificar ni eliminar datos históricos originales.
5. Evitar predicciones duplicadas mediante identificadores y validaciones.
6. Registrar errores y decisiones importantes.
7. No afirmar que una optimización funciona sin medirla.

## Primera etapa
- Definir el formato de datos.
- Leer métricas de Bitaxe sin modificarlas.
- Validar datos y marcas de tiempo.
- Evitar duplicados de forma persistente.
- Probar el núcleo antes de añadir predicciones.

## Límites iniciales
- Sin servicios en segundo plano.
- Sin dependencias externas innecesarias.
- Sin entrenamiento de modelos todavía.
- Sin modificaciones al proyecto histórico V7.

## Estructura
- core/: lógica central.
- config/: configuración.
- data/raw/: datos originales.
- data/processed/: datos validados y procesados.
- logs/: registros operativos.
- tests/: pruebas.
- docs/: documentación técnica.
