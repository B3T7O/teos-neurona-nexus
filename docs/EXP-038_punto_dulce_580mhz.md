# EXP-038: El Punto Dulce del Silicio (580 MHz) y la Integración del Proxy

**Fecha:** 2026-11-14
**Hardware:** Bitaxe Gamma 602 (BM1370)
**Objetivo:** Documentar el estado de máxima eficiencia logrado mediante la combinación de reglas lógicas (Rete), latencia ultrabaja (Lite Proxy) y ajuste fino de frecuencia/voltaje.

## Contexto
Tras múltiples experimentos con overclock (610 MHz) y undervolting (1080 mV), el sistema demostró inestabilidad (errores > 1.5%). Se implementó un Proxy Stratum local (latencia 1 ms) para eliminar los shares obsoletos y se ajustaron las reglas de Rete para priorizar la estabilidad sobre la velocidad bruta.

## Cambios Aplicados
1.  **Lite Proxy (Systemd):** Enrutamiento del Bitaxe a través de la laptop local, reduciendo la latencia de 150 ms a ~1 ms.
2.  **Regla de Rete (Estabilización):** Si el error supera el 1.0%, bajar a 580 MHz preventivamente.
3.  **Punto Dulce:** Frecuencia fijada en 580 MHz con 1095 mV.

## Resultados Obtenidos (Telemetría en Vivo)
*   **Frecuencia:** 580 MHz
*   **Voltaje:** 1095 mV (Consumo: 19.91 W)
*   **Error Rate:** **0.19%** (Récord histórico absoluto)
*   **Temperaturas:** ASIC 53.0 °C | VRM 68 °C (Zona segura)
*   **Shares:** 814 ok / 2 fail (99.75% de efectividad)

## Conclusión
El experimento confirma que **menos velocidad (MHz) puede resultar en mayor hashrate efectivo** si se reducen los errores de hardware. La combinación del Proxy local (cero latencia) y el control térmico estricto ha convertido al Bitaxe en un sistema de minería de precisión, minimizando el desgaste del silicio y maximizando la rentabilidad de los shares.
