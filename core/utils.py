from datetime import datetime, timedelta
from django.core.serializers.json import DjangoJSONEncoder
from .models import Message, Chat, PromptParameters, PromptHistory, MessageType
from string import Formatter
from .kandinsky_service import kandinsky_service
from .models import Message, MediaGenerationTask
from .detection.photo_checker import photo_checker

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
    parts = []
    
    # Базовая информация
    #content_type = parameters.get('content_type', 'контент')
    platform = parameters.get('platform', '')
    aspect_ratio = parameters.get('aspect_ratio', '1:1')
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
    
    if event_name or event_genre:
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
    # Получаем параметры для определения aspect ratio
    parameters = build_parameters_from_chat_messages(chat)
    aspect_ratio = parameters.get('aspect_ratio', '1:1')
    
    # Рассчитываем размеры
    width, height = calculate_dimensions(aspect_ratio)
        
    # Отправляем системное сообщение с информацией о размерах
    Message.objects.create(
        chat=chat,
        content=f"🎨 Запускаю генерацию изображения ({width}x{height}) с автоматической проверкой качества...",
        messageType=MessageType.SYSTEM
    )
    
    # Используем новую функцию с проверкой
    generation_result = check_and_regenerate_image(
        chat=chat,
        prompt_history=prompt_history,
        original_prompt=prompt_history.assembled_prompt,
        width=width,
        height=height,
        max_retries=3
    )
    
    if generation_result["success"]:
        task = generation_result["task"]
        
        # ✅ ОБНОВЛЕНО: Сообщение со ссылками для скачивания
        base_url = "http://localhost:8000"  # В реальном коде должен быть из настроек
        download_url = f"{base_url}/api/generation-tasks/{task.id}/download/"
        preview_url = f"{base_url}/api/generation-tasks/{task.id}/image-file/"
        
        attempts_info = ""
        regeneration_attempts = max(0, generation_result.get("attempts", 1) - 1)
        if regeneration_attempts > 0:
            attempts_info = f" (перегенераций: {regeneration_attempts})"
        
        preview_msg = f"✅ Генерация завершена{attempts_info}!\n\n"
        preview_msg += f"📥 Скачайте фото по ссылке:\n{download_url}\n\n"
        preview_msg += f"👀 Или просмотрите:\n{preview_url}"
        
        Message.objects.create(
            chat=chat,
            content=preview_msg,
            messageType=MessageType.SYSTEM
        )
       
        return {
            "success": True,
            "task_id": task.id,
            "attempts": generation_result["attempts"],
            "regeneration_attempts": regeneration_attempts,  # ⬅️ добавляем перегенерации
            "problems": generation_result.get("problems", [])
        }
    else:
        return {
            "success": False,
            "error": generation_result.get("error", "Unknown error"),
            "attempts": generation_result.get("attempts", 0),
            "regeneration_attempts": max(0, generation_result.get("attempts", 0) - 1)
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
    
    # ВОЗВРАЩАЕМ ДАННЫЕ С ИНФОРМАЦИЕЙ О ПЕРЕГЕНЕРАЦИЯХ
    return {
        "type": "completed", 
        "prompt_parameters": pp, 
        "prompt_history": ph,
        "generation_result": generation_result  # ⬅️ добавляем полный результат
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

def calculate_dimensions(aspect_ratio_str):
    """
    Расчет размеров изображения на основе aspect ratio
    """
    if aspect_ratio_str == "9:16":
        return 768, 1365  # Instagram portrait
    elif aspect_ratio_str == "16:9":
        return 1920, 1080  # Landscape
    elif aspect_ratio_str == "1:1":
        return 1024, 1024  # Square
    elif aspect_ratio_str == "4:5":
        return 1080, 1350  # Facebook/Instagram vertical
    elif aspect_ratio_str == "2:3":
        return 1200, 1800  # Portrait
    else:
        # По умолчанию квадрат
        return 1024, 1024

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


def check_and_regenerate_image(chat, prompt_history, original_prompt, width=1024, height=1024, max_retries=3):
    """
    Проверяет сгенерированное фото и при необходимости перегенерирует
    """
    attempts = 0
    problems_history = []
    
    print(f"🔧 UTILS DEBUG: Generating image with dimensions: {width}x{height}")
    
    while attempts < max_retries:
        attempts += 1
        
        # Создаем задачу генерации
        task = MediaGenerationTask.objects.create(
            user=chat.user,
            chat=chat,
            prompt_history=prompt_history,
            prompt_text=original_prompt if attempts == 1 else prompt_history.assembled_prompt,
            status=MediaGenerationTask.Status.PENDING
        )
        
        # Генерируем изображение с правильными размерами
        generation_result = kandinsky_service.generate_image(
            prompt=original_prompt if attempts == 1 else prompt_history.assembled_prompt,
            width=width,
            height=height,  # ⬅️ используем переданные размеры
            style="DEFAULT",
            negative_prompt="низкое качество, размытое, watermark, deformed, distorted, bad anatomy, extra fingers, missing fingers"
        )
        
        if not generation_result["success"]:
            task.status = MediaGenerationTask.Status.FAILED
            task.last_error = generation_result["error"]
            task.save()
            
            Message.objects.create(
                chat=chat,
                content=f"❌ Ошибка при генерации (попытка {attempts}): {generation_result['error']}",
                messageType=MessageType.SYSTEM
            )
            continue
        
        # Получаем сгенерированное изображение
        images_data = generation_result.get("images_data", [])
        if not images_data:
            task.status = MediaGenerationTask.Status.FAILED
            task.last_error = "Нет данных изображения"
            task.save()
            continue
        
        image_base64 = images_data[0]
        
        # Проверяем фото
        check_result = photo_checker.check_photo(image_base64)
        
        if check_result["passed"]:
            # Фото прошло проверку
            task.status = MediaGenerationTask.Status.SUCCESS
            task.result_image_base64 = image_base64
            task.attempts = attempts  # ⬅️ сохраняем количество попыток
            task.save()
            
            # Сообщаем о перегенерациях если были
            if attempts > 1:
                problems_text = "; ".join(problems_history)
                Message.objects.create(
                    chat=chat,
                    content=f"✅ Генерация завершена после {attempts} попыток. "
                           f"Проблемы исправлены: {problems_text}",
                    messageType=MessageType.SYSTEM
                )
            else:
                Message.objects.create(
                    chat=chat,
                    content="✅ Генерация завершена с первой попытки!",
                    messageType=MessageType.SYSTEM
                )
            
            return {
                "success": True,
                "task": task,
                "attempts": attempts,
                "regeneration_attempts": attempts - 1,  # ⬅️ количество перегенераций
                "problems": problems_history,
                "image_base64": image_base64
            }
        else:
            # Фото не прошло проверку
            task.status = MediaGenerationTask.Status.FAILED
            task.last_error = f"Проверка не пройдена: {check_result.get('reason', '')}"
            task.save()
            
            # Генерируем исправленный промпт
            fix_prompt, problems_text = photo_checker.generate_fix_prompt(
                original_prompt if attempts == 1 else prompt_history.assembled_prompt,
                check_result
            )
            
            problems_history.append(f"попытка {attempts}: {problems_text}")
            
            # Создаем новую историю промпта с исправлениями
            prompt_history = PromptHistory.objects.create(
                user=chat.user,
                prompt_template=prompt_history.prompt_template,
                parameters=prompt_history.parameters,
                assembled_prompt=fix_prompt
            )
            
            Message.objects.create(
                chat=chat,
                content=f"🔄 Попытка {attempts} не прошла проверку: {problems_text}. "
                       f"Пробую исправить...",
                messageType=MessageType.SYSTEM
            )
    
    # Все попытки исчерпаны
    Message.objects.create(
        chat=chat,
        content=f"❌ Не удалось сгенерировать корректное фото после {max_retries} попыток",
        messageType=MessageType.SYSTEM
    )
    
    return {
        "success": False,
        "attempts": attempts,
        "regeneration_attempts": max(0, attempts - 1),  # ⬅️ даже если не удалось
        "problems": problems_history,
        "error": "Превышено количество попыток перегенерации"
    }