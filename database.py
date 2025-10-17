import sqlite3
import hashlib
import uuid
import os

def get_db_path():
    if 'RAILWAY_ENVIRONMENT' in os.environ:
        return '/tmp/tambola.db'
    return 'tambola.db'

def init_db():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  device_id TEXT UNIQUE NOT NULL,
                  ticket_code TEXT UNIQUE NOT NULL,
                  ticket_data TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS used_tickets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ticket_hash TEXT UNIQUE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Add prizes table - FIXED: Check if table exists first
    c.execute('''CREATE TABLE IF NOT EXISTS prizes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  ticket_code TEXT,
                  prize_type TEXT NOT NULL,
                  claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    conn.commit()
    conn.close()
    
    # Initialize prizes table with some data if empty
    initialize_prizes_table()

def get_db_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def generate_device_id():
    return str(uuid.uuid4())

def get_or_create_device_id():
    return generate_device_id()
