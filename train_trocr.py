import os
import pandas as pd
from datasets import Dataset
from transformers import (
    TrOCRProcessor,
    VisionEncoderDecoderModel,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    default_data_collator
)
from PIL import Image
import torch
import numpy as np

# === 0. Настройки ===
images_folder = "data/images"        # папка с картинками
dataset_csv = "data/dataset.csv"     # CSV файл
output_dir = "data/trocr-finetuned-journal"
num_epochs = 10
batch_size = 2
learning_rate = 5e-5
max_target_length = 128  # Добавим максимальную длину текста

# === 1. Создаём dataset.csv, если его нет ===
if not os.path.exists(dataset_csv):
    os.makedirs(os.path.dirname(dataset_csv), exist_ok=True)
    data = []

    for img_file in os.listdir(images_folder):
        if img_file.lower().endswith((".png", ".jpg", ".jpeg")):
            name = os.path.splitext(img_file)[0]
            txt_file = os.path.join(images_folder, name + ".txt")
            if os.path.exists(txt_file):
                with open(txt_file, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                data.append([os.path.join(images_folder, img_file), text])
            else:
                print(f"[WARNING] Нет текста для изображения {img_file}, пропускаем.")

    if not data:
        raise ValueError("Нет изображений с текстовыми файлами! Добавьте хотя бы одну пару .png/.txt")

    df = pd.DataFrame(data, columns=["file", "text"])
    df.to_csv(dataset_csv, index=False, quoting=1)  # quoting=1 для QUOTE_ALL
    print(f"[INFO] dataset.csv создан с {len(df)} записями.")
else:
    df = pd.read_csv(dataset_csv)
    print(f"[INFO] dataset.csv найден, загружено {len(df)} записей.")

# Переименуем колонку для удобства
df = df.rename(columns={"file": "image_path"})

# === 2. Загружаем процессор и модель ===
processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

# === 3. Создаём Dataset для HuggingFace ===
def process_example(example):
    # Загружаем изображение
    image = Image.open(example["image_path"]).convert("RGB")
    
    # Подготавливаем текст для токенизации
    text = example["text"]
    
    # Обрабатываем изображение и текст вместе
    model_inputs = processor(
        images=image, 
        text=text, 
        padding="max_length",
        max_length=max_target_length,
        truncation=True,
        return_tensors="pt"
    )
    
    # Подготовка labels
    labels = model_inputs["labels"]
    pixel_values = model_inputs["pixel_values"].squeeze(0)  # Убираем batch dimension
    
    return {
        "pixel_values": pixel_values,
        "labels": labels
    }

# Создаем dataset
dataset = Dataset.from_pandas(df)
dataset = dataset.map(process_example, remove_columns=dataset.column_names)

# === 4. Data collator (УПРОЩЕННАЯ ВЕРСИЯ) ===
def collate_fn(batch):
    pixel_values = torch.stack([item["pixel_values"] for item in batch])
    labels = torch.stack([item["labels"] for item in batch])
    
    return {
        "pixel_values": pixel_values,
        "labels": labels
    }

# === 5. Аргументы обучения ===
training_args = Seq2SeqTrainingArguments(
    output_dir=output_dir,
    per_device_train_batch_size=batch_size,
    learning_rate=learning_rate,
    num_train_epochs=num_epochs,
    logging_dir="./logs",
    save_strategy="epoch",
    predict_with_generate=True,
    fp16=torch.cuda.is_available(),
    logging_steps=10,
    save_total_limit=2,
)

# === 6. Trainer ===
trainer = Seq2SeqTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    data_collator=collate_fn,
    tokenizer=processor.tokenizer,
)

# === 7. Запуск обучения ===
print("[INFO] Запуск обучения...")
trainer.train()

# === 8. Сохраняем модель ===
trainer.save_model()
processor.save_pretrained(output_dir)
print(f"[INFO] Модель сохранена в {output_dir}")