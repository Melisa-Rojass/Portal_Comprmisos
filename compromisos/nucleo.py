# -*- coding: utf-8 -*-
"""Núcleo del Portal de compromisos SAO6 (prueba1 · Django).

Es la misma lógica del portal original (portal.py): lectura directa del acta vigente de cada comité,
personas y responsables del proceso, correos automáticos, revisiones de las 11:00 y 4:00, Excel y cierre
de tareas en el acta. Lo único que cambia es dónde se guardan los datos: en la base de datos de Django
(ver almacen.py) en lugar de los archivos .json.
"""
import datetime as dt
import hashlib
import hmac
import importlib.util
import io
import os
import re
import secrets
import threading
import time
import smtplib
import ssl
import unicodedata
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape as hesc

import openpyxl

from . import almacen as A
from .config import CFG, archivo_portal

LOCK = threading.RLock()


# ------------------------------------------------------------------ códigos cifrados
def cifrar(texto):
    sal = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", texto.encode(), sal.encode(), 200_000).hex()
    return f"pbkdf2$200000${sal}${h}"


def verificar(cifrado, texto):
    try:
        _, it, sal, h = str(cifrado).split("$")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", texto.encode(), sal.encode(), int(it)).hex(), h)
    except Exception:   # noqa
        return False


# ------------------------------------------------------------------ datos
_cache = {"mtime": None, "datos": None}


