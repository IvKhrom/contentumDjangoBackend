from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Contentum Core'

    def ready(self):
        # Импортируем сигналы для автоматической загрузки шаблона
        # Важно: импортируем в ready(), а не в начале файла
        # чтобы избежать циклических импортов
        try:
            import core.signals
        except ImportError:
            pass