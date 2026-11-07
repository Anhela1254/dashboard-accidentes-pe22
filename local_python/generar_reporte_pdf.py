"""Reporte sintético PDF con trazabilidad de resultados, generado desde CSV."""
from pathlib import Path
import csv
import json
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

ROOT=Path(__file__).resolve().parent
O=ROOT/'resultados'
FUENTE='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FUENTE_B='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
pdfmetrics.registerFont(TTFont('DejaVu',FUENTE))
pdfmetrics.registerFont(TTFont('DejaVuBold',FUENTE_B))


def csvrows(name):
    with (O/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def pp(text,style):return Paragraph(text,style)


def main():
    info=json.loads((O/'RESUMEN_RESULTADOS.json').read_text(encoding='utf-8'))
    comp=csvrows('comparacion_modelos.csv')
    top=csvrows('prediccion_2026_por_kilometro.csv')[:5]
    st=getSampleStyleSheet()
    st.add(ParagraphStyle(name='Tit',fontName='DejaVuBold',fontSize=18,leading=24,textColor=colors.HexColor('#153D59'),spaceAfter=14))
    st.add(ParagraphStyle(name='Sub',fontName='DejaVuBold',fontSize=11.2,leading=16,textColor=colors.HexColor('#1B667C'),spaceBefore=12,spaceAfter=7))
    st.add(ParagraphStyle(name='CuerpoES',fontName='DejaVu',fontSize=9.1,leading=15,textColor=colors.HexColor('#2C3B43'),spaceAfter=8))
    st.add(ParagraphStyle(name='Chico',fontName='DejaVu',fontSize=7.6,leading=11,textColor=colors.HexColor('#485862')))
    st.add(ParagraphStyle(name='Tab',fontName='DejaVu',fontSize=8,leading=12,textColor=colors.HexColor('#233A48')))
    st.add(ParagraphStyle(name='TabB',fontName='DejaVuBold',fontSize=8,leading=12,textColor=colors.white))

    def p(t):return pp(t,st['CuerpoES'])
    def sub(t):return pp(t,st['Sub'])
    doc=SimpleDocTemplate(str(O/'INFORME_MODELO_PREDICTIVO.pdf'),pagesize=(21*cm,29.7*cm),
           leftMargin=1.9*cm,rightMargin=1.9*cm,topMargin=1.7*cm,bottomMargin=1.8*cm,
           title='Modelo predictivo de accidentes - PE-22',author='Análisis computacional reproducible')
    flow=[]
    flow += [pp('Modelo predictivo de accidentes mediante Machine Learning',st['Tit']),
             p('<b>Aplicación:</b> tramo de estudio Lima–La Oroya de la Carretera Central (PE-22). '
               '<b>Periodo de entrada:</b> 2022–2025. <b>Pronóstico exploratorio:</b> año completo 2026, '
               'únicamente km enteros 39–172. No se trata de una predicción normalizada por tránsito.'),
             sub('1. Datos examinados y control de calidad'),
             p('El libro unificado incorpora 3.335 registros conservados de OSITRAN/ONSV/MTC. '
               'Se excluyeron 101 filas externas aún no conciliadas, 13 registros OSITRAN relacionados '
               'o pendientes y 31 fuera de la cobertura GIS utilizada. El panel final contiene '
               '<b>3.190 registros OSITRAN</b> para 134 intervalos kilométricos aproximados.'),
             p('Los archivos CAD proporcionan marcas proyectadas al eje y cotas del modelo digital de '
               'superficie. El giro entre marcas y las diferencias de cota son <b>variables proxy</b>; '
               'no constituyen radios de curva ni pendientes longitudinales de rasante verificados. '
               'Faltan peralte, ancho de carril y TPDA comprobables por unidad de análisis.'),
             sub('2. Diseño de la validación temporal'),
             p('Se entrenan algoritmos Random Forest, XGBoost y Poisson sobre frecuencias anuales de '
               'siniestros por km. El año 2023 sirve de entrenamiento inicial, 2024 de validación para '
               'seleccionar por MAE y 2025 de prueba independiente. Las variables retrospectivas '
               'se calculan solo con años previos al que se intenta predecir. La media histórica '
               'y el último año sirven de modelos de referencia.'),
             sub('3. Comparación de modelos')]
    headers=[pp(x,st['TabB']) for x in ['Método','MAE 2024','MAE 2025','RMSE 2025']]
    data=[headers]
    met={}
    for r in comp:
        met[(r['Modelo'], '2024' if 'Validacion' in r['Corte'] else '2025')]=r
    for method in ('Random Forest','Poisson','XGBoost','Media histórica','Último año'):
        a=met.get((method,'2024')); b=met.get((method,'2025'))
        if not a or not b:continue
        data.append([pp(method,st['Tab']),a['MAE'],b['MAE'],b['RMSE']])
    tabla=Table(data,colWidths=[7*cm,3*cm,3.2*cm,3.6*cm],repeatRows=1)
    tabla.setStyle(TableStyle([
       ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173E5D')),
       ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#EFF5F8')]),
       ('BOTTOMPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),
       ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
       ('LINEBELOW',(0,-1),(-1,-1),0.4,colors.HexColor('#C8D6DE')),
    ]))
    flow += [tabla,Spacer(1,.4*cm),
             p('<b>Resultado:</b> en la validación 2024, la media histórica obtuvo el menor MAE '
               '(2,3582 accidentes/km-año). En la prueba independiente 2025 también se mantuvo '
               'ligeramente mejor (MAE 2,4527) que Random Forest (2,4710). '
               'Se entregan ambos modelos ML entrenados sin afirmar una mejora no demostrada.'),
             PageBreak(), pp('Pronóstico y priorización de inspecciones',st['Tit']),
             p('La referencia de menor error en 2024 genera una proyección agregada de '
               '<b>797,5 accidentes para 2026</b> en los 134 km examinados. '
               'El pronóstico anual no debe confundirse con una cifra observada ni extrapolarse a todo el corredor.'),
             sub('4. Cinco intervalos más prioritarios')]
    filas=[[pp(x,st['TabB']) for x in ['Kilómetro','Tramo GIS','Esperados 2026']]]
    for r in top:
        filas.append([f"{r['km_inicio']}–{r['km_fin']}",r['tramo_gis_ref'],r['prediccion_accidentes_2026']])
    t=Table(filas,colWidths=[5.6*cm,5.6*cm,5.6*cm],repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#173E5D')),
                          ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F0F5F8')]),
                          ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    flow += [t,Spacer(1,.45*cm)]
    im=Image(str(O/'03_top20_2026.png'),width=16.8*cm,height=10.8*cm)
    im.hAlign='CENTER'
    flow += [im,p('La prioridad alta corresponde al 20% superior de la distribución de frecuencia '
                 'pronosticada y representa una <b>clasificación interna relativa</b>, '
                 'no la delimitación oficial de puntos negros ni un indicador causal.'),
             PageBreak(),pp('Validación, interpretabilidad y límites',st['Tit'])]
    im2=Image(str(O/'02_validacion_2025.png'),width=10.8*cm,height=8.4*cm)
    im2.hAlign='CENTER';flow += [im2]
    flow += [sub('5. Interpretación de la validación'),
             p('El gráfico compara observados y predichos por kilómetro en 2025. '
               'Las predicciones se produjeron con datos anteriores a 2025. '
               'El resultado es útil como línea base para una mejora posterior con variables de '
               'diseño y tránsito completas; no permite afirmar que se alcanzó una reducción '
               'de siniestralidad por intervención.'),
             sub('6. Información pendiente para una fase ingenieril completa'),
             p('Se requieren radios de curvatura reales, pendientes de rasante, peraltes, '
               'anchos de carril, velocidad operativa, TPDA por segmento y, si es posible, '
               'georreferenciación precisa de cada evento. Se debe verificar el alineamiento '
               'en Civil 3D/LandXML y conciliar los registros OSITRAN/ONSV/MTC.'),
             p('Con esos datos sería posible incorporar exposición vehicular, validar espacialmente '
               'y contrastar escenarios de rediseño con el Highway Safety Manual y factores CMF, '
               'manteniendo separados los resultados observados de las estimaciones hipotéticas.'),
             sub('Archivos asociados'),
             p('Código: modelo_accidentes.py. Resultados: archivo Excel de seis hojas, '
               'validacion_independiente_2025.csv, comparacion_modelos.csv, '
               'predicciones_ML_2026_RF_XGBoost.csv, modelo_Random_Forest_entrenado.joblib, '
               'modelo_XGBoost_entrenado.joblib y predicciones_2026_QGIS.geojson.'),
            ]
    def pie(canvas,document):
        canvas.saveState()
        w,h=document.pagesize
        canvas.setStrokeColor(colors.HexColor('#B6C9D1'))
        canvas.line(1.9*cm,1.35*cm,w-1.9*cm,1.35*cm)
        canvas.setFont('DejaVu',7.2)
        canvas.setFillColor(colors.HexColor('#65747C'))
        canvas.drawString(1.9*cm,1.0*cm,'Análisis exploratorio - PE-22, registros 2022-2025')
        canvas.drawRightString(w-1.9*cm,1.0*cm,f'Página {document.page}')
        canvas.restoreState()
    doc.build(flow,onFirstPage=pie,onLaterPages=pie)
    print('PDF:',O/'INFORME_MODELO_PREDICTIVO.pdf')

if __name__=='__main__': main()
