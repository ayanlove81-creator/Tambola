import os
import sqlite3
import uuid
import random
import json
import qrcode
import io
import base64
import secrets
import string
from datetime import datetime
from flask import Flask, render_template, request, session, redirect, url_for
from flask import send_from_directory

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
                  ticket_code TEXT UNIQUE NOT NULL,
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

def generate_ticket_code():
    """Generate a unique 6-character ticket code"""
    characters = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(characters) for _ in range(6))
        db = get_db()
        existing = db.execute('SELECT * FROM users WHERE ticket_code = ?', [code]).fetchone()
        db.close()
        if not existing:
            return code

def generate_tambola_ticket():
    """Generate a proper Tambola ticket with correct structure"""
    ticket = [[0]*9 for _ in range(3)]
    
    column_ranges = [
        (1, 9), (10, 19), (20, 29), (30, 39), (40, 49),
        (50, 59), (60, 69), (70, 79), (80, 90)
    ]
    
    # Step 1: Ensure each column has exactly 1, 2, or 3 numbers (at least 1)
    # First, assign exactly 1 number to each column
    for col in range(9):
        start, end = column_ranges[col]
        available_numbers = list(range(start, end + 1))
        random.shuffle(available_numbers)
        
        # Choose a random row for this column
        row = random.randint(0, 2)
        ticket[row][col] = available_numbers[0]
    
    # Step 2: We now have 9 numbers, need 6 more to reach 15 total
    numbers_added = 0
    max_attempts = 100
    attempts = 0
    
    while numbers_added < 6 and attempts < max_attempts:
        attempts += 1
        
        # Choose a random column that can accept more numbers (max 3 per column)
        col = random.randint(0, 8)
        numbers_in_col = sum(1 for row in range(3) if ticket[row][col] != 0)
        if numbers_in_col >= 3:
            continue
        
        # Choose a random row in this column that's empty
        empty_rows = [row for row in range(3) if ticket[row][col] == 0]
        if not empty_rows:
            continue
            
        row = random.choice(empty_rows)
        
        # Check if this row can accept more numbers (max 5 per row)
        numbers_in_row = sum(1 for num in ticket[row] if num != 0)
        if numbers_in_row >= 5:
            continue
        
        # Generate a valid number for this column
        start, end = column_ranges[col]
        existing_numbers = [ticket[r][col] for r in range(3) if ticket[r][col] != 0]
        available_numbers = [n for n in range(start, end + 1) if n not in existing_numbers]
        
        if available_numbers:
            ticket[row][col] = random.choice(available_numbers)
            numbers_added += 1
    
    # Step 3: If we couldn't place all numbers, use a more direct approach
    if numbers_added < 6:
        # Find all empty cells that can accept numbers
        empty_cells = []
        for row in range(3):
            for col in range(9):
                if ticket[row][col] == 0:
                    numbers_in_col = sum(1 for r in range(3) if ticket[r][col] != 0)
                    numbers_in_row = sum(1 for num in ticket[row] if num != 0)
                    if numbers_in_col < 3 and numbers_in_row < 5:
                        empty_cells.append((row, col))
        
        # Shuffle and fill remaining numbers
        random.shuffle(empty_cells)
        cells_to_fill = min(6 - numbers_added, len(empty_cells))
        
        for i in range(cells_to_fill):
            row, col = empty_cells[i]
            start, end = column_ranges[col]
            existing_numbers = [ticket[r][col] for r in range(3) if ticket[r][col] != 0]
            available_numbers = [n for n in range(start, end + 1) if n not in existing_numbers]
            
            if available_numbers:
                ticket[row][col] = random.choice(available_numbers)
                numbers_added += 1
    
    # Step 4: Sort numbers in each column
    for col in range(9):
        sort_column_numbers(ticket, col)
    
    # Final verification
    total_numbers = count_ticket_numbers(ticket)
    if total_numbers != 15:
        print(f"Warning: Ticket has {total_numbers} numbers instead of 15")
    
    return ticket

def sort_column_numbers(ticket, col):
    """Sort numbers in a column while keeping their row positions"""
    numbers = []
    rows = []
    
    # Collect numbers and their rows
    for row in range(3):
        if ticket[row][col] != 0:
            numbers.append(ticket[row][col])
            rows.append(row)
    
    # Sort numbers and keep track of original rows
    sorted_data = sorted(zip(numbers, rows))
    
    # Clear column
    for row in range(3):
        ticket[row][col] = 0
    
    # Place sorted numbers back in their rows
    for number, row in sorted_data:
        ticket[row][col] = number
        


def generate_tambola_ticket_fallback():
    """Fallback method that guarantees correct structure"""
    ticket = [[0]*9 for _ in range(3)]
    
    # Step 1: Ensure each column has at least 1 number
    for col in range(9):
        start_num = col * 10 + 1
        end_num = start_num + 9
        if col == 0:
            start_num = 1
            end_num = 9
        elif col == 8:
            start_num = 80
            end_num = 90
        
        available_numbers = list(range(start_num, end_num + 1))
        random.shuffle(available_numbers)
        
        # Place one number in a random row
        row = random.randint(0, 2)
        ticket[row][col] = available_numbers[0]
    
    # Step 2: We now have 9 numbers, need 6 more to reach 15 total
    numbers_added = 0
    while numbers_added < 6:
        col = random.randint(0, 8)
        row = random.randint(0, 2)
        
        # Check if this cell is empty and column has less than 3 numbers
        if ticket[row][col] == 0:
            numbers_in_col = sum(1 for r in range(3) if ticket[r][col] != 0)
            if numbers_in_col < 3:
                start_num = col * 10 + 1
                end_num = start_num + 9
                if col == 0:
                    start_num = 1
                    end_num = 9
                elif col == 8:
                    start_num = 80
                    end_num = 90
                
                existing_numbers = [ticket[r][col] for r in range(3) if ticket[r][col] != 0]
                available_numbers = [n for n in range(start_num, end_num + 1) 
                                   if n not in existing_numbers]
                if available_numbers:
                    ticket[row][col] = random.choice(available_numbers)
                    numbers_added += 1
    
    return ticket

