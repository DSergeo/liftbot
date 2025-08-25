from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
import sqlite3
import json
from datetime import datetime
from app.utils import get_company_db_path
from app.utils import clean_currency_format

# Blueprint для HTML-страницы
contract_html = Blueprint('contract_html', __name__)

@contract_html.route("/documents/contract")
def documents_contract():
    if "user_email" not in session:
        return redirect(url_for("login"))
    return render_template("documents/contract.html")

@contract_html.route("/documents/contract/<int:contract_id>")
def view_contract(contract_id):
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    # Загрузка данных конкретного договора из базы данных
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        # Загружаем основные данные договора
        cursor.execute('''
            SELECT id, number, customer, date, end_date, total_lifts, monthly_cost, yearly_cost, status, created_at
            FROM contracts WHERE id = ?
        ''', (contract_id,))
        
        contract_row = cursor.fetchone()
        
        if not contract_row:
            conn.close()
            return "Договір не знайдено", 404
        
        # Загружаем адреса
        cursor.execute('''
            SELECT id, address, total_area, total_cost
            FROM contract_addresses
            WHERE contract_id = ?
            ORDER BY address
        ''', (contract_id,))
        
        address_rows = cursor.fetchall()
        
        # Загружаем лифты
        cursor.execute('''
            SELECT address_id, address, floors, reg_num, area, tariff, cost
            FROM contract_lifts
            WHERE contract_id = ?
            ORDER BY address_id, id
        ''', (contract_id,))
        
        lift_rows = cursor.fetchall()
        print(f"Loading addresses for contract {contract_id}: found {len(address_rows)} addresses and {len(lift_rows)} lifts")
        
        # Создаем словарь адресов
        addresses_data = {}
        for row in address_rows:
            address_id, address, total_area, total_cost = row
            print(f"Processing address: {address}")
            addresses_data[address_id] = {
                'address': address,
                'total_area': total_area,
                'total_cost': total_cost,
                'lifts': []
            }
        
        # Добавляем лифты к соответствующим адресам
        for lift_row in lift_rows:
            address_id, lift_address, floors, reg_num, area, tariff, cost = lift_row
            if address_id in addresses_data:
                print(f"Adding lift data: {lift_address}")
                addresses_data[address_id]['lifts'].append({
                    'address': lift_address,
                    'floors': floors,
                    'reg_num': reg_num,
                    'area': area,
                    'tariff': tariff,
                    'cost': cost
                })
        
        # Преобразуем в список
        addresses_list = list(addresses_data.values())
        print(f"Final addresses list: {len(addresses_list)} addresses")
        
        # Используем актуальную дату окончания из базы данных
        end_date = contract_row[4]  # end_date з бази даних
        status = contract_row[8]  # статус з бази даних
        
        # Только обновляем статус, не меняем дату окончания
        if end_date:
            try:
                current_date = datetime.now().date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                days_until_end = (end_date_obj - current_date).days
                
                # Определяем статус на основе дней до окончания
                if days_until_end <= 0:
                    new_status = 'active'  # Автопролонгация без изменения даты
                elif days_until_end <= 45:
                    new_status = 'заканчивается'
                else:
                    new_status = 'active'
                
                # Обновляем только статус, если он изменился
                if new_status != status and status != 'terminated':
                    cursor.execute('''
                        UPDATE contracts SET status = ?
                        WHERE id = ?
                    ''', (new_status, contract_id))
                    conn.commit()
                    status = new_status
                    
            except ValueError:
                # Если дата некорректна, оставляем как есть
                pass

        contract = {
            'id': contract_row[0],
            'number': contract_row[1],
            'customer': contract_row[2],
            'date': contract_row[3],
            'end_date': end_date,
            'total_lifts': contract_row[5],
            'monthly_cost': contract_row[6],
            'yearly_cost': contract_row[7],
            'status': status,
            'created_at': contract_row[9],
            'addresses_data': json.dumps(addresses_list, ensure_ascii=False)
        }
        
        # Додатково завантажуємо адреси для JavaScript
        cursor.execute('''
            SELECT ca.address, ca.total_area, ca.total_cost, COUNT(cl.id) as lifts_count
            FROM contract_addresses ca
            LEFT JOIN contract_lifts cl ON ca.id = cl.address_id
            WHERE ca.contract_id = ?
            GROUP BY ca.id, ca.address
            ORDER BY ca.address
        ''', (contract_id,))
        
        addresses_summary = cursor.fetchall()
        
        print(f"Contract {contract_id} loaded with {len(addresses_list)} addresses")
        print(f"Addresses data: {contract['addresses_data']}")
        print(f"Addresses summary: {addresses_summary}")
        
        conn.close()
        
        return render_template("documents/contract.html", 
                               contract=contract, 
                               edit_mode=True,
                               addresses_summary=addresses_summary)
        
    except Exception as e:
        print(f"Error loading contract: {e}")
        return "Помилка завантаження договору", 500


    if "user_email" not in session:
        return jsonify({'success': False, 'error': 'Не авторизовано'}), 401
    
    try:
        data = request.get_json()
        contract_ids = data.get('contract_ids', [])
        
        if not contract_ids:
            return jsonify({'success': False, 'error': 'Не вказано договори для видалення'})
        
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        # Cascading delete: First delete lifts, then addresses, then contracts
        for contract_id in contract_ids:
            # Get all address IDs for this contract
            cursor.execute('SELECT id FROM contract_addresses WHERE contract_id = ?', (contract_id,))
            address_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete lifts for all addresses
            if address_ids:
                addr_placeholders = ','.join('?' * len(address_ids))
                cursor.execute(f'DELETE FROM contract_lifts WHERE address_id IN ({addr_placeholders})', address_ids)
            
            # Delete addresses
            cursor.execute('DELETE FROM contract_addresses WHERE contract_id = ?', (contract_id,))
            
            # Delete contract
            cursor.execute('DELETE FROM contracts WHERE id = ?', (contract_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error deleting contracts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@contract_html.route("/registries/contracts")
def registries_contracts():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    # Загрузка договоров из базы данных
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, number, customer, date, end_date, total_lifts, monthly_cost, yearly_cost, status, created_at
            FROM contracts
            ORDER BY created_at DESC
        ''')
        
        contracts = []
        current_date = datetime.now().date()
        
        for row in cursor.fetchall():
            contract = {
                'id': row[0],
                'number': row[1],
                'customer': row[2],
                'date': row[3],
                'end_date': row[4],
                'total_lifts': row[5],
                'monthly_cost': row[6],
                'yearly_cost': row[7],
                'status': row[8],
                'created_at': row[9]
            }
            
            # Определяем статус договора на основе дат
            if contract['end_date']:
                try:
                    end_date = datetime.strptime(contract['end_date'], '%Y-%m-%d').date()
                    days_until_end = (end_date - current_date).days
                    new_status = contract['status']
                    
                    if days_until_end <= 0:
                        # Договор истек - автопролонгация на следующий день после окончания
                        if contract['status'] != 'terminated':
                            new_end_date = end_date.replace(year=end_date.year + 1)
                            cursor.execute('''
                                UPDATE contracts SET end_date = ?, status = 'active'
                                WHERE id = ?
                            ''', (new_end_date.strftime('%Y-%m-%d'), contract['id']))
                            contract['end_date'] = new_end_date.strftime('%Y-%m-%d')
                            contract['status'] = 'active'
                            new_status = 'active'
                            print(f"Auto-prolonged contract {contract['id']} from {end_date} to {new_end_date}")
                    elif days_until_end <= 45:  # 1,5 месяца = ~45 дней
                        new_status = 'заканчивается'
                        if contract['status'] != 'заканчивается' and contract['status'] != 'terminated':
                            cursor.execute('''
                                UPDATE contracts SET status = 'заканчивается'
                                WHERE id = ?
                            ''', (contract['id'],))
                            contract['status'] = 'заканчивается'
                    elif contract['status'] != 'terminated':
                        new_status = 'active'
                        if contract['status'] != 'active':
                            cursor.execute('''
                                UPDATE contracts SET status = 'active'
                                WHERE id = ?
                            ''', (contract['id'],))
                            contract['status'] = 'active'
                except ValueError:
                    contract['status'] = 'active'
            
            contracts.append(contract)
        
        conn.commit()
        
        # Подсчитываем статистику для виджетов
        total_contracts = len(contracts)
        active_contracts = len([c for c in contracts if c['status'] == 'active'])
        ending_contracts = len([c for c in contracts if c['status'] == 'заканчивается'])
        total_value = sum([float(c['monthly_cost'] or 0) for c in contracts])
        unique_customers = len(set([c['customer'] for c in contracts if c['customer']]))
        
        stats = {
            'total_contracts': total_contracts,
            'active_contracts': active_contracts,
            'ending_contracts': ending_contracts,
            'total_value': total_value,
            'unique_customers': unique_customers
        }
        
        conn.close()
        
        return render_template("registries/contracts.html", contracts=contracts, stats=stats)
        
    except Exception as e:
        print(f"Error loading contracts: {e}")
        return render_template("registries/contracts.html", contracts=[])

# API Blueprint
contract_api = Blueprint('contract_api', __name__, url_prefix='/api/contracts')

@contract_api.route("/save", methods=['POST'])
def save_contract():
    try:
        data = request.get_json()
        
        # Подключение к базе данных
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        # Создание таблицы для договоров если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT,
                date TEXT,
                end_date TEXT,
                customer TEXT,
                contact_person TEXT,
                phone TEXT,
                email TEXT,
                total_lifts INTEGER,
                monthly_cost REAL,
                yearly_cost REAL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавить поле end_date если его нет
        cursor.execute("PRAGMA table_info(contracts)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'end_date' not in columns:
            cursor.execute('ALTER TABLE contracts ADD COLUMN end_date TEXT')
        
        # Создание таблицы для адресов договоров
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contract_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER,
                address TEXT,
                total_area REAL,
                total_cost REAL,
                FOREIGN KEY (contract_id) REFERENCES contracts (id)
            )
        ''')
        
        # Создание таблицы для лифтов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contract_lifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER,
                address_id INTEGER,
                address TEXT,
                floors INTEGER,
                reg_num TEXT,
                area REAL,
                tariff REAL,
                cost REAL,
                FOREIGN KEY (contract_id) REFERENCES contracts (id),
                FOREIGN KEY (address_id) REFERENCES contract_addresses (id)
            )
        ''')
        
        # Вставка основной информации о договоре с очисткой форматирования
        monthly_cost = clean_currency_format(data.get('monthly_cost', 0))
        yearly_cost = monthly_cost * 12
        
        # Вычисляем дату окончания (через год от даты заключения)
        start_date = datetime.strptime(data.get('date'), '%Y-%m-%d')
        end_date = start_date.replace(year=start_date.year + 1)
        
        cursor.execute('''
            INSERT INTO contracts (number, date, end_date, customer, contact_person, phone, email, total_lifts, monthly_cost, yearly_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('number'),
            data.get('date'),
            end_date.strftime('%Y-%m-%d'),
            data.get('customer'),
            data.get('contact_person'),
            data.get('phone'),
            data.get('email'),
            int(data.get('total_lifts', 0)),
            monthly_cost,
            yearly_cost
        ))
        
        contract_id = cursor.lastrowid
        
        # Вставка адресов и лифтов
        for address_data in data.get('addresses', []):
            cursor.execute('''
                INSERT INTO contract_addresses (contract_id, address, total_area, total_cost)
                VALUES (?, ?, ?, ?)
            ''', (
                contract_id,
                address_data.get('address'),
                clean_currency_format(address_data.get('total_area', 0)),
                clean_currency_format(address_data.get('total_cost', 0))
            ))
            
            address_id = cursor.lastrowid
            
            # Вставка лифтов для этого адреса
            for lift_data in address_data.get('lifts', []):
                cursor.execute('''
                    INSERT INTO contract_lifts (contract_id, address_id, address, floors, reg_num, area, tariff, cost)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    contract_id,
                    address_id,
                    lift_data.get('address'),
                    int(lift_data.get('floors', 9)),
                    lift_data.get('reg_num'),
                    clean_currency_format(lift_data.get('area', 0)),
                    clean_currency_format(lift_data.get('tariff', 0)),
                    clean_currency_format(lift_data.get('cost', 0))
                ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'contract_id': contract_id})
        
    except Exception as e:
        print(f"Error saving contract: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@contract_api.route("/<int:contract_id>/lifts/<path:address>")
def get_lifts_for_address(contract_id, address):
    """API endpoint для загрузки лифтов конкретного адреса"""
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        # Найти address_id по адресу и contract_id
        cursor.execute('SELECT id FROM contract_addresses WHERE contract_id = ? AND address = ?', (contract_id, address))
        address_row = cursor.fetchone()
        
        if not address_row:
            return jsonify({'success': False, 'error': 'Address not found'})
        
        address_id = address_row[0]
        
        # Загрузить лифты для этого адреса
        cursor.execute('''
            SELECT id, floors, reg_num, area, tariff, cost
            FROM contract_lifts 
            WHERE address_id = ?
            ORDER BY id
        ''', (address_id,))
        
        lifts_data = cursor.fetchall()
        conn.close()
        
        lifts = []
        for lift in lifts_data:
            lifts.append({
                'id': lift[0],
                'floors': lift[1],
                'reg_num': lift[2],
                'area': lift[3],
                'tariff': lift[4],
                'cost': lift[5],
                'address': address
            })
        
        return jsonify({'success': True, 'lifts': lifts})
        
    except Exception as e:
        print(f"Error loading lifts for address: {e}")
        return jsonify({'success': False, 'error': str(e)})

@contract_api.route("/<int:contract_id>/update", methods=["PUT", "POST"])
def update_contract(contract_id):
    if "user_email" not in session:
        return jsonify({'success': False, 'error': 'Не авторизовано'}), 401
    
    try:
        data = request.get_json()
        print(f"Updating contract {contract_id} with data: {data}")
        
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        # Получаем данные для обновления с очисткой форматирования валюты
        monthly_cost_raw = data.get('monthly_cost', 0)
        if isinstance(monthly_cost_raw, str):
            # Убираем символы валюты и пробелы  
            monthly_cost_raw = monthly_cost_raw.replace('₴', '').replace('грн', '').strip()
        monthly_cost = clean_currency_format(monthly_cost_raw)
        yearly_cost = monthly_cost * 12
        
        # Используем переданную дату окончания, если она есть, иначе оставляем существующую
        end_date_str = data.get('end_date')
        if not end_date_str:
            # Получаем существующую дату окончания из базы данных
            cursor.execute('SELECT end_date FROM contracts WHERE id = ?', (contract_id,))
            existing_contract = cursor.fetchone()
            if existing_contract and existing_contract[0]:
                end_date_str = existing_contract[0]
            elif data.get('date'):
                # Только если нет существующей даты, вычисляем новую
                start_date = datetime.strptime(data.get('date'), '%Y-%m-%d')
                end_date = start_date.replace(year=start_date.year + 1)
                end_date_str = end_date.strftime('%Y-%m-%d')
        
        print(f"End date for contract {contract_id}: {end_date_str}")
        
        # Определяем новый статус на основе даты окончания
        new_status = 'active'
        if end_date_str:
            current_date = datetime.now().date()
            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            days_until_end = (end_date_obj - current_date).days
            
            print(f"Days until end: {days_until_end}")
            
            if days_until_end <= 0:
                new_status = 'active'  # Истекший договор остается активным (автопролонгация)
            elif days_until_end <= 45:  # 1,5 месяца = ~45 дней
                new_status = 'заканчивается'
            else:
                new_status = 'active'
        
        print(f"New status for contract {contract_id}: {new_status}")
        
        # Обновить основные данные договора
        cursor.execute('''
            UPDATE contracts SET
                number = ?, customer = ?, date = ?, end_date = ?, status = ?,
                contact_person = ?, phone = ?, email = ?,
                total_lifts = ?, monthly_cost = ?, yearly_cost = ?
            WHERE id = ?
        ''', (
            data.get('number'),
            data.get('customer'),
            data.get('date'),
            end_date_str,
            new_status,
            data.get('contact_person'),
            data.get('phone'),
            data.get('email'),
            int(data.get('total_lifts', 0)),
            monthly_cost,
            yearly_cost,
            contract_id
        ))
        
        # Обновляем адреса и лифты только если переданы данные адресов (полное редагування)
        if 'addresses' in data and data['addresses'] is not None:
            # Удалить старые адреса и лифты
            cursor.execute('DELETE FROM contract_lifts WHERE contract_id = ?', (contract_id,))
            cursor.execute('DELETE FROM contract_addresses WHERE contract_id = ?', (contract_id,))
            
            # Вставить новые адреса и лифты
            for address_data in data.get('addresses', []):
                cursor.execute('''
                INSERT INTO contract_addresses (contract_id, address, total_area, total_cost)
                VALUES (?, ?, ?, ?)
            ''', (
                contract_id,
                address_data.get('address'),
                clean_currency_format(address_data.get('total_area', 0)),
                clean_currency_format(address_data.get('total_cost', 0))
            ))
            
            address_id = cursor.lastrowid
            
            # Вставить лифты для этого адреса
            for lift_data in address_data.get('lifts', []):
                cursor.execute('''
                    INSERT INTO contract_lifts (contract_id, address_id, address, floors, reg_num, area, tariff, cost)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    contract_id,
                    address_id,
                    lift_data.get('address'),
                    int(lift_data.get('floors', 9)),
                    lift_data.get('reg_num'),
                    clean_currency_format(lift_data.get('area', 0)),
                    clean_currency_format(lift_data.get('tariff', 0)),
                    clean_currency_format(lift_data.get('cost', 0))
                ))
        
        conn.commit()
        conn.close()
        
        print(f"Contract {contract_id} successfully updated with status: {new_status}")
        
        return jsonify({
            'success': True, 
            'contract_id': contract_id,
            'status': new_status,
            'end_date': end_date_str,
            'monthly_cost': monthly_cost
        })
        
    except Exception as e:
        print(f"Error updating contract: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@contract_api.route("/<int:contract_id>/update_status", methods=["POST"])
def update_contract_status(contract_id):
    if "user_email" not in session:
        return jsonify({'success': False, 'error': 'Не авторизовано'}), 401
    
    try:
        data = request.get_json()
        end_date_str = data.get('end_date')
        
        if not end_date_str:
            return jsonify({'success': False, 'error': 'Дата закінчення не вказана'})
        
        # Определяем новый статус на основе даты окончания
        current_date = datetime.now().date()
        end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        days_until_end = (end_date_obj - current_date).days
        
        if days_until_end <= 0:
            new_status = 'active'  # Истекший договор остается активным (автопролонгация)
            # Автопролонгация на год
            new_end_date = end_date_obj.replace(year=end_date_obj.year + 1)
            end_date_str = new_end_date.strftime('%Y-%m-%d')
        elif days_until_end <= 45:  # 1,5 месяца = ~45 дней
            new_status = 'заканчивается'
        else:
            new_status = 'active'
        
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE contracts 
            SET end_date = ?, status = ?
            WHERE id = ?
        ''', (end_date_str, new_status, contract_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'status': new_status, 'end_date': end_date_str})
        
    except Exception as e:
        print(f"Error updating contract status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@contract_api.route("/<int:contract_id>/terminate", methods=["POST"])
def terminate_contract(contract_id):
    if "user_email" not in session:
        return jsonify({'success': False, 'error': 'Не авторизовано'}), 401
    
    try:
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE contracts 
            SET status = 'terminated'
            WHERE id = ?
        ''', (contract_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error terminating contract: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@contract_api.route("/delete", methods=["POST"])
def delete_contracts():
    if "user_email" not in session:
        return jsonify({'success': False, 'error': 'Не авторизовано'}), 401
    
    try:
        data = request.get_json()
        contract_ids = data.get('contract_ids', [])
        
        if not contract_ids:
            return jsonify({'success': False, 'error': 'Не вказано договори для видалення'})
        
        conn = sqlite3.connect(get_company_db_path())
        cursor = conn.cursor()
        
        # Cascading delete: First delete lifts, then addresses, then contracts
        for contract_id in contract_ids:
            # Get all address IDs for this contract
            cursor.execute('SELECT id FROM contract_addresses WHERE contract_id = ?', (contract_id,))
            address_ids = [row[0] for row in cursor.fetchall()]
            
            # Delete lifts for all addresses
            if address_ids:
                addr_placeholders = ','.join('?' * len(address_ids))
                cursor.execute(f'DELETE FROM contract_lifts WHERE address_id IN ({addr_placeholders})', address_ids)
            
            # Delete addresses
            cursor.execute('DELETE FROM contract_addresses WHERE contract_id = ?', (contract_id,))
            
            # Delete contract
            cursor.execute('DELETE FROM contracts WHERE id = ?', (contract_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error deleting contracts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

