import sqlite3
from datetime import datetime

DB_NAME = "taxi.db"
CLIENTS_DB = "clients.db"

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
            current_order_id INTEGER,
            queued_order_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS planned_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            from_address TEXT,
            from_lat REAL,
            from_lon REAL,
            to_address TEXT,
            to_lat REAL,
            to_lon REAL,
            phone TEXT,
            planned_time TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            reminded INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # Добавляем новые столбцы, если их нет
    try:
        c.execute('ALTER TABLE orders ADD COLUMN is_planned INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE orders ADD COLUMN planned_time TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE orders ADD COLUMN reminded INTEGER DEFAULT 0')
    except:
        pass
    conn.commit()
    conn.close()

    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            phone TEXT PRIMARY KEY,
            telegram_id INTEGER,
            name TEXT,
            total_rides INTEGER DEFAULT 0,
            total_discounts_used INTEGER DEFAULT 0,
            first_ride_at TEXT,
            last_ride_at TEXT
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
        CREATE TABLE IF NOT EXISTS blacklist (
            phone TEXT PRIMARY KEY,
            reason TEXT,
            blocked_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS start_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            first_seen TEXT
        )
    ''')
    conn.commit()
    conn.close()

def update_client(telegram_id, phone, name=None):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('SELECT phone FROM clients WHERE phone=?', (phone,))
    row = c.fetchone()
    if row:
        c.execute('UPDATE clients SET telegram_id=?, name=COALESCE(?, name), last_ride_at=? WHERE phone=?',
                  (telegram_id, name, now, phone))
    else:
        c.execute('INSERT INTO clients (phone, telegram_id, name, total_rides, first_ride_at, last_ride_at) VALUES (?, ?, ?, 0, ?, ?)',
                  (phone, telegram_id, name, now, now))
    conn.commit()
    conn.close()

def increment_client_rides(phone):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('UPDATE clients SET total_rides = total_rides + 1, last_ride_at=? WHERE phone=?', (now, phone))
    conn.commit()
    conn.close()

def get_client_info(phone):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM clients WHERE phone=?', (phone,))
    row = c.fetchone()
    conn.close()
    return row

def add_order(client_id, from_address, from_lat, from_lon, to_address, phone, discount=0, is_planned=0, planned_time=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''
        INSERT INTO orders (client_id, status, from_address, from_lat, from_lon, to_address, phone, discount, is_planned, planned_time, created_at)
        VALUES (?, 'searching', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (client_id, from_address, from_lat, from_lon, to_address, phone, discount, is_planned, planned_time, now))
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
    c.execute('INSERT OR IGNORE INTO driver_state (driver_id, is_online) VALUES (?, 1)', (driver_id,))
    c.execute('UPDATE orders SET driver_id=?, status="accepted", driver_info=? WHERE id=?',
              (driver_id, driver_info_json, order_id))
    c.execute('UPDATE driver_state SET current_order_id=? WHERE driver_id=?', (order_id, driver_id))
    conn.commit()
    conn.close()

def queue_order(order_id, driver_id, driver_info_json):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO driver_state (driver_id, is_online) VALUES (?, 1)', (driver_id,))
    c.execute('UPDATE orders SET driver_id=?, status="queued", driver_info=? WHERE id=?',
              (driver_id, driver_info_json, order_id))
    c.execute('UPDATE driver_state SET queued_order_id=? WHERE driver_id=?', (order_id, driver_id))
    conn.commit()
    conn.close()

def activate_queued_order(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT queued_order_id FROM driver_state WHERE driver_id=?', (driver_id,))
    row = c.fetchone()
    if row and row[0]:
        queued_id = row[0]
        c.execute('UPDATE orders SET status="accepted" WHERE id=?', (queued_id,))
        c.execute('UPDATE driver_state SET current_order_id=?, queued_order_id=NULL WHERE driver_id=?',
                  (queued_id, driver_id))
        conn.commit()
        conn.close()
        return queued_id
    conn.close()
    return None

def cancel_queued_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE orders SET status="cancelled" WHERE id=?', (order_id,))
    c.execute('UPDATE driver_state SET queued_order_id=NULL WHERE queued_order_id=?', (order_id,))
    conn.commit()
    conn.close()

def set_driver_online(driver_id, online=True):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO driver_state (driver_id, is_online, current_order_id, queued_order_id) VALUES (?, ?, ?, ?)',
              (driver_id, 1 if online else 0, None, None))
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

def get_driver_queued_order(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT queued_order_id FROM driver_state WHERE driver_id=?', (driver_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

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

def process_finished_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('UPDATE orders SET status="finished", finished_at=? WHERE id=?', (now, order_id))
    c.execute('SELECT client_id, phone, discount FROM orders WHERE id=?', (order_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    client_id, phone, discount = row

    conn2 = sqlite3.connect(CLIENTS_DB)
    c2 = conn2.cursor()
    if discount:
        c2.execute('UPDATE loyalty SET available_discounts = available_discounts - 1 WHERE client_id=? AND available_discounts > 0', (client_id,))

    c.execute('UPDATE driver_state SET current_order_id=NULL WHERE current_order_id=?', (order_id,))
    conn.commit()
    conn.close()

    c2.execute('INSERT OR IGNORE INTO loyalty (client_id) VALUES (?)', (client_id,))
    c2.execute('SELECT rides_count FROM loyalty WHERE client_id=?', (client_id,))
    row2 = c2.fetchone()
    rides_before = row2[0] if row2 else 0
    c2.execute('UPDATE loyalty SET rides_count = rides_count + 1 WHERE client_id=?', (client_id,))
    c2.execute('SELECT rides_count FROM loyalty WHERE client_id=?', (client_id,))
    new_count = c2.fetchone()[0]
    if new_count >= 5:
        c2.execute('UPDATE loyalty SET available_discounts = available_discounts + 1, rides_count = 0 WHERE client_id=?', (client_id,))

    if rides_before == 0:
        c2.execute('SELECT referrer_id FROM referrals WHERE referred_id=? AND used=0 LIMIT 1', (client_id,))
        ref_row = c2.fetchone()
        if ref_row:
            referrer_id = ref_row[0]
            c2.execute('UPDATE referrals SET used=1 WHERE referred_id=?', (client_id,))
            c2.execute('INSERT OR IGNORE INTO loyalty (client_id) VALUES (?)', (referrer_id,))
            c2.execute('UPDATE loyalty SET available_discounts = available_discounts + 1 WHERE client_id=?', (referrer_id,))
    conn2.commit()
    conn2.close()

    if phone:
        increment_client_rides(phone)

def add_planned_order(client_id, from_address, from_lat, from_lon, to_address, to_lat, to_lon, phone, planned_time):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''
        INSERT INTO planned_orders (client_id, from_address, from_lat, from_lon, to_address, to_lat, to_lon, phone, planned_time, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (client_id, from_address, from_lat, from_lon, to_address, to_lat, to_lon, phone, planned_time, now))
    conn.commit()
    conn.close()

def get_planned_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT * FROM planned_orders WHERE id=?', (order_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_client_planned_orders(client_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT id, planned_time, from_address, to_address, status FROM planned_orders WHERE client_id=? AND status="pending" ORDER BY planned_time', (client_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def cancel_planned_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE planned_orders SET status="cancelled" WHERE id=?', (order_id,))
    conn.commit()
    conn.close()

def get_due_reminders(now_iso):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT * FROM planned_orders
                 WHERE status='pending' AND reminded=0 AND planned_time <= ?''',
              (now_iso,))
    rows = c.fetchall()
    conn.close()
    return rows

