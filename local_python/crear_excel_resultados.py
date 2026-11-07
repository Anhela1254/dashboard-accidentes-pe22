"""Construye un panel XLSX legible desde los CSV resultantes mediante artifact_tool."""
import csv
import json
from pathlib import Path
from artifact_tool import Workbook, SpreadsheetFile

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'resultados'

def carga(n):
    with (OUT/n).open('r',encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def numero(s):
    try:
        x=float(s)
        return round(x,4) if x != int(x) else int(x)
    except (ValueError,TypeError):return s

def escribir(sh,cab,rows, widths=None):
    data=[cab]+[[numero(x) for x in r] for r in rows]
    ncols=len(cab)
    sh.get_range_by_indexes(0,0,len(data),ncols).values=data
    sh.get_range_by_indexes(0,0,1,ncols).format={
      'fill':'#143956','font':{'bold':True,'color':'#FFFFFF'},
      'row_height':34, 'wrap_text':True, 'vertical_alignment':'center'}
    sh.freeze_panes.freeze_rows(1)
    for j,w in enumerate(widths or [17]*ncols):
        sh.get_range_by_indexes(0,j,len(data),1).format.column_width=w
    if len(data)>1:
        sh.get_range_by_indexes(1,0,len(data)-1,ncols).format.row_height=21
    return data


def main():
    resumen=json.loads((OUT/'RESUMEN_RESULTADOS.json').read_text(encoding='utf-8'))
    tramos=carga('resumen_19_tramos.csv')
    comparacion=carga('comparacion_modelos.csv')
    pred=carga('prediccion_2026_por_kilometro.csv')
    ml=carga('predicciones_ML_2026_RF_XGBoost.csv')
    wb=Workbook.create()
    d=wb.worksheets.add('Resumen')
    d.merge_cells('A1:H2')
    d.get_range('A1').values=[['PREDICCIÓN DE SINIESTROS | CARRETERA CENTRAL PE-22']]
    d.get_range('A1:H2').format={'fill':'#143956','font':{'bold':True,'color':'#FFFFFF','size':17},
                                 'row_height':27,'vertical_alignment':'center'}
    d.merge_cells('A3:H3')
    d.get_range('A3').values=[['Estimación exploratoria por km; datos OSITRAN 2022–2025. Cobertura km 39–172.']]
    d.get_range('A3:H3').format={'fill':'#D9E9F1','font':{'color':'#143956'},'row_height':26}
    valores=[['Accidentes aptos para modelar',resumen['n_registros_para_modelo']],
             ['Modelo seleccionado en 2024',resumen['modelo_elegido_validacion_2024']],
             ['MAE prueba 2025',resumen['errores_prueba_2025']['MAE']],
             ['RMSE prueba 2025',resumen['errores_prueba_2025']['RMSE']],
             ['Accidentes proyectados 2026',resumen['suma_predicciones_2026']]]
    d.get_range('A5:B9').values=valores
    d.get_range('A5:A9').format={'fill':'#EAF2F6','font':{'bold':True},'row_height':24}
    d.get_range('A5:A16').format.column_width=35
    d.get_range('B5:B16').format.column_width=23
    d.get_range('A11:B11').values=[['Km prioritario 2026','Accidentes estimados']]
    d.get_range('A11:B11').format={'fill':'#1C698A','font':{'bold':True,'color':'#FFFFFF'},'row_height':24}
    top=pred[:5]
    d.get_range('A12:B16').values=[[f"Km {x['km_inicio']}–{x['km_fin']}", float(x['prediccion_accidentes_2026'])] for x in top]
    d.merge_cells('A19:H19'); d.get_range('A19').values=[['ADVERTENCIA TÉCNICA']]
    d.get_range('A19:H19').format={'fill':'#F7EBCE','font':{'bold':True,'color':'#794D12'},'row_height':25}
    for i,text in enumerate([
      'Los km de accidentes son enteros y las posiciones sobre el eje son referenciales.',
      'Giros CAD y pendientes DSM son proxies, no radios ni pendientes de rasante certificados.',
      'Sin TPDA validado, los resultados indican frecuencia, NO riesgo normalizado por exposición.',
      'La media histórica fue el mejor estimador según MAE 2024; RF y XGBoost están entrenados y comparados.',
      'Las prioridades no son puntos negros formalmente aprobados ni justifican por sí solas un rediseño.'
    ],start=20):
        d.merge_cells(f'A{i}:H{i}')
        d.get_range(f'A{i}').values=[[text]]
        d.get_range(f'A{i}:H{i}').format={'row_height':23,'fill':'#FFF9E9'}

    modelos=wb.worksheets.add('Comparación de modelos')
    escribir(modelos,['Algoritmo / referencia','Esquema temporal','MAE','RMSE','Deviancia de Poisson'],
             [[r['Modelo'],r['Corte'],r['MAE'],r['RMSE'],r['Deviancia_Poisson']] for r in comparacion],
             [25,54,13,13,24])

    st=wb.worksheets.add('19 tramos GIS')
    escribir(st,['Tramo','Sector','2022 obs.','2023 obs.','2024 obs.','2025 obs.',
                 'Pronóstico 2026','Nº km incluidos','Conteo GIS ref.'],
            [[r['tramo'],r['sector'],r['accidentes_hist_2022'],r['accidentes_hist_2023'],
              r['accidentes_hist_2024'],r['accidentes_hist_2025'],
              r['prediccion_total_km_incluidos_2026'],r['n_km_predichos'],
              r['gis_siniestros_referenciales_no_conciliados']] for r in tramos],
            [10,53,16,16,16,16,21,18,20])
    st.get_range('G2:G20').conditional_formats.add_data_bar({'color':'#2B7B9D','gradient':True})

    sk=wb.worksheets.add('Prioridad por km')
    escribir(sk,['Puesto','Km ini','Km fin','Tramo','Sector','Siniestros 2025',
                'Predicción 2026','Prioridad relativa','Pendiente DSM proxy (%)',
                'Giro CAD proxy (grados)'],
            [[r['puesto'],r['km_inicio'],r['km_fin'],r['tramo_gis_ref'],r['sector_gis_ref'],
              r['accidentes_2025'],r['prediccion_accidentes_2026'],
              r['nivel_prioridad_relativa'],r['pendiente_dsm_proxy_pct'],r['giro_cad_proxy_grados']]
             for r in pred], [10,10,10,10,54,18,19,24,23,26])
    sk.get_range('G2:G135').conditional_formats.add_data_bar({'color':'#C77755','gradient':True})

    sf=wb.worksheets.add('ML - Random Forest XGBoost')
    escribir(sf,['Modelo','Km ini','Km fin','Tramo','Predicción 2026 ML'],
            [[r['modelo'],r['km_inicio'],r['km_fin'],r['tramo'],r['accidentes_estimados_2026']] for r in ml],
            [22,12,12,14,23])
    sf.get_range('E2:E269').conditional_formats.add_data_bar({'color':'#247B74','gradient':True})

    metod=wb.worksheets.add('Limitaciones')
    disclaimers=[
      ['A. Fuentes','OSITRAN unificado y depurado; CSV CAD/DSM; tramos QGIS referenciales.'],
      ['B. Entrenamiento','2023; validación 2024; prueba independiente 2025; ajuste final 2023–2025.'],
      ['C. Resolución','1 km, por ser el kilometraje de siniestros entero; no apto para delimitar 100–200 m.'],
      ['D. Geometría','No hay radios, peraltes, ancho y TPDA validados por cada km; no se simulan.'],
      ['E. Predicción','2026: previsión exploratoria, no hecho observado.'],
      ['F. Riesgo','Clasificación relativa por número esperado; no tasa de accidente por veh-km.'],
      ['G. Métodos','Se compara ML contra referencias; no se presupone mayor precisión del ML.'],
    ]
    escribir(metod,['Aspecto','Definición'],disclaimers,[25,105])
    try:
        graf=d.charts.add('bar',d.get_range('A11:B16'))
        graf.title_text='Cinco km con mayor frecuencia prevista 2026'
        graf.set_position('D5','N17')
    except Exception as exc:
        print('Gráfico XLSX omitido:',exc)
    destino=OUT/'RESULTADOS_MODELO_ACCIDENTES.xlsx'
    SpreadsheetFile.export_xlsx(wb).save(str(destino))
    print('XLSX creado:',destino)
    print(wb.inspect({'kind':'table','range':'Resumen!A5:B9','include':'values','table_max_rows':5,'table_max_cols':2}).ndjson[:1500])
    print(wb.inspect({'kind':'match','search_term':'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A',
                      'options':{'use_regex':True,'max_results':30}}).ndjson[:1200])

if __name__=='__main__':main()
