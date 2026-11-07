#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Panel de análisis de seguridad vial - Carretera Central Lima–La Oroya.

Ejecutar desde D:\\ENTREGABLE: python panel_tkinter.py
Lee los resultados reales generados por modelo_accidentes.py; no simula datos.
Incluye filtros por modelo, prioridad, reportes, validación, gráficas y reentrenamiento.
"""
from __future__ import annotations

import csv
import json
import os
import queue
import subprocess
import sys
import threading
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

# Colores del panel. La prioridad roja/ámbar/verde representa cuantiles,
# no una declaración oficial de puntos negros ni causalidad.
NAVY = '#12233A'
NAVY_2 = '#1C324E'
BG = '#F0F4F9'
WHITE = '#FFFFFF'
INK = '#192D45'
MUTED = '#63758B'
BLUE = '#2466C6'
TEAL = '#0E9488'
AMBER = '#D78F16'
RED = '#CF4B57'
BORDER = '#DFE7F0'
FONT = 'Segoe UI'

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'resultados'
DATA = ROOT / 'datos'


def read_csv(path: Path):
    if not path.is_file():
        return []
    with path.open('r', encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path):
    if not path.is_file():
        return {}
    with path.open('r', encoding='utf-8-sig') as fh:
        return json.load(fh)


def num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def show_num(value, places=2):
    return f'{num(value):,.{places}f}'


def quantile(values, q):
    values = sorted(float(v) for v in values)
    if not values:
        return 0.0
    k = (len(values) - 1) * q
    lo, hi = int(k), min(len(values) - 1, int(k) + 1)
    return values[lo] + (k - lo) * (values[hi] - values[lo])


def safe_text(value, max_chars=75):
    s = str(value or '').strip()
    return s if len(s) <= max_chars else s[:max_chars - 1] + '…'


class PanelVial(tk.Tk):
    VIEWS = [
        ('Resumen general', '▦'),
        ('Predicciones 2026', '▤'),
        ('Comparar modelos', '▥'),
        ('Histórico 2022–2025', '▧'),
        ('Geometría y tramos', '◇'),
        ('Mapa y archivos', '⌖'),
    ]

    def __init__(self):
        super().__init__()
        self.title('Sistema de predicción de accidentes | Carretera Central PE-22')
        self.geometry('1320x820')
        self.minsize(1020, 650)
        self.configure(bg=BG)
        self.option_add('*Font', (FONT, 10))
        self.model_var = tk.StringVar(value='Media histórica')
        self.priority_var = tk.StringVar(value='Todos')
        self.search_var = tk.StringVar()
        self.corte_var = tk.StringVar(value='Prueba 2025')
        self.worker_messages = queue.Queue()
        self.running = False
        self.current_view = 'Resumen general'
        self.nav_buttons = {}
        self.table = None
        self.pred_note = None
        self.console = None
        self.refresh_data()
        self.configure_styles()
        self.draw_shell()
        self.open_view('Resumen general')
        self.after(180, self.read_worker_messages)

    def refresh_data(self):
        self.summary = read_json(OUT / 'RESUMEN_RESULTADOS.json')
        self.pred_baseline = read_csv(OUT / 'prediccion_2026_por_kilometro.csv')
        self.pred_ml = read_csv(OUT / 'predicciones_ML_2026_RF_XGBoost.csv')
        self.metrics = read_csv(OUT / 'comparacion_modelos.csv')
        self.importance = read_csv(OUT / 'importancia_variables_RF.csv')
        self.tramos = read_csv(OUT / 'resumen_19_tramos.csv')
        self.validacion = read_csv(OUT / 'validacion_independiente_2025.csv')
        self.ml_index = defaultdict(dict)
        for row in self.pred_ml:
            model = row.get('modelo', '')
            self.ml_index[model][str(row.get('km_inicio', ''))] = num(row.get('accidentes_estimados_2026'))
        self.model_options = ['Media histórica'] + [name for name in ('Random Forest', 'XGBoost') if name in self.ml_index]
        if self.model_var.get() not in self.model_options:
            self.model_var.set(self.model_options[0])

    def configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('Vial.Treeview', font=(FONT, 9), rowheight=30,
                        background=WHITE, fieldbackground=WHITE, foreground=INK,
                        borderwidth=0)
        style.map('Vial.Treeview', background=[('selected', BLUE)], foreground=[('selected', WHITE)])
        style.configure('Vial.Treeview.Heading', background='#E5EDF6', foreground=INK,
                        font=(FONT, 9, 'bold'), relief='flat', padding=8)
        style.configure('Vial.TCombobox', padding=5, foreground=INK)
        style.configure('Vial.Vertical.TScrollbar', width=13)

    def draw_shell(self):
        self.sidebar = tk.Frame(self, bg=NAVY, width=236)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        head = tk.Frame(self.sidebar, bg=NAVY)
        head.pack(fill='x', padx=18, pady=(25, 28))
        tk.Label(head, text='PE-22', bg=NAVY, fg='#6CD4CA',
                 font=(FONT, 26, 'bold')).pack(anchor='w')
        tk.Label(head, text='SEGURIDAD VIAL', bg=NAVY, fg=WHITE,
                 font=(FONT, 11, 'bold')).pack(anchor='w')
        tk.Label(head, text='Lima – La Oroya', bg=NAVY, fg='#B4C4D8',
                 font=(FONT, 9)).pack(anchor='w', pady=(4, 0))
        tk.Label(self.sidebar, text='PANEL DE NAVEGACIÓN', bg=NAVY,
                 fg='#8EA4BE', font=(FONT, 8, 'bold')).pack(anchor='w', padx=18, pady=(5, 12))
        for name, symbol in self.VIEWS:
            b = tk.Button(self.sidebar, text=f' {symbol}   {name}', anchor='w',
                          bg=NAVY, fg='#D8E5F2', activebackground=NAVY_2,
                          activeforeground=WHITE, relief='flat', bd=0,
                          font=(FONT, 10), padx=16, pady=13,
                          command=lambda n=name: self.open_view(n), cursor='hand2')
            b.pack(fill='x', padx=8, pady=2)
            self.nav_buttons[name] = b
        tk.Frame(self.sidebar, bg=NAVY).pack(fill='both', expand=True)
        tk.Label(self.sidebar, text='ANÁLISIS EXPLORATORIO', bg=NAVY,
                 fg='#EAB968', font=(FONT, 8, 'bold')).pack(anchor='w', padx=19)
        tk.Label(self.sidebar, text='Sin TPDA verificado\nGeometría no certificada',
                 bg=NAVY, fg='#B4C4D8', font=(FONT, 9), justify='left').pack(
                     anchor='w', padx=19, pady=(5, 18))

        self.main = tk.Frame(self, bg=BG)
        self.main.pack(side='left', expand=True, fill='both')
        self.top = tk.Frame(self.main, bg=WHITE, height=76)
        self.top.pack(fill='x')
        self.top.pack_propagate(False)
        self.top_title = tk.Label(self.top, bg=WHITE, fg=INK,
                                  font=(FONT, 18, 'bold'))
        self.top_title.pack(side='left', padx=26, pady=18)
        self.refresh_btn = tk.Button(self.top, text='⟳  Actualizar datos', command=self.reload,
                                      relief='flat', bg='#E8F0FB', fg=BLUE,
                                      font=(FONT, 10, 'bold'), padx=16, pady=9, cursor='hand2')
        self.refresh_btn.pack(side='right', padx=24)
        self.page = tk.Frame(self.main, bg=BG)
        self.page.pack(fill='both', expand=True, padx=24, pady=18)
        self.footer = tk.Label(self.main, text='', bg=BG, fg=MUTED,
                               font=(FONT, 8), anchor='w')
        self.footer.pack(fill='x', padx=25, pady=(0, 10))
        self.update_footer()

    def update_footer(self):
        status = 'Datos cargados' if self.pred_baseline else 'Faltan resultados: ejecuta modelo_accidentes.py'
        self.footer.config(text=f'{status}  ·  {OUT}  ·  PE-22 / Km 39–172 (referencial)')

    def open_view(self, name):
        self.current_view = name
        self.top_title.config(text=name)
        for key, button in self.nav_buttons.items():
            button.config(bg=NAVY_2 if key == name else NAVY,
                          fg=WHITE if key == name else '#D8E5F2',
                          font=(FONT, 10, 'bold' if key == name else 'normal'))
        for child in self.page.winfo_children():
            child.destroy()
        views = {
            'Resumen general': self.view_dashboard,
            'Predicciones 2026': self.view_predictions,
            'Comparar modelos': self.view_models,
            'Histórico 2022–2025': self.view_history,
            'Geometría y tramos': self.view_geometry,
            'Mapa y archivos': self.view_files,
        }
        views[name]()

    def reload(self):
        try:
            self.refresh_data()
            self.update_footer()
            self.open_view(self.current_view)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('Error al leer resultados', str(exc))

    def card(self, parent, title, value, sub='', color=BLUE):
        f = tk.Frame(parent, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        tk.Frame(f, bg=color, height=4).pack(fill='x')
        tk.Label(f, text=title, bg=WHITE, fg=MUTED, font=(FONT, 9)).pack(
            anchor='w', padx=16, pady=(13, 5))
        tk.Label(f, text=value, bg=WHITE, fg=INK, font=(FONT, 23, 'bold')).pack(
            anchor='w', padx=16)
        tk.Label(f, text=sub, bg=WHITE, fg=MUTED, font=(FONT, 8)).pack(
            anchor='w', padx=16, pady=(2, 15))
        return f

    def section(self, parent, title, desc=None):
        wrap = tk.Frame(parent, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        h = tk.Frame(wrap, bg=WHITE)
        h.pack(fill='x', padx=15, pady=(12, 5))
        tk.Label(h, text=title, bg=WHITE, fg=INK, font=(FONT, 11, 'bold')).pack(anchor='w')
        if desc:
            tk.Label(h, text=desc, bg=WHITE, fg=MUTED, font=(FONT, 8)).pack(anchor='w', pady=(3, 0))
        return wrap

    def alert(self, parent, message, kind='info'):
        colors = {'info': ('#EAF3FD', BLUE), 'warning': ('#FFF3DE', '#92621D')}
        bg, fg = colors[kind]
        frame = tk.Frame(parent, bg=bg)
        tk.Label(frame, text=message, bg=bg, fg=fg, anchor='w',
                 justify='left', wraplength=980, font=(FONT, 9)).pack(
                     fill='x', padx=15, pady=10)
        return frame

    def make_figure(self, parent, fig, height=300):
        canvas = FigureCanvasTkAgg(fig, master=parent)
        widget = canvas.get_tk_widget()
        widget.config(height=height, bg=WHITE, highlightthickness=0)
        widget.pack(fill='both', expand=True, padx=8, pady=(4, 12))
        canvas.draw()
        return canvas

    def empty(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=MUTED,
                 font=(FONT, 12), wraplength=780, justify='center').pack(
                     expand=True, padx=30, pady=60)

    def header_controls(self, parent, labels):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill='x', pady=(0, 14))
        for key, value in labels:
            tk.Label(bar, text=key, bg=BG, fg=MUTED, font=(FONT, 9)).pack(side='left', padx=(0, 7))
            tk.Label(bar, text=value, bg=BG, fg=INK, font=(FONT, 9, 'bold')).pack(side='left', padx=(0, 24))
        return bar

    def view_dashboard(self):
        if not self.pred_baseline:
            self.empty(self.page, 'No se encontraron los archivos de resultados.\nColoca panel_tkinter.py junto a modelo_accidentes.py y ejecuta el modelo.')
            return
        y = self.summary.get('anios_y_cuentas', {})
        top = self.pred_baseline[0]
        cards = tk.Frame(self.page, bg=BG)
        cards.pack(fill='x', pady=(0, 16))
        specs = [
            ('REGISTROS ANALIZADOS', f"{int(self.summary.get('n_registros_para_modelo',0)):,}", 'Accidentes filtrados 2022–2025', BLUE),
            ('PROYECCIÓN 2026', show_num(self.summary.get('suma_predicciones_2026'), 1), 'Frecuencia esperada, no observada', TEAL),
            ('KILÓMETROS EVALUADOS', str(len(self.pred_baseline)), '39–172 · intervalos de 1 km', '#4B65A7'),
            ('MAYOR PRIORIDAD', f"Km {top['km_inicio']}–{top['km_fin']}", f"{show_num(top['prediccion_accidentes_2026'])} accidentes estimados", AMBER),
        ]
        for i, spec in enumerate(specs):
            cards.grid_columnconfigure(i, weight=1)
            self.card(cards, *spec).grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 5, 5 if i < 3 else 0))

        charts = tk.Frame(self.page, bg=BG)
        charts.pack(fill='both', expand=True)
        charts.grid_columnconfigure(0, weight=1)
        charts.grid_columnconfigure(1, weight=1)
        charts.grid_rowconfigure(0, weight=1)
        a = self.section(charts, 'Accidentes históricos por año', 'Casos incluidos tras filtros de calidad')
        a.grid(row=0, column=0, sticky='nsew', padx=(0, 7))
        years = sorted(y, key=int)
        fig = Figure(figsize=(5, 3.1), dpi=100, facecolor=WHITE)
        ax = fig.add_subplot(111)
        vals = [int(y[yr]) for yr in years]
        bars = ax.bar(years, vals, color=BLUE, width=0.65)
        ax.bar_label(bars, padding=3, fontsize=9)
        ax.set_ylim(0, max(vals or [1]) * 1.18)
        ax.set_ylabel('Siniestros registrados', fontsize=9)
        self.polish_axes(fig, ax)
        self.make_figure(a, fig)

        b = self.section(charts, 'Top 10 kilómetros previstos · 2026', 'Modelo seleccionado: media histórica')
        b.grid(row=0, column=1, sticky='nsew', padx=(7, 0))
        pred = self.pred_baseline[:10][::-1]
        fig = Figure(figsize=(5, 3.1), dpi=100, facecolor=WHITE)
        ax = fig.add_subplot(111)
        colors = [RED if k < 5 else AMBER for k in range(len(pred) - 1, -1, -1)]
        ax.barh([f"Km {r['km_inicio']}" for r in pred],
                [num(r['prediccion_accidentes_2026']) for r in pred], color=colors)
        ax.set_xlabel('Accidentes anuales esperados', fontsize=9)
        self.polish_axes(fig, ax)
        self.make_figure(b, fig)

        self.alert(self.page, 'AVISO METODOLÓGICO: La selección del modelo se realizó por MAE en 2024; la prueba de 2025 es independiente.\nLos puntos críticos son candidatos exploratorios: kilometraje y parámetros geométricos requieren verificación en campo.', 'warning').pack(fill='x', pady=(13, 0))

    def polish_axes(self, fig, ax):
        ax.set_facecolor(WHITE)
        ax.spines[['top', 'right']].set_visible(False)
        ax.spines[['left', 'bottom']].set_color(BORDER)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        ax.grid(axis='y' if not ax.get_xlabel() else 'x', alpha=0.15)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=2)

    def prediction_rows(self):
        model = self.model_var.get()
        rows = []
        for base in self.pred_baseline:
            row = dict(base)
            km = str(base['km_inicio'])
            if model == 'Media histórica':
                p = num(base.get('prediccion_accidentes_2026'))
            else:
                if km not in self.ml_index[model]:
                    continue
                p = self.ml_index[model][km]
            row['_p'] = p
            rows.append(row)
        vals = [r['_p'] for r in rows]
        high, mid = quantile(vals, .8), quantile(vals, .5)
        for r in rows:
            r['_level'] = 'ALTA' if r['_p'] >= high else 'MEDIA' if r['_p'] >= mid else 'BAJA'
        rows.sort(key=lambda r: (-r['_p'], int(num(r.get('km_inicio')))))
        for i, r in enumerate(rows, 1):
            r['_pos'] = i
        return rows

    def filtered_rows(self):
        query = self.search_var.get().strip().casefold()
        level = self.priority_var.get()
        rows = self.prediction_rows()
        out = []
        for row in rows:
            if level != 'Todos' and level != row['_level']:
                continue
            haystack = ' '.join(str(row.get(k, '')) for k in
                                ('km_inicio', 'km_fin', 'tramo_gis_ref', 'sector_gis_ref')).casefold()
            if query and query not in haystack:
                continue
            out.append(row)
        return out

    def view_predictions(self):
        if not self.pred_baseline:
            self.empty(self.page, 'Primero genera los resultados con modelo_accidentes.py')
            return
        filters = tk.Frame(self.page, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        filters.pack(fill='x', pady=(0, 14))
        for lab, width in (('MODELO', 18), ('PRIORIDAD', 12), ('KM / SECTOR', 25)):
            pass
        form = tk.Frame(filters, bg=WHITE)
        form.pack(side='left', padx=16, pady=12)
        tk.Label(form, text='Modelo de proyección', bg=WHITE, fg=MUTED, font=(FONT, 9)).grid(row=0,column=0,sticky='w')
        combo = ttk.Combobox(form, textvariable=self.model_var, state='readonly',
                             values=self.model_options, width=19, style='Vial.TCombobox')
        combo.grid(row=1,column=0,padx=(0,13))
        combo.bind('<<ComboboxSelected>>', lambda e: self.populate_predictions())
        tk.Label(form, text='Prioridad relativa', bg=WHITE, fg=MUTED, font=(FONT, 9)).grid(row=0,column=1,sticky='w')
        cb2 = ttk.Combobox(form, textvariable=self.priority_var, state='readonly',
                           values=['Todos', 'ALTA','MEDIA','BAJA'], width=12, style='Vial.TCombobox')
        cb2.grid(row=1,column=1,padx=(0,13))
        cb2.bind('<<ComboboxSelected>>', lambda e: self.populate_predictions())
        tk.Label(form, text='Buscar kilómetro o sector', bg=WHITE, fg=MUTED, font=(FONT, 9)).grid(row=0,column=2,sticky='w')
        ent = tk.Entry(form, textvariable=self.search_var, bg='#F7F9FC', fg=INK,
                       relief='solid', bd=1, font=(FONT,10), width=31)
        ent.grid(row=1,column=2)
        ent.bind('<KeyRelease>', lambda e: self.populate_predictions())
        self.action_button(filters, 'Exportar tabla CSV', self.export_predictions, secondary=True).pack(
            side='right', padx=16, pady=16)

        block = self.section(self.page, 'Clasificación de kilómetros · frecuencia prevista 2026',
                             'ALTA = 20% superior; MEDIA = siguiente 30%; BAJA = 50% inferior (clasificación relativa)')
        block.pack(fill='both', expand=True)
        self.pred_note = tk.Label(block, bg=WHITE, fg=TEAL, font=(FONT,9,'bold'))
        self.pred_note.pack(anchor='w', padx=17, pady=(4, 6))
        cols = ('puesto','km','tramo','sector','2025','hist','2026','prioridad')
        headers = ('N°','INTERVALO (KM)','TRAMO','SECTOR DE REFERENCIA','ACC. 2025','MEDIA HIST.','PRED. 2026','PRIORIDAD')
        widths = (56, 103, 85, 310, 92, 110, 110, 95)
        container = tk.Frame(block, bg=WHITE)
        container.pack(fill='both', expand=True, padx=15, pady=(0,15))
        self.table = ttk.Treeview(container, columns=cols, show='headings', style='Vial.Treeview')
        for col, h, width in zip(cols, headers, widths):
            self.table.heading(col,text=h)
            self.table.column(col,width=width,minwidth=width//2,
                              anchor='center' if col not in ('sector','tramo') else 'w')
        self.table.tag_configure('ALTA', background='#FFF1F1', foreground='#9C2533')
        self.table.tag_configure('MEDIA', background='#FFF9ED', foreground='#735210')
        self.table.tag_configure('BAJA', background='#F1FAF7', foreground='#146A60')
        self.table.bind('<Double-1>', self.prediction_detail)
        vbar = ttk.Scrollbar(container, orient='vertical', command=self.table.yview)
        hbar = ttk.Scrollbar(container, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.table.grid(row=0,column=0,sticky='nsew')
        vbar.grid(row=0,column=1,sticky='ns')
        hbar.grid(row=1,column=0,sticky='ew')
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)
        self.populate_predictions()
        self.alert(self.page, 'Doble clic en una fila para ver el detalle. Las predicciones ML pueden cambiar la clasificación; no implican reducción causal ni riesgo ajustado por tránsito.').pack(fill='x',pady=(12,0))

    def populate_predictions(self):
        if self.table is None or not self.table.winfo_exists():
            return
        self.table.delete(*self.table.get_children())
        rows = self.filtered_rows()
        for r in rows:
            self.table.insert('', 'end', iid=str(r['km_inicio']),
                 values=(r['_pos'], f"{r['km_inicio']}–{r['km_fin']}",r['tramo_gis_ref'],
                         safe_text(r['sector_gis_ref'],48),r['accidentes_2025'],
                         show_num(r['media_historica_2022_2025']),show_num(r['_p']),r['_level']),
                 tags=(r['_level'],))
        total = sum(r['_p'] for r in rows)
        if self.pred_note and self.pred_note.winfo_exists():
            self.pred_note.config(text=f'{len(rows)} intervalos mostrados · {show_num(total,1)} accidentes anuales esperados · {self.model_var.get()}')

    def prediction_detail(self, event):
        if not self.table:
            return
        selected = self.table.selection()
        if not selected:
            return
        km = selected[0]
        row = next((r for r in self.prediction_rows() if str(r['km_inicio']) == km), None)
        if row is None:
            return
        detail = tk.Toplevel(self)
        detail.title(f"Detalle de riesgo | km {row['km_inicio']}–{row['km_fin']}")
        detail.geometry('520x420')
        detail.configure(bg=WHITE)
        detail.transient(self)
        tk.Label(detail, text=f"Km {row['km_inicio']}–{row['km_fin']}", bg=WHITE, fg=INK,
                 font=(FONT,20,'bold')).pack(anchor='w',padx=25,pady=(20,4))
        for label,value in [
            ('Sector',row['sector_gis_ref']), ('Código de tramo',row['tramo_gis_ref']),
            ('Modelo',self.model_var.get()), ('Frecuencia anual 2026',show_num(row['_p'])),
            ('Accidentes observados 2025',row['accidentes_2025']),
            ('Prioridad relativa',row['_level']),
            ('Pendiente DSM (proxy, %)',row.get('pendiente_dsm_proxy_pct') or 'Sin dato'),
            ('Giro CAD (proxy, grados)',row.get('giro_cad_proxy_grados') or 'Sin dato'),
        ]:
            f = tk.Frame(detail,bg=WHITE)
            f.pack(fill='x',padx=25,pady=5)
            tk.Label(f,text=label,bg=WHITE,fg=MUTED,width=25,anchor='w',font=(FONT,9)).pack(side='left')
            tk.Label(f,text=safe_text(value,40),bg=WHITE,fg=INK,anchor='w',font=(FONT,9,'bold')).pack(side='left')
        tk.Label(detail,text='Ubicación provisional: confirmar eje vial, kilometraje y geometría en campo.',
                 wraplength=450,bg='#FFF3DE',fg='#8A5C19',font=(FONT,9),justify='left').pack(
                     fill='x',padx=25,pady=14,ipadx=10,ipady=10)

    def export_predictions(self):
        rows = self.filtered_rows()
        if not rows:
            messagebox.showwarning('Sin filas', 'No hay registros que coincidan con el filtro.')
            return
        dest = filedialog.asksaveasfilename(parent=self,defaultextension='.csv',
            initialfile='predicciones_filtradas_tkinter.csv',
            filetypes=[('CSV','*.csv')])
        if not dest:
            return
        columns = ['puesto','km_inicio','km_fin','modelo','tramo','sector','accidentes_2025',
                   'media_historica','prediccion_2026','prioridad_relativa']
        with open(dest,'w',encoding='utf-8-sig',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=columns)
            writer.writeheader()
            for r in rows:
                writer.writerow({'puesto':r['_pos'],'km_inicio':r['km_inicio'],
                    'km_fin':r['km_fin'],'modelo':self.model_var.get(),
                    'tramo':r['tramo_gis_ref'],'sector':r['sector_gis_ref'],
                    'accidentes_2025':r['accidentes_2025'],
                    'media_historica':r['media_historica_2022_2025'],
                    'prediccion_2026':round(r['_p'],4),'prioridad_relativa':r['_level']})
        messagebox.showinfo('CSV exportado',f'Archivo guardado:\n{dest}')

    def view_models(self):
        if not self.metrics:
            self.empty(self.page, 'No está disponible resultados/comparacion_modelos.csv')
            return
        chooser = tk.Frame(self.page,bg=BG)
        chooser.pack(fill='x',pady=(0,10))
        tk.Label(chooser,text='Periodo de evaluación:',bg=BG,fg=INK,font=(FONT,10,'bold')).pack(side='left',padx=(0,10))
        cb = ttk.Combobox(chooser,textvariable=self.corte_var,state='readonly',width=20,
                          values=['Prueba 2025','Validación 2024'])
        cb.pack(side='left')
        cb.bind('<<ComboboxSelected>>',lambda e:self.open_view('Comparar modelos'))
        cut = '2025' if '2025' in self.corte_var.get() else '2024'
        metric_rows = [r for r in self.metrics if cut in r['Corte']]
        if not metric_rows:
            self.empty(self.page,'No hay métricas disponibles para ese periodo.')
            return
        best = min(metric_rows,key=lambda r:num(r.get('MAE'),100000))
        self.header_controls(self.page,[('Menor MAE:',best['Modelo']),('Valor:',show_num(best['MAE'],4)),('Prueba:',cut)])
        table_sec = self.section(self.page,'Comparación cuantitativa','MAE y RMSE: cuanto más bajos, menor error predictivo')
        table_sec.pack(fill='x',pady=(0,14))
        cols=('modelo','mae','rmse','poisson')
        tree=ttk.Treeview(table_sec,columns=cols,show='headings',height=len(metric_rows),style='Vial.Treeview')
        for key,head,width in zip(cols,('MODELO','MAE','RMSE','DEVIANCIA POISSON'),(220,140,140,190)):
            tree.heading(key,text=head)
            tree.column(key,width=width,anchor='w' if key=='modelo' else 'center')
        tree.tag_configure('best',background='#EAF7F1',foreground='#0C775A')
        for r in sorted(metric_rows,key=lambda r:num(r['MAE'])):
            tree.insert('', 'end',values=(r['Modelo'],r['MAE'],r['RMSE'],r['Deviancia_Poisson']),
                        tags=('best',) if r is best else ())
        tree.pack(fill='x',padx=15,pady=(6,13))

        charts=tk.Frame(self.page,bg=BG)
        charts.pack(fill='both',expand=True)
        charts.grid_columnconfigure(0,weight=1)
        charts.grid_columnconfigure(1,weight=1)
        charts.grid_rowconfigure(0,weight=1)
        sec=self.section(charts,'Error absoluto medio (MAE)',f'Comparación temporal {cut}')
        sec.grid(row=0,column=0,sticky='nsew',padx=(0,7))
        fig=Figure(figsize=(5,3.2),dpi=100,facecolor=WHITE)
        ax=fig.add_subplot(111)
        rows=sorted(metric_rows,key=lambda r:num(r['MAE']),reverse=True)
        ax.barh([r['Modelo'] for r in rows],[num(r['MAE']) for r in rows],
                color=[TEAL if r['Modelo']==best['Modelo'] else BLUE for r in rows])
        ax.set_xlabel('MAE (accidentes por km-año)')
        self.polish_axes(fig,ax)
        self.make_figure(sec,fig)

        sec=self.section(charts,'Importancia de variables · Random Forest',
             'Importancia predictiva, NO relación causal demostrada')
        sec.grid(row=0,column=1,sticky='nsew',padx=(7,0))
        fig=Figure(figsize=(5,3.2),dpi=100,facecolor=WHITE)
        ax=fig.add_subplot(111)
        subset=sorted(self.importance,key=lambda r:num(r.get('importancia')),reverse=True)[:7][::-1]
        clean=lambda s: str(s).replace('accidentes_','').replace('_historica','_hist.').replace('pendiente_dsm_proxy_pct','pendiente_DSM').replace('giro_cad_proxy_grados','giro_CAD').replace('_',' ')
        ax.barh([clean(r['variable']) for r in subset],
                [num(r['importancia']) for r in subset],color=TEAL)
        ax.set_xlabel('Importancia relativa')
        self.polish_axes(fig,ax)
        self.make_figure(sec,fig)
        self.alert(self.page,'La media histórica ganó la selección por MAE en 2024. Random Forest y XGBoost se entrenan y se conservan como comparadores; los resultados de 2025 son una prueba independiente.','warning').pack(fill='x',pady=(11,0))

    def view_history(self):
        counts = self.summary.get('anios_y_cuentas',{})
        if not counts:
            self.empty(self.page,'No hay conteos históricos disponibles.')
            return
        yearcards=tk.Frame(self.page,bg=BG)
        yearcards.pack(fill='x',pady=(0,15))
        for idx,(year,value) in enumerate(sorted(counts.items())):
            yearcards.grid_columnconfigure(idx,weight=1)
            self.card(yearcards,f'AÑO {year}',f'{int(value):,}',
                'accidentes incluidos', [BLUE,TEAL,AMBER,RED][idx%4]).grid(
                    row=0,column=idx,sticky='nsew',padx=5)
        sec=self.section(self.page,'Comportamiento 2022–2025',
                          'Conteos de la base analítica, con exclusiones para evitar duplicados')
        sec.pack(fill='both',expand=True,pady=(0,14))
        fig=Figure(figsize=(9,4),dpi=100,facecolor=WHITE)
        ax=fig.add_subplot(111)
        years=sorted(counts,key=int)
        vals=[int(counts[y]) for y in years]
        ax.plot(years,vals,marker='o',color=TEAL,linewidth=3,markersize=9)
        for yy,v in zip(years,vals):
            ax.annotate(str(v),(yy,v),textcoords='offset points',xytext=(0,12),ha='center',weight='bold')
        ax.set_ylim(min(vals)*.87,max(vals)*1.13)
        ax.set_ylabel('Accidentes en el ámbito filtrado')
        self.polish_axes(fig,ax)
        self.make_figure(sec,fig,height=310)
        self.alert(self.page,'Los conteos corresponden solo a los km 39–172 y a los registros aceptados. No representan todos los siniestros Lima–La Oroya ni tasas por volumen de tránsito.').pack(fill='x')

    def view_geometry(self):
        self.alert(self.page,'DATOS EN DESARROLLO: Los indicadores CAD y DSM son aproximaciones referenciales. No representan radios de curva, pendientes de rasante ni peraltes certificados.','warning').pack(fill='x',pady=(0,14))
        sec=self.section(self.page,'Proxies geométricos en kilómetros prioritarios',
                         'Se muestran proxies solo para ayudar a orientar la inspección de campo')
        sec.pack(fill='both',expand=True,pady=(0,13))
        cols=('km','sector','p','g','2026')
        tree=ttk.Treeview(sec,columns=cols,show='headings',style='Vial.Treeview')
        for key,txt,width in zip(cols,('KM','SECTOR GIS REFERENCIAL','PENDIENTE DSM PROXY (%)',
                                     'GIRO CAD PROXY (°)','ACCIDENTES 2026'),
                                 (85,340,210,190,145)):
            tree.heading(key,text=txt)
            tree.column(key,width=width,anchor='w' if key=='sector' else 'center')
        scroll=ttk.Scrollbar(sec,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True,padx=(16,0),pady=(8,16))
        scroll.pack(side='right',fill='y',pady=(8,16),padx=(0,14))
        for r in self.pred_baseline:
            tree.insert('','end',values=(f"{r['km_inicio']}–{r['km_fin']}",
                safe_text(r.get('sector_gis_ref'),50),
                show_num(r['pendiente_dsm_proxy_pct']) if r.get('pendiente_dsm_proxy_pct') else 'Sin dato',
                show_num(r['giro_cad_proxy_grados']) if r.get('giro_cad_proxy_grados') else 'Sin dato',
                show_num(r['prediccion_accidentes_2026'])))
        foot=tk.Frame(self.page,bg=BG)
        foot.pack(fill='x')
        self.action_button(foot,'Abrir plantilla de mediciones',lambda:self.open_file(DATA / 'PLANTILLA_geometria_transito_VERIFICADA.csv'),secondary=True).pack(side='left',padx=(0,10))
        self.action_button(foot,'Abrir resumen de tramos',lambda:self.open_file(OUT / 'resumen_19_tramos.csv'),secondary=True).pack(side='left')
        tk.Label(foot,text='Completa mediciones oficiales para mejorar el modelo.',bg=BG,fg=MUTED,
                 font=(FONT,9)).pack(side='right')

    def action_button(self,parent,label,action,secondary=False):
        return tk.Button(parent,text=label,command=action,cursor='hand2',
                         bg='#E8F0FB' if secondary else BLUE,
                         activebackground='#D8E7FC' if secondary else '#184D9C',
                         fg=BLUE if secondary else WHITE,
                         activeforeground=BLUE if secondary else WHITE,
                         relief='flat',bd=0,padx=14,pady=10,font=(FONT,10,'bold'))

    def view_files(self):
        actions=self.section(self.page,'Archivos y herramientas','Abre recursos del proyecto con las aplicaciones de tu PC')
        actions.pack(fill='x',pady=(0,14))
        buttons=tk.Frame(actions,bg=WHITE)
        buttons.pack(fill='x',padx=16,pady=(9,16))
        files=[
            ('Abrir mapa interactivo',OUT / 'mapa_interactivo_2026.html'),
            ('Abrir reporte Excel',OUT / 'RESULTADOS_MODELO_ACCIDENTES.xlsx'),
            ('Abrir informe PDF',OUT / 'INFORME_MODELO_PREDICTIVO.pdf'),
            ('Abrir resultados',OUT),
            ('Abrir carpeta de datos',DATA),
            ('Abrir GeoJSON para QGIS',OUT / 'predicciones_2026_QGIS.geojson'),
        ]
        for i,(name,path) in enumerate(files):
            b=self.action_button(buttons,name,lambda p=path:self.open_file(p),secondary=True)
            b.grid(row=i//3,column=i%3,padx=6,pady=6,sticky='ew')
        for col in range(3):
            buttons.grid_columnconfigure(col,weight=1)
        control=self.section(self.page,'Ejecución del modelo Python','El entrenamiento se ejecuta en otro proceso para no bloquear la ventana')
        control.pack(fill='both',expand=True,pady=(0,14))
        tools=tk.Frame(control,bg=WHITE)
        tools.pack(fill='x',padx=16,pady=(7,12))
        self.run_button=self.action_button(tools,'▶  Entrenar y actualizar',self.train_model)
        self.run_button.pack(side='left',padx=(0,10))
        self.action_button(tools,'⟳  Recargar resultados',self.reload,secondary=True).pack(side='left')
        self.console=tk.Text(control,height=13,wrap='word',bg=NAVY,fg='#E3EDF8',
                             insertbackground=WHITE,font=('Consolas',9),bd=0,padx=14,pady=12)
        self.console.pack(fill='both',expand=True,padx=16,pady=(0,16))
        self.log('Proyecto: '+str(ROOT))
        self.log('Intérprete activo: '+sys.executable)
        self.log('Al entrenar, se actualizarán los CSV, modelos y gráficos de resultados.')
        if self.running:
            self.run_button.config(state='disabled',text='Procesando…')
        self.alert(self.page,'Los mapas usan OpenStreetMap y necesitan conexión a Internet. Verifica coordenadas QGIS y kilometraje antes de usar el mapa para decisiones de ingeniería.').pack(fill='x')

    def log(self,message):
        if self.console is None or not self.console.winfo_exists():
            return
        self.console.insert('end',message+'\n')
        self.console.see('end')

    def open_file(self,path):
        path=Path(path)
        if not path.exists():
            messagebox.showerror('Archivo no encontrado',f'No existe:\n{path}\n\nEjecuta el modelo para crear los resultados.')
            return
        try:
            if path.suffix.lower() in {'.html','.htm'}:
                webbrowser.open(path.resolve().as_uri())
            elif sys.platform == 'win32':
                os.startfile(str(path))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open',str(path)])
            else:
                subprocess.Popen(['xdg-open',str(path)])
        except (OSError, ValueError) as exc:
            messagebox.showerror('No se pudo abrir',str(exc))

    def train_model(self):
        if self.running:
            return
        source=ROOT / 'modelo_accidentes.py'
        if not source.exists():
            messagebox.showerror('Falta modelo_accidentes.py',f'No se encontró:\n{source}\n\nColoca ambos .py en la misma carpeta.')
            return
        self.running=True
        if self.run_button and self.run_button.winfo_exists():
            self.run_button.config(state='disabled',text='Procesando…')
        self.log('\n----- INICIO DE ENTRENAMIENTO -----')
        threading.Thread(target=self.training_worker,args=(source,),daemon=True).start()

    def training_worker(self,source):
        try:
            flags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            cmd=[sys.executable,'-u',str(source)]
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                  text=True,encoding='utf-8',errors='replace',
                                  bufsize=1,creationflags=flags)
            for line in proc.stdout:
                self.worker_messages.put(('log',line.rstrip()))
            code=proc.wait()
            self.worker_messages.put(('done',code))
        except Exception as exc:
            self.worker_messages.put(('log',f'ERROR: {exc}'))
            self.worker_messages.put(('done',1))

    def read_worker_messages(self):
        try:
            while True:
                event,value=self.worker_messages.get_nowait()
                if event == 'log':
                    self.log(value)
                elif event == 'done':
                    self.running=False
                    if value == 0:
                        self.log('----- ENTRENAMIENTO FINALIZADO -----')
                        try:
                            self.refresh_data()
                            self.update_footer()
                        except Exception as exc:
                            self.log(f'No se pudo actualizar: {exc}')
                        messagebox.showinfo('Modelo completado','Resultados y modelos actualizados. Puedes abrir Predicciones 2026.')
                    else:
                        self.log('----- FINALIZÓ CON ERROR; revisa los mensajes anteriores -----')
                        messagebox.showerror('Error de entrenamiento','Revisa el detalle en la consola del panel.')
                    if self.current_view=='Mapa y archivos' and self.run_button and self.run_button.winfo_exists():
                        self.run_button.config(state='normal',text='▶  Entrenar y actualizar')
        except queue.Empty:
            pass
        self.after(180,self.read_worker_messages)


if __name__ == '__main__':
    app = PanelVial()
    app.mainloop()
