import sqlite3
import hashlib
import uuid
import os

def get_db_path():
    if 'RAILWAY_ENVIRONMENT' in os.environ:
        return '/tmp/tambola.db'
    return 'tambola.db'

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  device_id TEXT UNIQUE NOT NULL,
                  ticket_data TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def generate_device_id():
    return str(uuid.uuid4())

def get_or_create_device_id():
    return generate_device_id()