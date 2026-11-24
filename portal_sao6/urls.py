# -*- coding: utf-8 -*-
"""Direcciones del portal: las mismas del portal original, más el panel /admin de Django."""
from django.contrib import admin
from django.urls import path

from compromisos import views as v

admin.site.site_header = "Portal de compromisos SAO6 · administración"
admin.site.site_title = "Compromisos SAO6"
admin.site.index_title = "Datos del portal"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", v.inicio),
    path("manifest.json", v.manifest),
    path("icono-<int:n>.png", v.icono),
    path("favicon.ico", v.favicon),
    path("api/solicitar-codigo", v.solicitar_codigo),
    path("api/entrar", v.entrar),
    path("api/salir", v.salir),
    path("api/sesion", v.sesion),
    path("api/mis-tareas", v.mis_tareas),
    path("api/equipo", v.mi_equipo),
    path("api/cambiar-clave", v.cambiar_clave),
    path("api/notas", v.notas),
    path("api/admin/notas", v.todas_las_notas),
    path("descargar/mis-compromisos.xlsx", v.descargar_mias),
    path("descargar/compromisos.xlsx", v.descargar_todas),
    path("api/admin/datos", v.admin_datos),
    path("api/admin/personas", v.admin_personas),
    path("api/admin/importar", v.admin_importar),
    path("api/admin/correo", v.admin_correo),
    path("api/admin/correo/prueba", v.admin_prueba_correo),
    path("api/admin/ver-como", v.admin_ver_como),
    path("api/admin/cerrar", v.admin_cerrar),
    path("api/admin/codigo", v.admin_codigo),
    path("api/admin/bloquear", v.admin_bloquear),
    path("api/admin/actualizar", v.admin_actualizar),
]
