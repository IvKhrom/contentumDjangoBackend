from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.conf import settings
import os
from .models import PromptTemplate

@receiver(post_migrate)
def create_or_update_default_prompt_template(sender, **kwargs):
    """
    Создает или обновляет дефолтный шаблон промпта после миграций
    """
    # Проверяем, что это наше приложение
    if sender.name == 'core':
        template_path = os.path.join(settings.BASE_DIR, 'core', 'prompt_templates', 'default_template.txt')
        
        try:
            with open(template_path, 'r', encoding='utf-8') as file:
                template_content = file.read()
            
            # Ищем существующий активный шаблон
            existing_template = PromptTemplate.objects.filter(is_active=True).first()
            
            if existing_template:
                # Обновляем существующий шаблон
                existing_template.template = template_content
                existing_template.name = "Основной шаблон контента"
                existing_template.save()
                print("✅ Дефолтный шаблон промпта успешно обновлен")
            else:
                # Создаем новый шаблон
                PromptTemplate.objects.create(
                    name="Основной шаблон контента",
                    template=template_content,
                    is_active=True
                )
                print("✅ Дефолтный шаблон промпта успешно создан")
                
        except FileNotFoundError:
            print("⚠️  Файл шаблона не найден, проверяю наличие шаблона в БД")
            
            # Проверяем, есть ли хоть какой-то шаблон
            if not PromptTemplate.objects.exists():
                # Создаем базовый шаблон если файл не найден И нет шаблонов в БД
                basic_template = """Фото для {platform} в формате {aspect_ratio}.

Идея: {idea}
Стиль: {visual_style}
Фокус композиции: {composition_focus}
Цветовая палитра: {color_palette}
Визуальные ассоциации: {visual_associations}

{event_info}

Современно, эстетично, гармонично для {platform}."""
                
                PromptTemplate.objects.create(
                    name="Базовый шаблон",
                    template=basic_template,
                    is_active=True
                )
                print("⚠️  Создан базовый шаблон")