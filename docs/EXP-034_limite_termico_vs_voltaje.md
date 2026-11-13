# EXP-034: Prueba de Overclock a 625 MHz (Límite Térmico vs Límite de Silicio)

**Fecha:** 2026-11-13
**Hardware:** Bitaxe Gamma 602 (BM1370)
**Objetivo:** Evaluar si una mejora en la refrigeración permite sostener 625 MHz de forma estable, alimentando el modelo de aprendizaje con un hashrate mayor.

## Configuración del Experimento
1. **Refrigeración Mejorada:** Se ajustó el `temptarget` a 55°C y `minFanSpeed` a 50%.
2. **Resultado Térmico:** VRM bajó de 78°C a 69°C. ASIC bajó de 60°C a 52.9°C.
3. **Acción:** Se envió un PATCH para subir la frecuencia de 600 MHz a 625 MHz (manteniendo el voltaje en 1100 mV).

## Resultados Observados
*   **Frecuencia:** El firmware (AxeOS) abortó el overclock y devolvió el equipo a **600 MHz** de forma automática.
*   **Tasa de Error:** Alcanzó el **1.26%** (superando el umbral de seguridad del 1.0%).
*   **Hashrate:** Se mantuvo estable en ~1224 GH/s (tras el auto-rollback).

## Conclusión para la Neurona (Machine Learning)
El límite para este chip **no es térmico**, sino de **voltaje/silicio**. A 1100 mV, el hardware no puede procesar correctamente a 625 MHz, incluso con temperaturas excelentes (VRM a 69°C). 

*   **Aprendizaje registrado:** El overclock a 625 MHz requiere obligatoriamente un aumento de voltaje (>1100 mV), lo que afectará negativamente la eficiencia (J/TH).
*   **Estado actual:** Sistema estable a 600 MHz, VRM a 69°C, Error < 1%. Ventilador al 50%.

## Próximos Pasos (Opcional)
Evaluar en un futuro experimento si 625 MHz con 1150 mV o 1180 mV es viable, asumiendo el costo energético.
