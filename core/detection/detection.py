import numpy as np
import cv2
from ultralytics import YOLO
import os

# Определяем базовый путь к моделям
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, 'models')

# Полные пути к файлам моделей
POSE_MODEL_PATH = os.path.join(MODELS_DIR, 'yolo11l-pose.pt')
HANDS_MODEL_PATH = os.path.join(MODELS_DIR, 'best.pt')


# Проверяем существование файлов моделей
if not os.path.exists(POSE_MODEL_PATH):
    print(f"❌ ERROR: Pose model not found at {POSE_MODEL_PATH}")
    raise FileNotFoundError(f"Pose model not found at {POSE_MODEL_PATH}")

if not os.path.exists(HANDS_MODEL_PATH):
    print(f"❌ ERROR: Hands model not found at {HANDS_MODEL_PATH}")
    raise FileNotFoundError(f"Hands model not found at {HANDS_MODEL_PATH}")

# Загружаем модели
try:
    pose_model = YOLO(POSE_MODEL_PATH)
    hands_model = YOLO(HANDS_MODEL_PATH)
except Exception as e:
    raise

def dist(a, b):
    """Расстояние между двумя точками."""
    return np.linalg.norm(a - b)

def angle(a, b, c):
    """
    Возвращает угол ABC в градусах.
    a, b, c — точки в формате (x, y), b — вершина угла.
    """
    ba = a - b
    bc = c - b
    cosang = np.dot(ba, bc) / (np.linalg.norm(ba)*np.linalg.norm(bc) + 1e-6)
    return np.degrees(np.arccos(np.clip(cosang, -1, 1)))


def extract_pose(path):
    """
    Запускает YOLO11L-pose, возвращает список людей.
    Каждый человек → { "kps": (17, 2), "conf": (17,) }.
    """
    result = pose_model(path)[0]

    persons = []
    for det in result:
        if det.keypoints is None:
            continue

        kps = det.keypoints.xy.cpu().numpy()[0]
        conf = det.keypoints.conf.cpu().numpy()[0]
        persons.append({"kps": kps, "conf": conf})

    return persons


def extract_hands(path):
    """
    Запускает YOLO11L-hand-pose, возвращает список рук.
    Каждая рука → { "kps": (21, 2), "conf": (21,) }.
    """
    result = hands_model(path)[0]

    hands = []
    for det in result:
        if det.keypoints is None:
            continue

        kps = det.keypoints.xy.cpu().numpy()[0]
        conf = det.keypoints.conf.cpu().numpy()[0]
        hands.append({"kps": kps, "conf": conf})

    return hands


def has_all_limbs(person):
    """
    Проверка наличия важных keypoints:
    локти + запястья обеих рук (5,6,7,8,9,10 COCO).
    Но только если они вообще должны быть видны!
    """
    if person is None or "conf" not in person:
        return True  # Не можем проверить - считаем что ок
    
    # Проверяем уверенность в том, что человек вообще в кадре
    # (ключевые точки носа, глаз и т.д.)
    face_keypoints_conf = [person["conf"][i] for i in [0, 1, 2, 3, 4] if i < len(person["conf"])]
    if face_keypoints_conf and max(face_keypoints_conf) > 0.5:
        # Лицо видно хорошо - значит человек в кадре и конечности должны быть
        required = [5, 6, 7, 8, 9, 10]
        return all(person["conf"][i] > 0.3 for i in required)
    else:
        # Лицо не видно - может быть крупный план или что-то еще
        return True  # Не требуем наличия всех конечностей


def limb_length_check(kps):
    """
    Проверка пропорций длин сегментов руки:
    плечо → локоть и локоть → кисть.
    Отношение должно быть в разумных пределах.
    """
    up_l = dist(kps[5], kps[7])
    low_l = dist(kps[7], kps[9])

    up_r = dist(kps[6], kps[8])
    low_r = dist(kps[8], kps[10])

    def ok(upper, lower):
        if lower == 0:
            return False
        r = upper / lower
        return 0.4 < r < 2.5

    return ok(up_l, low_l) and ok(up_r, low_r)


