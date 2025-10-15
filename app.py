import os
import sqlite3
import uuid
import random
import json
import qrcode
import io
import base64
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-123')

# Database setup for Render
def get_db_path():
    return '/tmp/tambola.db' if 'RENDER' in os.environ else 'tambola.db'

def init_db():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  device_id TEXT UNIQUE NOT NULL,
                  ticket_data TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Add table for tracking used numbers to prevent duplicates
    c.execute('''CREATE TABLE IF NOT EXISTS used_tickets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ticket_hash TEXT UNIQUE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def generate_tambola_ticket():
    """
    Generate proper Tambola ticket with exactly 15 numbers
    following standard Tambola rules
    """
    # Initialize 3x9 ticket with zeros
    ticket = [[0 for _ in range(9)] for _ in range(3)]
    
    # Define column ranges
    columns = [
        list(range(1, 10)),    # 1-9
        list(range(10, 20)),   # 10-19
        list(range(20, 30)),   # 20-29
        list(range(30, 40)),   # 30-39
        list(range(40, 50)),   # 40-49
        list(range(50, 60)),   # 50-59
        list(range(60, 70)),   # 60-69
        list(range(70, 80)),   # 70-79
        list(range(80, 91))    # 80-90
    ]
    
    # Step 1: Ensure each column has at least one number
    for col in range(9):
        available_numbers = columns[col][:]
        random.shuffle(available_numbers)
        
        # Place one number in a random row
        row = random.randint(0, 2)
        ticket[row][col] = available_numbers[0]
    
    # Step 2: We now have 9 numbers, need 6 more to reach 15
    numbers_to_add = 6
    attempts = 0
    max_attempts = 100
    
    while numbers_to_add > 0 and attempts < max_attempts:
        col = random.randint(0, 8)
        row = random.randint(0, 2)
        
        # Check if this cell is empty and column has less than 3 numbers
        if ticket[row][col] == 0:
            numbers_in_col = sum(1 for r in range(3) if ticket[r][col] != 0)
            if numbers_in_col < 3:
                available_numbers = [n for n in columns[col] if n not in [ticket[r][col] for r in range(3)]]
                if available_numbers:
                    ticket[row][col] = random.choice(available_numbers)
                    numbers_to_add -= 1
        
        attempts += 1
    
    # Step 3: Sort numbers in each column (while maintaining row positions)
    for col in range(9):
        # Get non-zero numbers and their rows
        numbers_with_rows = []
        for row in range(3):
            if ticket[row][col] != 0:
                numbers_with_rows.append((row, ticket[row][col]))
        
        # Sort by number
        numbers_with_rows.sort(key=lambda x: x[1])
        
        # Clear the column
        for row in range(3):
            ticket[row][col] = 0
        
        # Put sorted numbers back in their original rows
        for row, number in numbers_with_rows:
            ticket[row][col] = number
    
    return ticket

def is_ticket_unique(ticket):
    """Check if this ticket is unique by creating a hash"""
    ticket_str = json.dumps(ticket, sort_keys=True)
    ticket_hash = str(hash(ticket_str))
    
    db = get_db()
    result = db.execute('SELECT * FROM used_tickets WHERE ticket_hash = ?', [ticket_hash]).fetchone()
    db.close()
    
    return result is None

def mark_ticket_used(ticket):
    """Mark ticket as used to prevent duplicates"""
    ticket_str = json.dumps(ticket, sort_keys=True)
    ticket_hash = str(hash(ticket_str))
    
    db = get_db()
    try:
        db.execute('INSERT INTO used_tickets (ticket_hash) VALUES (?)', [ticket_hash])
        db.commit()
        db.close()
        return True
    except sqlite3.IntegrityError:
        db.close()
        return False

def generate_unique_ticket():
    """Generate a unique ticket that hasn't been used before"""
    max_attempts = 50
    for _ in range(max_attempts):
        ticket = generate_tambola_ticket()
        if is_ticket_unique(ticket):
            if mark_ticket_used(ticket):
                return ticket
    # If no unique ticket found after max attempts, return any ticket
    return generate_tambola_ticket()

def count_ticket_numbers(ticket):
    """Count total numbers in ticket"""
    return sum(1 for row in ticket for num in row if num != 0)

def generate_qr(url):
    """Generate QR code as base64"""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception as e:
        print(f"QR Generation Error: {e}")
        return None

@app.route('/')
def index():
    if 'device_id' not in session:
        session['device_id'] = str(uuid.uuid4())
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    db.close()
    
    if user:
        return redirect('/ticket')
    
    qr_url = request.url_root + 'register'
    qr_code = generate_qr(qr_url)
    
    return render_template('index.html', qr_code=qr_code, qr_url=qr_url)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'device_id' not in session:
        session['device_id'] = str(uuid.uuid4())
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    
    if user:
        db.close()
        return redirect('/ticket')
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        if name:
            # Generate unique ticket
            ticket = generate_unique_ticket()
            ticket_json = json.dumps(ticket)
            
            try:
                db.execute('INSERT INTO users (name, device_id, ticket_data) VALUES (?, ?, ?)',
                          [name, session['device_id'], ticket_json])
                db.commit()
                db.close()
                return redirect('/ticket')
            except sqlite3.IntegrityError:
                # User already exists, redirect to ticket
                db.close()
                return redirect('/ticket')
        else:
            db.close()
            return render_template('register.html', error='Please enter your name')
    
    db.close()
    return render_template('register.html')  # This renders the registration form

@app.route('/ticket')
def show_ticket():
    if 'device_id' not in session:
        return redirect('/')
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    db.close()
    
    if not user:
        return redirect('/register')
    
    try:
        ticket = json.loads(user['ticket_data'])
        total_numbers = count_ticket_numbers(ticket)
        
        # Debug info
        print(f"Ticket data: {ticket}")
        print(f"Total numbers: {total_numbers}")
        print(f"User name: {user['name']}")
        
        return render_template('ticket.html', 
                             ticket=ticket, 
                             user_name=user['name'], 
                             total_numbers=total_numbers)
    except Exception as e:
        print(f"Error loading ticket: {e}")
        return "Error loading ticket. Please register again."

@app.route('/admin')
def admin():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    total_tickets = db.execute('SELECT COUNT(*) as count FROM used_tickets').fetchone()['count']
    db.close()
    
    user_list = []
    for user in users:
        try:
            ticket_data = json.loads(user['ticket_data'])
            user_list.append({
                'name': user['name'],
                'ticket': ticket_data,
                'created_at': user['created_at'],
                'numbers_count': count_ticket_numbers(ticket_data)
            })
        except:
            continue
    
    return render_template('admin.html', users=user_list, total_tickets=total_tickets)

@app.route('/stats')
def stats():
    db = get_db()
    total_users = db.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    total_unique_tickets = db.execute('SELECT COUNT(*) as count FROM used_tickets').fetchone()['count']
    db.close()
    
    return {
        'total_users': total_users,
        'unique_tickets_generated': total_unique_tickets
    }

@app.route('/health')
def health():
    return 'OK'

# Initialize database
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
