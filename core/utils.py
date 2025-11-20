# utils.py
import json
from datetime import datetime, timedelta
from django.core.serializers.json import DjangoJSONEncoder
from .models import Message, Chat, PromptParameters, PromptHistory, MessageType
from string import Formatter
import re
from .kandinsky_service import kandinsky_service
from .models import Message, MediaGenerationTask

QUESTIONS_FLOW = [
    #("content_type", "Что нужно создать — фото или видео? (content_type)", False),
    ("idea", "Кратко опишите идею или цель контента (например: 'Концертный зал на постановке')", False),
    #("emotion", "Какой эмоциональный тон нужен? (energy/nostalgic/романтичный/и т.д.)", False),
    #("relation_to_event", "Нужно ли привязать к событию? (прямая / тематическая / без привязки)", True),
    ("event_name", "Введите название постановки.", True),
    ("event_genre", "Укажите жанр (мюзикл, драма, комедия и т.д.).", True),
    #("event_description", "Краткое описание события (event_description).", True),
    ("visual_style", "Выберите художественный стиль (реализм, минимализм, арт-деко, неон, сюрреализм...).", False),
    ("composition_focus", "Что в центре композиции? (человек, сцена, предмет, абстракция, пейзаж)", False),
    ("color_palette", "Какая цветовая палитра преобладает? (тёплая, холодная и т.п.)", True),
    ("visual_associations", "Назови несколько слов-ассоциаций (например: “огни сцены, движение, свет прожекторов”)", True),
    ("platform", "Где будет опубликовано? (VK, YouTube Shorts, digital screen и т.д.)", True),
    ("aspect_ratio", "Выберите формат кадра (9:16, 1:1, 16:9)", True),
    #("duration", "Длительность в секундах (duration) — для видео.", True),
    #("slogan", "Текст/слоган, если нужен (slogan).", True),
    #("text_style", "Стиль текста (text_style).", True),
]

FLOW_KEYS = [k for k, _, _ in QUESTIONS_FLOW]

class CustomJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def validate_email_domain(email):
    """Валидация домена email"""
    allowed_domains = ['gmail.com', 'yandex.ru', 'mail.ru', 'sberbank.ru']
    domain = email.split('@')[-1]
    return domain in allowed_domains

def assemble_prompt_from_template(template_text: str, parameters: dict) -> str:
    class SafeDict(dict):
        def __missing__(self, key):
            return ""

    params = {k: (v if v is not None else "") for k, v in parameters.items()}
    safe = SafeDict(params)
    
    try:
        return template_text.format_map(safe)
    except Exception:
        result = template_text
        for k, v in params.items():
            result = result.replace("{" + k + "}", str(v))
        for literal_text, field_name, format_spec, conversion in Formatter().parse(result):
            if field_name and "{" + field_name + "}" in result:
                result = result.replace("{" + field_name + "}", "")
        return result

def enrich_prompt_with_gigachat(short_text):
    """
    Заглушка для интеграции с GigaChat
    В реальной реализации здесь будет вызов API GigaChat
    """
    # Временная реализация - просто возвращаем обогащенный текст
    enrichment_map = {
        "театр": "великолепный театральный мир с богатой историей и культурой",
        "концерт": "захватывающее музыкальное представление с живым звуком",
        "выставка": "уникальная художественная экспозиция с современным искусством",
        "спектакль": "театральное представление с профессиональной актерской игрой",
    }
    
    for key, value in enrichment_map.items():
        if key in short_text.lower():
            return value
    
    return short_text + " - созданное с вниманием к деталям и художественному вкусу"

def simple_semantic_vector_from_params(parameters: dict) -> dict:
    """Создание простого семантического вектора из параметров"""
    vec = {}
    for k, v in parameters.items():
        try:
            vec[k] = len(str(v))
        except Exception:
            vec[k] = 0
    return vec

def quality_check_generated(result_meta: dict) -> bool:
    """Проверка качества сгенерированного контента"""
    if result_meta.get("ok") is True:
        return True
    prompt_len = result_meta.get("prompt_len", 0)
    return prompt_len >= 30

def next_question_for_chat(chat: Chat):
    """
    Возвращает (key, question_text, optional) для следующего шага или (None, None, None) если flow завершён.
    """
    step = chat.flow_step or 0
    if step < len(QUESTIONS_FLOW):
        key, text, optional = QUESTIONS_FLOW[step]
        return key, text, optional
    return None, None, None

