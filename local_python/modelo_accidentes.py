#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CARRETERA CENTRAL (PE-22) - MACHINE LEARNING EXPLORATORIO
Frecuencia anual de accidentes por kilometro: entrenamiento 2023, validacion 2024,
prueba independiente 2025 y proyeccion 2026.

ADVERTENCIAS: km enteros OSITRAN con eje por verificar. CAD/DSM genera PROXIES
referenciales, NO radios de curva ni pendientes de rasante certificados.
Sin TPDA verificado no estima tasas ajustadas por exposicion ni efectos causales.
"""
from __future__ import annotations
import csv
import json
import math
import warnings
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import joblib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_poisson_deviance
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBRegressor
    TIENE_XGBOOST = True
except ImportError:
    TIENE_XGBOOST = False

BASE = Path(__file__).resolve().parent
DATOS = BASE / 'datos'
SALIDA = BASE / 'resultados'
SALIDA.mkdir(exist_ok=True)
KM_MIN, KM_MAX = 39, 172  # >=39 y <173; km entero original, sesgo de ubicacion presente
ANIOS = [2022, 2023, 2024, 2025]
SEMILLA = 42

plt.rcParams.update({'figure.dpi': 130, 'savefig.dpi': 160,
                     'font.size': 10, 'axes.titlesize': 13,
                     'axes.labelsize': 10, 'figure.facecolor': 'white',
                     'axes.spines.top': False, 'axes.spines.right': False})


def leer_csv(p):
    with Path(p).open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def guardar_csv(nombre, columnas, filas):
    path = SALIDA / nombre
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction='ignore')
        w.writeheader()
        for row in filas:
            w.writerow({k: normalizar_export(row.get(k, '')) for k in columnas})
    return path


def normalizar_export(v):
    if v is None: return ''
    if isinstance(v, np.generic):return v.item()
    if isinstance(v, float) and not np.isfinite(v):return ''
    return v


def numero(v, fallback=None):
    try:
        if v is None or str(v).strip() == '':return fallback
        val = float(str(v).replace(',', '.'))
        return val if math.isfinite(val) else fallback
    except (TypeError, ValueError):return fallback


def cargar_accidentes():
    datos = leer_csv(DATOS / 'registros_originales_2022_2025.csv')
    validos, descartados = [], Counter()
    por_ano = Counter()
    ids = set()
    for r in datos:
        fuente = r['Fuentes conservadas'].strip()
        if fuente != 'OSITRAN':
            descartados['Fuente externa (conciliacion pendiente)'] += 1
            continue
        ano = int(numero(r.get('Año'), 0))
        por_ano[ano] += 1
        if ano not in ANIOS:
            descartados['Anio fuera de 2022-2025'] += 1
            continue
        ident = r['ID lista'].strip()
        if ident in ids:
            descartados['ID repetido'] += 1
            continue
        ids.add(ident)
        # No computar registros que segun la propia base requieren conciliacion.
        if r.get('Estado de revisión', '').strip() != 'SIN DUPLICADO CONFIRMADO' \
           or r.get('Registros relacionados', '').strip():
            descartados['Evento OSITRAN relacionado o en revision'] += 1
            continue
        km = numero(r.get('Km registrado o extraído'))
        if km is None or not float(km).is_integer():
            descartados['Kilometraje ausente/no entero'] += 1
            continue
        km = int(km)
        if not (KM_MIN <= km <= KM_MAX):
            descartados['Fuera de cobertura GIS 39-172'] += 1
            continue
        validos.append({'id': ident, 'ano': ano, 'km': km,
                        'tipo': r.get('Tipo de siniestro', '').upper(),
                        'fuente': fuente})
    print('Registros de entrada:', len(datos), '| OSITRAN por ano:', dict(sorted(por_ano.items())))
    print('Incluidos al modelo:', len(validos), '| Descartados:', dict(descartados))
    return validos, descartados, por_ano


def cargar_tramos():
    tramos = []
    for r in leer_csv(DATOS / 'tramos_gis_referenciales.csv'):
        tramos.append({'id': r['id_tramo'], 'ini': float(r['km_ini']),
                       'fin': float(r['km_fin']), 'sector': r['sector'],
                       'n_gis_referencial': int(r['accidentes_gis_referenciales'])})
    tramos.sort(key=lambda t: t['ini'])
    return tramos


def asignar_tramo(km, tramos):
    p = km + 0.5
    for t in tramos:
        if t['ini'] <= p < t['fin']:
            return t['id'], t['sector']
    return 'SIN_TRAMO', ''


def cargar_proxies_cad():
    # Seleccion solo de marcas CAD proyectadas al eje (<=25m). No es geometria certificada.
    registros = []
    for r in leer_csv(DATOS / 'progresivas_cad_dsm.csv'):
        if r.get('METODO') != 'Rotulo CAD proyectado al eje':continue
        if numero(r.get('DIST_TEXTO'), 999) > 25:continue
        metros = numero(r.get('METROS'))
        x, y = numero(r.get('X')), numero(r.get('Y'))
        if None in (metros, x, y):continue
        registros.append({'metros': metros, 'x': x, 'y': y,
                          'z': numero(r.get('COTA_DSM'))})
    registros.sort(key=lambda d: d['metros'])
    por_km_pendiente = defaultdict(list)
    por_km_angulo = defaultdict(list)
    for anterior, actual in zip(registros, registros[1:]):
        paso = actual['metros']-anterior['metros']
        if not (75 <= paso <= 125):continue
        if anterior['z'] is not None and actual['z'] is not None:
            # No es pendiente de rasante; deriva de cota DSM, con error del terreno.
            pendiente = abs(actual['z']-anterior['z']) / paso * 100
            if math.isfinite(pendiente) and pendiente < 100:
                por_km_pendiente[int(anterior['metros']//1000)].append(pendiente)
    for i in range(1, len(registros)-1):
        p, c, q = registros[i-1:i+2]
        if not (75 <= c['metros']-p['metros'] <= 125 and
                75 <= q['metros']-c['metros'] <= 125):continue
        a = np.array([c['x']-p['x'], c['y']-p['y']], dtype=float)
        b = np.array([q['x']-c['x'], q['y']-c['y']], dtype=float)
        la, lb = np.linalg.norm(a), np.linalg.norm(b)
        if not (35 <= la <= 180 and 35 <= lb <= 180):continue
        costheta = np.clip(float(a @ b / (la*lb)), -1, 1)
        grados = float(np.degrees(np.arccos(costheta)))
        if grados <= 60:por_km_angulo[int(c['metros']//1000)].append(grados)
    proxies = {}
    for km in range(KM_MIN, KM_MAX+1):
        pend = por_km_pendiente.get(km, [])
        giros = por_km_angulo.get(km, [])
        proxies[km] = {
            'pendiente_dsm_proxy_pct': float(np.median(pend)) if len(pend)>=4 else np.nan,
            'giro_cad_proxy_grados': float(sum(giros)) if len(giros)>=4 else np.nan,
            'n_tramos_dsm': len(pend), 'n_angulos_cad': len(giros)}
    return proxies, registros


def cargar_geometria_verificada():
    """Solo leer datos medidos que el investigador rellene en la copia sin prefijo PLANTILLA."""
    ruta = DATOS / 'geometria_transito_VERIFICADA.csv'
    columnas = ['radio_curva_m', 'pendiente_longitudinal_pct',
                'peralte_pct', 'ancho_carril_m', 'tpda_veh_dia']
    if not ruta.exists():
        return {}, [], ['Sin archivo verificado; se usan solo proxies CAD/DSM e historial.']
    datos = {}
    for r in leer_csv(ruta):
        km = numero(r.get('km_inicio'))
        if km is None or not float(km).is_integer():continue
        km = int(km)
        if KM_MIN <= km <= KM_MAX:
            datos[km] = {col: numero(r.get(col)) for col in columnas}
    # Campos incompletos se excluyen del aprendizaje, nunca inventar imputaciones generalizadas.
    lista = [col for col in columnas if sum(datos.get(k,{}).get(col) is not None
                                                for k in range(KM_MIN, KM_MAX+1))
             >= int(0.9*(KM_MAX-KM_MIN+1))]
    avisos = [f'Campo medido disponible {col} en >=90% de km' for col in lista]
    avisos += [f'Campo {col}: excluido por cobertura menor al 90%'
               for col in columnas if col not in lista]
    return datos, lista, avisos


def construir_panel(accidentes, tramos, proxies, geo_medida, campos_medidos):
    counts = Counter((x['ano'], x['km']) for x in accidentes)
    desp = Counter((x['ano'], x['km']) for x in accidentes if 'DESPISTE' in x['tipo'])
    panel = []
    for ano in [2023, 2024, 2025, 2026]:
        for km in range(KM_MIN, KM_MAX+1):
            h = [counts[(prev, km)] for prev in range(2022, ano)]
            if not h:continue
            tramo, sector = asignar_tramo(km, tramos)
            row = {'ano_prediccion': ano, 'km_inicio': km,
                   'km_fin': km+1, 'tramo_gis_ref': tramo,
                   'sector_gis_ref': sector,
                   'accidentes_observados': counts[(ano,km)] if ano<=2025 else np.nan,
                   'accidentes_ano_previo': float(h[-1]),
                   'accidentes_media_historica': float(np.mean(h)),
                   'accidentes_max_historico': float(max(h)),
                   'accidentes_tendencia': float(h[-1]-h[-2]) if len(h)>=2 else 0.0,
                   'despistes_ano_previo': float(desp[(ano-1,km)]),
                   'n_anos_historicos': len(h),
                   **proxies[km]}
            for col in campos_medidos:
                row[col] = geo_medida.get(km,{}).get(col, np.nan)
            panel.append(row)
    columnas = ['accidentes_ano_previo', 'accidentes_media_historica',
                'accidentes_max_historico','accidentes_tendencia',
                'despistes_ano_previo','pendiente_dsm_proxy_pct',
                'giro_cad_proxy_grados', 'km_inicio'] + campos_medidos
    return panel, columnas, counts


def matriz(rows, columnas):
    return np.array([[np.nan if r.get(col) is None else r.get(col, np.nan)
                      for col in columnas] for r in rows], dtype=float)


def modelos():
    lista = {
        'Random Forest': make_pipeline(SimpleImputer(strategy='median'),
             RandomForestRegressor(n_estimators=320, max_depth=7, min_samples_leaf=4,
                                   max_features=0.8, random_state=SEMILLA, n_jobs=-1)),
        'Poisson': make_pipeline(SimpleImputer(strategy='median'),
                    StandardScaler(), PoissonRegressor(alpha=1.0, max_iter=1500)),
    }
    if TIENE_XGBOOST:
        lista['XGBoost'] = make_pipeline(SimpleImputer(strategy='median'),
                    XGBRegressor(n_estimators=320, learning_rate=0.035,
                                 max_depth=3, min_child_weight=7,
                                 reg_lambda=8, subsample=0.85,
                                 colsample_bytree=0.9, objective='count:poisson',
                                 random_state=SEMILLA, n_jobs=2))
    return lista


def estadisticas(y, p):
    p = np.maximum(np.asarray(p, dtype=float), 0)
    return {'MAE': round(float(mean_absolute_error(y,p)), 4),
            'RMSE': round(float(np.sqrt(mean_squared_error(y,p))), 4),
            'Deviancia_Poisson': round(float(mean_poisson_deviance(y, np.maximum(p,1e-6))),4)}


def entrenar_y_predecir(panel, campos):
    por_anio = {a:[r for r in panel if r['ano_prediccion']==a] for a in [2023,2024,2025,2026]}
    x23 = matriz(por_anio[2023], campos); y23=np.array([r['accidentes_observados'] for r in por_anio[2023]])
    x24 = matriz(por_anio[2024], campos); y24=np.array([r['accidentes_observados'] for r in por_anio[2024]])
    x25 = matriz(por_anio[2025], campos); y25=np.array([r['accidentes_observados'] for r in por_anio[2025]])
    x26 = matriz(por_anio[2026], campos)
    registro_metricas = []
    val = {}
    for nombre, modelo in modelos().items():
        modelo.fit(x23,y23)
        p24 = np.maximum(modelo.predict(x24),0)
        val[nombre] = estadisticas(y24,p24)
        registro_metricas.append({'Modelo':nombre, 'Corte':'Validacion 2024 (entrenado 2023)', **val[nombre]})
    for nombre, vfunc in [('Media histórica', lambda rows: [r['accidentes_media_historica'] for r in rows]),
                          ('Último año', lambda rows: [r['accidentes_ano_previo'] for r in rows])]:
        p24 = np.array(vfunc(por_anio[2024]),dtype=float)
        val[nombre] = estadisticas(y24, p24)
        registro_metricas.append({'Modelo':nombre,'Corte':'Validacion 2024 (referencia sin entrenamiento)',**val[nombre]})
    mejor = min(val, key=lambda m: (val[m]['MAE'], val[m]['RMSE']))
    print('Modelo elegido por MAE 2024:', mejor)

    x2324 = np.vstack((x23,x24)); y2324=np.r_[y23,y24]
    test25 = {}
    for nombre, modelo in modelos().items():
        modelo.fit(x2324,y2324)
        pred=np.maximum(modelo.predict(x25),0)
        test25[nombre] = pred
        registro_metricas.append({'Modelo':nombre, 'Corte':'Prueba 2025 (entrenado 2023-2024)',**estadisticas(y25,pred)})
    for nombre, col in [('Media histórica','accidentes_media_historica'),
                        ('Último año','accidentes_ano_previo')]:
        pred=np.array([r[col] for r in por_anio[2025]],dtype=float)
        test25[nombre] = pred
        registro_metricas.append({'Modelo':nombre,'Corte':'Prueba 2025 (referencia)',**estadisticas(y25,pred)})

    if mejor in modelos():
        modelo_final = modelos()[mejor]
        modelo_final.fit(np.vstack((x23,x24,x25)), np.r_[y23,y24,y25])
        pred26 = np.maximum(modelo_final.predict(x26),0)
        joblib.dump({'modelo': modelo_final,'columnas': campos,
                     'resolucion':'1 km referencial',
                     'entrenamiento':'2023-2025; variables 2022-2025'}, SALIDA/'modelo_entrenado.joblib')
    else:
        campo = 'accidentes_media_historica' if mejor=='Media histórica' else 'accidentes_ano_previo'
        pred26 = np.array([r[campo] for r in por_anio[2026]],dtype=float)
        joblib.dump({'modelo': mejor, 'campo_baseline': campo, 'columnas': campos,
                     'resolucion':'1 km referencial'}, SALIDA/'modelo_entrenado.joblib')

    # Entrenar y guardar tambien los modelos ML solicitados, aunque un baseline gane.
    xcompleto=np.vstack((x23,x24,x25)); ycompleto=np.r_[y23,y24,y25]
    registros_pred_ml=[]
    for nombre in ('Random Forest','XGBoost'):
        if nombre not in modelos(): continue
        estimador=modelos()[nombre]
        estimador.fit(xcompleto, ycompleto)
        joblib.dump({'modelo':estimador,'columnas':campos,
                     'tipo':'regresion de conteos por km y ano',
                     'cobertura':'km 39-172 provisional; sin TPDA verificado'},
                    SALIDA / ('modelo_'+nombre.replace(' ','_')+'_entrenado.joblib'))
        pronostico=np.maximum(estimador.predict(x26),0)
        for fila,pr in zip(por_anio[2026],pronostico):
            registros_pred_ml.append({'modelo':nombre, 'km_inicio':fila['km_inicio'],
                                     'km_fin':fila['km_fin'],'tramo':fila['tramo_gis_ref'],
                                     'accidentes_estimados_2026':round(float(pr),4)})
    if registros_pred_ml:
        guardar_csv('predicciones_ML_2026_RF_XGBoost.csv',
                    list(registros_pred_ml[0]),registros_pred_ml)

    datosprueba=[]
    for r, pp in zip(por_anio[2025], test25[mejor]):
        datosprueba.append({'km_inicio':r['km_inicio'],'tramo_gis_ref':r['tramo_gis_ref'],
                            'observado_2025':int(r['accidentes_observados']),
                            'predicho_2025':round(float(pp),3),
                            'error_absoluto':round(abs(float(pp)-r['accidentes_observados']),3)})
    guardar_csv('validacion_independiente_2025.csv',list(datosprueba[0]),datosprueba)
    guardar_csv('comparacion_modelos.csv',['Modelo','Corte','MAE','RMSE','Deviancia_Poisson'],registro_metricas)
    return mejor, registro_metricas, pred26, por_anio[2026], test25[mejor], y25


def clasificar_predicciones(rows, pred):
    lim_alto=float(np.quantile(pred,.8))
    lim_medio=float(np.quantile(pred,.5))
    salida=[]
    for r, p in zip(rows,pred):
        nivel = ('ALTA (top 20%)' if p>=lim_alto else 'MEDIA' if p>=lim_medio else 'BAJA')
        salida.append({'km_inicio':r['km_inicio'], 'km_fin':r['km_fin'],
                       'tramo_gis_ref':r['tramo_gis_ref'], 'sector_gis_ref':r['sector_gis_ref'],
                       'accidentes_2025':int(r['accidentes_ano_previo']),
                       'media_historica_2022_2025':round(r['accidentes_media_historica'],3),
                       'prediccion_accidentes_2026':round(float(p),3),
                       'nivel_prioridad_relativa':nivel,
                       'pendiente_dsm_proxy_pct':normalizar_export(r['pendiente_dsm_proxy_pct']),
                       'giro_cad_proxy_grados':normalizar_export(r['giro_cad_proxy_grados']),
                       'ubicacion':'PROVISIONAL: kilometraje entero; eje CAD por verificar'})
    salida.sort(key=lambda d: d['prediccion_accidentes_2026'], reverse=True)
    for i,d in enumerate(salida,1): d['puesto'] = i
    guardar_csv('prediccion_2026_por_kilometro.csv',
                ['puesto']+list(salida[0].keys())[:-1],salida)
    return salida


def resumen_por_tramos(pred, accidentes, tramos):
    acc = Counter()
    for a in accidentes:
        tr,_ = asignar_tramo(a['km'], tramos)
        acc[(tr,a['ano'])] += 1
    forecast = defaultdict(float)
    for r in pred:
        forecast[r['tramo_gis_ref']] += r['prediccion_accidentes_2026']
    resumen=[]
    for t in tramos:
        v=forecast[t['id']]
        resumen.append({'tramo':t['id'], 'sector':t['sector'],
                       'km_inicio_gis':t['ini'],'km_fin_gis':t['fin'],
                       'accidentes_hist_2022':acc[(t['id'],2022)],
                       'accidentes_hist_2023':acc[(t['id'],2023)],
                       'accidentes_hist_2024':acc[(t['id'],2024)],
                       'accidentes_hist_2025':acc[(t['id'],2025)],
                       'prediccion_total_km_incluidos_2026':round(v,3),
                       'n_km_predichos':sum(r['tramo_gis_ref']==t['id'] for r in pred),
                       'gis_siniestros_referenciales_no_conciliados':t['n_gis_referencial']})
    resumen.sort(key=lambda d: d['prediccion_total_km_incluidos_2026'],reverse=True)
    guardar_csv('resumen_19_tramos.csv',list(resumen[0]),resumen)
    return resumen


def generar_graficos(accidentes, pred, test_pred, test_y, cols, mejor):
    historical=Counter(x['ano'] for x in accidentes)
    fig,ax=plt.subplots(figsize=(8.7,4.3))
    ax.bar([str(y) for y in ANIOS], [historical[y] for y in ANIOS], color='#166083',alpha=.9)
    for i,y in enumerate(ANIOS):ax.text(i,historical[y]+5,str(historical[y]),ha='center',fontsize=10)
    ax.set_title('Accidentes OSITRAN por año - km 39 a 172 (filtrados)')
    ax.set_ylabel('Accidentes registrados');ax.set_ylim(0,max(historical.values())*1.15)
    fig.tight_layout();fig.savefig(SALIDA/'01_historia_2022_2025.png');plt.close(fig)

    fig,ax=plt.subplots(figsize=(6.6,5.2))
    ax.scatter(test_y,test_pred,alpha=.65,c='#148a87',s=35)
    superior=max(10,float(np.max(test_y)),float(np.max(test_pred)))+2
    ax.plot([0,superior],[0,superior],ls='--',c='#b75448',lw=1.5)
    ax.set_xlim(0,superior);ax.set_ylim(0,superior)
    ax.set_xlabel('Accidentes observados 2025')
    ax.set_ylabel('Predicción sin datos futuros de 2025')
    ax.set_title(f'Prueba temporal 2025 - {mejor}')
    fig.tight_layout();fig.savefig(SALIDA/'02_validacion_2025.png');plt.close(fig)

    top=sorted(pred, key=lambda r:r['prediccion_accidentes_2026'],reverse=True)[:20]
    fig,ax=plt.subplots(figsize=(9.2,6))
    labels=[f"Km {v['km_inicio']}-{v['km_fin']}" for v in top[::-1]]
    vals=[v['prediccion_accidentes_2026'] for v in top[::-1]]
    ax.barh(labels, vals,color='#cb7349')
    ax.set_title('20 km prioritarios estimados para 2026 (exploratorio)')
    ax.set_xlabel('Accidentes/año estimados - sin ajuste TPDA')
    fig.tight_layout();fig.savefig(SALIDA/'03_top20_2026.png');plt.close(fig)

    # Mostrar importancias de RF incluso si fue elegido otro modelo, rotulado claramente.
    panel = leer_panel_cache()
    arr_train=[r for r in panel if r['ano_prediccion'] in [2023,2024,2025]]
    X=matriz(arr_train,cols)
    Y=np.array([r['accidentes_observados'] for r in arr_train])
    rf=modelos()['Random Forest'];rf.fit(X,Y)
    imps=rf[-1].feature_importances_
    ord_idx=np.argsort(imps)[::-1]
    fig,ax=plt.subplots(figsize=(8.6,5.2))
    ax.barh([cols[i].replace('_',' ') for i in ord_idx[::-1]],imps[ord_idx[::-1]],color='#226b7e')
    ax.set_title('Importancia predictiva de variables - Random Forest (no causal)')
    ax.set_xlabel('Importancia relativa del modelo')
    fig.tight_layout();fig.savefig(SALIDA/'04_importancia_variables_RF.png');plt.close(fig)
    guardar_csv('importancia_variables_RF.csv',['variable','importancia'],
                [{'variable':cols[i],'importancia':round(float(imps[i]),5)} for i in ord_idx])


def guardar_panel_cache(panel, columnas):
    headers=['ano_prediccion','km_inicio','km_fin','tramo_gis_ref','sector_gis_ref',
             'accidentes_observados']+columnas
    guardar_csv('panel_entrenamiento_anual.csv',headers,panel)


def leer_panel_cache():
    rows=leer_csv(SALIDA/'panel_entrenamiento_anual.csv')
    for r in rows:
        for k,v in list(r.items()):
            if k in ('tramo_gis_ref','sector_gis_ref'):continue
            r[k]=numero(v,np.nan)
    return rows


def exportar_geojson(pred, cad):
    try:
        from pyproj import Transformer
        transform=Transformer.from_crs('EPSG:32718','EPSG:4326',always_xy=True)
    except ImportError:
        print('pyproj no instalado: mapa espacial omitido')
        return
    features=[]
    for r in pred:
        km=r['km_inicio']
        centro=(km+0.5)*1000
        marcador=min(cad,key=lambda p:abs(p['metros']-centro))
        lon,lat=transform.transform(marcador['x'], marcador['y'])
        if not (-15 < lat < -9 and -80 < lon < -74):continue
        prop={k:normalizar_export(v) for k,v in r.items() if k not in ('sector_gis_ref',)}
        prop['sector_gis_ref']=r['sector_gis_ref']
        prop['nota_posicion']='Marca CAD aproximada al centro del km; ubicacion provisional'
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[lon,lat]},
                         'properties':prop})
    data={'type':'FeatureCollection','features':features}
    (SALIDA/'predicciones_2026_QGIS.geojson').write_text(
        json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        import folium
        fmap=folium.Map(location=[-11.85,-76.40],zoom_start=9,tiles='OpenStreetMap',control_scale=True)
        colores={'ALTA (top 20%)':'#C14949','MEDIA':'#E0A342','BAJA':'#238973'}
        for f in features:
            pr=f['properties'];lat,lon=f['geometry']['coordinates'][::-1]
            texto=(f"<b>Km {pr['km_inicio']}-{pr['km_fin']}</b><br>"
                   f"Pred. 2026: {pr['prediccion_accidentes_2026']:.2f} accidentes/año<br>"
                   f"Prioridad: {pr['nivel_prioridad_relativa']}<br>"
                   'Posicion CAD aproximada; verificar en campo')
            folium.CircleMarker([lat,lon],radius=5,weight=1,
                                color=colores[pr['nivel_prioridad_relativa']],
                                fill=True,fill_opacity=.75,popup=texto).add_to(fmap)
        fmap.save(str(SALIDA/'mapa_interactivo_2026.html'))
    except ImportError:pass


def escribir_reporte(accidentes, descartados, por_ano, mejor, metricas, pred, resumen, avisos, campos):
    test=next(d for d in metricas if d['Modelo']==mejor and d['Corte'].startswith('Prueba'))
    v=next(d for d in metricas if d['Modelo']==mejor and d['Corte'].startswith('Validacion'))
    annual=Counter(a['ano'] for a in accidentes)
    total=float(sum(v['prediccion_accidentes_2026'] for v in pred))
    texto=[
        '# Informe reproducible - Modelo predictivo de accidentes (PE-22)',
        '',
        '## Propósito',
        'Evaluar frecuencia anual estimada de accidentes registrados en los km enteros 39 a 172',
        'de la Carretera Central, con historial OSITRAN 2022-2025. Clasificacion relativa,',
        'NO declaratoria oficial de punto negro ni inferencia causal.',
        '',
        '## Evidencia y filtros',
        f'- Registros aceptados para el modelo: {len(accidentes)}.',
        '- Registros externos ONSV/MTC excluidos por conciliacion pendiente.',
        '- Registros OSITRAN relacionados/pendientes excluidos (para evitar potencial duplicidad).',
        '- Ubicacion por km entero y eje vial referencial por verificar; no se permite inferir puntos de 100-200m.',
        '- Progresivas CAD: marcas proyectadas al eje si distancias al texto <=25m.',
        '- Cotas Copernicus DSM: proxy del relieve, NO pendiente longitudinal certificada.',
        '- Giro entre marcas CAD: proxy de sinuosidad, NO radio de curva medido.',
        '- El Formato 3B MTC registra danos del pavimento, no un inventario verificado de radios, peraltes o TPDA.',
        '- Tabla BLACKSPOT: TPDA sin unidad/escala documentada; no usar como vehiculos/dia.',
        '- Las cifras agregadas de victimas no se suman por discrepancias entre las fuentes.',
        f'- Accidentes por ano incluidos: {dict(sorted(annual.items()))}.',
        f'- Otras exclusiones: {dict(descartados)}.',
        '',
        '## Protocolo de aprendizaje automatico',
        '- 134 unidades por ano (km 39-40 ... km 172-173), con celdas de cero accidentes incluidas.',
        '- 2022 sirve solo como antecedente temporal; 2023 entrenamiento inicial.',
        '- 2024 validacion para seleccionar modelo por menor MAE (desempate RMSE).',
        '- 2025 prueba temporal independiente; el modelo seleccionado se ajusta usando 2023-2024.',
        '- 2026 proyeccion exploratoria; reajuste final del modelo con 2023-2025.',
        '- Tecnicas: Random Forest, Poisson, XGBoost (opcional), y baselines de media historica y ultimo ano.',
        '- Variables de accidentes historicos solo de anos ANTERIORES al predicho; se evita fuga temporal.',
        f'- Variables del modelo: {", ".join(campos)}.',
        '',
        '## Resultados de comprobacion',
        f'- Modelo elegido exclusivamente con validacion 2024: **{mejor}**.',
        f'- Validacion 2024: MAE={v["MAE"]:.3f}, RMSE={v["RMSE"]:.3f}.',
        f'- Prueba temporal 2025: MAE={test["MAE"]:.3f}, RMSE={test["RMSE"]:.3f}, '
        f'Deviancia Poisson={test["Deviancia_Poisson"]:.3f}.',
        f'- Proyeccion total 2026 en km incluidos: {total:.1f} accidentes/anio (no todo el tramo Lima-La Oroya).',
        '- Prioridad ALTA = top 20% de kilometros por frecuencia predicha; umbral RELATIVO, no norma vial.',
        '',
        '## Cinco kilometros de mayor prioridad exploratoria',
    ]
    texto += [f"{i}. Km {r['km_inicio']}-{r['km_fin']}, {r['tramo_gis_ref']}: "
              f"{r['prediccion_accidentes_2026']:.2f} accidentes estimados en 2026"
              for i,r in enumerate(pred[:5],1)]
    texto += ['', '## Cinco tramos de mayor frecuencia agregada proyectada',
              'IMPORTANTE: los tramos no tienen igual longitud; esta no es una tasa por vehiculo-km.']
    texto += [f"{i}. {r['tramo']}, {r['sector']}: "
              f"{r['prediccion_total_km_incluidos_2026']:.2f} accidentes en km incluidos"
              for i,r in enumerate(resumen[:5],1)]
    texto += ['', '## Comparacion critica del Machine Learning',
              '- Se entrenaron y guardaron modelos Random Forest y XGBoost por separado,',
              '  incluso cuando una referencia historica es preferible para la proyeccion principal.',
              '- Las predicciones de los modelos ML estan en predicciones_ML_2026_RF_XGBoost.csv.',
              '- No afirmar mejora del ML sobre un baseline sin demostrarla en validacion externa.',
              '', '## Variables de campo pendientes',
              'Para el modelo ingenieril completo: exportar de Civil 3D radios/geometria rasante;',
              'levantar peraltes y anchos de carril; usar TPDA oficial en vehiculos/dia por tramo/anio.',
              'Guardar una copia de PLANTILLA_geometria_transito_VERIFICADA.csv como',
              'datos/geometria_transito_VERIFICADA.csv, completar valores sin inventar y volver a ejecutar.',
              'El modelo no predice los efectos de redisenos o escenarios HSM/CMF sin datos adecuados.',
              '', '## Control de disponibilidad de mediciones']
    texto += ['- '+a for a in avisos]
    texto += ['', '## Interpretacion',
              'Los factores historicos pueden dominar la prediccion; su importancia en el modelo no demuestra',
              'causalidad de radios, pendientes u otros factores. El modelo sirve para priorizar inspecciones.',
              'La validacion usa un solo ano final; se requiere mas historia y verificacion espacial para',
              'demostrar generalizacion e identificar formalmente puntos negros bajo HSM.',
              'La posicion de los marcadores de QGIS es referencial y no debe usarse para replanteo de obra.',
              '']
    (SALIDA/'INFORME_METODOLOGICO.md').write_text('\n'.join(texto),encoding='utf-8')
    resumen_json={
       'modelo_elegido_validacion_2024':mejor,
       'n_registros_para_modelo':len(accidentes),
       'anios_y_cuentas':dict(annual),
       'errores_prueba_2025':test,
       'suma_predicciones_2026':round(total,2),
       'km_cobertura':'39-172 (intervalos 39-40 a 172-173)',
       'advertencia':'Riesgo relativo exploratorio; CAD/DSM no es geometria certificada; falta TPDA verificado',
       'variables':campos,
       'exclusiones':dict(descartados)}
    (SALIDA/'RESUMEN_RESULTADOS.json').write_text(json.dumps(resumen_json,indent=2,ensure_ascii=False),encoding='utf-8')
    print('2025 (prueba independiente):',test)
    print('2026 total proyectado:',round(total,1))
    print('5 km prioritarios:',[(r['km_inicio'],r['prediccion_accidentes_2026']) for r in pred[:5]])


def main():
    np.random.seed(SEMILLA)
    accidentes, descartados, por_ano = cargar_accidentes()
    tramos = cargar_tramos()
    proxies, cad = cargar_proxies_cad()
    geo_medida, campos_medidos, avisos=cargar_geometria_verificada()
    panel, columnas, counts=construir_panel(accidentes,tramos,proxies,geo_medida,campos_medidos)
    guardar_panel_cache(panel,columnas)
    mejor,metricas, pred_2026, rows_2026, pred_2025, real_2025=entrenar_y_predecir(panel,columnas)
    pred=clasificar_predicciones(rows_2026,pred_2026)
    resumen=resumen_por_tramos(pred,accidentes,tramos)
    generar_graficos(accidentes,pred,pred_2025,real_2025,columnas,mejor)
    exportar_geojson(pred,cad)
    escribir_reporte(accidentes, descartados,por_ano,mejor,metricas,pred,resumen,avisos,columnas)
    print('Archivos generados en:', SALIDA)

if __name__=='__main__':
    main()