def _iso(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    return None if v in (None, "") else str(v).strip()


_MOD = {"mtime": None, "mod": None}


def _script():
    """Script que encuentra y lee las actas (se recarga solo si cambia). Se busca primero en la carpeta
    del portal y, si no está ahí, en la carpeta «Comités y reuniones»."""
    ruta = archivo_portal(CFG["script_consolidado"])          # prueba1 o la carpeta del portal
    if not os.path.exists(ruta):
        ruta = os.path.join(CFG["carpeta_actas"], CFG["script_consolidado"])
    mt = os.path.getmtime(ruta)
    if _MOD["mtime"] != mt:
        spec = importlib.util.spec_from_file_location("consolidar", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MOD.update(mtime=mt, mod=mod)
    return _MOD["mod"]


def leer_datos():
    """Tareas leídas DIRECTAMENTE del acta vigente de cada comité (la más reciente de cada subcarpeta).
    Se vuelven a leer solo cuando alguna acta cambia, así que cualquier cambio se ve al recargar la página."""
    try:
        mod = _script()
        vig = mod.vigentes(CFG["carpeta_actas"])
        clave = tuple(sorted((f, os.path.getmtime(f)) for f in vig.values()))
    except Exception as ex:   # noqa
        return {"tareas": [], "generado": f"No se pudieron leer las actas: {ex}", "error": True}
    if _cache["mtime"] == clave and _cache["datos"]:
        return _cache["datos"]
    filas, fuentes, _logo = mod.leer(CFG["carpeta_actas"])
    tareas = [{"c": _iso(r[0]), "i": r[1], "r": _iso(r[2]), "t": _iso(r[3]), "p": _iso(r[4]), "pl": _iso(r[5]),
               "e": (_iso(r[6]) or "Pendiente").capitalize(), "fc": _iso(r[7]), "n": _iso(r[8]), "s": _iso(r[9])}
              for r in filas if r[3]]
    ultima = max((m for _, m in clave), default=0)
    datos = {"tareas": tareas, "generado": f"{len(tareas)} compromisos de {len(fuentes)} actas vigentes",
             "archivo": dt.datetime.fromtimestamp(ultima).strftime("%d/%m/%Y %H:%M") if ultima else ""}
    _cache.update(mtime=clave, datos=datos)
    return datos


def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def nombres(resp):
    """'Ricardo Montoya / Carlos Alvarado' -> ['Ricardo Montoya', 'Carlos Alvarado']"""
    s = str(resp or "")
    s = re.sub(r"\(([^)]*)\)", lambda m: "/" + m.group(1).strip()[4:] if m.group(1).strip().lower().startswith("con ") else "", s)
    s = re.sub(r"\s+con\s+", "/", s, flags=re.I)
    return [p.strip() for p in re.split(r"[/,;]|\s+y\s+|\s+-\s+|\s+e\s+", s) if p.strip()]


def personas():
    return A.personas()


def resolver_persona(nombre, lista=None):
    """'Natalia Ospina' -> la persona del listado (por nombre, alias o nombre completo)."""
    lista = lista if lista is not None else personas()
    n = norm(nombre)
    if not n:
        return None
    exactas = [p for p in lista if p.get("email") and (norm(p["nombre"]) == n or any(norm(a) == n for a in p["alias"]))]
    if len(exactas) == 1:
        return exactas[0]
    toks = set(n.split())
    parciales = [p for p in lista if p.get("email") and toks <= {norm(t) for t in str(p.get("completo", "")).split()}]
    return parciales[0] if len(parciales) == 1 else (exactas[0] if exactas else None)


def jefes_de(p, lista=None):
    """Correos de los responsables del proceso de una persona (sin incluirse a sí misma)."""
    out = []
    for n in p.get("jefes", []):
        j = resolver_persona(n, lista)
        if j and j["email"] != p.get("email") and j["email"] not in out:
            out.append(j["email"])
    return out


def equipo_de(email):
    """Personas a cargo de un jefe, directas e indirectas (los equipos de sus equipos)."""
    lista = personas()
    a_cargo = {}
    for p in lista:
        for j in jefes_de(p, lista):
            a_cargo.setdefault(j, []).append(p)
    vistos, cola, out = {email}, [email], []
    while cola:
        for p in a_cargo.get(cola.pop(0), []):
            if p["email"] not in vistos:
                vistos.add(p["email"])
                out.append(p)
                cola.append(p["email"])
    return out


def persona_por_email(email):
    return next((p for p in personas() if p.get("email", "").lower() == email), None)


def _mapa_alias():
    return {norm(a): p["nombre"] for p in personas() for a in p["alias"]}


def con_personas(tareas):
    """Agrega a cada tarea 'comp': las personas involucradas (nombres de las actas unidos a cada persona)."""
    mapa = _mapa_alias()
    out = []
    for t in tareas:
        vistos = []
        for a in nombres(t.get("p")):
            n = mapa.get(norm(a), a)
            if n not in vistos:
                vistos.append(n)
        out.append(dict(t, comp=vistos))
    return out


def tareas_de(email):
    alias = {norm(a) for p in personas() if p.get("email", "").lower() == email for a in p["alias"]}
    return [t for t in leer_datos()["tareas"] if any(norm(a) in alias for a in nombres(t["p"]))]


def _nombre_corto(email, completo):
    """'sonia.osorio@..' + 'OSORIO PULIDO SONIA' -> 'Sonia Osorio' (con tildes del nombre completo)."""
    toks = str(completo or "").split()
    partes = []
    for parte in email.split("@")[0].replace("_", ".").split("."):
        t = next((t for t in toks if norm(t) == norm(parte)), parte)
        partes.append(t.capitalize())
    return " ".join(p for p in partes if p)


def importar_listado(origen, lista):
    """Agrega o actualiza personas desde el Excel de correos (columnas: Email, Nombre, Cargo, Área).
    No borra a nadie ni cambia los nombres de actas ya asignados."""
    wb = openpyxl.load_workbook(origen, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    filas = list(ws.iter_rows(values_only=True))
    wb.close()
    if not filas:
        raise ValueError("El archivo está vacío.")
    enc = [norm(c) for c in filas[0]]
    def col(*claves):
        return next((i for i, h in enumerate(enc) if any(k in h for k in claves)), None)
    ce, cn, cc, ca = col("email", "correo"), col("nombre"), col("cargo"), col("ccosto", "area", "centro")
    cm = col("celular", "movil", "telefono", "whatsapp")
    cj = col("responsable", "jefe")          # "Responsables del proceso": nombres separados por " - "
    if ce is None:
        raise ValueError("No encontré la columna de correo (Email).")
    por_email = {p.get("email"): p for p in lista if p.get("email")}
    nuevos = actualizados = 0
    for r in filas[1:]:
        e = str(r[ce] or "").strip().lower()
        if not email_valido(e):
            continue
        completo = str(r[cn] or "").strip() if cn is not None else ""
        cargo = str(r[cc] or "").strip().capitalize() if cc is not None else ""
        area = str(r[ca] or "").strip() if ca is not None else ""
        cel = re.sub(r"\D", "", str(r[cm] or ""))[-10:] if cm is not None else ""
        jefes = [x.strip() for x in re.split(r"\s+-\s+|/|;|,", str(r[cj] or "")) if x.strip()] if cj is not None else None
        p = por_email.get(e)
        if not p:
            # ¿Ya existe en las actas sin correo? (p. ej. "Ana Cristina" -> "ORTIZ ANA CRISTINA")
            toks = {norm(t) for t in completo.split()}
            cands = [q for q in lista if not q.get("email") and toks and
                     any(set(norm(a).split()) <= toks for a in q["alias"] + [q["nombre"]])]
            if len(cands) == 1:
                p = cands[0]
                p["email"] = e
                por_email[e] = p
        if p:
            p.update(cargo=cargo or p.get("cargo", ""), area=area or p.get("area", ""), completo=completo or p.get("completo", ""))
            if cel:
                p["celular"] = cel
            if jefes is not None:
                p["jefes"] = jefes
            actualizados += 1
        else:
            corto = _nombre_corto(e, completo)
            if completo and not all(any(norm(t) == norm(x) for x in completo.split()) for t in corto.split()):
                corto = completo.title()          # correo que no coincide con el nombre (p. ej. gmail)
            p = {"k": secrets.token_hex(4), "nombre": corto, "alias": [corto], "email": e,
                 "cargo": cargo, "area": area, "completo": completo}
            if cel:
                p["celular"] = cel
            if jefes is not None:
                p["jefes"] = jefes
            lista.append(p)
            por_email[e] = p
            nuevos += 1
    return nuevos, actualizados


# ------------------------------------------------------------------ usuarios
def es_admin(email):
    return email in CFG["administradores"]


def email_valido(email):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""))


def registrado(email):
    if A.usuario(email).get("bloqueado"):
        return False
    return es_admin(email) or persona_por_email(email) is not None



# ------------------------------------------------------------------ correos

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def nombre_equipo():
    import socket
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "localhost"


def url_portal():
    return CFG.get("url_portal") or f"http://{nombre_equipo()}:{CFG['puerto']}"


def correo_listo():
    c = CFG["correo"]
    return bool(c.get("servidor") and c.get("remitente"))


def _registrar_envio(dest, asunto, ok, detalle=""):
    A.registrar_envio(dt.datetime.now().strftime("%d/%m/%Y %H:%M"), dest, asunto, ok, detalle)


def enviar_correo(dest, asunto, html, texto, siempre_real=False):
    """Envía un correo. En modo prueba lo manda a correo_prueba (salvo los códigos de acceso)."""
    real = dest
    if CFG.get("modo_prueba") and not siempre_real:
        dest = CFG.get("correo_prueba") or dest
        asunto = f"[PRUEBA · para {real}] {asunto}" if real != dest else f"[PRUEBA] {asunto}"
    c = CFG["correo"]
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((c.get("nombre_remitente") or "Compromisos SAO6", c["remitente"]))
    msg["To"] = dest
    msg.set_content(texto)
    cid = make_msgid(domain="sao6.portal")
    msg.add_alternative(html.replace("cid:logo", "cid:" + cid[1:-1]), subtype="html")
    try:
        with open(archivo_portal("icono-192.png"), "rb") as f:
            msg.get_payload()[1].add_related(f.read(), "image", "png", cid=cid)
    except OSError:
        pass
    try:
        puerto = int(c.get("puerto") or 587)
        seg = c.get("seguridad", "starttls")
        if seg == "ssl":
            srv = smtplib.SMTP_SSL(c["servidor"], puerto, context=ssl.create_default_context(), timeout=30)
        else:
            srv = smtplib.SMTP(c["servidor"], puerto, timeout=30)
            if seg == "starttls":
                srv.starttls(context=ssl.create_default_context())
        with srv:
            if c.get("usuario"):
                srv.login(c["usuario"], c.get("clave", ""))
            srv.send_message(msg)
        _registrar_envio(real if real == dest else f"{real} → {dest}", asunto, True)
        return True, ""
    except Exception as ex:   # noqa
        _registrar_envio(real, asunto, False, ex)
        return False, str(ex)


def _fmt(d):
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else (d or "—")


def _vencida(t):
    pl = t.get("pl") or ""
    return t.get("e") != "Cerrado" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", pl) and pl < dt.date.today().isoformat()


def _por_vencer(t, dias=7):
    pl = t.get("pl") or ""
    if t.get("e") == "Cerrado" or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pl):
        return False
    hoy = dt.date.today()
    return hoy.isoformat() <= pl <= (hoy + dt.timedelta(days=dias)).isoformat()


