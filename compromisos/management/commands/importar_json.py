# -*- coding: utf-8 -*-
"""Carga una sola vez los datos del portal original (archivos .json de la carpeta «_Portal de compromisos»)
en la base de datos de Django. No modifica los archivos originales.

    python manage.py importar_json            (solo si la base está vacía)
    python manage.py importar_json --forzar   (borra lo cargado y vuelve a copiar)
"""
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from compromisos import almacen as A
from compromisos.config import PADRE, leer_json
from compromisos.models import Cierre, Cuenta, Envio, Nota, Parametro, Persona


class Command(BaseCommand):
    help = "Copia personas, cuentas, notas y estado del portal original a la base de datos."

    def add_arguments(self, parser):
        parser.add_argument("--forzar", action="store_true", help="Volver a copiar aunque la base ya tenga datos.")

    def handle(self, *args, **o):
        if Persona.objects.exists() and not o["forzar"]:
            self.stdout.write(" La base de datos ya tiene personas; no se vuelve a importar (use --forzar).")
            return
        ruta = lambda n: os.path.join(PADRE, n)   # noqa: E731
        personas = leer_json(ruta("personas.json"), {"personas": []}).get("personas", [])
        usuarios = leer_json(ruta("usuarios.json"), {})
        notas = leer_json(ruta("notas.json"), {})
        estado = leer_json(ruta("estado.json"), {})
        with transaction.atomic():
            for m in (Cuenta, Nota, Parametro, Envio, Cierre):
                m.objects.all().delete()
            A.guardar_personas(personas)
            for email, u in usuarios.items():
                # Los códigos y contraseñas del portal original están cifrados con otro método: no se copian
                # (cada persona pide un código nuevo al entrar). Se conservan ingreso y bloqueo.
                A.guardar_usuario(email, {"activado": u.get("activado", ""), "ultimo_ingreso": u.get("ultimo_ingreso", ""),
                                          "bloqueado": bool(u.get("bloqueado"))})
            for email, ns in notas.items():
                for clave, n in ns.items():
                    A.guardar_nota(email, clave, n.get("texto", ""), n.get("fecha", ""))
            for clave in ("vistas", "ultimo_recordatorio", "turno_revision", "listado_leido"):
                if clave in estado:
                    A.poner_estado(clave, estado[clave])
            for e in reversed(estado.get("envios", [])):
                A.registrar_envio(e.get("fecha", ""), e.get("para", ""), e.get("asunto", ""), e.get("ok", True), e.get("detalle", ""))
            for c in reversed(estado.get("cierres", [])):
                A.registrar_cierre(c.get("fecha", ""), c.get("por", ""), c.get("tarea", ""), c.get("estado", ""), c.get("acta", ""))
        self.stdout.write(f" Importado del portal original: {len(personas)} personas, {len(usuarios)} cuentas, "
                          f"{sum(len(n) for n in notas.values())} notas.")
