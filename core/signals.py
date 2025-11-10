from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.conf import settings
import os
from .models import PromptTemplate

@receiver(post_migrate)
def create_default_prompt_template(sender, **kwargs):
    """
    Создает дефолтный шаблон промпта после миграций
    """
    if sender.name == 'core' and not PromptTemplate.objects.filter(is_active=True).exists():
        template_path = os.path.join(settings.BASE_DIR, 'core', 'prompt_templates', 'default_template.txt')
        
        try:
            with open(template_path, 'r', encoding='utf-8') as file:
                template_content = file.read()
            
            PromptTemplate.objects.create(
                name="Основной шаблон контента",
                template=template_content,
                is_active=True
            )
            print("✅ Дефолтный шаблон промпта успешно создан")
            
        except FileNotFoundError:
            # Создаем базовый шаблон если файл не найден
            basic_template = """Создай {content_type} для {platform} с идеей: {idea}. 
Эмоциональный тон: {emotion}. 
Визуальный стиль: {visual_style} с акцентом на {composition_focus}.
Цветовая палитра: {color_palette}."""
            
            PromptTemplate.objects.create(
                name="Базовый шаблон",
                template=basic_template,
                is_active=True
            )
            print("⚠️  Файл шаблона не найден, создан базовый шаблон")