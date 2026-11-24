# -*- coding: utf-8 -*-
"""Enciende el portal (equivale a «python portal.py» del portal original):

    python manage.py iniciar

Lee el listado de correos, arranca la revisión automática (11:00 y 4:00, recordatorio diario) y atiende
las páginas en el puerto de config.json (8051 en prueba1). Todo lo que muestra queda también en portal.log.
"""
import os
import sys
import threading

from django.core.management import call_command
from django.core.management.base import BaseCommand

from compromisos import nucleo as N
from compromisos.config import BASE, CFG


class _Registro:
    """Escribe lo que muestra el portal también en portal.log (necesario cuando corre sin ventana)."""
    def __init__(self, consola):
        self.consola = consola
        self.archivo = open(os.path.join(BASE, "portal.log"), "a", encoding="utf-8", buffering=1)

    def write(self, txt):
        for dest in (self.consola, self.archivo):
            try:
                if dest:
                    dest.write(txt)
            except Exception:   # noqa
                pass

    def flush(self):
        for dest in (self.consola, self.archivo):
            try:
                if dest:
                    dest.flush()
            except Exception:   # noqa
                pass

    def isatty(self):
        return False


class Command(BaseCommand):
    help = "Enciende el Portal de compromisos SAO6."

    def handle(self, *args, **o):
        sys.stdout = _Registro(sys.stdout)
        sys.stderr = _Registro(sys.stderr)
        puerto = int(CFG["puerto"])
        nuevo = os.path.join(BASE, "portal_nuevo.html")      # actualización pendiente de la página
        if os.path.exists(nuevo):
            try:
                os.replace(nuevo, os.path.join(BASE, "portal.html"))
            except OSError as ex:
                print(f" No se pudo actualizar portal.html: {ex}")
        try:
            N.revisar_listado()
        except Exception as ex:   # noqa
            print(f" No se pudo leer el listado de correos: {ex}")
        threading.Thread(target=N.vigilante, daemon=True).start()
        print("=" * 60)
        print(" Portal de compromisos SAO6 · prueba1 (Django)")
        print(f" Abrir en este equipo:     http://localhost:{puerto}")
        print(f" Desde otros equipos:      http://{N.nombre_equipo()}:{puerto}")
        print(f" Panel de datos (Django):  http://localhost:{puerto}/admin")
        print(f" Actas:                    {CFG['carpeta_actas']}")
        print(f" Revisa las actas y el listado a las {' y '.join(CFG.get('horas_revision', []))}.")
        if CFG.get("modo_prueba"):
            print(f" MODO PRUEBA: los correos automáticos llegan solo a {CFG.get('correo_prueba')}.")
        print(" No cierres esta ventana mientras el portal deba estar disponible.")
        print("=" * 60)
        call_command("runserver", f"0.0.0.0:{puerto}", use_reloader=False, insecure_serving=True)
