#!/usr/bin/env python3
"""
Скрипт для завантаження всіх зовнішніх CSS/JS файлів локально
для повної переносимості проекту
"""

import os
import requests
from pathlib import Path

# Створюємо необхідні директорії
static_dir = Path('static')
css_dir = static_dir / 'css'
js_dir = static_dir / 'js'
fonts_dir = static_dir / 'fonts'

for dir_path in [css_dir, js_dir, fonts_dir]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Список ресурсів для завантаження
resources = {
    'css/bootstrap.min.css': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'css/bootstrap-icons.css': 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css',
    'css/fontawesome.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'js/bootstrap.bundle.min.js': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'js/chart.min.js': 'https://cdn.jsdelivr.net/npm/chart.js@4.3.0/dist/chart.min.js',
    'js/xlsx.full.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js'
}

def download_file(url, local_path):
    """Завантажує файл з URL і зберігає локально"""
    try:
        print(f"Завантаження {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        full_path = static_dir / local_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ Збережено: {full_path}")
        return True
    except Exception as e:
        print(f"✗ Помилка завантаження {url}: {e}")
        return False

def download_font_files():
    """Завантажує шрифти Bootstrap Icons"""
    try:
        # Завантажуємо CSS файл щоб знайти посилання на шрифти
        css_content = requests.get('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css').text
        
        # Знаходимо URL шрифтів у CSS
        import re
        font_urls = re.findall(r'url\(([^)]+\.woff2?)\)', css_content)
        
        for font_url in font_urls:
            font_url = font_url.strip('"\'')
            if font_url.startswith('//'):
                font_url = 'https:' + font_url
            elif font_url.startswith('./'):
                font_url = 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/' + font_url[2:]
            
            font_name = Path(font_url).name
            download_file(font_url, f'fonts/{font_name}')
            
        # Оновлюємо CSS файл для використання локальних шрифтів
        updated_css = css_content
        for font_url in font_urls:
            font_name = Path(font_url.strip('"\'').split('/')[-1]).name
            updated_css = updated_css.replace(font_url, f'../fonts/{font_name}')
        
        # Зберігаємо оновлений CSS
        with open(static_dir / 'css/bootstrap-icons.css', 'w', encoding='utf-8') as f:
            f.write(updated_css)
            
    except Exception as e:
        print(f"Помилка завантаження шрифтів: {e}")

if __name__ == '__main__':
    print("Початок завантаження ресурсів...")
    
    success_count = 0
    total_count = len(resources)
    
    for local_path, url in resources.items():
        if download_file(url, local_path):
            success_count += 1
    
    # Завантажуємо шрифти окремо
    download_font_files()
    
    print(f"\nЗавершено: {success_count}/{total_count} файлів завантажено")
    print("Тепер проект повністю автономний!")