def elbow_angle_ok(kps):
    """
    Проверка углов в локтях.
    Диапазон 20–170 градусов — естественный изгиб.
    """
    left = angle(kps[5], kps[7], kps[9])
    right = angle(kps[6], kps[8], kps[10])
    return (20 < left < 170) and (20 < right < 170)


def not_self_intersect(kps):
    """
    Проверка, что запястья не попадают внутрь контура торса.
    Пересечение рук с телом — частый артефакт генерации.
    """
    torso = np.array([kps[11], kps[12], kps[6], kps[5]], dtype=np.float32)
    wrists = [kps[9], kps[10]]

    for w in wrists:
        inside = cv2.pointPolygonTest(torso, tuple(w.astype(np.float32)), False)
        if inside >= 0:  # wrist inside torso
            return False
    return True


def symmetry_check(kps):
    """
    Проверка симметрии рук и ног:
    — длины правой/левой руки должны быть похожи,
    — длины правой/левой ноги тоже должны быть похожи.
    Это выявляет "левую ногу 2 метра, правую 30 см".
    """

    # Руки: плечо→локоть, локоть→кисть
    left_upper = dist(kps[5], kps[7])
    right_upper = dist(kps[6], kps[8])

    left_fore = dist(kps[7], kps[9])
    right_fore = dist(kps[8], kps[10])

    # Ноги: бедро→колено→стопа
    left_leg = dist(kps[11], kps[13]) + dist(kps[13], kps[15])
    right_leg = dist(kps[12], kps[14]) + dist(kps[14], kps[16])

    def similar(a, b, tol=0.6):
        """Проверка близости двух значений с допуском ±60%."""
        if b == 0:
            return False
        r = a / b
        return (1 - tol) < r < (1 + tol)

    return (
        similar(left_upper, right_upper) and
        similar(left_fore, right_fore) and
        similar(left_leg, right_leg)
    )


def hand_deformation(hands):
    """
    Проверка деформации пальцев, "слипания" пальцев,
    нереалистичных углов в суставах.
    ТОЛЬКО ЕСЛИ РУКИ ОБНАРУЖЕНЫ!
    """
    # Если рук нет - это не ошибка, просто нет рук
    if len(hands) == 0:
        return True  # нет рук — это нормально
    
    print(f"🔍 DETECTION DEBUG: Checking {len(hands)} hands for deformations")
    
    try:
        for h_idx, h in enumerate(hands):
            kps = h["kps"]
            conf = h["conf"]
            
            # Проверяем уверенность детекции
            avg_conf = np.mean(conf)
            if avg_conf < 0.2:  # Слишком низкая уверенность
                print(f"🔍 DETECTION DEBUG: Hand {h_idx} has low confidence {avg_conf:.2f}")
                continue  # Пропускаем эту руку
            
            print(f"🔍 DETECTION DEBUG: Hand {h_idx} detected with confidence {avg_conf:.2f}")
            
            # Пальцы (каждый по 4 точки): 
            fingers = [
                kps[1:5],    # большой
                kps[5:9],    # указательный
                kps[9:13],   # средний
                kps[13:17],  # безымянный
                kps[17:21]   # мизинец
            ]

            # Проверка "слипания" кончиков пальцев
            tips = np.array([f[-1] for f in fingers])
            for i in range(len(tips) - 1):
                if dist(tips[i], tips[i+1]) < 5:
                    # два пальца почти в одной точке — артефакт
                    print(f"❌ DETECTION DEBUG: Fingers {i} and {i+1} are fused")
                    return False

            # Проверка углов суставов пальцев
            for f_idx, f in enumerate(fingers):
                p0, p1, p2, p3 = f
                a1 = angle(p0, p1, p2)
                a2 = angle(p1, p2, p3)
                if a1 < 10 or a2 < 10:   # палец сломан или слипся
                    print(f"❌ DETECTION DEBUG: Finger {f_idx} has broken joints: angles {a1:.1f}, {a2:.1f}")
                    return False
        
        return True
    except Exception as e:
        print(f"❌ ERROR in hand_deformation: {str(e)}")
        return True  # При ошибке считаем, что руки нормальные


