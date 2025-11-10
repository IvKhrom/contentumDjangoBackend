# middleware.py
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

class JWTAuthenticationMiddleware(MiddlewareMixin):
    """Middleware для JWT аутентификации"""

    def process_request(self, request):
        public_paths = [
            "/api/auth/login/",
            "/api/auth/refresh/", 
            "/api/users/",
            "/admin/",
            "/swagger/",
            "/redoc/",
            "/swagger.json",
            "/favicon.ico",
        ]

        # Проверяем точное совпадение или начало пути
        if any(request.path == path or request.path.startswith(path) for path in public_paths):
            return None

        if request.method == "OPTIONS":
            return None

        jwt_auth = JWTAuthentication()
        try:
            auth_result = jwt_auth.authenticate(request)
            if auth_result is not None:
                user, token = auth_result
                request.user = user
            else:
                return JsonResponse({
                    "status": "error", 
                    "message": "Требуется аутентификация"
                }, status=401, json_dumps_params={'ensure_ascii': False})
        except AuthenticationFailed as e:
            return JsonResponse({
                "status": "error", 
                "message": f"Ошибка аутентификации: {str(e)}"
            }, status=401, json_dumps_params={'ensure_ascii': False})

        return None