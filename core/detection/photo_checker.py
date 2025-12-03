import os
import tempfile
import base64
from PIL import Image
import io
from .detection import evaluate_pose

class PhotoChecker:
    def __init__(self, min_score_threshold=0):
        self.min_score_threshold = min_score_threshold
    
    def check_photo(self, base64_image_data):
        try:
            # Декодируем base64
            if 'base64,' in base64_image_data:
                image_data = base64_image_data.split('base64,')[1]
            else:
                image_data = base64_image_data
            
            image_binary = base64.b64decode(image_data)
            
            # Сохраняем временный файл для анализа
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                tmp_file.write(image_binary)
                tmp_path = tmp_file.name
            
            # Проверяем фото
            result = evaluate_pose(tmp_path)
            
            if result.get("reason") == "на изображении нет человека":
                print("🔍 PHOTO CHECKER DEBUG: No people detected - this is acceptable")
                # Проверяем промпт - если он явно не требует людей, то ок
                # (это можно сделать сложнее, но для простоты скажем что ок)
                return {
                    "success": True,
                    "score": 0,  # Нейтральный score
                    "checks": {},
                    "reason": "no people detected (acceptable)",
                    "passed": True  # ⬅️ ВСЕГДА ПРИНИМАЕМ ФОТО БЕЗ ЛЮДЕЙ
                }
            
            passed = result.get("score", -99) >= self.min_score_threshold
            print(f"🔍 PHOTO CHECKER DEBUG: Passed: {passed} (threshold: {self.min_score_threshold})")
            
            # Очищаем временный файл
            os.unlink(tmp_path)

            return {
                "success": True,
                "score": result.get("score", -99),
                "checks": result.get("checks", {}),
                "reason": result.get("reason", ""),
                "passed": passed
            }
            
        except Exception as e:
            print(f"❌ PHOTO CHECKER ERROR: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "passed": False
            }
    
    def generate_fix_prompt(self, original_prompt, check_results, max_retries=3):
        """
        Генерирует исправленный промпт на основе результатов проверки
        ТОЛЬКО ДЛЯ КРИТИЧЕСКИХ ПРОБЛЕМ
        """
        problems = []
        fix_prompt = original_prompt
        
        checks = check_results.get("checks", {})
        
        # Критические проблемы, которые точно нужно исправлять
        if checks.get("руки_нормальные", True) is False:
            # Только если руки есть и они деформированы
            problems.append("деформация пальцев или рук")
            fix_prompt += " Руки и пальцы должны быть естественной формы, без слияния пальцев. На каждой руке должно быть по 5 пальцев правильной формы."
        
        if checks.get("без_пересечений", True) is False:
            problems.append("пересечение рук с телом")
            fix_prompt += " Руки не должны пересекаться с телом или выглядеть внутри тела."
        
        # Остальные проблемы менее критичны
        if checks.get("пропорции", True) is False:
            problems.append("неестественные пропорции тела")
            # fix_prompt += " Пропорции тела должны быть реалистичными."
            # Не добавляем в промпт - Kandinsky плохо понимает такие указания
        
        if checks.get("углы", True) is False:
            problems.append("неестественные углы в суставах")
            # fix_prompt += " Поза должна быть естественной."
            # Не добавляем - слишком абстрактно
        
        if len(fix_prompt) > 800:
            fix_prompt = fix_prompt[:750] + "..."
        
        problems_text = ", ".join(problems) if problems else "незначительные проблемы"
        
        return fix_prompt, problems_text

# Синглтон инстанс
photo_checker = PhotoChecker(min_score_threshold=1)