def set_planned_reminded(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE planned_orders SET reminded=1 WHERE id=?', (order_id,))
    conn.commit()
    conn.close()

def activate_planned_order(order_id):
    plan = get_planned_order(order_id)
    if not plan or plan[9] != 'pending':
        return None
    new_order_id = add_order(plan[1], plan[2], plan[3], plan[4], plan[5], plan[7])
    cancel_planned_order(order_id)
    return new_order_id

def get_planned_orders_to_remind():
    from datetime import datetime, timedelta
    now = datetime.now()
    one_hour_later = now + timedelta(hours=1)
    now_iso = now.isoformat()
    later_iso = one_hour_later.isoformat()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT id, client_id, driver_id, planned_time FROM orders
                 WHERE is_planned=1 AND status='accepted' AND reminded=0
                 AND planned_time BETWEEN ? AND ?''', (now_iso, later_iso))
    rows = c.fetchall()
    conn.close()
    return rows

def set_planned_reminded_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE orders SET reminded=1 WHERE id=?', (order_id,))
    conn.commit()
    conn.close()

def save_driver(driver_id, name=None, phone=None, car_model=None, car_color=None, car_plate=None):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO drivers (driver_id, name, phone, car_model, car_color, car_plate)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (driver_id, name, phone, car_model, car_color, car_plate))
    conn.commit()
    conn.close()

def get_driver(driver_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM drivers WHERE driver_id=?', (driver_id,))
    row = c.fetchone()
    conn.close()
    return row

def is_driver_allowed(driver_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT 1 FROM allowed_drivers WHERE driver_id=?', (driver_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def add_allowed_driver(driver_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO allowed_drivers (driver_id) VALUES (?)', (driver_id,))
    conn.commit()
    conn.close()

def remove_allowed_driver(driver_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('DELETE FROM allowed_drivers WHERE driver_id=?', (driver_id,))
    c.execute('DELETE FROM drivers WHERE driver_id=?', (driver_id,))
    conn.commit()
    conn.close()

def get_all_drivers():
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT * FROM drivers')
    rows = c.fetchall()
    conn.close()
    return rows

def get_allowed_drivers_list():
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT driver_id FROM allowed_drivers')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_loyalty(client_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO loyalty (client_id) VALUES (?)', (client_id,))
    c.execute('SELECT rides_count, available_discounts FROM loyalty WHERE client_id=?', (client_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row

def use_discount(client_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('UPDATE loyalty SET available_discounts = available_discounts - 1 WHERE client_id=? AND available_discounts > 0', (client_id,))
    conn.commit()
    conn.close()

def save_referral(referrer_id, referred_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, referred_id))
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
        return True
    return val == 'True'

def set_workday_active(active: bool):
    set_setting('workday_active', str(active))

def save_review(order_id, review_text):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE orders SET review=? WHERE id=?', (review_text, order_id))
    conn.commit()
    conn.close()

def block_client(phone, reason=""):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('INSERT OR REPLACE INTO blacklist (phone, reason, blocked_at) VALUES (?, ?, ?)',
              (phone, reason, now))
    conn.commit()
    conn.close()

def unblock_client(phone):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('DELETE FROM blacklist WHERE phone=?', (phone,))
    conn.commit()
    conn.close()

def is_blocked(phone):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT reason FROM blacklist WHERE phone=?', (phone,))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_block_reason(phone):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT reason FROM blacklist WHERE phone=?', (phone,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def log_start(telegram_id):
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('INSERT OR IGNORE INTO start_stats (telegram_id, first_seen) VALUES (?, ?)',
              (telegram_id, now))
    conn.commit()
    conn.close()

def get_start_count():
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM start_stats')
    count = c.fetchone()[0]
    conn.close()
    return count

def get_all_started_users():
    conn = sqlite3.connect(CLIENTS_DB)
    c = conn.cursor()
    c.execute('SELECT telegram_id FROM start_stats')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_driver_stats(driver_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT COUNT(*), AVG(rating) FROM orders WHERE driver_id=? AND status="finished"', (driver_id,))
    finished, avg_rating = c.fetchone()
    c.execute('SELECT COUNT(*) FROM orders WHERE driver_id=? AND status="cancelled"', (driver_id,))
    cancelled = c.fetchone()[0]
    conn.close()
    return {
        'finished': finished or 0,
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        'cancelled': cancelled or 0
    }

def get_all_drivers_stats():
    conn_clients = sqlite3.connect(CLIENTS_DB)
    c_clients = conn_clients.cursor()
    c_clients.execute('SELECT driver_id, name FROM drivers')
    drivers = c_clients.fetchall()
    conn_clients.close()

    conn_orders = sqlite3.connect(DB_NAME)
    c_orders = conn_orders.cursor()
    result = []
    for driver_id, name in drivers:
        c_orders.execute('''SELECT COUNT(*), AVG(rating) FROM orders
                           WHERE driver_id=? AND status='finished' ''',
                        (driver_id,))
        total, avg_r = c_orders.fetchone()
        result.append({
            'driver_id': driver_id,
            'name': name,
            'total': total or 0,
            'avg_rating': round(avg_r, 1) if avg_r else 0
        })
    conn_orders.close()
    return result