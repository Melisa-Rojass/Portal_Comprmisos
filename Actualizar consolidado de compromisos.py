# -*- coding: utf-8 -*-
"""
Consolida en un solo archivo todos los compromisos de las actas de
Z:\\GERENCIA\\PRIVADA\\Comités y reuniones.

- Lee, en cada subcarpeta, el archivo vigente "... - Acta y compromisos.xlsx"
  (si hay varios, el de fecha más reciente en el nombre) y su hoja Compromisos.
- Genera "Consolidado de compromisos.xlsx" en la carpeta raíz.
- No modifica las actas. El consolidado se regenera completo en cada ejecución:
  los cambios se hacen siempre en el acta de cada comité.

Uso: doble clic o  python "Actualizar consolidado de compromisos.py" [carpeta_raiz]
Requiere: openpyxl (incluido en Anaconda).
"""
import datetime as dt
import glob
import io
import os
import sys

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
OUT_NAME = "Consolidado de compromisos.xlsx"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, OUT_NAME)

VERDE_OSC, VERDE_TIT, GRIS = "005439", "46913C", "747074"
F = "Arial"


def vigentes(root):
    por_carpeta = {}
    for f in glob.glob(os.path.join(root, "*", "*Acta y compromisos.xlsx")):
        if os.path.basename(f).startswith("~$"):
            continue
        por_carpeta.setdefault(os.path.basename(os.path.dirname(f)), []).append(f)
    return {k: sorted(v)[-1] for k, v in sorted(por_carpeta.items())}


def nombre_comite(titulo, carpeta):
    if titulo and "–" in str(titulo):
        return str(titulo).split("–", 1)[1].strip()
    return carpeta.split(". ", 1)[-1]


def leer(root):
    filas, fuentes, logo = [], [], None
    for carpeta, f in vigentes(root).items():
        wb = openpyxl.load_workbook(f, data_only=True)
        if "Compromisos" not in wb.sheetnames:
            continue
        ws = wb["Compromisos"]
        if logo is None and getattr(ws, "_images", None):
            try:
                logo = ws._images[0]._data()
            except Exception:
                pass
        comite = nombre_comite(ws["A1"].value, carpeta)
        hdr, n, ultima = None, 0, None
        for r in ws.iter_rows(values_only=True):
            r = (list(r) + [None] * 9)[:9]
            if r[0] == "ID":
                hdr = True
                continue
            if not hdr or not isinstance(r[0], (int, float)) or not r[2]:
                continue
            estado = (str(r[5]).strip().capitalize() if r[5] else "Pendiente")
            filas.append([comite, int(r[0]), r[1], r[2], r[3], r[4], estado, r[6], r[7], r[8],
                          os.path.relpath(f, root)])
            n += 1
            if isinstance(r[1], dt.datetime) and (ultima is None or r[1] > ultima):
                ultima = r[1]
        fuentes.append((comite, carpeta, os.path.relpath(f, root), n, ultima))
    return filas, fuentes, logo


def encabezado(ws, titulo, subtitulo, ncols, logo):
    ult = get_column_letter(ncols)
    ws.merge_cells(f"A1:{ult}1")
    ws.merge_cells(f"A2:{ult}2")
    ws["A1"] = titulo
    ws["A1"].font = Font(name=F, size=16, bold=True, color=VERDE_OSC)
    ws["A2"] = subtitulo
    ws["A2"].font = Font(name=F, size=10, color=GRIS)
    for c in ("A1", "A2"):
        ws[c].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 6
    ws.row_dimensions[4].height = 4
    ws.sheet_view.showGridLines = False
    if logo:
        img = XLImage(io.BytesIO(logo))
        img.width, img.height = 64, 64
        ws.add_image(img, "A1")


def fila_titulos(ws, fila, titulos):
    for i, t in enumerate(titulos, 1):
        c = ws.cell(fila, i, t)
        c.font = Font(name=F, size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=VERDE_OSC)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[fila].height = 19.5


