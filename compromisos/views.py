# -*- coding: utf-8 -*-
"""Vistas del portal: las mismas direcciones y respuestas del portal original, para que la página
(portal.html) funcione sin cambios."""
import datetime as dt
import functools
import json
import re
import secrets
import time

from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import almacen as A
from . import nucleo as N
from .config import CFG, CONFIG_PATH, archivo_portal, cargar_config, guardar_json, leer_json

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ------------------------------------------------------------------ utilidades
def responder(datos, estado=200):
    return JsonResponse(datos, status=estado, safe=False, json_dumps_params={"ensure_ascii": False})


def error(texto, estado):
    return responder({"error": texto}, estado)


def cuerpo(request):
    try:
        d = json.loads(request.body or b"{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def iniciar_sesion(request, email):
    request.session.flush()
    request.session["email"] = email
    request.session.set_expiry(int(CFG.get("horas_sesion", 720)) * 3600)


def api(admin=False, metodos=("GET",)):
    """Igual que el decorador del portal original: exige sesión (y administradora si admin=True).
    Los POST deben traer la cabecera X-Portal (protección contra solicitudes de otros sitios)."""
    def deco(f):
        @functools.wraps(f)
        def w(request, *a, **k):
            if request.method not in metodos:
                return error("Método no permitido", 405)
            if request.method == "POST" and request.headers.get("X-Portal") != "1":
                return error("Solicitud no válida", 400)
            email = request.session.get("email")
            if not email or not N.registrado(email):
                request.session.flush()
                return error("Debes iniciar sesión", 401)
            if admin and not N.es_admin(email):
                return error("Solo administradores", 403)
            return f(request, email, *a, **k)
        return csrf_exempt(w)
    return deco


def publica(f):
    """Vistas POST sin sesión (pedir código, entrar, salir)."""
    @functools.wraps(f)
    def w(request, *a, **k):
        if request.method != "POST":
            return error("Método no permitido", 405)
        if request.headers.get("X-Portal") != "1":
            return error("Solicitud no válida", 400)
        return f(request, *a, **k)
    return csrf_exempt(w)


def archivo(nombre, tipo, cache=0):
    resp = FileResponse(open(archivo_portal(nombre), "rb"), content_type=tipo)
    if cache:
        resp["Cache-Control"] = f"max-age={cache}"
    return resp


# ------------------------------------------------------------------ página y archivos
def inicio(request):
    return archivo("portal.html", "text/html; charset=utf-8")


def manifest(request):
    return responder({"name": "Portal de compromisos SAO6", "short_name": "Compromisos SAO6", "start_url": "/",
                      "display": "standalone", "background_color": "#F5F7F3", "theme_color": "#005439", "lang": "es",
                      "icons": [{"src": "/icono-192.png", "sizes": "192x192", "type": "image/png"},
                                {"src": "/icono-512.png", "sizes": "512x512", "type": "image/png"}]})


def icono(request, n):
    if n not in (192, 512):
        return HttpResponse(status=404)
    return archivo(f"icono-{n}.png", "image/png", 86400)


def favicon(request):
    return archivo("portal.ico", "image/x-icon", 86400)


# ------------------------------------------------------------------ ingreso
@publica
def solicitar_codigo(request):
    """Ingreso sin contraseña: la persona escribe su correo y le llega un código para entrar."""
    d = cuerpo(request)
    email = str(d.get("email", "")).strip().lower()
    if not N.email_valido(email):
        return error("Escribe un correo válido.", 400)
    if N._limite("ip:" + (request.META.get("REMOTE_ADDR") or ""), 20, 3600) or N._limite("e:" + email, 4, 900):
        return error("Ya pediste varios códigos. Espera unos minutos y revisa tu correo (también la carpeta de correo no deseado).", 429)
    if not N.registrado(email):
        return error("Ese correo no tiene acceso al portal. Comunícate con Gerencia.", 404)
    if not N.correo_listo():
        return error("El envío de códigos no está disponible en este momento. Comunícate con Gerencia.", 503)
    p = N.persona_por_email(email) or {}
    codigo = "".join(secrets.choice("0123456789") for _ in range(6))
    minutos = int(CFG.get("minutos_codigo", 10))
    with N.LOCK:
        u = A.usuario(email)
        u.update(codigo=N.cifrar(codigo), codigo_vence=(dt.datetime.now() + dt.timedelta(minutes=minutos)).isoformat())
        A.guardar_usuario(email, u)
    ok, _err = N.enviar_correo(email, f"Tu código para entrar: {codigo}", N._html_codigo(p.get("nombre", ""), codigo, minutos),
                               f"Tu código para entrar al Portal de compromisos SAO6 es {codigo}. Vence en {minutos} minutos.",
                               siempre_real=True)
    if not ok:
        return error("No se pudo enviar el correo. Intenta de nuevo en unos minutos o comunícate con Gerencia.", 502)
    return responder({"ok": True, "minutos": minutos})


@publica
def entrar(request):
    """Correo + código recibido -> sesión iniciada. El código sirve una sola vez."""
    d = cuerpo(request)
    email = str(d.get("email", "")).strip().lower()
    codigo = re.sub(r"[\s-]", "", str(d.get("codigo", ""))).upper()
    if N._bloqueado(email):
        return error("Demasiados intentos. Espera 15 minutos y pide un código nuevo.", 429)
    with N.LOCK:
        u = A.usuario(email)
        ok = (N.registrado(email) and u.get("codigo") and u.get("codigo_vence", "") > dt.datetime.now().isoformat()
              and N.verificar(u["codigo"], codigo))
        if not ok:
            N._fallo(email)
            time.sleep(0.5)
            return error("El código no es válido o ya venció. Pide uno nuevo.", 400)
        u.update(codigo="", codigo_vence="", ultimo_ingreso=dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
        u.setdefault("activado", u["ultimo_ingreso"])
        A.guardar_usuario(email, u)
    N._intentos.pop(email, None)
    iniciar_sesion(request, email)
    return responder({"ok": True})


@csrf_exempt
def salir(request):
    request.session.flush()
    return responder({"ok": True})


# ------------------------------------------------------------------ consulta
@api()
def sesion(request, email):
    p = N.persona_por_email(email)
    d = N.leer_datos()
    return responder({"email": email, "nombre": (p or {}).get("nombre", ""), "admin": N.es_admin(email),
                      "equipo": len(N.equipo_de(email)), "actualizado": d.get("archivo", ""),
                      "revision": N.ESTADO["revision"],
                      "error_actualizacion": N.ESTADO["error"] if N.es_admin(email) else None})


@api()
def mis_tareas(request, email):
    d = N.leer_datos()
    p = N.persona_por_email(email)
    return responder({"nombre": (p or {}).get("nombre", ""), "tareas": N.con_personas(N.tareas_de(email)),
                      "actualizado": d.get("archivo", "")})


@api()
def mi_equipo(request, email):
    """Para los responsables de proceso: compromisos de las personas a su cargo."""
    eq = N.equipo_de(email)
    if not eq:
        return error("No tienes personas a cargo en el listado.", 403)
    alias = {N.norm(a) for p in eq for a in p["alias"]}
    tareas = [t for t in N.leer_datos()["tareas"] if any(N.norm(a) in alias for a in N.nombres(t["p"]))]
    return responder({"personas": [{"k": p["k"], "nombre": p["nombre"], "alias": p["alias"], "email": p["email"],
                                    "cargo": p.get("cargo", "")} for p in eq],
                      "tareas": N.con_personas(tareas), "generado": N.leer_datos().get("generado", "")})


@api(metodos=("POST",))
def cambiar_clave(request, email):
    """Del ingreso antiguo con contraseña (se conserva por compatibilidad)."""
    d = cuerpo(request)
    pw, nueva = str(d.get("actual", "")), str(d.get("nueva", ""))
    if len(nueva) < 8 or not re.search(r"[A-Za-z]", nueva) or not re.search(r"\d", nueva):
        return error("La contraseña debe tener al menos 8 caracteres, con letras y números.", 400)
    with N.LOCK:
        u = A.usuario(email)
        if not u.get("pw") or not N.verificar(u["pw"], pw):
            return error("La contraseña actual no es correcta.", 400)
        u["pw"] = N.cifrar(nueva)
        A.guardar_usuario(email, u)
    return responder({"ok": True})


# ---------------- notas personales sobre las tareas
@api(metodos=("GET", "POST"))
def notas(request, email):
    if request.method == "GET":
        return responder(A.notas_de(email))
    d = cuerpo(request)
    clave = str(d.get("clave", ""))[:200]
    texto = str(d.get("texto", "")).strip()[:1500]
    if not clave:
        return error("Falta la tarea.", 400)
    mias = {N._clave(t) for t in N.tareas_de(email)} | ({N._clave(t) for t in N.leer_datos()["tareas"]} if N.es_admin(email) else set())
    if clave not in mias:
        return error("Esa tarea no está asignada a ti.", 403)
    with N.LOCK:
        if texto:
            A.guardar_nota(email, clave, texto, dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
        else:
            A.borrar_nota(email, clave)
    return responder({"ok": True, "nota": A.notas_de(email).get(clave)})


@api(admin=True)
def todas_las_notas(request, email):
    """Notas de todos los responsables, agrupadas por tarea (solo lectura para la administradora)."""
    nombres_p = {p.get("email"): p.get("nombre", "") for p in N.personas()}
    out = {}
    for e, ns in A.notas().items():
        for clave, n in ns.items():
            out.setdefault(clave, []).append({"email": e, "nombre": nombres_p.get(e, e), "texto": n.get("texto", ""),
                                              "fecha": n.get("fecha", "")})
    return responder(out)


# ---------------- descarga en Excel
def _xlsx(bio, nombre):
    return FileResponse(bio, as_attachment=True, filename=nombre, content_type=XLSX)


@api()
def descargar_mias(request, email):
    p = N.persona_por_email(email) or {}
    ts = N._filtrar(N.tareas_de(email), request.GET)
    notas_ = {k: f"{v.get('texto', '')} ({v.get('fecha', '')})" for k, v in A.notas_de(email).items()}
    return _xlsx(N._excel(ts, f"Compromisos de {p.get('nombre') or email}", notas_),
                 f"Mis compromisos {dt.date.today():%Y-%m-%d}.xlsx")


@api(admin=True)
def descargar_todas(request, email):
    ts = N._filtrar(N.leer_datos()["tareas"], request.GET)
    persona = request.GET.get("persona", "")
    if persona:
        if persona == "__none":
            alias = {N.norm(a) for p in N.personas() for a in p["alias"]}
            ts = [t for t in ts if not any(N.norm(a) in alias for a in N.nombres(t["p"]))]
        else:
            elegidas = [x for x in N.personas() if N.norm(persona) in N.norm(x.get("nombre", ""))]
            alias = {N.norm(a) for x in elegidas for a in x.get("alias", [])}
            ts = [t for t in ts if any(N.norm(a) in alias for a in N.nombres(t["p"]))]
    nombres_p = {x.get("email"): x.get("nombre", "") for x in N.personas()}
    notas_ = {}
    for e, ns in A.notas().items():
        for k, v in ns.items():
            notas_[k] = (notas_.get(k, "") + "\n" if k in notas_ else "") + f"{nombres_p.get(e, e)}: {v.get('texto', '')} ({v.get('fecha', '')})"
    titulo = ("Compromisos" + (f" de {persona}" if persona and persona != "__none" else "")
              + (f" · {request.GET.get('comite')}" if request.GET.get("comite") else ""))
    return _xlsx(N._excel(ts, titulo, notas_), f"Compromisos {dt.date.today():%Y-%m-%d}.xlsx")


# ------------------------------------------------------------------ administración
@api(admin=True)
def admin_datos(request, email):
    d = dict(N.leer_datos())
    d["tareas"] = N.con_personas(d["tareas"])
    return responder(d)


@api(admin=True, metodos=("GET", "POST"))
def admin_personas(request, email):
    if request.method == "GET":
        lista = N.personas()
        nombre_por_email = {p.get("email"): p["nombre"] for p in lista}
        jefes = {p["k"]: [nombre_por_email.get(e, e) for e in N.jefes_de(p, lista)] for p in lista}
        return responder({"personas": lista, "cuentas": N._estado_cuentas(), "admins": CFG["administradores"],
                          "jefes": jefes, "listado": CFG["archivo_correos"], "listado_leido": A.estado("listado_leido", "")})
    d = cuerpo(request)
    lista, vistos = [], set()
    for p in d.get("personas", []):
        e = str(p.get("email", "")).strip().lower()
        if e and not N.email_valido(e):
            return error(f"Correo no válido: {e}", 400)
        if e and e in vistos:
            return error(f"El correo {e} está en dos personas.", 400)
        if e:
            vistos.add(e)
        lista.append({"k": str(p.get("k") or secrets.token_hex(4)), "nombre": str(p.get("nombre", "")).strip()[:80],
                      "alias": [str(a).strip()[:80] for a in p.get("alias", []) if str(a).strip()], "email": e,
                      "cargo": str(p.get("cargo", ""))[:120], "area": str(p.get("area", ""))[:80],
                      "completo": str(p.get("completo", ""))[:120],
                      "celular": re.sub(r"\D", "", str(p.get("celular", "")))[-10:],
                      "jefes": [str(x)[:80] for x in p.get("jefes", []) if str(x).strip()][:5]})
    with N.LOCK:
        A.guardar_personas(lista)
    return responder({"ok": True, "cuentas": N._estado_cuentas()})


@api(admin=True, metodos=("POST",))
def admin_importar(request, email):
    """Vuelve a leer ya el listado de correos de la carpeta."""
    try:
        res = N.revisar_listado(forzar=True)
    except PermissionError:
        return error("El listado está abierto en Excel. Ciérralo e intenta de nuevo.", 409)
    except Exception as ex:   # noqa
        return error(f"No se pudo leer el listado: {ex}", 400)
    if res is None:
        return error(f"No encontré «{CFG['archivo_correos']}» en la carpeta Comités y reuniones.", 400)
    return responder({"ok": True, "nuevos": res[0], "actualizados": res[1]})


@api(admin=True, metodos=("GET", "POST"))
def admin_correo(request, email):
    if request.method == "GET":
        c = dict(CFG["correo"]); c["clave_guardada"] = bool(c.pop("clave", ""))
        return responder({"correo": c, "url_portal": N.url_portal(), "notificar_nuevas": CFG.get("notificar_nuevas"),
                          "recordatorio_diario": CFG.get("recordatorio_diario"), "resumen_jefes": CFG.get("resumen_jefes"),
                          "hora_recordatorio": CFG.get("hora_recordatorio"), "dias_recordatorio": CFG.get("dias_recordatorio"),
                          "modo_prueba": CFG.get("modo_prueba"), "correo_prueba": CFG.get("correo_prueba"),
                          "listo": N.correo_listo(), "ultimo_recordatorio": A.estado("ultimo_recordatorio", ""),
                          "envios": A.envios(30)})
    d = cuerpo(request)
    c = d.get("correo", {})
    with N.LOCK:
        cfg = leer_json(CONFIG_PATH, {})
        actual = dict(CFG["correo"])
        for k in ("servidor", "usuario", "remitente", "nombre_remitente", "seguridad"):
            if k in c:
                actual[k] = str(c[k]).strip()
        if "puerto" in c:
            actual["puerto"] = int(c["puerto"] or 587)
        if c.get("clave"):
            actual["clave"] = str(c["clave"])
        cfg["correo"] = actual
        for k in ("notificar_nuevas", "recordatorio_diario", "resumen_jefes", "modo_prueba"):
            if k in d:
                cfg[k] = bool(d[k])
        if "hora_recordatorio" in d and re.fullmatch(r"\d{2}:\d{2}", str(d["hora_recordatorio"])):
            cfg["hora_recordatorio"] = d["hora_recordatorio"]
        if "dias_recordatorio" in d:
            cfg["dias_recordatorio"] = sorted({int(x) for x in d["dias_recordatorio"] if 0 <= int(x) <= 6})
        if "correo_prueba" in d and N.email_valido(str(d["correo_prueba"]).strip()):
            cfg["correo_prueba"] = str(d["correo_prueba"]).strip().lower()
        if "url_portal" in d:
            cfg["url_portal"] = str(d["url_portal"]).strip().rstrip("/")
        guardar_json(CONFIG_PATH, cfg)
        CFG.update(cargar_config())
    return responder({"ok": True})


@api(admin=True, metodos=("POST",))
def admin_prueba_correo(request, email):
    """Envía a correo_prueba un ejemplo de cada correo (aviso de nuevas, recordatorio y resumen a jefes)."""
    if not N.correo_listo():
        return error("Primero configura el servidor de correo y el remitente.", 400)
    dest = CFG.get("correo_prueba") or email
    p = N.persona_por_email(dest) or {"nombre": ""}
    pend = [t for t in N.tareas_de(dest) if t.get("e") != "Cerrado"]
    ejemplo = not pend
    if ejemplo:   # sin pendientes propios: usa compromisos reales de ejemplo
        pend = [t for t in N.leer_datos()["tareas"] if t.get("e") != "Cerrado"][:8]
    a1, h1, t1 = N.correo_nuevas(p["nombre"], pend[:2], pend)
    a2, h2, t2 = N.correo_recordatorio(p["nombre"], pend)
    prev = CFG.get("modo_prueba"); CFG["modo_prueba"] = False
    try:
        ok1, e1 = N.enviar_correo(dest, "[PRUEBA] " + a1, h1, t1)
        ok2, e2 = N.enviar_correo(dest, "[PRUEBA] " + a2, h2, t2) if ok1 else (False, e1)
        lista = N.personas()
        jefes = sorted({j for x in lista for j in N.jefes_de(x, lista)}, key=lambda j: -len(N.equipo_de(j)))
        filas = N.resumen_equipo(jefes[0]) if jefes else []
        if ok2 and filas:
            jn = (N.persona_por_email(jefes[0]) or {}).get("nombre", "")
            a3, h3, t3 = N.correo_jefe(jn, filas)
            N.enviar_correo(dest, f"[PRUEBA · resumen para {jn}] " + a3, h3, t3)
    finally:
        CFG["modo_prueba"] = prev
    if not (ok1 and ok2):
        return error(f"No se pudo enviar: {e1 or e2}", 502)
    return responder({"ok": True, "para": dest, "ejemplo": ejemplo})


@api(admin=True)
def admin_ver_como(request, email):
    """Vista previa de solo lectura: lo que ve otra persona (sus tareas, sus notas y, si es jefe, su equipo)."""
    e = str(request.GET.get("email", "")).strip().lower()
    p = N.persona_por_email(e)
    if not p:
        return error("Esa persona no está en el listado.", 404)
    eq = N.equipo_de(e)
    out = {"email": e, "nombre": p.get("nombre", ""), "tareas": N.con_personas(N.tareas_de(e)),
           "notas": A.notas_de(e), "equipo": len(eq)}
    if eq:
        alias = {N.norm(a) for x in eq for a in x["alias"]}
        out["equipo_personas"] = [{"k": x["k"], "nombre": x["nombre"], "alias": x["alias"], "email": x["email"]} for x in eq]
        out["equipo_tareas"] = N.con_personas([t for t in N.leer_datos()["tareas"]
                                               if any(N.norm(a) in alias for a in N.nombres(t["p"]))])
    return responder(out)


@api(admin=True, metodos=("POST",))
def admin_cerrar(request, email):
    """Cierra un compromiso escribiendo en el acta vigente del comité."""
    d = cuerpo(request)
    clave = str(d.get("clave", ""))
    if "|" not in clave:
        return error("Tarea no válida.", 400)
    estado = "Cerrado" if d.get("estado") == "Cerrado" else "Pendiente"
    nota = str(d.get("nota", "")).strip()[:1000]
    fecha = None
    if estado == "Cerrado":
        try:
            fecha = dt.datetime.strptime(str(d.get("fecha") or dt.date.today().isoformat()), "%Y-%m-%d")
        except ValueError:
            return error("Fecha de cierre no válida.", 400)
    res, cod = N.cerrar_en_acta(clave, estado, fecha, nota, email)
    return responder(res, cod)


@api(admin=True, metodos=("POST",))
def admin_codigo(request, email):
    d = cuerpo(request)
    e = str(d.get("email", "")).strip().lower()
    if not N.registrado(e):
        return error("Primero guarda el correo en la persona.", 400)
    if A.usuario(e).get("bloqueado"):
        return error("Ese correo está bloqueado. Primero permite su acceso.", 400)
    codigo, vence = N.nuevo_codigo_respaldo(e)
    return responder({"codigo": codigo[:4] + "-" + codigo[4:], "vence": vence.strftime("%d/%m/%Y")})


@api(admin=True, metodos=("POST",))
def admin_bloquear(request, email):
    """Bloquea (o desbloquea) el acceso de un correo."""
    d = cuerpo(request)
    e = str(d.get("email", "")).strip().lower()
    if N.es_admin(e):
        return error("No se puede bloquear a una administradora.", 400)
    with N.LOCK:
        if d.get("desbloquear"):
            A.quitar_usuario(e)
        else:
            A.guardar_usuario(e, {"bloqueado": True})
    return responder({"ok": True, "cuentas": N._estado_cuentas()})


@api(admin=True, metodos=("POST",))
def admin_actualizar(request, email):
    """Hace ya la revisión de las 11:00 / 4:00: lee el listado, vuelve a leer las actas y avisa compromisos nuevos."""
    try:
        N.revision_completa()
    except Exception as ex:   # noqa
        return error(f"No se pudo completar la revisión: {ex}", 500)
    d = N.leer_datos()
    return responder({"ok": True, "total": len(d["tareas"]), "archivo": d.get("archivo")})
