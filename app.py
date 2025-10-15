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
    """
    Generate proper Tambola ticket with exactly 15 numbers
    - 3 rows, 9 columns
    - Exactly 5 numbers per row (15 total)
    - Numbers arranged in ascending order per column
    - Each column has 1-3 numbers
    """
    # Initialize 3x9 ticket with zeros
    ticket = [[0 for _ in range(9)] for _ in range(3)]
    
    # Define column ranges
    column_ranges = [
        (1, 9),     # Column 0: 1-9
        (10, 19),   # Column 1: 10-19
        (20, 29),   # Column 2: 20-29
        (30, 39),   # Column 3: 30-39
        (40, 49),   # Column 4: 40-49
        (50, 59),   # Column 5: 50-59
        (60, 69),   # Column 6: 60-69
        (70, 79),   # Column 7: 70-79
        (80, 90)    # Column 8: 80-90
    ]
    
    # Step 1: Ensure each column has exactly 1, 2, or 3 numbers
    # We need exactly 15 numbers distributed across 9 columns
    # This means: 3 columns with 2 numbers, 6 columns with 1 number
    column_counts = [2, 2, 2, 1, 1, 1, 1, 1, 1]  # Total: 2*3 + 1*6 = 6 + 9 = 15
    random.shuffle(column_counts)
    
    # Fill each column with required number of numbers
    for col in range(9):
        start, end = column_ranges[col]
        numbers_needed = column_counts[col]
        
        # Get available numbers for this column
        available_numbers = list(range(start, end + 1))
        random.shuffle(available_numbers)
        
        # Select required numbers
        selected_numbers = available_numbers[:numbers_needed]
        
        # Choose random rows for these numbers
        available_rows = list(range(3))
        random.shuffle(available_rows)
        selected_rows = available_rows[:numbers_needed]
        
        # Place numbers in selected rows
        for i, row in enumerate(selected_rows):
            ticket[row][col] = selected_numbers[i]
    
    # Step 2: Verify and fix row counts to ensure exactly 5 numbers per row
    row_counts = [sum(1 for num in row if num != 0) for row in ticket]
    
    # Fix rows that don't have exactly 5 numbers
    max_attempts = 100
    for attempt in range(max_attempts):
        # Check if all rows have exactly 5 numbers
        if all(count == 5 for count in row_counts):
            break
            
        # Find rows with too many or too few numbers
        for row_idx in range(3):
            current_count = row_counts[row_idx]
            
            if current_count > 5:
                # This row has too many numbers, move one to a row with fewer numbers
                # Find columns in this row that have numbers
                cols_with_numbers = [col for col in range(9) if ticket[row_idx][col] != 0]
                random.shuffle(cols_with_numbers)
                
                for col in cols_with_numbers:
                    # Find a row that needs more numbers and can accept this number
                    for target_row in range(3):
                        if (row_counts[target_row] < 5 and 
                            ticket[target_row][col] == 0 and 
                            self.can_accept_number(ticket, target_row, col, column_ranges[col])):
                            
                            # Move the number
                            ticket[target_row][col] = ticket[row_idx][col]
                            ticket[row_idx][col] = 0
                            row_counts[row_idx] -= 1
                            row_counts[target_row] += 1
                            break
                    
                    if row_counts[row_idx] == 5:
                        break
                        
            elif current_count < 5:
                # This row needs more numbers
                needed = 5 - current_count
                empty_cols = [col for col in range(9) if ticket[row_idx][col] == 0]
                random.shuffle(empty_cols)
                
                for col in empty_cols:
                    if needed <= 0:
                        break
                        
                    # Check if we can add a number to this column
                    numbers_in_col = sum(1 for r in range(3) if ticket[r][col] != 0)
                    if numbers_in_col < 3 and self.can_accept_number(ticket, row_idx, col, column_ranges[col]):
                        # Find an available number for this column
                        start, end = column_ranges[col]
                        existing_numbers = [ticket[r][col] for r in range(3) if ticket[r][col] != 0]
                        available_numbers = [n for n in range(start, end + 1) if n not in existing_numbers]
                        
                        if available_numbers:
                            ticket[row_idx][col] = random.choice(available_numbers)
                            row_counts[row_idx] += 1
                            needed -= 1
    
    # Step 3: Sort numbers in each column in ascending order
    for col in range(9):
        # Get numbers and their rows
        numbers_with_rows = []
        for row in range(3):
            if ticket[row][col] != 0:
                numbers_with_rows.append((row, ticket[row][col]))
        
        # Sort by number
        numbers_with_rows.sort(key=lambda x: x[1])
        
        # Clear the column
        for row in range(3):
            ticket[row][col] = 0
        
        # Put sorted numbers back
        for row, number in numbers_with_rows:
            ticket[row][col] = number
    
    # Final verification
    total_numbers = sum(1 for row in ticket for num in row if num != 0)
    row_counts_final = [sum(1 for num in row if num != 0) for row in ticket]
    
    if total_numbers != 15 or not all(count == 5 for count in row_counts_final):
        # If still not correct, use fallback method
        return generate_tambola_ticket_fallback()
    
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

def generate_tambola_ticket_fallback():
    """Fallback method that guarantees 5 numbers per row"""
    ticket = [[0 for _ in range(9)] for _ in range(3)]
    
    column_ranges = [
        (1, 9), (10, 19), (20, 29), (30, 39), (40, 49),
        (50, 59), (60, 69), (70, 79), (80, 90)
    ]
    
    # Step 1: Assign exactly 5 positions per row
    for row in range(3):
        # Choose 5 random columns for this row
        positions = random.sample(range(9), 5)
        for col in positions:
            ticket[row][col] = -1  # Mark for number assignment
    
    # Step 2: Assign numbers to marked positions
    for col in range(9):
        start, end = column_ranges[col]
        available_numbers = list(range(start, end + 1))
        random.shuffle(available_numbers)
        
        # Get rows that need numbers in this column
        rows_needing_numbers = [row for row in range(3) if ticket[row][col] == -1]
        
        # Assign numbers
        for i, row in enumerate(rows_needing_numbers):
            if i < len(available_numbers):
                ticket[row][col] = available_numbers[i]
            else:
                # Fallback: use any available number from range
                ticket[row][col] = random.randint(start, end)
    
    # Step 3: Sort numbers in each column
    for col in range(9):
        numbers_with_rows = []
        for row in range(3):
            if ticket[row][col] != 0:
                numbers_with_rows.append((row, ticket[row][col]))
        
        numbers_with_rows.sort(key=lambda x: x[1])
        
        # Clear and reassign sorted numbers
        for row in range(3):
            ticket[row][col] = 0
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
    """Count total numbers in ticket and verify row counts"""
    total = 0
    row_counts = []
    
    for row in ticket:
        row_count = sum(1 for num in row if num != 0)
        row_counts.append(row_count)
        total += row_count
    
    print(f"Ticket verification - Total: {total}, Row counts: {row_counts}")
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
                'ticket_code': user['ticket_code'],
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
