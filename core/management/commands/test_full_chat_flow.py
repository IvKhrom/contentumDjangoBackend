from django.core.management.base import BaseCommand
from core.models import User, Chat, Message, MessageType
from core.utils import handle_user_message_and_advance
from core.kandinsky_service import kandinsky_service
import base64
import os
from datetime import datetime

class Command(BaseCommand):
    help = 'Test full chat flow with automatic generation'

    def handle(self, *args, **options):
        self.stdout.write('🧪 Testing full chat flow...')
        
        # Получаем или создаем тестового пользователя
        try:
            user = User.objects.get(email='test@example.com')
        except User.DoesNotExist:
            user = User.objects.create_user(
                email='test@example.com',
                fullName='Test User',
                password='testpassword123'
            )
            self.stdout.write('✅ Created test user')
        
        # Создаем чат
        chat = Chat.objects.create(
            user=user,
            title='Тестовый чат для генерации',
            is_temporary=False
        )
        self.stdout.write(f'✅ Created chat: {chat.id}')
        
        # Создаем первый системный вопрос
        from core.utils import next_question_for_chat
        key, question_text, optional = next_question_for_chat(chat)
        if question_text:
            Message.objects.create(
                chat=chat, 
                content=question_text, 
                messageType=MessageType.SYSTEM
            )
            self.stdout.write(f'❓ System question: {question_text}')
        
        # Имитируем быстрые ответы на все вопросы
        test_answers = [
            "фото",  # content_type
            "вдохновляющее изображение космического корабля в далекой галактике",  # idea
            "эпичный",  # emotion
            "без привязки",  # relation_to_event
            "-",  # event_name (пустое)
            "-",  # event_genre (пустое)
            "-",  # event_description (пустое)
            "футуристический",  # visual_style
            "космический корабль",  # composition_focus
            "синие и фиолетовые тона",  # color_palette
            "космос, будущее, технологии",  # visual_associations
            "ВКонтакте",  # platform
            "16:9",  # aspect_ratio
            "-",  # duration (пустое для фото)
            "Исследуй неизвестное",  # slogan
            "modern",  # text_style
            "3"  # variation_count
        ]
        
        self.stdout.write('📝 Sending test answers...')
        
        for i, answer in enumerate(test_answers):
            if answer:  # Отправляем только непустые ответы
                # Создаем пользовательское сообщение
                user_message = Message.objects.create(
                    chat=chat,
                    content=answer,
                    messageType=MessageType.USER
                )
                self.stdout.write(f'   {i+1}. User: {answer}')
                
                # Обрабатываем сообщение
                result = handle_user_message_and_advance(chat, user_message)
                
                if result["type"] == "question":
                    self.stdout.write(f'   💬 System: {result["message"].content}')
                elif result["type"] == "completed":
                    self.stdout.write('🎉 CHAT COMPLETED!')
                    self.stdout.write(f'   Prompt Parameters ID: {result["prompt_parameters"].id}')
                    self.stdout.write(f'   Prompt History ID: {result["prompt_history"].id}')
                    
                    # Показываем полный промпт
                    full_prompt = result["prompt_history"].assembled_prompt
                    self.stdout.write(f'   Assembled Prompt: {full_prompt}')
                    self.stdout.write(f'   Prompt length: {len(full_prompt)} characters')
                    
                    if "generation_result" in result:
                        gen_result = result["generation_result"]
                        if gen_result["success"]:
                            self.stdout.write(self.style.SUCCESS('✅ Automatic generation successful!'))
                            self.stdout.write(f'   Task ID: {gen_result.get("task_id")}')
                            
                            images_data = gen_result.get("images_data", [])
                            
                            # СОХРАНЕНИЕ ИЗОБРАЖЕНИЯ В ФАЙЛ
                            if images_data:
                                # Преобразуем task_id в строку для использования в имени файла
                                task_id_str = str(gen_result.get("task_id"))
                                variation_count = result["prompt_parameters"].data.get('variation_count', '1')
                                self.save_generated_images(images_data, full_prompt, task_id_str, variation_count)
                            else:
                                self.stdout.write(self.style.WARNING('⚠️ No image data received'))
                                
                        else:
                            self.stdout.write(self.style.ERROR(f'❌ Generation failed: {gen_result.get("error")}'))
                    
                    break
        
        # Показываем все сообщения в чате
        self.stdout.write('\n📋 Chat messages:')
        for msg in chat.messages.order_by('createdAt'):
            icon = '🤖' if msg.messageType == MessageType.SYSTEM else '👤'
            self.stdout.write(f'   {icon} {msg.content[:80]}{"..." if len(msg.content) > 80 else ""}')

    def save_generated_images(self, images_data, prompt, task_id, variation_count):
        """
        Сохраняет все сгенерированные изображения в файлы
        """
        try:
            # Создаем папку для сохранения изображений
            save_dir = 'media/generated'
            os.makedirs(save_dir, exist_ok=True)
            
            # Генерируем базовое имя файла с временной меткой
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_id_short = task_id[:8] if len(task_id) > 8 else task_id
            
            saved_files = []
            
            # Сохраняем каждое изображение
            for i, image_data in enumerate(images_data):
                filename = f"generated_{timestamp}_{task_id_short}_v{i+1}.png"
                filepath = os.path.join(save_dir, filename)
                
                # Обрабатываем Base64 данные
                if 'base64,' in image_data:
                    image_data = image_data.split('base64,')[1]
                
                # Декодируем Base64 и сохраняем в файл
                image_binary = base64.b64decode(image_data)
                
                with open(filepath, 'wb') as f:
                    f.write(image_binary)
                
                saved_files.append(filepath)
                self.stdout.write(self.style.SUCCESS(f'💾 Image {i+1} saved: {filepath}'))
                self.stdout.write(f'   Size: {len(image_binary)} bytes')
            
            # Создаем общий файл с промптом
            prompt_filename = f"prompt_{timestamp}_{task_id_short}.txt"
            prompt_filepath = os.path.join(save_dir, prompt_filename)
            
            with open(prompt_filepath, 'w', encoding='utf-8') as f:
                f.write(f"Task ID: {task_id}\n")
                f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Variation count: {variation_count}\n")
                f.write(f"Images generated: {len(images_data)}\n")
                f.write(f"Prompt length: {len(prompt)} characters\n\n")
                f.write("PROMPT:\n")
                f.write(prompt)
            
            self.stdout.write(self.style.SUCCESS(f'📝 Prompt saved: {prompt_filepath}'))
            self.stdout.write(f'📊 Total images saved: {len(saved_files)}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error saving images: {str(e)}'))