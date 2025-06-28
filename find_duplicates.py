import sqlite3

# Connect to database and find duplicate addresses
conn = sqlite3.connect('requests.db')
cursor = conn.cursor()

# Find all addresses with their IDs and contract_id
cursor.execute('''
    SELECT id, contract_id, address, total_area, total_cost
    FROM contract_addresses
    ORDER BY address, id
''')

addresses = cursor.fetchall()

print("All addresses in database:")
duplicates = []
seen_addresses = {}

for addr in addresses:
    addr_id, contract_id, address, area, cost = addr
    print(f"ID: {addr_id}, Contract: {contract_id}, Address: '{address}', Area: {area}, Cost: {cost}")
    
    # Check for duplicates
    if address in seen_addresses:
        duplicates.append((addr_id, address))
        print(f"  DUPLICATE FOUND: {address} (ID: {addr_id})")
    else:
        seen_addresses[address] = addr_id

print(f"\nFound {len(duplicates)} duplicate addresses:")
for dup_id, dup_address in duplicates:
    print(f"  ID {dup_id}: {dup_address}")

# Find addresses that come after "вул. Світла, 14"
print("\nAddresses after 'вул. Світла, 14':")
svetla_found = False
for addr in addresses:
    addr_id, contract_id, address, area, cost = addr
    if "Світла" in address and "14" in address:
        svetla_found = True
        print(f"Found reference address: {address}")
        continue
    
    if svetla_found:
        print(f"  After Світла 14: ID {addr_id} - {address}")

conn.close()