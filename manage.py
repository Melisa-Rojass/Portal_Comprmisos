#!/usr/bin/env python
"""Comandos de Django del Portal de compromisos SAO6 (prueba1)."""
import os
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True          # no dejar carpetas __pycache__ en Z:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal_sao6.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
