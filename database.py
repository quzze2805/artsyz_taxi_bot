import sqlite3
from datetime import datetime

DB_NAME = "taxi.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        driver_id INTEGER,
        status TEXT DEFAULT 'searching',
        from_address TEXT,
        from_lat REAL,
        from_lon REAL,
        to_address TEXT,
        phone TEXT,
        driver_info TEXT,
        discount INTEGER DEFAULT 0,
        created_at TEXT,
        finished_at TEXT,
        rating INTEGER,
        review TEXT
    )
''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS driver_state (
            driver_id INTEGER PRIMARY KEY,
            is_online BOOLEAN DEFAULT 0,
            current_order_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS drivers (
            driver_id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            car_model TEXT,
            car_color TEXT,
            car_plate TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS allowed_drivers (
            driver_id INTEGER PRIMARY KEY
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS loyalty (
            client_id INTEGER PRIMARY KEY,
            rides_count INTEGER DEFAULT 0,
            available_discounts INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER,
            used BOOLEAN DEFAULT 0,
            PRIMARY KEY (referrer_id, referred_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- Заказы ---
def add_order(client_id, from_address, from_lat, from_lon, to_address, phone, discount=0):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''
        INSERT INTO orders (client_id, status, from_address, from_lat, from_lon, to_address, phone, discount, created_at)
        VALUES (?, 'searching', ?, ?, ?, ?, ?, ?, ?)
    ''', (client_id, from_address, from_lat, from_lon, to_address, phone, discount, now))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id

def get_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE id=?', (order_id,))
    order = c.fetchone()
    conn.close()
    return order

def accept_order(order_id, driver_id, driver_info_json):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE orders SET driver_id=?, status="accepted", driver_info=? WHERE id=?',
              (driver_id, driver_info_json, order_id))
    c.execute('UPDATE driver_state SET current_order_id=? WHERE driver_id=?', (order_id, driver_id))
    conn.commit()
    conn.close()

def set_driver_online(driver_id, online=True):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO driver_state (driver_id, is_online, current_order_id) VALUES (?, ?, ?)',
              (driver_id, 1 if online else 0, None))
    conn.commit()
    conn.close()

def get_online_drivers():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT driver_id FROM driver_state WHERE is_online=1')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_driver_current_order(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT current_order_id FROM driver_state WHERE driver_id=?', (driver_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def process_finished_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().isoformat()

    # 1. Завершаем заказ
    c.execute('UPDATE orders SET status="finished", finished_at=? WHERE id=?', (now, order_id))

    # 2. Списываем скидку, если была
    c.execute('SELECT client_id, discount FROM orders WHERE id=?', (order_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    client_id, discount = row
    if discount:
        c.execute('UPDATE loyalty SET available_discounts = available_discounts - 1 WHERE client_id=? AND available_discounts > 0', (client_id,))

    # 3. Освобождаем водителя
    c.execute('UPDATE driver_state SET current_order_id=NULL WHERE current_order_id=?', (order_id,))

    # 4. Лояльность: получаем текущее количество поездок до инкремента
    c.execute('INSERT OR IGNORE INTO loyalty (client_id) VALUES (?)', (client_id,))
    c.execute('SELECT rides_count FROM loyalty WHERE client_id=?', (client_id,))
    row = c.fetchone()
    rides_before = row[0] if row else 0

    # Увеличиваем счётчик
    c.execute('UPDATE loyalty SET rides_count = rides_count + 1 WHERE client_id=?', (client_id,))
    c.execute('SELECT rides_count FROM loyalty WHERE client_id=?', (client_id,))
    new_count = c.fetchone()[0]
    if new_count >= 5:
        c.execute('UPDATE loyalty SET available_discounts = available_discounts + 1, rides_count = 0 WHERE client_id=?', (client_id,))

    # 5. Реферальная программа: если это первая поездка
    if rides_before == 0:
        c.execute('SELECT referrer_id FROM referrals WHERE referred_id=? AND used=0 LIMIT 1', (client_id,))
        ref_row = c.fetchone()
        if ref_row:
            referrer_id = ref_row[0]
            c.execute('UPDATE referrals SET used=1 WHERE referred_id=?', (client_id,))
            c.execute('INSERT OR IGNORE INTO loyalty (client_id) VALUES (?)', (referrer_id,))
            c.execute('UPDATE loyalty SET available_discounts = available_discounts + 1 WHERE client_id=?', (referrer_id,))

    conn.commit()
    conn.close()

def cancel_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE orders SET status="cancelled" WHERE id=?', (order_id,))
    c.execute('UPDATE driver_state SET current_order_id=NULL WHERE current_order_id=?', (order_id,))
    conn.commit()
    conn.close()

def get_client_last_orders(client_id, limit=5):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE client_id=? ORDER BY created_at DESC LIMIT ?', (client_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

# --- Водители ---
def save_driver(driver_id, name=None, phone=None, car_model=None, car_color=None, car_plate=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO drivers (driver_id, name, phone, car_model, car_color, car_plate)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (driver_id, name, phone, car_model, car_color, car_plate))
    conn.commit()
    conn.close()

def get_driver(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT * FROM drivers WHERE driver_id=?', (driver_id,))
    row = c.fetchone()
    conn.close()
    return row

def is_driver_allowed(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT 1 FROM allowed_drivers WHERE driver_id=?', (driver_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def add_allowed_driver(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO allowed_drivers (driver_id) VALUES (?)', (driver_id,))
    conn.commit()
    conn.close()

def remove_allowed_driver(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM allowed_drivers WHERE driver_id=?', (driver_id,))
    c.execute('DELETE FROM drivers WHERE driver_id=?', (driver_id,))
    conn.commit()
    conn.close()

def get_all_drivers():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT * FROM drivers')
    rows = c.fetchall()
    conn.close()
    return rows

def get_allowed_drivers_list():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT driver_id FROM allowed_drivers')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

# --- Лояльность ---
def get_loyalty(client_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO loyalty (client_id) VALUES (?)', (client_id,))
    c.execute('SELECT rides_count, available_discounts FROM loyalty WHERE client_id=?', (client_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row

def increment_rides(client_id):
    """Увеличивает счётчик поездок, при достижении 5 конвертирует в скидку"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE loyalty SET rides_count = rides_count + 1 WHERE client_id=?', (client_id,))
    c.execute('SELECT rides_count FROM loyalty WHERE client_id=?', (client_id,))
    count = c.fetchone()[0]
    if count >= 5:
        c.execute('UPDATE loyalty SET available_discounts = available_discounts + 1, rides_count = 0 WHERE client_id=?', (client_id,))
    conn.commit()
    conn.close()

def use_discount(client_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE loyalty SET available_discounts = available_discounts - 1 WHERE client_id=? AND available_discounts > 0', (client_id,))
    conn.commit()
    conn.close()

# --- Рефералы ---
def save_referral(referrer_id, referred_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, referred_id))
    conn.commit()
    conn.close()

def save_review(order_id, review_text):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE orders SET review=? WHERE id=?', (review_text, order_id))
    conn.commit()
    conn.close()

def complete_referral(referred_id):
    """После первой поездки друга: начисляет скидку пригласившему"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT referrer_id FROM referrals WHERE referred_id=? AND used=0 LIMIT 1', (referred_id,))
    row = c.fetchone()
    if row:
        referrer_id = row[0]
        c.execute('UPDATE referrals SET used=1 WHERE referred_id=?', (referred_id,))
        c.execute('INSERT OR IGNORE INTO loyalty (client_id) VALUES (?)', (referrer_id,))
        c.execute('UPDATE loyalty SET available_discounts = available_discounts + 1 WHERE client_id=?', (referrer_id,))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()

def is_workday_active():
    val = get_setting('workday_active')
    if val is None:
        return True  # по умолчанию включено
    return val == 'True'

def set_workday_active(active: bool):
    set_setting('workday_active', str(active))