"""Prepara los CSV del estudio Carretera Central sin artifact_tool.

Requisitos: Python 3.12 y openpyxl (pip install openpyxl).
Si los cuatro CSV de la carpeta datos/ ya existen, NO es necesario
volver a ejecutarlo: se omite la reconstrucción para protegerlos.
Para regenerarlos desde los documentos originales, ejecute:
    python preparar_datos.py --reconstruir
Coloque los originales XLSX y ZIP en la subcarpeta originales/ o junto
al presente archivo. Nunca supone valores faltantes de geometría/TPDA.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATOS = BASE / 'datos'

ESPERADOS = (
    'registros_originales_2022_2025.csv',
    'progresivas_cad_dsm.csv',
    'tramos_gis_referenciales.csv',
    'PLANTILLA_geometria_transito_VERIFICADA.csv',
)


def stringify(value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time().isoformat() == '00:00:00' else value.isoformat(sep=' ')
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def buscar_original(patron):
    for carpeta in [BASE / 'originales', BASE]:
        if carpeta.is_dir():
            candidatos = sorted(carpeta.glob(patron))
            if candidatos:
                return candidatos[0]
    return None


def guardar_csv(destino, encabezados, filas):
    with destino.open('w', encoding='utf-8-sig', newline='') as fichero:
        escritor = csv.writer(fichero)
        escritor.writerow(encabezados)
        escritor.writerows(filas)


def reconstruir():
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise SystemExit('Falta openpyxl. Instala: python -m pip install openpyxl') from exc

    excel = buscar_original('LISTA DE DATOS - 2022 - 2025*.xlsx')
    cad_zip = buscar_original('Carretera_Central_CAD_completo*.zip')
    if excel is None or cad_zip is None:
        raise SystemExit(
            'No encuentro los archivos originales. Coloca dentro de D:\\ENTREGABLE\\originales\\\n'
            '  - LISTA DE DATOS - 2022 - 2025.xlsx\n'
            '  - Carretera_Central_CAD_completo (1).zip\n'
            'Si ya tienes la carpeta datos/ completa, simplemente ejecuta modelo_accidentes.py.'
        )

    DATOS.mkdir(exist_ok=True)
    print('Leyendo XLSX:', excel.name)
    libro = load_workbook(excel, read_only=True, data_only=True)
    try:
        if 'Lista_unificada' not in libro.sheetnames:
            raise ValueError('La hoja "Lista_unificada" no existe en ' + excel.name)
        hoja = libro['Lista_unificada']
        iterable = hoja.iter_rows(min_row=1, max_col=31, values_only=True)
        cabecera = [stringify(v) for v in next(iterable)]
        filas = [[stringify(v) for v in fila] for fila in iterable if fila[1]]
    finally:
        libro.close()
    guardar_csv(DATOS / ESPERADOS[0], cabecera, filas)
    print('Accidentes CSV:', len(filas))

    print('Leyendo CAD/QGIS:', cad_zip.name)
    with zipfile.ZipFile(cad_zip) as archivo:
        archivo_csv = next((n for n in archivo.namelist() if n.endswith('Progresivas_y_cotas_CAD.csv')), None)
        archivo_gpkg = next((n for n in archivo.namelist() if n.endswith('/datos/Tramos_con_accidentes.gpkg')), None)
        if not archivo_csv or not archivo_gpkg:
            raise ValueError('Faltan Progresivas_y_cotas_CAD.csv o Tramos_con_accidentes.gpkg en el ZIP CAD')
        contenido = archivo.read(archivo_csv).decode('utf-8-sig')
        (DATOS / ESPERADOS[1]).write_text(contenido, encoding='utf-8-sig')
        with tempfile.TemporaryDirectory() as temporal:
            ruta_gpkg = Path(temporal) / 'tramos.gpkg'
            ruta_gpkg.write_bytes(archivo.read(archivo_gpkg))
            with sqlite3.connect(ruta_gpkg) as conexion:
                segmentos = conexion.execute('''
                    SELECT ID_TRAMO, KM_INI, KM_FIN, LONG_NOM_KM,
                           SECTOR, N_ACC, ESTADO
                    FROM Eje_5_10km ORDER BY KM_INI
                ''').fetchall()
    guardar_csv(
        DATOS / ESPERADOS[2],
        ['id_tramo', 'km_ini', 'km_fin', 'longitud_nominal_km',
         'sector', 'accidentes_gis_referenciales', 'estado_gis'],
        segmentos,
    )
    print('Tramos QGIS:', len(segmentos))

    plantilla = DATOS / ESPERADOS[3]
    if not plantilla.exists():
        guardar_csv(
            plantilla,
            ['km_inicio', 'radio_curva_m', 'pendiente_longitudinal_pct',
             'peralte_pct', 'ancho_carril_m', 'tpda_veh_dia'],
            ((km, '', '', '', '', '') for km in range(39, 173)),
        )
        print('Plantilla geométrica creada: 134 filas sin datos inventados')
    else:
        print('Plantilla geométrica existente: conservada sin cambios')
    print('Datos listos en:', DATOS)


def main():
    parser = argparse.ArgumentParser(description='Prepara datos del proyecto sin artifact_tool')
    parser.add_argument('--reconstruir', action='store_true',
                        help='Recrea CSV desde archivos originales XLSX/ZIP de originales/')
    args = parser.parse_args()
    faltantes = [n for n in ESPERADOS if not (DATOS / n).is_file()]
    if not faltantes and not args.reconstruir:
        print('Los 4 archivos CSV ya existen en:', DATOS)
        print('No es necesario preparar datos. Ejecuta: python modelo_accidentes.py')
        print('Para regenerar desde originales usa: python preparar_datos.py --reconstruir')
        return
    print('Archivos CSV faltantes:', faltantes if faltantes else 'ninguno; reconstrucción solicitada')
    reconstruir()


if __name__ == '__main__':
    main()
