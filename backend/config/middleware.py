def static_headers(headers, path, url):
    # Une entrée HTML ouverte directement doit suivre le dernier déploiement.
    if path.endswith(".html"):
        headers["Cache-Control"] = "no-cache"


class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(("/api/", "/admin/")):
            response["Cache-Control"] = "no-store, private"
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.path.startswith("/admin/"):
            response["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data: https:; font-src 'self'; connect-src 'self'; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
            )
        return response
