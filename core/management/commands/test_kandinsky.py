from django.core.management.base import BaseCommand
from core.kandinsky_service import kandinsky_service

class Command(BaseCommand):
    help = 'Test Kandinsky API connection'

    def handle(self, *args, **options):
        self.stdout.write('🔌 Testing Kandinsky API connection...')
        
        # Тест получения pipeline
        pipeline_id = kandinsky_service.get_pipeline()
        if pipeline_id:
            self.stdout.write(self.style.SUCCESS(f'✅ Pipeline ID: {pipeline_id}'))
        else:
            self.stdout.write(self.style.ERROR('❌ Failed to get pipeline'))
            return

        # Тест получения стилей
        styles = kandinsky_service.get_available_styles()
        if styles:
            self.stdout.write(self.style.SUCCESS(f'✅ Available styles: {len(styles)}'))
            for style in styles[:5]:  # Покажем первые 5
                self.stdout.write(f'   - {style}')
        else:
            self.stdout.write(self.style.WARNING('⚠️ No styles available'))

        # Тест генерации (опционально - может потратить кредиты)
        test_prompt = "красивый закат над морем"
        self.stdout.write(f'🎨 Testing generation with prompt: "{test_prompt}"')
        
        result = kandinsky_service.generate_image(test_prompt, width=512, height=512)
        if result["success"]:
            self.stdout.write(self.style.SUCCESS('✅ Generation successful!'))
            self.stdout.write(f'   Task ID: {result.get("task_id")}')
            self.stdout.write(f'   Image data length: {len(result.get("image_data", ""))}')
            self.stdout.write(f'   Censored: {result.get("censored", False)}')
        else:
            self.stdout.write(self.style.ERROR(f'❌ Generation failed: {result["error"]}'))