def _por_comite(tareas):
    g = {}
    for t in tareas:
        x = g.setdefault(t.get("c") or "Sin comité", [0, 0])
        x[0] += 1
        x[1] += 1 if _vencida(t) else 0
    return sorted(g.items(), key=lambda kv: (-kv[1][1], -kv[1][0], kv[0]))


def _html_correo(nombre, titulo, intro, cajas, grupos, col2="Pendientes", boton="Ver mis compromisos", col1="Comité / reunión"):
    """Correo resumido en un recuadro de 600 px (maquetado con tablas para que Outlook lo respete)."""
    url = url_portal()
    F = "font-family:Arial,Helvetica,sans-serif;"
    ancho = 100 // len(cajas)
    tds = "".join(
        f'<td width="{ancho}%" valign="top" style="padding:0 4px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #E3E8DF;border-top:4px solid {color}">'
        f'<tr><td align="center" style="{F}padding:10px 4px 2px;font-size:24px;font-weight:bold;color:{"#C00000" if color == "#C00000" and n else "#005439"}">{n}</td></tr>'
        f'<tr><td align="center" style="{F}padding:0 4px 10px;font-size:11px;color:#747074">{hesc(lab)}</td></tr></table></td>'
        for lab, n, color in cajas)
    filas = "".join(
        f'<tr><td style="{F}padding:8px 10px;border-bottom:1px solid #E3E8DF;font-size:13px;color:#1f2a1f">{hesc(c)}</td>'
        f'<td align="center" style="{F}padding:8px 10px;border-bottom:1px solid #E3E8DF;font-size:13px;color:#1f2a1f">{n}</td>'
        f'<td align="center" style="{F}padding:8px 10px;border-bottom:1px solid #E3E8DF;font-size:13px;{"color:#C00000;font-weight:bold" if v else "color:#747074"}">{v or "—"}</td></tr>'
        for c, (n, v) in grupos)
    th = f'style="{F}background:#005439;color:#ffffff;padding:8px 10px;font-size:11px;font-weight:bold"'
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#F5F7F3">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#F5F7F3" style="background:#F5F7F3">
<tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" bgcolor="#ffffff" style="width:600px;max-width:600px;background:#ffffff;border:1px solid #DDE3D8">
 <tr><td bgcolor="#005439" style="background:#005439;padding:14px 22px">
  <table role="presentation" cellpadding="0" cellspacing="0"><tr>
   <td valign="middle"><img src="cid:logo" width="34" height="34" alt="SAO6" style="display:block;border:0"></td>
   <td valign="middle" style="{F}padding-left:10px;font-size:17px;font-weight:bold;color:#ffffff">{hesc(titulo)}</td>
  </tr></table></td></tr>
 <tr><td style="{F}padding:20px 24px 6px;font-size:14px;color:#1f2a1f;line-height:20px">
  Hola {hesc(nombre.split(" ")[0] if nombre else "")},<br><br>{intro}</td></tr>
 <tr><td style="padding:12px 20px 4px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{tds}</tr></table></td></tr>
 <tr><td style="padding:14px 24px 4px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
   <tr><td {th}>{hesc(col1)}</td><td align="center" {th}>{hesc(col2)}</td><td align="center" {th}>Vencidos</td></tr>{filas}</table></td></tr>
 <tr><td align="center" style="padding:22px 24px 6px">
  <table role="presentation" cellpadding="0" cellspacing="0"><tr>
   <td bgcolor="#46913C" style="background:#46913C;border-radius:6px;padding:12px 28px">
    <a href="{url}" style="{F}font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;display:inline-block">{boton}</a></td>
  </tr></table></td></tr>
 <tr><td align="center" style="{F}padding:6px 30px 16px;font-size:12px;color:#747074;line-height:17px">
  El detalle de cada compromiso, sus plazos y notas está en el portal, donde también puedes descargarlos en Excel.</td></tr>
 <tr><td style="{F}padding:12px 24px 18px;font-size:11px;color:#747074;line-height:16px;border-top:1px solid #E3E8DF">
  Ingresa en <a href="{url}" style="color:#46913C">{url}</a> con tu correo de la empresa: te llegará un código para entrar, sin contraseña.<br>Este es un mensaje automático del Portal de compromisos SAO6.</td></tr>