def evaluate_pose(image_path):
    """
    Полная проверка:
    — наличие конечностей (если человек есть)
    — пропорции (если конечности есть)
    — углы (если локти обнаружены)
    — симметрия (если обе стороны есть)
    — пересечения (если торс и запястья есть)
    — корректность рук (ТОЛЬКО ЕСЛИ РУКИ ОБНАРУЖЕНЫ)
    """
    print(f"🔍 DETECTION DEBUG: Evaluating pose for {image_path}")
    
    try:
        if not os.path.exists(image_path):
            return {"score": -99, "reason": f"файл не найден: {image_path}"}
        
        people = extract_pose(image_path)
        hands = extract_hands(image_path)
        
        print(f"🔍 DETECTION DEBUG: Found {len(people)} people, {len(hands)} hands")

        if len(people) == 0:
            return {"score": -99, "reason": "на изображении нет человека"}

        person = people[0]
        kps = person["kps"]
        conf = person["conf"]
        
        print(f"🔍 DETECTION DEBUG: Keypoints confidence: {np.mean(conf):.2f}")
        
        # Проверяем, какие ключевые точки вообще обнаружены
        detected_keypoints = [i for i, c in enumerate(conf) if c > 0.3]
        print(f"🔍 DETECTION DEBUG: Detected keypoints: {detected_keypoints}")
        
        # Проверки с учетом того, какие части тела обнаружены
        checks = {}
        
        # 1. Проверка наличия конечностей - ТОЛЬКО если они должны быть в кадре
        # (если человек в полный рост, то конечности должны быть)
        checks["наличие_конечностей"] = has_all_limbs(person) if len(detected_keypoints) > 10 else True
        
        # 2. Проверка пропорций - ТОЛЬКО если есть соответствующие ключевые точки
        required_for_proportions = all(i in detected_keypoints for i in [5, 6, 7, 8, 9, 10])
        checks["пропорции"] = limb_length_check(kps) if required_for_proportions else True
        
        # 3. Проверка углов - ТОЛЬКО если есть локти
        required_for_angles = all(i in detected_keypoints for i in [5, 6, 7, 8, 9, 10])
        checks["углы"] = elbow_angle_ok(kps) if required_for_angles else True
        
        # 4. Проверка пересечений - ТОЛЬКО если есть торс и запястья
        required_for_intersect = all(i in detected_keypoints for i in [5, 6, 9, 10, 11, 12])
        checks["без_пересечений"] = not_self_intersect(kps) if required_for_intersect else True
        
        # 5. Проверка симметрии - ТОЛЬКО если есть обе стороны
        has_left_side = any(i in detected_keypoints for i in [5, 7, 9, 11, 13, 15])
        has_right_side = any(i in detected_keypoints for i in [6, 8, 10, 12, 14, 16])
        checks["симметрия"] = symmetry_check(kps) if (has_left_side and has_right_side) else True
        
        # 6. Проверка рук - ТОЛЬКО ЕСЛИ РУКИ ОБНАРУЖЕНЫ
        # Если рук нет вообще - это нормально
        checks["руки_нормальные"] = hand_deformation(hands) if len(hands) > 0 else True
        
        print(f"🔍 DETECTION DEBUG: Checks: {checks}")
        
        # Подсчет очков: +1 за успех, 0 за пропущенную проверку, -1 за провал
        score = 0
        for check_name, result in checks.items():
            if result is True:
                score += 1
            elif result is False:
                score -= 1
            # Если None или что-то еще - не влияет на счет
        
        print(f"🔍 DETECTION DEBUG: Final score: {score}")
        
        # Определяем причину если есть проблемы
        reason = ""
        failed_checks = [name for name, result in checks.items() if result is False]
        if failed_checks:
            reason = f"провалены проверки: {', '.join(failed_checks)}"
        
        return {
            "score": score,
            "checks": checks,
            "reason": reason if reason else "все проверки пройдены"
        }
        
    except Exception as e:
        print(f"❌ ERROR in evaluate_pose: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"score": -99, "reason": f"ошибка при проверке: {str(e)}"}
