import torch
from PIL import Image
import numpy as np
import os

print("=== DETAILED TROCR TEST ===")
print("PyTorch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())

# Создаем простое тестовое изображение
def create_test_image():
    # Создаем белое изображение с черным текстом
    img_array = np.ones((100, 400, 3), dtype=np.uint8) * 255  # белый фон
    
    # Добавляем простой текст
    for i in range(20, 80):
        for j in range(50, 350):
            if (i + j) % 20 < 10:  # Простой паттерн для имитации текста
                img_array[i, j] = [0, 0, 0]  # черные пиксели
    
    return Image.fromarray(img_array)

try:
    print("1. Creating test image...")
    test_image = create_test_image()
    
    print("2. Loading processor...")
    # Пробуем разные способы загрузки процессора
    from transformers import TrOCRProcessor
    
    # Вариант 1: Базовый процессор
    try:
        processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-printed")
        print("   Success with printed version")
    except Exception as e:
        print("   Error with printed:", e)
        try:
            # Вариант 2: Handwritten версия
            processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
            print("   Success with handwritten version")
        except Exception as e2:
            print("   Error with handwritten:", e2)
            # Вариант 3: Любой доступный процессор
            try:
                processor = TrOCRProcessor.from_pretrained("microsoft/trocr-small-stage1")
                print("   Success with small-stage1 version")
            except Exception as e3:
                print("   All processor loading failed")
                raise e3
    
    print("3. Testing image processing...")
    # Тестируем обработку изображения
    pixel_values = processor(test_image, return_tensors="pt").pixel_values
    print("   Pixel values shape:", pixel_values.shape)
    print("   Pixel values type:", type(pixel_values))
    
    print("4. Testing tokenizer...")
    # Тестируем токенизатор
    text = "test 123"
    inputs = processor.tokenizer(text, return_tensors="pt")
    print("   Input keys:", list(inputs.keys()))
    print("   Input shapes:", {k: v.shape for k, v in inputs.items()})
    
    print("✅ All tests passed successfully!")
    
except Exception as e:
    print("❌ Error occurred:")
    print("Error type:", type(e).__name__)
    print("Error message:", str(e))
    import traceback
    traceback.print_exc()