</table>
</td></tr></table></body></html>"""


def _texto(intro, cajas, grupos):
    lin = [re.sub("<[^>]+>", "", intro), ""]
    lin += [f"{lab}: {n}" for lab, n, _ in cajas]
    lin += [""] + [f"- {c}: {n}" + (f" ({v} vencidos)" if v else "") for c, (n, v) in grupos]
    lin += ["", f"Ver el detalle en el portal: {url_portal()}"]
    return "\n".join(lin)


def _clave(t):
    return f"{t.get('c')}|{t.get('i')}"


def _pl(n, s, p=None):
    return s if n == 1 else (p or s + "s")


def correo_nuevas(nombre, nuevas, pendientes):
    n = len(nuevas)
    asunto = "Tienes un compromiso nuevo" if n == 1 else f"Tienes {n} compromisos nuevos"
    intro = (f"Se te {_pl(n, 'asignó', 'asignaron')} <b>{n} {_pl(n, 'compromiso nuevo', 'compromisos nuevos')}</b> en las actas de los comités. "
             "Ingresa al portal para ver de qué se trata y su plazo.")
    venc = sum(1 for t in pendientes if _vencida(t))
    cajas = [("Nuevos", n, "#6BA43A"), ("Pendientes en total", len(pendientes), "#E0B000"), ("Vencidos", venc, "#C00000")]
    grupos = _por_comite(nuevas)
    return asunto, _html_correo(nombre, asunto, intro, cajas, grupos, col2="Nuevos"), _texto(intro, cajas, grupos)


def correo_jefe(nombre, filas):
    """filas = [(persona, pendientes, vencidas, dias_max)] del equipo."""
    tot_p, tot_v = sum(f[1] for f in filas), sum(f[2] for f in filas)
    asunto = f"Compromisos de tu equipo: {tot_p} {_pl(tot_p, 'pendiente')}" + (f" ({tot_v} {_pl(tot_v, 'vencido')})" if tot_v else "")
    intro = (f"Este es el resumen de los compromisos pendientes de las personas a tu cargo: <b>{tot_p}</b> en total"
             + (f', de los cuales <b style="color:#C00000">{tot_v} {_pl(tot_v, "está vencido", "están vencidos")}</b>' if tot_v else "")
             + ". En el portal, pestaña «Mi equipo», puedes ver el detalle de cada persona.")
    cajas = [("Personas con pendientes", len(filas), "#6BA43A"), ("Pendientes", tot_p, "#E0B000"), ("Vencidos", tot_v, "#C00000")]
    grupos = [(f[0], (f[1], f[2])) for f in filas]
    return asunto, _html_correo(nombre, "Compromisos de tu equipo", intro, cajas, grupos, col2="Pendientes", boton="Ver el indicador de mi equipo",
                                col1="Persona"), _texto(intro, cajas, grupos)


def correo_recordatorio(nombre, pend):
    n, venc, pronto = len(pend), sum(1 for t in pend if _vencida(t)), sum(1 for t in pend if _por_vencer(t))
    asunto = f"Recordatorio: tienes {n} {_pl(n, 'compromiso pendiente', 'compromisos pendientes')}" + (f" ({venc} {_pl(venc, 'vencido')})" if venc else "")
    intro = (f"Tienes <b>{n} {_pl(n, 'compromiso pendiente', 'compromisos pendientes')}</b>"
             + (f', <b style="color:#C00000">{venc} ya {_pl(venc, "vencido")}</b>' if venc else "")
             + ". Ingresa al portal para revisarlos y ponerte al día.")
    cajas = [("Pendientes", n, "#E0B000"), ("Vencidos", venc, "#C00000"), ("Vencen en 7 días", pronto, "#6BA43A")]
    grupos = _por_comite(pend)
    return asunto, _html_correo(nombre, "Tus compromisos pendientes", intro, cajas, grupos), _texto(intro, cajas, grupos)


def revisar_correos(avisos=True):
    """Avisos de compromisos nuevos (en cada revisión) y recordatorio diario (a su hora)."""
    if not correo_listo():
        return
    gente = [p for p in personas() if p.get("email")]
    if avisos:
        vistas = A.estado("vistas", {})
        cambios = False
        for p in gente:
            e = p["email"]
            ts = tareas_de(e)
            claves = {_clave(t) for t in ts}
            if e not in vistas:            # primera vez: se toma como base, sin avisar
                vistas[e] = sorted(claves)
                cambios = True
                continue
            nuevas = [t for t in ts if _clave(t) not in set(vistas[e]) and t.get("e") != "Cerrado"]
            if nuevas and CFG.get("notificar_nuevas"):
                ok, _ = enviar_correo(e, *correo_nuevas(p["nombre"], nuevas, [t for t in ts if t.get("e") != "Cerrado"]))
                if not ok:
                    continue
            if set(vistas[e]) != claves:
                vistas[e] = sorted(claves)
                cambios = True
        if cambios:
            A.poner_estado("vistas", vistas)

    # recordatorio diario
    ahora = dt.datetime.now()
    hoy = ahora.date().isoformat()
    if (CFG.get("recordatorio_diario") and ahora.weekday() in CFG.get("dias_recordatorio", [])
            and ahora.strftime("%H:%M") >= CFG.get("hora_recordatorio", "07:30")
            and A.estado("ultimo_recordatorio") != hoy):
        A.poner_estado("ultimo_recordatorio", hoy)
        for p in gente:
            pend = [t for t in tareas_de(p["email"]) if t.get("e") != "Cerrado"]
            if pend:
                enviar_correo(p["email"], *correo_recordatorio(p["nombre"], pend))
        if CFG.get("resumen_jefes"):
            enviar_resumen_jefes()


def resumen_equipo(email):
    filas = []
    for p in equipo_de(email):
        pend = [t for t in tareas_de(p["email"]) if t.get("e") != "Cerrado"]
        if pend:
            venc = [t for t in pend if _vencida(t)]
            dmax = max(((dt.date.today() - dt.date.fromisoformat(t["pl"])).days for t in venc), default=0)
            filas.append((p["nombre"], len(pend), len(venc), dmax))
    return sorted(filas, key=lambda f: (-f[3], -f[2], -f[1], f[0]))


def enviar_resumen_jefes():
    """Envía a cada responsable de proceso el resumen de pendientes de su equipo."""
    lista = personas()
    jefes = {j for p in lista for j in jefes_de(p, lista)}
    for e in sorted(jefes):
        filas = resumen_equipo(e)
        if filas:
            j = persona_por_email(e) or {"nombre": ""}
            enviar_correo(e, *correo_jefe(j["nombre"], filas))


# ------------------------------------------------------------------ actualización automática
ESTADO = {"revision": None, "error": None}


def acta_de_comite(comite):
    """Ruta del acta vigente (la más reciente) del comité o reunión con ese nombre."""
    mod = _script()
    for carpeta, f in mod.vigentes(CFG["carpeta_actas"]).items():
        try:
            wb = openpyxl.load_workbook(f, read_only=True)
            titulo = wb["Compromisos"]["A1"].value
            wb.close()
        except Exception:   # noqa
            continue
        if mod.nombre_comite(titulo, carpeta) == comite:
            return f
    return None


def _actas_mas_reciente():
    import glob
    fs = [f for f in glob.glob(os.path.join(CFG["carpeta_actas"], "*", "*Acta y compromisos.xlsx"))
          if not os.path.basename(f).startswith("~$")]
    return max((os.path.getmtime(f) for f in fs), default=0)


def revisar_listado(forzar=False):
    """Importa el listado de correos de la carpeta si cambió desde la última vez."""
    ruta = os.path.join(CFG["carpeta_actas"], CFG["archivo_correos"])
    if not os.path.exists(ruta):
        return None
    mt = os.path.getmtime(ruta)
    if not forzar and A.estado("listado_mtime") == mt:
        return None
    with LOCK:
        lista = personas()
        res = importar_listado(ruta, lista)
        A.guardar_personas(lista)
        A.poner_estado("listado_mtime", mt)
        A.poner_estado("listado_leido", dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
    print(f" [{dt.datetime.now():%d/%m/%Y %H:%M}] Listado de correos leído: {res[0]} nuevas, {res[1]} actualizadas.")
    return res


def _turno_pendiente(ahora):
    """Devuelve el turno de revisión de hoy que ya llegó y aún no se hizo (p. ej. '2026-11-20 11:00')."""
    hechos = A.estado("turno_revision", "")
    hoy = ahora.date().isoformat()
    vencidos = [h for h in sorted(CFG.get("horas_revision", ["11:00", "16:00"])) if ahora.strftime("%H:%M") >= h]
    if not vencidos:
        return None
    turno = f"{hoy} {vencidos[-1]}"
    return turno if turno > hechos else None


def revision_completa():
    """Lee el listado de correos, vuelve a leer las actas y envía los avisos de tareas nuevas."""
    try:
        revisar_listado()
    except PermissionError:
        pass
    except Exception as ex:   # noqa
        print(f" No se pudo leer el listado de correos: {ex}")
    ESTADO.update(revision=dt.datetime.now().strftime("%d/%m/%Y %H:%M"), error=None)
    try:
        revisar_correos(avisos=True)
    except Exception as ex:   # noqa
        print(f" Error en el envío de correos: {ex}")


def vigilante():
    """Revisa actas y listado SOLO en las horas configuradas (11:00 y 16:00); si el portal estaba apagado a esa hora,
    hace la revisión pendiente al encender. El recordatorio diario se revisa cada minuto."""
    while True:
        ahora = dt.datetime.now()
        turno = _turno_pendiente(ahora)
        if turno:
            try:
                revision_completa()
                A.poner_estado("turno_revision", turno)
            except PermissionError:
                ESTADO["error"] = "Un archivo está abierto en Excel; se reintentará en 10 minutos."
                time.sleep(600)
                continue
            except Exception as ex:   # noqa
                ESTADO["error"] = f"No se pudo actualizar: {ex}"
                print(" " + ESTADO["error"])
                time.sleep(600)
                continue
        try:
            revisar_correos(avisos=False)      # solo el recordatorio diario, a su hora
        except Exception as ex:   # noqa
            print(f" Error en el recordatorio: {ex}")
        time.sleep(60)


# ------------------------------------------------------------------ Excel
COLS_XL = [("Comité / reunión", 30), ("ID", 6), ("Reunión", 12), ("Compromiso", 60), ("Responsable", 26), ("Plazo", 14),
           ("Estado", 12), ("Días de atraso", 10), ("Fecha de cierre", 13), ("Nota de cierre", 36), ("Seguimiento", 36),
           ("Notas del responsable", 40)]


def _excel(tareas, titulo, notas=None):
    """Excel de compromisos (mismo formato del portal original)."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Compromisos"
    n = len(COLS_XL)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
    ws["A1"] = titulo
    ws["A1"].font = Font(name="Arial", size=14, bold=True, color="005439")
    ws["A2"] = f"Portal de compromisos SAO6 · descargado el {dt.datetime.now():%d/%m/%Y %H:%M} · datos actualizados {leer_datos().get('archivo', '')}"
    ws["A2"].font = Font(name="Arial", size=9, color="747074")
    for i, (h, w) in enumerate(COLS_XL, 1):
        c = ws.cell(4, i, h)
        c.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="005439")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    def fecha(v):
        return dt.datetime.strptime(v, "%Y-%m-%d") if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else v
    orden = sorted(tareas, key=lambda t: (t.get("e") == "Cerrado", not _vencida(t), t.get("pl") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t.get("pl") or "") else "9999"))
    for r, t in enumerate(orden, 5):
        v = _vencida(t)
        est = "Vencido" if v else ("Cerrado" if t.get("e") == "Cerrado" else "Pendiente")
        atraso = (dt.date.today() - dt.date.fromisoformat(t["pl"])).days if v else None
        vals = [t.get("c"), t.get("i"), fecha(t.get("r")), t.get("t"), t.get("p"), fecha(t.get("pl")), est, atraso, fecha(t.get("fc")), t.get("n"), t.get("s"),
                (notas or {}).get(_clave(t))]
        for i, val in enumerate(vals, 1):
            c = ws.cell(r, i, val)
            c.font = Font(name="Arial", size=10, color="C00000" if v and i in (4, 6, 7, 8) else "000000", bold=v and i in (7, 8))
            c.alignment = Alignment(vertical="top", wrap_text=i in (1, 4, 5, 10, 11, 12), horizontal="center" if i in (2, 3, 6, 7, 8, 9) else "left")
            if isinstance(val, dt.datetime):
                c.number_format = "dd/mm/yyyy"
        if est == "Cerrado":
            for i in range(1, n + 1):
                ws.cell(r, i).fill = PatternFill("solid", fgColor="E2EFDA")
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:{get_column_letter(n)}{max(5, 4 + len(orden))}"
    ws.sheet_view.showGridLines = False
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def _filtrar(tareas, a):
    estado, comite, q = a.get("estado", "Todas"), a.get("comite", ""), norm(a.get("q", ""))
    out = []
    for t in tareas:
        if estado == "Pendiente" and t.get("e") == "Cerrado":
            continue
        if estado == "Vencido" and not _vencida(t):
            continue
        if estado == "Cerrado" and t.get("e") != "Cerrado":
            continue
        if comite and norm(comite) not in norm(t.get("c") or ""):
            continue
        if q and q not in norm(" ".join(str(t.get(k) or "") for k in ("t", "c", "p", "s", "n"))):
            continue
        out.append(t)
    return out