def build_parameters_from_chat_messages(chat: Chat) -> dict:
    """
    Собирает параметры из сообщений чата
    """
    user_msgs = list(chat.messages.filter(messageType=MessageType.USER).order_by("createdAt"))
    params = {}
    
    for idx, (key, _, optional) in enumerate(QUESTIONS_FLOW):
        if idx < len(user_msgs):
            content = user_msgs[idx].content.strip()
            if content:  # Не сохраняем пустые ответы для опциональных полей
                params[key] = content
        elif not optional:
            # Для обязательных полей без ответа ставим пустую строку
            params[key] = ""
    
    return params

def assemble_optimized_prompt(parameters: dict) -> str:
    """
    Сборка оптимизированного промпта для Kandinsky
    """
    parts = []
    
    # Базовая информация
    #content_type = parameters.get('content_type', 'контент')
    platform = parameters.get('platform', '')
    aspect_ratio = parameters.get('aspect_ratio', '')
    #duration = parameters.get('duration', '')
    
    # Первая строка
    first_line = f"Фото для {platform}" if platform else "Фото"
    if aspect_ratio:
        first_line += f" в формате {aspect_ratio}"
    #if duration and content_type == 'видео':
    #    first_line += f", длительность {duration} секунд"
    parts.append(first_line + ".")
    
    # Стиль и эмоции
    style_parts = []
    if parameters.get('visual_style'):
        style_parts.append(f"Стиль: {parameters['visual_style']}")
    #if parameters.get('emotion'):
    #    style_parts.append(f"Эмоция: {parameters['emotion']}")
    if style_parts:
        parts.append(". ".join(style_parts) + ".")
    
    # Идея
    if parameters.get('idea'):
        parts.append(f"Идея: {parameters['idea']}.")
    
    # Композиция и визуал
    visual_parts = []
    if parameters.get('composition_focus'):
        visual_parts.append(f"Фокус на {parameters['composition_focus']}")
    if parameters.get('color_palette'):
        visual_parts.append(f"Цвета: {parameters['color_palette']}")
    if parameters.get('visual_associations'):
        visual_parts.append(f"Ассоциации: {parameters['visual_associations']}")
    
    if visual_parts:
        parts.append(" ".join(visual_parts) + ".")
    
    # Событие (только если указано)
    event_name = parameters.get('event_name', '').strip()
    event_genre = parameters.get('event_genre', '').strip()
    #event_description = parameters.get('event_description', '').strip()
    
    if event_name or event_genre: #or event_description:
        event_parts = []
        if event_name:
            event_parts.append(f"Событие: {event_name}")
        if event_genre:
            event_parts.append(f"Жанр: {event_genre}")
        #if event_description:
        #    event_parts.append(f"Описание: {event_description}")
        
        parts.append(" | ".join(event_parts) + ".")
    
    # Слоган (только если указан)
    #slogan = parameters.get('slogan', '').strip()
    #text_style = parameters.get('text_style', '').strip()
    
    #if slogan:
    #    slogan_phrase = f'Текст: "{slogan}"'
    #    if text_style:
    #        slogan_phrase += f" в стиле {text_style}"
    #    parts.append(slogan_phrase + ".")
    
    # Финальная строка
    if platform:
        parts.append(f"Современно и эстетично для {platform}.")
    else:
        parts.append("Современный и эстетичный контент.")
    
    # Собираем все части
    final_prompt = " ".join(parts)
    
    # Обеспечиваем, что промпт не превышает лимит
    return optimize_prompt_for_kandinsky(final_prompt)

def optimize_prompt_for_kandinsky(prompt_text, max_length=800):
    """
    Оптимизация промпта для Kandinsky API (макс. 1000 символов)
    """
    if len(prompt_text) <= max_length:
        return prompt_text
    
    # Сначала убираем лишние пробелы
    optimized = ' '.join(prompt_text.split())
    
    if len(optimized) <= max_length:
        return optimized
    
    # Если все еще длинный, ищем хорошее место для обрезки
    # Предпочитаем обрезать после точки или запятой
    cut_point = optimized[:max_length].rfind('.')
    if cut_point == -1:
        cut_point = optimized[:max_length].rfind(',')
    if cut_point == -1:
        cut_point = optimized[:max_length].rfind(' ')
    
    if cut_point > max_length * 0.6:  # Если нашли хорошее место для обрезки
        optimized = optimized[:cut_point + 1]
    else:
        # Просто обрезаем по границе слова
        optimized = optimized[:max_length]
    
    return optimized

