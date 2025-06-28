CREATE TABLE requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            district TEXT,
            address TEXT,
            entrance TEXT,
            issue TEXT,
            phone TEXT,
            timestamp TEXT,
            completed BOOLEAN,
            completed_time TEXT,
            processed_by TEXT,
            status TEXT,
            chat_msg_id INTEGER
        );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE contracts (
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
            );
CREATE TABLE contract_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER,
                address TEXT,
                total_area REAL,
                total_cost REAL,
                FOREIGN KEY (contract_id) REFERENCES contracts (id)
            );
CREATE TABLE contract_lifts (
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
            );
