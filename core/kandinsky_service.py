import requests
import json
import time
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class KandinskyService:
    def __init__(self):
        self.base_url = "https://api-key.fusionbrain.ai/"
        self.api_key = getattr(settings, 'KANDINSKY_API_KEY', '')
        self.secret_key = getattr(settings, 'KANDINSKY_SECRET_KEY', '')
        self.auth_headers = {
            'X-Key': f'Key {self.api_key}',
            'X-Secret': f'Secret {self.secret_key}',
        }

    def get_pipeline(self):
        """Получение доступного пайплайна (модели)"""
        try:
            response = requests.get(
                self.base_url + 'key/api/v1/pipelines', 
                headers=self.auth_headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return data[0]['id']  # Берем первую доступную модель
                else:
                    logger.error("No available pipelines found")
                    return None
            else:
                logger.error(f"Pipeline request error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Pipeline error: {str(e)}")
            return None

    def generate_image(self, prompt, width=1024, height=1024, style=None, negative_prompt=None):
        """
        Генерация изображения через Kandinsky API
        """
        try:
            # Получаем pipeline_id
            pipeline_id = self.get_pipeline()
            if not pipeline_id:
                return {
                    "success": False,
                    "error": "Не удалось получить доступную модель для генерации"
                }

            # Подготавливаем параметры согласно документации
            params = {
                "type": "GENERATE",
                "numImages": 1,
                "width": width,
                "height": height,
                "generateParams": {
                    "query": f"{prompt}"
                }
            }

            # Добавляем опциональные параметры
            if style:
                params["style"] = style
            if negative_prompt:
                params["negativePromptDecoder"] = negative_prompt

            # Подготавливаем данные для multipart/form-data
            files = {
                'pipeline_id': (None, pipeline_id),
                'params': (None, json.dumps(params), 'application/json')
            }

            # Отправляем запрос на генерацию
            response = requests.post(
                self.base_url + 'key/api/v1/pipeline/run',
                headers=self.auth_headers,
                files=files,
                timeout=30
            )

            # Принимаем как 200, так и 201 статус как успешные
            if response.status_code in [200, 201]:
                data = response.json()
                task_id = data.get('uuid')
                
                if task_id:
                    # Ждем завершения генерации
                    result = self.check_generation_status(task_id)
                    return result
                else:
                    return {
                        "success": False,
                        "error": "Не получен ID задачи генерации"
                    }
            else:
                logger.error(f"Kandinsky API error: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"API error: {response.status_code} - {response.text}"
                }

        except Exception as e:
            logger.error(f"Kandinsky service error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def check_generation_status(self, task_id, max_attempts=30, delay=5):
        """
        Проверка статуса генерации с ожиданием
        """
        print(f"🎨 KANDINSKY DEBUG: Checking status for task {task_id}")
        attempts = 0
        
        while attempts < max_attempts:
            try:
                response = requests.get(
                    self.base_url + 'key/api/v1/pipeline/status/' + task_id,
                    headers=self.auth_headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status')
                    
                    print(f"🎨 KANDINSKY DEBUG: Status check attempt {attempts + 1}/{max_attempts}, status: {status}")
                    
                    if status == 'DONE':
                        # Генерация завершена успешно
                        result = data.get('result', {})
                        files = result.get('files', [])
                        censored = result.get('censored', False)
                        
                        print(f"🎨 KANDINSKY DEBUG: Generation DONE, files: {files}")
                        print(f"🎨 KANDINSKY DEBUG: Files count: {len(files) if files else 0}")
                        
                        if files and len(files) >= 1:
                            # Возвращаем все изображения
                            print(f"🎨 KANDINSKY DEBUG: Generation completed successfully, received {len(files)} images")
                            return {
                                "success": True,
                                "images_data": files[:1],
                                "task_id": task_id,
                                "censored": censored,
                                "images_count": len(files[:1])
                            }
                        elif files and len(files) > 0:
                            # Получили меньше изображений чем запрашивали
                            print(f"🎨 KANDINSKY DEBUG: Requested 1 image but received {len(files)}")
                            return {
                                "success": True,
                                "images_data": files,  # Все что получили
                                "task_id": task_id,
                                "censored": censored,
                                "images_count": len(files),
                                "warning": f"Requested 1 but received {len(files)} images"
                            }
                        else:
                            print(f"🎨 KANDINSKY DEBUG: No image data in response")
                            return {
                                "success": False,
                                "error": "Нет данных изображения в ответе"
                            }
                    
                    elif status == 'FAIL':
                        error_desc = data.get('errorDescription', 'Неизвестная ошибка')
                        print(f"🎨 KANDINSKY DEBUG: Generation failed: {error_desc}")
                        return {
                            "success": False,
                            "error": f"Ошибка генерации: {error_desc}"
                        }
                    
                    elif status in ['INITIAL', 'PROCESSING']:
                        # Ждем и пробуем снова
                        attempts += 1
                        time.sleep(delay)
                        continue
                    
                    else:
                        # Неизвестный статус
                        print(f"🎨 KANDINSKY DEBUG: Unknown status: {status}")
                        attempts += 1
                        time.sleep(delay)
                        continue
                        
                else:
                    print(f"🎨 KANDINSKY DEBUG: Status check error: {response.status_code} - {response.text}")
                    attempts += 1
                    time.sleep(delay)
                    
            except Exception as e:
                print(f"🎨 KANDINSKY DEBUG: Status check exception: {str(e)}")
                attempts += 1
                time.sleep(delay)

        # Превышено количество попыток
        error_msg = f"Превышено время ожидания генерации ({max_attempts * delay} секунд)"
        print(f"🎨 KANDINSKY DEBUG: {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }

    def get_available_styles(self):
        """Получение списка доступных стилей"""
        try:
            response = requests.get(
                "https://cdn.fusionbrain.ai/static/styles/key",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Styles request error: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Styles error: {str(e)}")
            return []

# Синглтон экземпляр сервиса
kandinsky_service = KandinskyService()