# ------------------------------------------------------------------ ingreso
_intentos = {}   # email -> [fallos, bloqueado_hasta]


def _bloqueado(email):
    f = _intentos.get(email)
    return f and f[1] > time.time()


def _fallo(email):
    f = _intentos.setdefault(email, [0, 0])
    f[0] += 1
    if f[0] >= 5:
        f[0], f[1] = 0, time.time() + 15 * 60



_solicitudes = {}   # email/ip -> [marcas de tiempo]


def _limite(clave, maximo, segundos):
    ahora = time.time()
    lst = [t for t in _solicitudes.get(clave, []) if ahora - t < segundos]
    _solicitudes[clave] = lst
    if len(lst) >= maximo:
        return True
    lst.append(ahora)
    return False


def _html_codigo(nombre, codigo, minutos):
    F = "font-family:Arial,Helvetica,sans-serif;"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:0;background:#F5F7F3">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#F5F7F3"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" bgcolor="#ffffff" style="width:480px;border:1px solid #DDE3D8">
 <tr><td bgcolor="#005439" style="padding:14px 22px"><table role="presentation" cellpadding="0" cellspacing="0"><tr>
  <td><img src="cid:logo" width="34" height="34" alt="SAO6" style="display:block;border:0"></td>
  <td style="{F}padding-left:10px;font-size:17px;font-weight:bold;color:#ffffff">Tu código para entrar</td></tr></table></td></tr>
 <tr><td style="{F}padding:20px 24px 4px;font-size:14px;color:#1f2a1f;line-height:20px">Hola {hesc(nombre.split(" ")[0] if nombre else "")},<br><br>
  Este es tu código para entrar al Portal de compromisos SAO6:</td></tr>
 <tr><td align="center" style="padding:14px 24px"><table role="presentation" cellpadding="0" cellspacing="0"><tr>
  <td bgcolor="#E2EFDA" style="{F}padding:12px 28px;font-size:30px;letter-spacing:6px;font-weight:bold;color:#005439">{codigo}</td></tr></table></td></tr>
 <tr><td style="{F}padding:4px 24px 20px;font-size:12px;color:#747074;line-height:17px">Vence en {minutos} minutos.
  Si no lo pediste tú, ignora este correo: nadie podrá entrar sin acceso a tu buzón.</td></tr>
