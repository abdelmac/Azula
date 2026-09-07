from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def csrf_failure(request, reason=""):
    return JsonResponse({"code": "csrf_failed", "detail": "csrf_failed"}, status=403)


@never_cache
@require_GET
def spa(request):
    path = settings.ROOT_DIR / "frontend" / "dist" / "index.html"
    if not path.is_file():
        return HttpResponse("Frontend absent. Exécutez npm run build dans frontend/.", status=503)
    return HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
