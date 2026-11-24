# -*- coding: utf-8 -*-
"""Configuración del portal (prueba1 · Django).

Se guarda en prueba1/config.json, igual que en el portal original. La primera vez se crea copiando la
configuración del portal original (carpeta de actas, servidor de correo, administradoras), pero con:
  - puerto 8051 (el portal original sigue en el 8050),
  - modo prueba activo: todos los correos automáticos llegan solo a correo_prueba,
  - una clave secreta propia.
"""
import json
import os
import secrets

BASE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))   # ...\_Portal de compromisos\prueba1
PADRE = os.path.dirname(BASE)                                         # ...\_Portal de compromisos
CONFIG_PATH = os.path.join(BASE, "config.json")

DEFAULT_CONFIG = {
    "puerto": 8051,
    "carpeta_actas": os.path.dirname(PADRE),        # Z:\GERENCIA\PRIVADA\Comités y reuniones
    "archivo_correos": "Correos Administrativos.xlsx",
    "script_consolidado": "Actualizar consolidado de compromisos.py",
    "administradores": ["melisa.rojas@sao6.com.co"],
    "dias_validez_codigo": 7,
    "horas_sesion": 720,
    "minutos_codigo": 10,
    "horas_revision": ["11:00", "16:00"],
    "url_portal": "",
    "correo": {
        "servidor": "", "puerto": 587, "seguridad": "starttls", "usuario": "", "clave": "",
        "remitente": "", "nombre_remitente": "Compromisos SAO6",
    },
    "notificar_nuevas": True,
    "recordatorio_diario": True,
    "resumen_jefes": True,
    "hora_recordatorio": "07:30",
    "dias_recordatorio": [0, 1, 2, 3, 4],
    "modo_prueba": True,
    "correo_prueba": "melisa.rojas@sao6.com.co",
}


def leer_json(path, defecto):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return defecto


def guardar_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _primera_vez():
    """Crea prueba1/config.json a partir del config.json del portal original."""
    original = leer_json(os.path.join(PADRE, "config.json"), {})
    cfg = {k: original[k] for k in ("carpeta_actas", "archivo_correos", "script_consolidado", "administradores",
                                     "dias_validez_codigo", "horas_sesion", "minutos_codigo", "horas_revision",
                                     "hora_recordatorio", "dias_recordatorio", "notificar_nuevas",
                                     "recordatorio_diario", "resumen_jefes") if k in original}
    if original.get("correo"):
        cfg["correo"] = original["correo"]
    cfg.update(puerto=8051, url_portal="", modo_prueba=True,
               correo_prueba=original.get("correo_prueba") or "melisa.rojas@sao6.com.co",
               clave_secreta=secrets.token_hex(32))
    guardar_json(CONFIG_PATH, cfg)


def cargar_config():
    if not os.path.exists(CONFIG_PATH):
        _primera_vez()
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    guardado = leer_json(CONFIG_PATH, {})
    correo = dict(cfg["correo"]); correo.update(guardado.get("correo", {}))
    cfg.update(guardado); cfg["correo"] = correo
    if not cfg.get("clave_secreta"):
        cfg["clave_secreta"] = secrets.token_hex(32)
        guardado["clave_secreta"] = cfg["clave_secreta"]
        guardar_json(CONFIG_PATH, guardado)
    cfg["administradores"] = [e.strip().lower() for e in cfg["administradores"]]
    # Si la carpeta guardada no existe en este equipo (p. ej. "Z:\..." en un servidor Linux), usar la que contiene al portal
    if not os.path.isdir(str(cfg.get("carpeta_actas", ""))):
        cfg["carpeta_actas"] = os.path.dirname(PADRE)
    return cfg


CFG = cargar_config()


def archivo_portal(nombre):
    """Busca un archivo del portal primero en prueba1 y luego en la carpeta del portal original."""
    for carpeta in (BASE, PADRE):
        ruta = os.path.join(carpeta, nombre)
        if os.path.exists(ruta):
            return ruta
    return os.path.join(BASE, nombre)
