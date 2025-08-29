import os
import pandas as pd
from torch.utils.data import Dataset, DataLoader
from transformers import (
    TrOCRProcessor,
    VisionEncoderDecoderModel,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer
)
from PIL import Image
import torch
import numpy as np
 
 
# === 0. Настройки ===
images_folder = "data/images"
dataset_csv = "data/dataset.csv"
output_dir = "data/trocr-finetuned-journal"
num_epochs = 3
batch_size = 1
learning_rate = 5e-5
max_target_length = 128

# === 1. Загрузка данных ===
df = pd.read_csv(dataset_csv)
print(f"[INFO] dataset.csv найден, загружено {len(df)} записей.")

# === 2. Загрузка процессора и модели ===
processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

# === 3. УСТАНАВЛИВАЕМ decoder_start_token_id ===
# Это критически важно для encoder-decoder моделей
model.config.decoder_start_token_id = processor.tokenizer.cls_token_id
model.config.pad_token_id = processor.tokenizer.pad_token_id
print(f"[INFO] decoder_start_token_id установлен: {model.config.decoder_start_token_id}")
print(f"[INFO] pad_token_id установлен: {model.config.pad_token_id}")

# === 4. Создаем собственный Dataset ===
class CustomOCRDataset(Dataset):
    def __init__(self, dataframe, processor, max_target_length=128):
        self.dataframe = dataframe
        self.processor = processor
        self.max_target_length = max_target_length
        
    def __len__(self):
        return len(self.dataframe)
    
    def __getitem__(self, idx):
        row = self.dataframe.iloc[idx]
        image_path = row["image_path"]
        text = row["text"]
        
        # Загрузка и обработка изображения
        image = Image.open(image_path).convert("RGB")
        
        # Обработка изображения через processor
        encoding = self.processor(images=image, return_tensors="pt")
        
        # Извлекаем pixel_values
        pixel_values = encoding.pixel_values
        if isinstance(pixel_values, list):
            pixel_values = pixel_values[0]
        pixel_values = pixel_values.squeeze(0)
        
        # Токенизация текста
        labels = self.processor.tokenizer(
            text,
            padding="max_length",
            max_length=self.max_target_length,
            truncation=True,
            return_tensors="pt"
        ).input_ids.squeeze(0)
        
        return {
            "pixel_values": pixel_values,
            "labels": labels
        }

# Создаем dataset
train_dataset = CustomOCRDataset(df, processor, max_target_length)

# === 5. Data collator ===
def collate_fn(batch):
    pixel_values = [item["pixel_values"] for item in batch]
    labels = [item["labels"] for item in batch]
    
    pixel_values = torch.stack(pixel_values)
    labels = torch.stack(labels)
    
    return {
        "pixel_values": pixel_values,
        "labels": labels
    }

# === 6. Проверка данных ===
print("=== ПРОВЕРКА ДАННЫХ ===")
if len(train_dataset) > 0:
    sample = train_dataset[0]
    print(f"Тип pixel_values: {type(sample['pixel_values'])}")
    print(f"Форма pixel_values: {sample['pixel_values'].shape}")
    print(f"Тип labels: {type(sample['labels'])}")
    print(f"Форма labels: {sample['labels'].shape}")

# === 7. Аргументы обучения ===
training_args = Seq2SeqTrainingArguments(
    output_dir=output_dir,
    per_device_train_batch_size=batch_size,
    learning_rate=learning_rate,
    num_train_epochs=num_epochs,
    logging_dir="./logs",
    save_strategy="epoch",
    predict_with_generate=True,
    logging_steps=1,
    save_total_limit=1,
    remove_unused_columns=False,
    report_to="none",  # Отключаем отчеты
)

# === 8. Trainer ===
trainer = Seq2SeqTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    data_collator=collate_fn,
    tokenizer=processor.tokenizer,
)

# === 9. Запуск обучения ===
print("[INFO] Запуск обучения...")
try:
    train_result = trainer.train()
    print("[INFO] Обучение завершено успешно!")
    
    # Сохранение модели
    trainer.save_model()
    processor.save_pretrained(output_dir)
    print(f"[INFO] Модель сохранена в {output_dir}")
    
    # Тестирование модели
    print("[INFO] Тестирование модели...")
    test_image = Image.open(df.iloc[0]["image_path"]).convert("RGB")
    pixel_values = processor(test_image, return_tensors="pt").pixel_values
    
    generated_ids = model.generate(pixel_values)
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    
    print(f"Оригинальный текст: {df.iloc[0]['text']}")
    print(f"Распознанный текст: {generated_text}")
    
except Exception as e:
    print(f"[ERROR] Ошибка при обучении: {e}")
    import traceback
    traceback.print_exc()