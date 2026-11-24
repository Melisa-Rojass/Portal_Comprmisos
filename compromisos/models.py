# -*- coding: utf-8 -*-
"""Modelos: lo que en el portal original estaba en personas.json, usuarios.json, notas.json y estado.json.
Las tareas NO se guardan aquí: se siguen leyendo directamente del acta vigente de cada comité."""
from django.db import models


class Persona(models.Model):
    k = models.CharField("clave", max_length=20, db_index=True)
    nombre = models.CharField(max_length=80)
    alias = models.JSONField("nombres en las actas", default=list, blank=True)
    email = models.CharField("correo", max_length=254, blank=True, db_index=True)
    cargo = models.CharField(max_length=120, blank=True)
    area = models.CharField("área", max_length=80, blank=True)
    completo = models.CharField("nombre completo", max_length=120, blank=True)
    celular = models.CharField(max_length=20, blank=True)
    jefes = models.JSONField("responsables del proceso", default=list, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name_plural = "personas"

    def __str__(self):
        return f"{self.nombre} <{self.email}>" if self.email else self.nombre


class Cuenta(models.Model):
    """Acceso al portal: código de ingreso (cifrado), último ingreso y bloqueo."""
    email = models.CharField("correo", max_length=254, unique=True)
    codigo = models.CharField("código cifrado", max_length=200, blank=True)
    codigo_vence = models.CharField(max_length=32, blank=True)
    pw = models.CharField("contraseña cifrada (ya no se usa)", max_length=200, blank=True)
    activado = models.CharField(max_length=20, blank=True)
    ultimo_ingreso = models.CharField("último ingreso", max_length=20, blank=True)
    bloqueado = models.BooleanField(default=False)

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email


class Nota(models.Model):
    """Nota personal de un responsable sobre una tarea (clave = «comité|ID»)."""
    email = models.CharField("correo", max_length=254, db_index=True)
    clave = models.CharField("tarea", max_length=200)
    texto = models.TextField()
    fecha = models.CharField(max_length=20)

    class Meta:
        unique_together = [("email", "clave")]
        ordering = ["email", "clave"]

    def __str__(self):
        return f"{self.email} · {self.clave}"


class Parametro(models.Model):
    """Estado interno de las revisiones (turno hecho, tareas ya avisadas, último recordatorio, etc.)."""
    clave = models.CharField(max_length=60, unique=True)
    valor = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "parámetro interno"
        verbose_name_plural = "parámetros internos"

    def __str__(self):
        return self.clave


class Envio(models.Model):
    """Registro de correos enviados."""
    fecha = models.CharField(max_length=20)
    para = models.CharField(max_length=600)
    asunto = models.CharField(max_length=400)
    ok = models.BooleanField(default=True)
    detalle = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "correo enviado"
        verbose_name_plural = "correos enviados"

    def __str__(self):
        return f"{self.fecha} · {self.para}"


class Cierre(models.Model):
    """Registro de tareas cerradas desde el portal (se escriben en el acta del comité)."""
    fecha = models.CharField(max_length=20)
    por = models.CharField(max_length=254)
    tarea = models.CharField(max_length=200)
    estado = models.CharField(max_length=20)
    acta = models.CharField(max_length=300)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.fecha} · {self.tarea}"
