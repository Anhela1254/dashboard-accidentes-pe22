# Informe reproducible - Modelo predictivo de accidentes (PE-22)

## Propósito
Evaluar frecuencia anual estimada de accidentes registrados en los km enteros 39 a 172
de la Carretera Central, con historial OSITRAN 2022-2025. Clasificacion relativa,
NO declaratoria oficial de punto negro ni inferencia causal.

## Evidencia y filtros
- Registros aceptados para el modelo: 3190.
- Registros externos ONSV/MTC excluidos por conciliacion pendiente.
- Registros OSITRAN relacionados/pendientes excluidos (para evitar potencial duplicidad).
- Ubicacion por km entero y eje vial referencial por verificar; no se permite inferir puntos de 100-200m.
- Progresivas CAD: marcas proyectadas al eje si distancias al texto <=25m.
- Cotas Copernicus DSM: proxy del relieve, NO pendiente longitudinal certificada.
- Giro entre marcas CAD: proxy de sinuosidad, NO radio de curva medido.
- El Formato 3B MTC registra danos del pavimento, no un inventario verificado de radios, peraltes o TPDA.
- Tabla BLACKSPOT: TPDA sin unidad/escala documentada; no usar como vehiculos/dia.
- Las cifras agregadas de victimas no se suman por discrepancias entre las fuentes.
- Accidentes por ano incluidos: {2022: 814, 2023: 804, 2024: 775, 2025: 797}.
- Otras exclusiones: {'Evento OSITRAN relacionado o en revision': 13, 'Fuente externa (conciliacion pendiente)': 101, 'Fuera de cobertura GIS 39-172': 31}.

## Protocolo de aprendizaje automatico
- 134 unidades por ano (km 39-40 ... km 172-173), con celdas de cero accidentes incluidas.
- 2022 sirve solo como antecedente temporal; 2023 entrenamiento inicial.
- 2024 validacion para seleccionar modelo por menor MAE (desempate RMSE).
- 2025 prueba temporal independiente; el modelo seleccionado se ajusta usando 2023-2024.
- 2026 proyeccion exploratoria; reajuste final del modelo con 2023-2025.
- Tecnicas: Random Forest, Poisson, XGBoost (opcional), y baselines de media historica y ultimo ano.
- Variables de accidentes historicos solo de anos ANTERIORES al predicho; se evita fuga temporal.
- Variables del modelo: accidentes_ano_previo, accidentes_media_historica, accidentes_max_historico, accidentes_tendencia, despistes_ano_previo, pendiente_dsm_proxy_pct, giro_cad_proxy_grados, km_inicio.

## Resultados de comprobacion
- Modelo elegido exclusivamente con validacion 2024: **Media histórica**.
- Validacion 2024: MAE=2.358, RMSE=3.232.
- Prueba temporal 2025: MAE=2.453, RMSE=3.129, Deviancia Poisson=1.579.
- Proyeccion total 2026 en km incluidos: 797.5 accidentes/anio (no todo el tramo Lima-La Oroya).
- Prioridad ALTA = top 20% de kilometros por frecuencia predicha; umbral RELATIVO, no norma vial.

## Cinco kilometros de mayor prioridad exploratoria
1. Km 132-133, T14: 19.25 accidentes estimados en 2026
2. Km 98-99, T07: 17.00 accidentes estimados en 2026
3. Km 127-128, T13: 15.75 accidentes estimados en 2026
4. Km 138-139, T15: 15.00 accidentes estimados en 2026
5. Km 50-51, T02: 14.75 accidentes estimados en 2026

## Cinco tramos de mayor frecuencia agregada proyectada
IMPORTANTE: los tramos no tienen igual longitud; esta no es una tasa por vehiculo-km.
1. T02, Corcona – San Bartolomé: 61.50 accidentes en km incluidos
2. T14, Paso de Ticlio – Morococha · subtramo: 60.75 accidentes en km incluidos
3. T05, Salida de Matucana – Cañón de Viso: 56.75 accidentes en km incluidos
4. T01, Puente Ricardo Palma – Cupiche: 55.50 accidentes en km incluidos
5. T13, Lazos de Chinchan – Pre abra Anticona · subtramo: 54.25 accidentes en km incluidos

## Comparacion critica del Machine Learning
- Se entrenaron y guardaron modelos Random Forest y XGBoost por separado,
  incluso cuando una referencia historica es preferible para la proyeccion principal.
- Las predicciones de los modelos ML estan en predicciones_ML_2026_RF_XGBoost.csv.
- No afirmar mejora del ML sobre un baseline sin demostrarla en validacion externa.

## Variables de campo pendientes
Para el modelo ingenieril completo: exportar de Civil 3D radios/geometria rasante;
levantar peraltes y anchos de carril; usar TPDA oficial en vehiculos/dia por tramo/anio.
Guardar una copia de PLANTILLA_geometria_transito_VERIFICADA.csv como
datos/geometria_transito_VERIFICADA.csv, completar valores sin inventar y volver a ejecutar.
El modelo no predice los efectos de redisenos o escenarios HSM/CMF sin datos adecuados.

## Control de disponibilidad de mediciones
- Sin archivo verificado; se usan solo proxies CAD/DSM e historial.

## Interpretacion
Los factores historicos pueden dominar la prediccion; su importancia en el modelo no demuestra
causalidad de radios, pendientes u otros factores. El modelo sirve para priorizar inspecciones.
La validacion usa un solo ano final; se requiere mas historia y verificacion espacial para
demostrar generalizacion e identificar formalmente puntos negros bajo HSM.
La posicion de los marcadores de QGIS es referencial y no debe usarse para replanteo de obra.
