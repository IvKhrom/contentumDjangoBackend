from django.core.management.base import BaseCommand
from core.kandinsky_service import kandinsky_service
import base64
import os

class Command(BaseCommand):
    help = 'Save test generated image to file'

    def handle(self, *args, **options):
        self.stdout.write('🎨 Generating and saving test image...')
        
        test_prompt = "красивый закат над морем, цифровое искусство, высокое качество"
        result = kandinsky_service.generate_image(test_prompt, width=1024, height=1024)
        
        if result["success"]:
            image_data = result.get("image_data", "")
            if image_data:
                try:
                    # Убираем data:image/... префикс если есть
                    if 'base64,' in image_data:
                        image_data = image_data.split('base64,')[1]
                    
                    image_binary = base64.b64decode(image_data)
                    
                    # Создаем папку media если нет
                    media_dir = 'media/generated'
                    os.makedirs(media_dir, exist_ok=True)
                    
                    # Сохраняем файл
                    filename = f'{media_dir}/test_generation_{result["task_id"]}.png'
                    with open(filename, 'wb') as f:
                        f.write(image_binary)
                    
                    self.stdout.write(self.style.SUCCESS(f'✅ Image saved: {filename}'))
                    self.stdout.write(f'📏 Size: {len(image_binary)} bytes')
                    self.stdout.write(f'🎯 Prompt: "{test_prompt}"')
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Save error: {e}'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ Generation failed: {result["error"]}'))