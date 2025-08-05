import sqlite3
import json

# Connect to database
conn = sqlite3.connect('requests.db')
cursor = conn.cursor()

# Get contracts with addresses_data
cursor.execute("SELECT id, addresses_data FROM contracts WHERE addresses_data IS NOT NULL AND addresses_data != ''")
contracts = cursor.fetchall()

print(f"Found {len(contracts)} contracts with addresses data")

for contract_id, addresses_data in contracts:
    try:
        # Parse JSON addresses data
        addresses = json.loads(addresses_data)
        print(f"\nContract {contract_id}: {len(addresses)} addresses")
        
        for addr in addresses:
            address = addr.get('address', '')
            total_area = float(addr.get('total_area', 0))
            total_cost = float(addr.get('total_cost', 0))
            
            # Insert address
            cursor.execute('''
                INSERT INTO contract_addresses (contract_id, address, total_area, total_cost)
                VALUES (?, ?, ?, ?)
            ''', (contract_id, address, total_area, total_cost))
            
            address_id = cursor.lastrowid
            print(f"  Address: {address} (ID: {address_id})")
            
            # Insert lifts for this address
            for lift in addr.get('lifts', []):
                floors = int(lift.get('floors', 9))
                reg_num = lift.get('reg_num', '')
                area = float(lift.get('area', 0))
                tariff = float(lift.get('tariff', 0.68))
                cost = float(lift.get('cost', 0))
                
                cursor.execute('''
                    INSERT INTO contract_lifts (address_id, floors, reg_num, area, tariff, cost)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (address_id, floors, reg_num, area, tariff, cost))
                
                print(f"    Lift: {reg_num} - {area}m² @ {tariff} = {cost}")
    
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON for contract {contract_id}: {e}")
    except Exception as e:
        print(f"Error processing contract {contract_id}: {e}")

# Commit changes
conn.commit()

# Verify migration
cursor.execute("SELECT COUNT(*) FROM contract_addresses")
addresses_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM contract_lifts")
lifts_count = cursor.fetchone()[0]

print(f"\nMigration completed:")
print(f"  {addresses_count} addresses created")
print(f"  {lifts_count} lifts created")

conn.close()