# -*- coding: utf-8 -*-
"""Ajustes de Django del Portal de compromisos SAO6 (prueba1)."""
import os
from pathlib import Path

from compromisos.config import CFG

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = CFG["clave_secreta"]
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "compromisos.apps.CompromisosConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "compromisos.middleware.cabeceras",
]

ROOT_URLCONF = "portal_sao6.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

WSGI_APPLICATION = "portal_sao6.wsgi.application"

# Base de datos: personas, cuentas, notas, cierres, correos enviados y estado de las revisiones.
# Para pasar al servidor basta con cambiar este bloque por PostgreSQL.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "portal.sqlite3",
        "OPTIONS": {"timeout": 30},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sesión del portal: firmada en la cookie (como en el portal original), 30 días en el mismo navegador.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_NAME = "sao6_prueba1"
SESSION_COOKIE_AGE = int(CFG.get("horas_sesion", 720)) * 3600
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_NAME = "sao6_prueba1_csrf"
X_FRAME_OPTIONS = "DENY"

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = False

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["consola"], "level": os.environ.get("DJANGO_LOG", "WARNING")}},
}
