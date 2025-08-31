import os
import pandas as pd
from torch.utils.data import Dataset
from transformers import (
    TrOCRProcessor,
    VisionEncoderDecoderModel,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer
)
from PIL import Image
import torch

# === 0. Настройки ===
images_folder = "data/images"
dataset_csv = "data/dataset.csv"
output_dir = "data/trocr-finetuned-journal"
num_epochs = 3
batch_size = 1
learning_rate = 5e-5
max_target_length = 128
save_steps = 50  # каждые 50 шагов сохраняем чекпоинт

# === 1. Загрузка данных ===
df = pd.read_csv(dataset_csv)
print(f"[INFO] dataset.csv найден, загружено {len(df)} записей.")

# === 2. Загрузка процессора и модели ===
processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

# === 3. Устанавливаем decoder_start_token_id и pad_token_id ===
model.config.decoder_start_token_id = processor.tokenizer.cls_token_id
model.config.pad_token_id = processor.tokenizer.pad_token_id
print(f"[INFO] decoder_start_token_id: {model.config.decoder_start_token_id}")
print(f"[INFO] pad_token_id: {model.config.pad_token_id}")

# === 4. Dataset ===
class CustomOCRDataset(Dataset):
    def __init__(self, dataframe, processor, max_target_length=128):
        self.dataframe = dataframe
        self.processor = processor
        self.max_target_length = max_target_length
        
    def __len__(self):
        return len(self.dataframe)
    
    def __getitem__(self, idx):
        row = self.dataframe.iloc[idx]
        image = Image.open(row["image_path"]).convert("RGB")
        encoding = self.processor(images=image, return_tensors="pt")
        pixel_values = encoding.pixel_values.squeeze(0)
        labels = self.processor.tokenizer(
            row["text"],
            padding="max_length",
            max_length=self.max_target_length,
            truncation=True,
            return_tensors="pt"
        ).input_ids.squeeze(0)
        return {"pixel_values": pixel_values, "labels": labels}

train_dataset = CustomOCRDataset(df, processor, max_target_length)

# === 5. Data collator ===
def collate_fn(batch):
    pixel_values = torch.stack([item["pixel_values"] for item in batch])
    labels = torch.stack([item["labels"] for item in batch])
    return {"pixel_values": pixel_values, "labels": labels}

# === 6. Аргументы обучения ===
training_args = Seq2SeqTrainingArguments(
    output_dir=output_dir,
    per_device_train_batch_size=batch_size,
    learning_rate=learning_rate,
    num_train_epochs=num_epochs,
    logging_dir="./logs",
    logging_steps=10,
    save_strategy="steps",
    save_steps=save_steps,
    save_total_limit=5,
    predict_with_generate=True,
    remove_unused_columns=False,
    report_to="none",
)

# === 7. Trainer ===
trainer = Seq2SeqTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    data_collator=collate_fn,
    tokenizer=processor.tokenizer,
)

# === 8. Поиск последнего чекпоинта ===
last_checkpoint = None
if os.path.isdir(output_dir):
    checkpoints = [os.path.join(output_dir, d) for d in os.listdir(output_dir) if "checkpoint" in d]
    if checkpoints:
        last_checkpoint = sorted(checkpoints, key=lambda x: int(x.split("-")[-1]))[-1]
        print(f"[INFO] Найден чекпоинт: {last_checkpoint}")

# === 9. Запуск обучения с возобновлением ===
print("[INFO] Запуск обучения...")
try:
    train_result = trainer.train(resume_from_checkpoint=last_checkpoint)
    print("[INFO] Обучение завершено!")

    # Сохранение финальной модели
    trainer.save_model()
    processor.save_pretrained(output_dir)
    print(f"[INFO] Модель сохранена в {output_dir}")

    # Тестирование модели
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
