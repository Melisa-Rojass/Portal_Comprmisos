# -*- coding: utf-8 -*-
def cabeceras(get_response):
    """Mismas cabeceras de seguridad que el portal original; el panel /admin conserva las de Django."""
    def middleware(request):
        resp = get_response(request)
        if not request.path.startswith(("/admin", "/static")):
            resp["X-Content-Type-Options"] = "nosniff"
            resp["Cache-Control"] = "no-store"
        return resp
    return middleware
