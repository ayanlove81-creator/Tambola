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
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def generate_proper_tambola_ticket():
    """
    Generate a proper Tambola ticket with:
    - 3 rows, 9 columns
    - Exactly 15 numbers total (5 per row)
    - Numbers arranged in ascending order per column
    - Each column has 1-3 numbers
    """
    ticket = [[0]*9 for _ in range(3)]  # 3x9 grid filled with zeros
    
    # Define number ranges for each column
    column_ranges = [
        (1, 9),    # col 0: 1-9
        (10, 19),  # col 1: 10-19
        (20, 29),  # col 2: 20-29
        (30, 39),  # col 3: 30-39
        (40, 49),  # col 4: 40-49
        (50, 59),  # col 5: 50-59
        (60, 69),  # col 6: 60-69
        (70, 79),  # col 7: 70-79
        (80, 90)   # col 8: 80-90
    ]
    
    # Step 1: Ensure each column has at least 1 number
    for col in range(9):
        start, end = column_ranges[col]
        available_numbers = list(range(start, end + 1))
        random.shuffle(available_numbers)
        
        # Place 1 number in a random row for this column
        row = random.randint(0, 2)
        ticket[row][col] = available_numbers.pop()
    
    # Step 2: Add remaining numbers to reach 15 total (we have 9 now, need 6 more)
    numbers_added = 0
    while numbers_added < 6:
        col = random.randint(0, 8)
        start, end = column_ranges[col]
        
        # Count how many numbers are already in this column
        numbers_in_col = sum(1 for row in range(3) if ticket[row][col] != 0)
        
        # Add number only if column has less than 3 numbers and we can find an available number
        if numbers_in_col < 3:
            available_numbers = list(range(start, end + 1))
            existing_numbers = [ticket[row][col] for row in range(3) if ticket[row][col] != 0]
            possible_numbers = [n for n in available_numbers if n not in existing_numbers]
            
            if possible_numbers:
                # Find an empty row in this column
                empty_rows = [row for row in range(3) if ticket[row][col] == 0]
                if empty_rows:
                    row = random.choice(empty_rows)
                    ticket[row][col] = random.choice(possible_numbers)
                    numbers_added += 1
    
    # Step 3: Sort numbers in each column in ascending order
    for col in range(9):
        column_numbers = [(row, ticket[row][col]) for row in range(3) if ticket[row][col] != 0]
        column_numbers.sort(key=lambda x: x[1])
        
        # Put sorted numbers back in the same rows they came from
        rows_with_numbers = [row for row, _ in column_numbers]
        for idx, (original_row, number) in enumerate(column_numbers):
            ticket[original_row][col] = number
    
    return ticket

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
    except:
        # Fallback if QR generation fails
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
            ticket = generate_proper_tambola_ticket()
            try:
                db.execute('INSERT INTO users (name, device_id, ticket_data) VALUES (?, ?, ?)',
                          [name, session['device_id'], json.dumps(ticket)])
                db.commit()
                db.close()
                return redirect('/ticket')
            except sqlite3.IntegrityError:
                db.close()
                return redirect('/ticket')
    
    db.close()
    return render_template('register.html')

@app.route('/ticket')
def show_ticket():
    if 'device_id' not in session:
        return redirect('/')
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    db.close()
    
    if not user:
        return redirect('/register')
    
    ticket = json.loads(user['ticket_data'])
    
    # Count total numbers to verify it's 15
    total_numbers = sum(1 for row in ticket for num in row if num != 0)
    
    return render_template('ticket.html', ticket=ticket, user_name=user['name'], total_numbers=total_numbers)

@app.route('/admin')
def admin():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    
    user_list = []
    for user in users:
        user_list.append({
            'name': user['name'],
            'ticket': json.loads(user['ticket_data']),
            'created_at': user['created_at']
        })
    
    return render_template('admin.html', users=user_list)

@app.route('/health')
def health():
    return 'OK'

# Initialize database
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
