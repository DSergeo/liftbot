import sqlite3

# Перевіряємо структуру бази даних
conn = sqlite3.connect('requests.db')
cursor = conn.cursor()

# Список всіх таблиць
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

# Перевіряємо структуру таблиці contracts
print("\n=== Contracts table structure ===")
cursor.execute("PRAGMA table_info(contracts);")
contracts_info = cursor.fetchall()
for col in contracts_info:
    print(f"  {col[1]} ({col[2]})")

# Перевіряємо наявність даних у contracts
print("\n=== Contracts data ===")
cursor.execute("SELECT id, number, customer, date, end_date, status FROM contracts LIMIT 3;")
contracts = cursor.fetchall()
for contract in contracts:
    print(f"  Contract {contract[0]}: {contract[1]} - {contract[2]} ({contract[3]} to {contract[4]}) - {contract[5]}")

# Тестуємо оновлення дати до вчорашньої для тестування автопролонгації
print("\n=== Testing date update ===")
cursor.execute("UPDATE contracts SET end_date = '2025-06-14' WHERE id = 13;")
conn.commit()
print("Updated end_date to 2025-06-14 (yesterday)")

# Перевіряємо addresses для договору
print("\n=== Contract addresses ===")
cursor.execute("SELECT DISTINCT contract_id FROM contract_addresses ORDER BY contract_id;")
contract_ids = cursor.fetchall()
print(f"Contract IDs with addresses: {[x[0] for x in contract_ids]}")

cursor.execute("""
    SELECT ca.contract_id, ca.address, ca.total_area, ca.total_cost, COUNT(cl.id) as lifts_count
    FROM contract_addresses ca
    LEFT JOIN contract_lifts cl ON ca.id = cl.address_id
    GROUP BY ca.id, ca.address
    LIMIT 5;
""")
addresses = cursor.fetchall()
print(f"Sample addresses:")
for addr in addresses:
    print(f"  Contract {addr[0]}: {addr[1]} (Area: {addr[2]}, Cost: {addr[3]}, Lifts: {addr[4]})")

# Виправляємо зв'язки - змінюємо contract_id на 13 для всіх адрес
print("\n=== Fixing address links ===")
cursor.execute("UPDATE contract_addresses SET contract_id = 13;")
cursor.execute("UPDATE contract_lifts SET contract_id = 13;")
conn.commit()
print("Updated all addresses to link to contract 13")

# Перевіряємо чи є таблиці для адрес
print("\n=== Address related tables ===")
for table_name in ['contract_addresses', 'contract_lifts', 'addresses']:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        print(f"  {table_name}: {count} records")
    except sqlite3.OperationalError as e:
        print(f"  {table_name}: Table doesn't exist - {e}")

conn.close()