def complete_chat_and_generate(chat, prompt_history):
    """
    Завершает чат и запускает генерацию изображения
    """
    print(f"🔧 UTILS DEBUG: Starting complete_chat_and_generate")
    print(f"🔧 UTILS DEBUG: Chat ID: {chat.id}")
    print(f"🔧 UTILS DEBUG: Prompt History ID: {prompt_history.id}")
    print(f"🔧 UTILS DEBUG: Assembled prompt: {prompt_history.assembled_prompt[:100]}...")
  
    # Создаем задачу генерации
    task = MediaGenerationTask.objects.create(
        user=chat.user,
        chat=chat,
        prompt_history=prompt_history,
        prompt_text=prompt_history.assembled_prompt,
        status=MediaGenerationTask.Status.PENDING
    )
    
    print(f"🔧 UTILS DEBUG: Task created: {task.id}")
    
    # Отправляем системное сообщение о начале генерации
    Message.objects.create(
        chat=chat,
        content="🎨 Запускаю генерацию изображения... Это может занять 1-2 минуты.",
        messageType=MessageType.SYSTEM
    )
    
    print(f"🔧 UTILS DEBUG: Calling kandinsky_service.generate_image...")
    
    # Запускаем генерацию
    generation_result = kandinsky_service.generate_image(
        prompt=prompt_history.assembled_prompt,
        width=1024,
        height=1024,
        style="DEFAULT",
        negative_prompt="низкое качество, размытое, watermark"
    )
    
    print(f"🔧 UTILS DEBUG: Kandinsky result keys: {generation_result.keys()}")
    print(f"🔧 UTILS DEBUG: Kandinsky success: {generation_result.get('success')}")
    
    if generation_result["success"]:
        task.status = MediaGenerationTask.Status.SUCCESS
        images_data = generation_result.get("images_data", [])
        
        print(f"🔧 UTILS DEBUG: Images data received: {len(images_data)} images")
        
        # ✅ ИСПРАВЛЕНО: Сохраняем изображение
        if images_data and len(images_data) > 0:
            # Берем первое изображение из массива
            task.result_image_base64 = images_data[0]
            task.save()
            
            print(f"🔧 UTILS DEBUG: Image saved to task, length: {len(images_data[0])}")
            
            # ✅ ОБНОВЛЕНО: Сообщение со ссылками для скачивания
            download_url = f"http://localhost:8000/api/generation-tasks/{task.id}/download/"
            preview_url = f"http://localhost:8000/api/generation-tasks/{task.id}/image/?format=file"
            
            preview_msg = f"✅ Генерация завершена! Ваше фото готово.\n\n📥 Скачайте его по ссылке:\n{download_url}\n\n👀 Или просмотрите:\n{preview_url}"
        else:
            print(f"🔧 UTILS DEBUG: No images data in result!")
            preview_msg = "✅ Генерация завершена, но изображение не получено."
        
        Message.objects.create(
            chat=chat,
            content=preview_msg,
            messageType=MessageType.SYSTEM
        )
        
        print(f"🔧 UTILS DEBUG: Generation completed successfully")
        
        return {
            "success": True,
            "images_data": images_data,
            "task_id": task.id
        }
    else:
        task.status = MediaGenerationTask.Status.FAILED
        task.last_error = generation_result["error"]
        task.save()
        
        print(f"🔧 UTILS DEBUG: Generation failed: {generation_result['error']}")
        
        # Отправляем сообщение об ошибке
        error_msg = generation_result["error"]
        if "1000 characters" in error_msg:
            error_msg = "Промпт слишком длинный для генерации. Попробуйте более краткие описания."
        
        Message.objects.create(
            chat=chat,
            content=f"❌ Произошла ошибка при генерации: {error_msg}",
            messageType=MessageType.SYSTEM
        )
        
        return {
            "success": False,
            "error": generation_result["error"],
            "task_id": task.id
        }


