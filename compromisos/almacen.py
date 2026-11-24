# -*- coding: utf-8 -*-
"""Lectura y escritura de los datos del portal en la base de datos de Django.
El núcleo (nucleo.py) solo usa estas funciones, así la lógica es la misma del portal original."""
from django.db import transaction

from .models import Cierre, Cuenta, Envio, Nota, Parametro, Persona

CAMPOS_PERSONA = ("k", "nombre", "alias", "email", "cargo", "area", "completo", "celular", "jefes")
CAMPOS_CUENTA = ("codigo", "codigo_vence", "pw", "activado", "ultimo_ingreso", "bloqueado")


# ---------------- personas
def _persona_dict(p):
    d = {c: getattr(p, c) for c in CAMPOS_PERSONA}
    d["alias"] = list(d["alias"] or [])
    d["jefes"] = list(d["jefes"] or [])
    return d


def personas():
    return [_persona_dict(p) for p in Persona.objects.all()]


def guardar_personas(lista):
    """Reemplaza el listado completo (como se hacía con personas.json), conservando el orden."""
    with transaction.atomic():
        Persona.objects.all().delete()
        Persona.objects.bulk_create([
            Persona(orden=i, **{c: (p.get(c) if p.get(c) is not None else ([] if c in ("alias", "jefes") else ""))
                                for c in CAMPOS_PERSONA})
            for i, p in enumerate(lista)])


# ---------------- cuentas (usuarios)
def _cuenta_dict(c):
    return {k: v for k, v in ((k, getattr(c, k)) for k in CAMPOS_CUENTA) if v not in ("", None, False)}


def usuarios():
    return {c.email: _cuenta_dict(c) for c in Cuenta.objects.all()}


def usuario(email):
    c = Cuenta.objects.filter(email=email).first()
    return _cuenta_dict(c) if c else {}


def guardar_usuario(email, datos):
    """Guarda la cuenta tal cual queda en el diccionario (lo que no está se deja vacío)."""
    valores = {k: (bool(datos.get(k)) if k == "bloqueado" else (datos.get(k) or "")) for k in CAMPOS_CUENTA}
    Cuenta.objects.update_or_create(email=email, defaults=valores)


def quitar_usuario(email):
    Cuenta.objects.filter(email=email).delete()


# ---------------- notas
def notas():
    out = {}
    for n in Nota.objects.all():
        out.setdefault(n.email, {})[n.clave] = {"texto": n.texto, "fecha": n.fecha}
    return out


def notas_de(email):
    return {n.clave: {"texto": n.texto, "fecha": n.fecha} for n in Nota.objects.filter(email=email)}


def guardar_nota(email, clave, texto, fecha):
    Nota.objects.update_or_create(email=email, clave=clave, defaults={"texto": texto, "fecha": fecha})


def borrar_nota(email, clave):
    Nota.objects.filter(email=email, clave=clave).delete()


# ---------------- estado interno
def estado(clave, defecto=None):
    p = Parametro.objects.filter(clave=clave).first()
    return p.valor if p and p.valor is not None else defecto


def poner_estado(clave, valor):
    Parametro.objects.update_or_create(clave=clave, defaults={"valor": valor})


# ---------------- registros
def registrar_envio(fecha, para, asunto, ok, detalle=""):
    Envio.objects.create(fecha=fecha, para=str(para)[:600], asunto=str(asunto)[:400], ok=bool(ok), detalle=str(detalle)[:200])


def envios(n=30):
    return [{"fecha": e.fecha, "para": e.para, "asunto": e.asunto, "ok": e.ok, "detalle": e.detalle}
            for e in Envio.objects.all()[:n]]


def registrar_cierre(fecha, por, tarea, estado_, acta):
    Cierre.objects.create(fecha=fecha, por=por, tarea=tarea[:200], estado=estado_, acta=acta[:300])