</table></td></tr></table></body></html>"""


# ------------------------------------------------------------------ administración
def _estado_cuentas():
    U, ahora = A.usuarios(), dt.datetime.now().isoformat()
    out = {}
    for e, u in U.items():
        if u.get("bloqueado"):
            out[e] = {"estado": "bloqueado"}
            continue
        if u.get("pw") or u.get("activado"):
            out[e] = {"estado": "activa", "desde": u.get("ultimo_ingreso") or u.get("activado", "")}
        elif u.get("codigo") and u.get("codigo_vence", "") > ahora:
            out[e] = {"estado": "codigo", "vence": u["codigo_vence"][:16].replace("T", " ")}
    return out


def cerrar_en_acta(clave, estado, fecha, nota, por):
    """Escribe el cierre (o reapertura) de un compromiso en el acta vigente del comité.
    Devuelve (respuesta, código HTTP) igual que el portal original."""
    comite, ident = clave.rsplit("|", 1)
    try:
        ruta = acta_de_comite(comite)
    except Exception as ex:   # noqa
        return {"error": f"No se pudo buscar el acta: {ex}"}, 500
    if not ruta:
        return {"error": f"No encontré el acta vigente de «{comite}»."}, 404
    tmp = os.path.join(os.path.dirname(ruta), "._portal_guardando.xlsx")
    with LOCK:
        try:
            wb = openpyxl.load_workbook(ruta)
            ws = wb["Compromisos"]
            fila_hdr = next((c.row for c in ws["A"] if c.value == "ID"), None)
            fila = next((c.row for c in ws["A"] if fila_hdr and c.row > fila_hdr and str(c.value).strip() == str(ident).strip()), None)
            if not fila:
                return {"error": f"No encontré la tarea #{ident} en el acta."}, 404
            ws.cell(fila, 6).value = estado
            formato = next((c.number_format for c in ws["G"] if c.row > fila_hdr and c.row != fila
                            and isinstance(c.value, dt.datetime) and not c.number_format.startswith("yyyy-mm-dd h")), "dd/mm/yyyy")
            ws.cell(fila, 7).value = fecha
            if fecha:
                ws.cell(fila, 7).number_format = formato
            ws.cell(fila, 8).value = nota or None
            wb.calculation.fullCalcOnLoad = True     # Excel recalcula los conteos del acta al abrirla
            wb.save(tmp)
            os.replace(tmp, ruta)
        except PermissionError:
            try:
                os.remove(tmp)
            except Exception:   # noqa
                pass
            return {"error": "El acta está abierta en Excel (por ti o por otra persona). Ciérrala e intenta de nuevo."}, 409
        except Exception as ex:   # noqa
            return {"error": f"No se pudo guardar el acta: {ex}"}, 500
        A.registrar_cierre(dt.datetime.now().strftime("%d/%m/%Y %H:%M"), por, clave, estado, os.path.basename(ruta))
    return {"ok": True, "acta": os.path.relpath(ruta, CFG["carpeta_actas"])}, 200


def nuevo_codigo_respaldo(e):
    """Código de 8 caracteres que la administradora le puede dar a una persona (vale varios días)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codigo = "".join(secrets.choice(alfabeto) for _ in range(8))
    vence = dt.datetime.now() + dt.timedelta(days=CFG["dias_validez_codigo"])
    with LOCK:
        u = A.usuario(e)
        u.update(codigo=cifrar(codigo), codigo_vence=vence.isoformat())
        A.guardar_usuario(e, u)
    return codigo, vence
