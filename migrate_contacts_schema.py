import sqlite3

DB_PATH = 'elestek_lift.db'  # при необходимости поменяйте путь к вашей базе

def create_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Таблица контактов
    c.execute('''
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        -- добавьте другие нужные поля
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Таблица компаний
    c.execute('''
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        -- добавьте другие нужные поля
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Связующая таблица контактов и компаний (many-to-many)
    c.execute('''
    CREATE TABLE IF NOT EXISTS contact_companies (
        contact_id INTEGER NOT NULL,
        company_id INTEGER NOT NULL,
        PRIMARY KEY (contact_id, company_id),
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
    )
    ''')

    conn.commit()
    conn.close()
    print('Таблицы успешно созданы или уже существуют.')

if __name__ == '__main__':
    create_tables()