def construir(filas, fuentes, logo, salida):
    ahora = dt.datetime.now()
    wb = openpyxl.Workbook()

    # ---------------- Compromisos ----------------
    ws = wb.active
    ws.title = "Compromisos"
    cols = ["Comité / reunión", "ID", "Reunión", "Tarea", "Responsable", "Plazo", "Estado",
            "Días vencido", "Fecha de cierre", "Nota de cierre", "Seguimiento", "Acta de origen"]
    anchos = [30, 6, 12, 60, 26, 16, 12, 10, 14, 34, 34, 22]
    encabezado(ws, "Compromisos consolidados – Comités y reuniones",
               f"Todos los comités · Actualizado el {ahora:%d/%m/%Y %H:%M} · "
               f"{len(filas)} compromisos de {len(fuentes)} actas vigentes", len(cols), logo)
    H = 6
    fila_titulos(ws, H, cols)
    for i, w in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    orden = {f[0]: i for i, f in enumerate(fuentes)}  # orden de las subcarpetas (0., 1., 2. ...)
    filas.sort(key=lambda x: (orden.get(x[0], 99), x[1]))
    for k, (comite, idn, reu, tarea, resp, plazo, estado, fcierre, nota, seg, origen) in enumerate(filas):
        r = H + 1 + k
        vals = [comite, idn, reu, tarea, resp, plazo, estado,
                f'=IF(AND(G{r}="Pendiente",ISNUMBER(F{r})),IF(TODAY()>F{r},TODAY()-F{r},""),"")',
                fcierre, nota, seg, os.path.basename(os.path.dirname(origen))]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(r, c, v)
            cell.font = Font(name=F, size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True,
                                       horizontal="left" if c in (1, 4, 5, 10, 11, 12) else "center")
            if isinstance(v, (dt.datetime, dt.date)):
                cell.number_format = "dd/mm/yyyy"
        ws.cell(r, 8).number_format = "0"
        link = ws.cell(r, 12)
        link.hyperlink = origen.replace("\\", "/")
        link.font = Font(name=F, size=10, color="0563C1", underline="single")

    last = max(H + 1, H + len(filas))
    rng = f"A{H+1}:L{last}"
    ws.auto_filter.ref = f"A{H}:L{last}"
    ws.freeze_panes = f"E{H+1}"
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'$G{H+1}="Cerrado"'],
                                  fill=PatternFill("solid", fgColor="E2EFDA", bgColor="E2EFDA")))
    ws.conditional_formatting.add(f"G{H+1}:G{last}", FormulaRule(formula=[f'$G{H+1}="Pendiente"'],
                                  fill=PatternFill("solid", fgColor="FFF2CC", bgColor="FFF2CC")))
    ws.conditional_formatting.add(f"F{H+1}:F{last}", FormulaRule(
        formula=[f'AND($G{H+1}="Pendiente",ISNUMBER($F{H+1}),$F{H+1}<TODAY())'],
        font=Font(name=F, color="C00000", bold=True)))
    ws.conditional_formatting.add(f"H{H+1}:H{last}", FormulaRule(
        formula=[f'AND(ISNUMBER($H{H+1}),$H{H+1}>0)'], font=Font(name=F, color="C00000", bold=True)))
    dv = DataValidation(type="list", formula1='"Pendiente,Cerrado"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"G{H+1}:G{last}")
    ws.print_title_rows = f"{H}:{H}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # ---------------- Resumen ----------------
    rs = wb.create_sheet("Resumen")
    rcols = ["Comité / reunión", "Total", "Pendientes", "Vencidos", "Cerrados", "% cumplimiento",
             "Última reunión", "Acta vigente"]
    encabezado(rs, "Resumen de compromisos por comité",
               f"Actualizado el {ahora:%d/%m/%Y %H:%M} · Vencidos = pendientes con plazo en fecha ya pasada",
               len(rcols), logo)
    fila_titulos(rs, 6, rcols)
    for i, w in enumerate([44, 10, 12, 11, 11, 15, 15, 60], 1):
        rs.column_dimensions[get_column_letter(i)].width = w
    C = "Compromisos!"
    rg = lambda col: f"{C}${col}${H+1}:${col}${last}"
    for k, (comite, carpeta, archivo, n, ultima) in enumerate(fuentes):
        r = 7 + k
        vals = [comite,
                f'=COUNTIF({rg("A")},A{r})',
                f'=COUNTIFS({rg("A")},A{r},{rg("G")},"Pendiente")',
                f'=COUNTIFS({rg("A")},A{r},{rg("H")},">0")',
                f'=COUNTIFS({rg("A")},A{r},{rg("G")},"Cerrado")',
                f'=IF(B{r}=0,"",E{r}/B{r})',
                ultima, archivo]
        for c, v in enumerate(vals, 1):
            cell = rs.cell(r, c, v)
            cell.font = Font(name=F, size=10)
            cell.alignment = Alignment(horizontal="left" if c in (1, 8) else "center", vertical="center")
        rs.cell(r, 6).number_format = "0%"
        rs.cell(r, 7).number_format = "dd/mm/yyyy"
        rs.cell(r, 8).hyperlink = archivo.replace("\\", "/")
        rs.cell(r, 8).font = Font(name=F, size=10, color="0563C1", underline="single")
    t = 7 + len(fuentes)
    rs.cell(t, 1, "Total").font = Font(name=F, size=10, bold=True)
    for c in range(2, 6):
        L = get_column_letter(c)
        cell = rs.cell(t, c, f"=SUM({L}7:{L}{t-1})")
        cell.font = Font(name=F, size=10, bold=True)
        cell.alignment = Alignment(horizontal="center")
    cell = rs.cell(t, 6, f'=IF(B{t}=0,"",E{t}/B{t})')
    cell.font = Font(name=F, size=10, bold=True)
    cell.alignment = Alignment(horizontal="center")
    cell.number_format = "0%"
    for c in range(1, 9):
        rs.cell(t, c).fill = PatternFill("solid", fgColor="E2EFDA")
    nota = rs.cell(t + 2, 1, "Este archivo se genera automáticamente desde el acta vigente de cada subcarpeta. "
                   "Las correcciones se hacen en el acta del comité; los cambios hechos aquí se pierden "
                   "en la siguiente actualización.")
    nota.font = Font(name=F, size=9, italic=True, color=GRIS)
    rs.merge_cells(start_row=t + 2, start_column=1, end_row=t + 2, end_column=8)
    nota.alignment = Alignment(wrap_text=True, vertical="top")
    rs.row_dimensions[t + 2].height = 28

    wb.move_sheet("Resumen", offset=-1)
    wb.active = 0
    wb.save(salida)
    return salida


if __name__ == "__main__":
    filas, fuentes, logo = leer(ROOT)
    out = construir(filas, fuentes, logo, OUT)
    print(f"Listo: {len(filas)} compromisos de {len(fuentes)} actas -> {out}")