def handle_user_message_and_advance(chat: Chat, message: Message):
    """
    Обработчик пользовательского сообщения с автоматической генерацией после завершения
    """
    from django.utils import timezone
    
    # Увеличиваем шаг
    chat.flow_step = (chat.flow_step or 0) + 1
    chat.updatedAt = timezone.now()
    chat.save(update_fields=["flow_step", "updatedAt"])

    # Проверяем, есть ли следующий вопрос
    next_key, next_text, optional = next_question_for_chat(chat)
    if next_text:
        # Создаем системное сообщение со следующим вопросом
        sys_msg = Message.objects.create(
            chat=chat, 
            content=next_text, 
            messageType=MessageType.SYSTEM
        )
        return {"type": "question", "message": sys_msg}

    # Flow завершён — собираем параметры
    params = build_parameters_from_chat_messages(chat)
    
    # Обогащаем короткие параметры через GigaChat
    #enrich_keys = ["idea", "visual_associations"]
    #for key in enrich_keys:
    #    if key in params and isinstance(params[key], str) and 0 < len(params[key]) < 80:
    #        params[key] = enrich_prompt_with_gigachat(params[key])
    
    # Сохраняем параметры
    pp = PromptParameters.objects.create(
        user=chat.user, 
        data=params, 
        semantic_vector=simple_semantic_vector_from_params(params)
    )
    
    # СОБИРАЕМ ОПТИМИЗИРОВАННЫЙ ПРОМПТ
    assembled_prompt = assemble_optimized_prompt(params)
    
    # Получаем шаблон для истории (но не используем его для генерации)
    template = get_default_prompt_template()
    
    ph = PromptHistory.objects.create(
        user=chat.user, 
        prompt_template=template,
        parameters=pp, 
        assembled_prompt=assembled_prompt
    )
    
    # ЗАПУСКАЕМ ГЕНЕРАЦИЮ АВТОМАТИЧЕСКИ
    generation_result = complete_chat_and_generate(chat, ph)
    
    # ВОЗВРАЩАЕМ ТОЛЬКО ДАННЫЕ О ПРОМПТАХ
    return {
        "type": "completed", 
        "prompt_parameters": pp, 
        "prompt_history": ph
    }

def get_default_prompt_template():
    """Получение активного шаблона промпта с созданием дефолтного если нет активных"""
    from .models import PromptTemplate
    
    template = PromptTemplate.objects.filter(is_active=True).first()
    
    if not template:
        # Создаем базовый шаблон если нет активных
        template = PromptTemplate.objects.create(
            name="Автоматически созданный шаблон",
            template="Создай {content_type} для {platform}. Идея: {idea}. Эмоция: {emotion}.",
            is_active=True
        )
    
    return template

def get_user_chats_summary(user):
    """Сводка по чатам пользователя"""
    chats = Chat.objects.filter(user=user, isActive=True)
    total_chats = chats.count()
    completed_chats = chats.filter(flow_step__gte=len(QUESTIONS_FLOW)).count()
    active_chats = total_chats - completed_chats
    
    return {
        "total_chats": total_chats,
        "completed_chats": completed_chats,
        "active_chats": active_chats,
        "total_messages": Message.objects.filter(chat__user=user).count()
    }

def has_empty_chat(user):
    """
    Проверяет, есть ли у пользователя чат без пользовательских сообщений
    """
    return Chat.objects.filter(
        user=user, 
        isActive=True
    ).exclude(
        messages__messageType=MessageType.USER
    ).exists()

def get_empty_chat(user):
    """
    Возвращает чат без пользовательских сообщений, если есть
    """
    chats_without_user_messages = Chat.objects.filter(
        user=user, 
        isActive=True
    ).exclude(
        messages__messageType=MessageType.USER
    )
    return chats_without_user_messages.first()

def get_unfinished_chat(user):
    """
    Возвращает незавершенный чат пользователя, если есть
    """
    return Chat.objects.filter(
        user=user, 
        isActive=True,
        flow_step__lt=len(QUESTIONS_FLOW)
    ).first()

def cleanup_expired_temporary_chats(minutes=10):
    """
    Удаляет временные чаты, созданные больше minutes назад и у которых нет пользовательских ответов.
    """
    from django.utils import timezone
    cutoff = timezone.now() - timedelta(minutes=minutes)
    
    expired_chats = Chat.objects.filter(
        is_temporary=True, 
        temp_created_at__lt=cutoff
    )
    
    # Логируем удаление
    count = expired_chats.count()
    for chat in expired_chats:
        # Создаем запись в логах аудита
        from .models import AuditLog
        AuditLog.objects.create(
            user=chat.user,
            action="cleanup_expired_chat",
            model_name="Chat",
            object_id=str(chat.id),
            details={"title": chat.title, "created_at": chat.createdAt.isoformat()}
        )
    
    expired_chats.delete()
    return count

def paraphrase_prompt(prompt_text):
    """
    Перефразирование промпта для улучшения качества генерации
    """
    paraphrases = [
        "\n\nСделай формулировку более конкретной и насыщенной деталями.",
        "\n\nДобавь больше художественных деталей и эмоциональной насыщенности.",
        "\n\nСфокусируйся на композиции и визуальной гармонии.",
        "\n\nУсиль эмоциональное воздействие через цвет и свет.",
    ]
    
    # Простая эвристика - выбираем парафраз на основе длины промпта
    index = min(len(prompt_text) // 50, len(paraphrases) - 1)
    return prompt_text + paraphrases[index]