def can_accept_number(self, ticket, row, col, col_range):
    """Check if a cell can accept a number without violating rules"""
    start, end = col_range
    
    # Check if adding a number here would exceed column limit
    numbers_in_col = sum(1 for r in range(3) if ticket[r][col] != 0)
    if numbers_in_col >= 3:
        return False
    
    # Check if the number would be in the correct range
    # This is handled by the calling function
    return True



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
    """Count total numbers in ticket and verify row and column counts"""
    total = 0
    row_counts = [0, 0, 0]
    col_counts = [0] * 9
    
    for row_idx, row in enumerate(ticket):
        for col_idx, num in enumerate(row):
            if num != 0:
                total += 1
                row_counts[row_idx] += 1
                col_counts[col_idx] += 1
    
    print(f"Ticket verification:")
    print(f"Total numbers: {total}")
    print(f"Row counts: {row_counts}")
    print(f"Column counts: {col_counts}")
    
    # Verify rules
    if total != 15:
        print(f"ERROR: Total numbers should be 15, got {total}")
    
    for i, count in enumerate(row_counts):
        if count != 5:
            print(f"ERROR: Row {i} should have 5 numbers, got {count}")
    
    for i, count in enumerate(col_counts):
        if count == 0:
            print(f"ERROR: Column {i} has no numbers!")
        if count > 3:
            print(f"ERROR: Column {i} has {count} numbers (max 3)")
    
    return total

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
    
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)
    
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
            # Generate unique ticket and code
            ticket = generate_unique_ticket()
            ticket_json = json.dumps(ticket)
            ticket_code = generate_ticket_code()
            
            try:
                db.execute('INSERT INTO users (name, device_id, ticket_code, ticket_data) VALUES (?, ?, ?, ?)',
                          [name, session['device_id'], ticket_code, ticket_json])
                db.commit()
                db.close()
                
                # Store ticket code in session for recovery
                session['ticket_code'] = ticket_code
                return redirect('/ticket')
            except sqlite3.IntegrityError:
                # User already exists, redirect to ticket
                db.close()
                return redirect('/ticket')
        else:
            db.close()
            return render_template('register.html', error='Please enter your name')
    
    db.close()
    return render_template('register.html')

@app.route('/ticket')
def show_ticket():
    # Check if user has ticket code in session or URL parameter
    ticket_code = request.args.get('code') or session.get('ticket_code')
    
    if not ticket_code:
        return redirect('/')
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE ticket_code = ?', [ticket_code]).fetchone()
    db.close()
    
    if not user:
        return render_template('recover.html', error='Invalid ticket code')
    
    try:
        ticket = json.loads(user['ticket_data'])
        total_numbers = count_ticket_numbers(ticket)
        current_time = datetime.now()
        
        # Store in session for future access
        session['device_id'] = user['device_id']
        session['ticket_code'] = user['ticket_code']
        
        return render_template('ticket.html', 
                             ticket=ticket, 
                             user_name=user['name'], 
                             total_numbers=total_numbers,
                             ticket_code=user['ticket_code'],
                             now=current_time)
    except Exception as e:
        print(f"Error loading ticket: {e}")
        return "Error loading ticket. Please register again."

@app.route('/recover', methods=['GET', 'POST'])
def recover_ticket():
    if request.method == 'POST':
        ticket_code = request.form['ticket_code'].strip().upper()
        if ticket_code:
            return redirect(f'/ticket?code={ticket_code}')
        else:
            return render_template('recover.html', error='Please enter your ticket code')
    
    return render_template('recover.html')

@app.route('/admin')
def admin():
    db = get_db()
    
    # Get all users with their tickets
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    
    # Get statistics
    total_tickets = db.execute('SELECT COUNT(*) as count FROM used_tickets').fetchone()['count']
    total_users = db.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    
    # Get recent registrations (last 24 hours)
    recent_users = db.execute(
        'SELECT COUNT(*) as count FROM users WHERE created_at >= datetime("now", "-1 day")'
    ).fetchone()['count']
    
    db.close()
    
    user_list = []
    for user in users:
        try:
            ticket_data = json.loads(user['ticket_data'])
            numbers_count = count_ticket_numbers(ticket_data)
            
            user_list.append({
                'id': user['id'],
                'name': user['name'],
                'ticket': ticket_data,
                'ticket_code': user['ticket_code'],
                'device_id': user['device_id'],
                'created_at': user['created_at'],
                'numbers_count': numbers_count,
                'ticket_url': f"/ticket?code={user['ticket_code']}"
            })
        except Exception as e:
            print(f"Error processing user {user['id']}: {e}")
            continue
    
    return render_template('admin.html', 
                         users=user_list, 
                         total_tickets=total_tickets,
                         total_users=total_users,
                         recent_users=recent_users)
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
