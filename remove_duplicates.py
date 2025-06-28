import sqlite3

# Connect to database
conn = sqlite3.connect('requests.db')
cursor = conn.cursor()

# Get all duplicate address IDs from contract 15 (the duplicates)
duplicate_ids = [
    399, 398, 400, 402, 401, 394, 395, 396, 403, 404, 405, 406, 
    407, 408, 409, 397, 410, 411, 412, 413, 414, 415, 416, 417, 
    418, 419, 420, 421, 422
]

print(f"Removing {len(duplicate_ids)} duplicate addresses...")

# First, delete associated lifts
for addr_id in duplicate_ids:
    cursor.execute('DELETE FROM contract_lifts WHERE address_id = ?', (addr_id,))
    print(f"Deleted lifts for address ID {addr_id}")

# Then delete the duplicate addresses
for addr_id in duplicate_ids:
    cursor.execute('DELETE FROM contract_addresses WHERE id = ?', (addr_id,))
    print(f"Deleted address ID {addr_id}")

# Also delete contract 15 entirely if it's the duplicate contract
cursor.execute('DELETE FROM contracts WHERE id = 15')
print("Deleted contract 15")

conn.commit()

# Verify cleanup
cursor.execute('SELECT COUNT(*) FROM contract_addresses')
remaining_addresses = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM contract_lifts')
remaining_lifts = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM contracts')
remaining_contracts = cursor.fetchone()[0]

print(f"\nCleanup completed:")
print(f"Remaining addresses: {remaining_addresses}")
print(f"Remaining lifts: {remaining_lifts}")
print(f"Remaining contracts: {remaining_contracts}")

# Show remaining addresses grouped by contract
cursor.execute('''
    SELECT contract_id, COUNT(*) as address_count
    FROM contract_addresses
    GROUP BY contract_id
    ORDER BY contract_id
''')

contracts_summary = cursor.fetchall()
print(f"\nAddresses by contract:")
for contract_id, count in contracts_summary:
    print(f"  Contract {contract_id}: {count} addresses")

conn.close()