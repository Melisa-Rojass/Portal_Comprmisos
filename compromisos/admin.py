# -*- coding: utf-8 -*-
"""Panel /admin de Django para consultar y corregir los datos del portal."""
from django.contrib import admin

from .models import Cierre, Cuenta, Envio, Nota, Parametro, Persona


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "email", "cargo", "area", "jefes")
    search_fields = ("nombre", "email", "completo", "cargo", "area")
    list_filter = ("area",)


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ("email", "activado", "ultimo_ingreso", "bloqueado")
    search_fields = ("email",)
    list_filter = ("bloqueado",)
    exclude = ("codigo", "pw")


@admin.register(Nota)
class NotaAdmin(admin.ModelAdmin):
    list_display = ("email", "clave", "fecha", "texto")
    search_fields = ("email", "clave", "texto")


@admin.register(Envio)
class EnvioAdmin(admin.ModelAdmin):
    list_display = ("fecha", "para", "asunto", "ok")
    search_fields = ("para", "asunto")
    list_filter = ("ok",)


@admin.register(Cierre)
class CierreAdmin(admin.ModelAdmin):
    list_display = ("fecha", "tarea", "estado", "por", "acta")
    search_fields = ("tarea", "acta")


@admin.register(Parametro)
class ParametroAdmin(admin.ModelAdmin):
    list_display = ("clave",)
