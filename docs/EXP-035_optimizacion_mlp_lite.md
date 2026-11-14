# EXP-035: Optimización del MLP Lite (Neuronas vs Feature Engineering)

**Fecha:** 2026-11-13
**Hardware:** Bitaxe Gamma 602 (BM1370)
**Modelo:** TEOS MLP Lite v1 (Red Neuronal Multicapa en Numpy)
**Objetivo:** Mejorar la precisión del modelo predictivo integrado al Meta Learner, evaluando la disyuntiva entre aumentar la capacidad de cómputo (neuronas) o mejorar la calidad de los datos de entrada (features).

---

## Contexto Inicial
El modelo debutó con un APE (Error Porcentual Absoluto) combinado de **3.34%**, posicionándose en el 6to lugar del ranking. La red contaba con 8 neuronas ocultas y solo 3 variables de entrada (temperatura, vram y hashrate instantáneo).

## Fase 1: El Experimento Fallido (16 Neuronas, 3 Features)
*   **Acción:** Se subió la capacidad a 16 neuronas y se aumentaron las muestras a 300.
*   **Resultado:** El APE se disparó a **>10%** (picos de 17.67%).
*   **Diagnóstico (Overfitting):** El hashrate instantáneo del ASIC es extremadamente volátil (oscila entre 1.05 y 1.4 Th/s por la naturaleza del *solo mining*). Al darle más "detectives" (neuronas) sin mejorar la calidad de las pistas, la red intentó memorizar el ruido, volviéndose esquizofrénica.
*   **Acción tomada:** Rollback inmediato a 8 neuronas.

## Fase 2: Feature Engineering (8 Neuronas, 5 Features)
*   **Acción:** En lugar de subir neuronas, se le dieron "mejores ojos" al modelo. Se añadieron:
    1.  `hashRate_10m` (Promedio de 10 minutos para suavizar los picos).
    2.  `errorPercentage` (Para entender la volatilidad de la red).
*   **Resultado:** El modelo se volvió a estabilizar, con errores que oscilaban entre 0.60% y 8.65%.

## Fase 3: El Ganador (16 Neuronas, 5 Features, 300 Muestras)
*   **Acción:** Con los datos ya suavizados, se volvió a subir a 16 neuronas.
*   **Resultado:** El APE combinado se estabilizó en **3.26%**, devolviendo al modelo al **Top 5** del ranking. 
*   **Rendimiento Destacado:** En momentos de estabilidad, el modelo alcanzó precisiones **quirúrgicas** de **0.04%** y **0.66%** de error.

## Conclusiones para la Neurona
1.  **Data > Modelo:** Un modelo más simple con mejores datos (5 features) es infinitamente superior a un modelo complejo con datos ruidosos.
2.  **El límite de la predicción:** El hashrate instantáneo es impredecible a corto plazo. El modelo debe enfocarse en predecir la tendencia (el promedio) para ser útil en la toma de decisiones.
3.  **Eficiencia del Hardware:** A pesar de cuadruplicar la capacidad (8 -> 16 neuronas) y triplicar los datos (100 -> 300 muestras), el modelo sigue consumiendo apenas **1.1 segundos de CPU** por ejecución, manteniendo el bajo impacto en el sistema.

## Configuración Final
*   `INPUT_SIZE = 5`
*   `HIDDEN_SIZE = 16`
*   `n_samples = 300`
*   `epochs = 200`
