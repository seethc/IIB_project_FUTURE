import sqlite3
import os

DB_PATH = 'devices.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            secret_key TEXT NOT NULL,
            sync_time INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def get_all_devices():
    conn = get_db_connection()
    devices = conn.execute('SELECT * FROM devices').fetchall()
    conn.close()
    return [dict(ix) for ix in devices]

def get_device(device_id):
    conn = get_db_connection()
    device = conn.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    conn.close()
    return dict(device) if device else None

def add_device(name, secret_key, sync_time):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO devices (name, secret_key, sync_time) VALUES (?, ?, ?)',
                   (name, secret_key, sync_time))
    conn.commit()
    device_id = cursor.lastrowid
    conn.close()
    return device_id

def delete_device(device_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM devices WHERE id = ?', (device_id,))
    conn.commit()
    conn.close()
