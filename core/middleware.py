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
        
        # Префиксы для динамических путей
        public_prefixes = [
            "/api/generation-tasks/",
        ]

        # Проверяем, является ли путь публичным
        is_public = (
            any(request.path == path or request.path.startswith(path) for path in public_paths) or
            any(request.path.startswith(prefix) and 
               (request.path.endswith('/download/') or request.path.endswith('/image/') or request.path.endswith('/image-file/'))
               for prefix in public_prefixes) or
            request.method == "OPTIONS"
        )

        if is_public:
            return None

        # Только для защищенных путей выполняем аутентификацию
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