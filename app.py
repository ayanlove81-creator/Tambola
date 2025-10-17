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
from flask import jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-123')

# Database setup for Render
def get_db_path():
    return '/tmp/tambola.db' if 'RENDER' in os.environ else 'tambola.db'

def init_db():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Create all tables
    tables = [
        '''CREATE TABLE IF NOT EXISTS users
           (id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            device_id TEXT UNIQUE NOT NULL,
            ticket_code TEXT UNIQUE NOT NULL,
            ticket_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            
        '''CREATE TABLE IF NOT EXISTS used_tickets
           (id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_hash TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            
        '''CREATE TABLE IF NOT EXISTS prizes
           (id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ticket_code TEXT,
            user_name TEXT,
            prize_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP NULL,
            approved_by TEXT NULL)''',
            
        '''CREATE TABLE IF NOT EXISTS called_numbers
           (id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER NOT NULL,
            called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            called_by TEXT DEFAULT 'system')'''
    ]
    
    for table_sql in tables:
        try:
            c.execute(table_sql)
        except Exception as e:
            print(f"Error creating table: {e}")
    
    conn.commit()
    conn.close()
    
    # Initialize prizes table with some data if empty
    initialize_prizes_table()

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
    
def claim_prize(user_id, ticket_code, prize_type, user_name):
    """Submit a prize claim for admin approval"""
    try:
        db = get_db()
        
        # Check if this prize type is already approved
        existing_approved = db.execute(
            'SELECT * FROM prizes WHERE prize_type = ? AND status = "approved"', 
            [prize_type]
        ).fetchone()
        
        if existing_approved:
            db.close()
            return False, "This prize has already been claimed and approved!"
        
        # Check if user already has a pending or approved claim for this prize
        user_existing = db.execute(
            'SELECT * FROM prizes WHERE user_id = ? AND prize_type = ? AND status IN ("pending", "approved")', 
            [user_id, prize_type]
        ).fetchone()
        
        if user_existing:
            db.close()
            if user_existing['status'] == 'pending':
                return False, "You already have a pending claim for this prize!"
            else:
                return False, "You have already claimed this prize!"
        
        # Submit the claim for approval
        db.execute(
            'INSERT INTO prizes (user_id, ticket_code, user_name, prize_type, status) VALUES (?, ?, ?, ?, "pending")',
            [user_id, ticket_code, user_name, prize_type]
        )
        db.commit()
        db.close()
        return True, "Prize claim submitted for admin approval!"
    except Exception as e:
        return False, f"Error submitting claim: {str(e)}"
    
    # Submit the claim for approval
    try:
        db.execute(
            'INSERT INTO prizes (user_id, ticket_code, user_name, prize_type, status) VALUES (?, ?, ?, ?, "pending")',
            [user_id, ticket_code, user_name, prize_type]
        )
        db.commit()
        db.close()
        return True, "Prize claim submitted for admin approval!"
    except Exception as e:
        db.close()
        return False, f"Error submitting claim: {str(e)}"

def get_prize_claims():
    """Get all prize claims with user details"""
    db = get_db()
    claims = db.execute('''
        SELECT p.*, u.name 
        FROM prizes p 
        JOIN users u ON p.user_id = u.id 
        ORDER BY p.claimed_at DESC
    ''').fetchall()
    db.close()
    return claims

def get_pending_claims():
    """Get all pending prize claims for admin approval"""
    db = get_db()
    claims = db.execute('''
        SELECT p.*, u.name 
        FROM prizes p 
        JOIN users u ON p.user_id = u.id 
        WHERE p.status = 'pending'
        ORDER BY p.claimed_at ASC
    ''').fetchall()
    db.close()
    return claims

def get_approved_claims():
    """Get all approved prize claims"""
    db = get_db()
    claims = db.execute('''
        SELECT p.*, u.name 
        FROM prizes p 
        JOIN users u ON p.user_id = u.id 
        WHERE p.status = 'approved'
        ORDER BY p.approved_at DESC
    ''').fetchall()
    db.close()
    return claims

def check_ticket_patterns(ticket, called_numbers):
    """Check which patterns are completed on the ticket"""
    patterns = {
        'first_line': all(num == 0 or num in called_numbers for num in ticket[0]),
        'middle_line': all(num == 0 or num in called_numbers for num in ticket[1]),
        'bottom_line': all(num == 0 or num in called_numbers for num in ticket[2]),
        'early_five': len([num for row in ticket for num in row if num != 0 and num in called_numbers]) >= 5,
        'full_house': all(num == 0 or num in called_numbers for row in ticket for num in row)
    }
    return patterns

def approve_prize_claim(claim_id, approved_by="admin"):
    """Approve a prize claim"""
    db = get_db()
    
    # Check if this prize type is already approved by someone else
    claim = db.execute('SELECT * FROM prizes WHERE id = ?', [claim_id]).fetchone()
    if not claim:
        db.close()
        return False, "Claim not found"
    
    existing_approved = db.execute(
        'SELECT * FROM prizes WHERE prize_type = ? AND status = "approved" AND id != ?', 
        [claim['prize_type'], claim_id]
    ).fetchone()
    
    if existing_approved:
        db.close()
        return False, "This prize has already been approved for someone else!"
    
    # Approve the claim
    try:
        db.execute(
            'UPDATE prizes SET status = "approved", approved_at = CURRENT_TIMESTAMP, approved_by = ? WHERE id = ?',
            [approved_by, claim_id]
        )
        db.commit()
        db.close()
        return True, "Prize claim approved successfully!"
    except Exception as e:
        db.close()
        return False, f"Error approving claim: {str(e)}"

def reject_prize_claim(claim_id):
    """Reject a prize claim"""
    db = get_db()
    try:
        db.execute(
            'UPDATE prizes SET status = "rejected" WHERE id = ?',
            [claim_id]
        )
        db.commit()
        db.close()
        return True, "Prize claim rejected!"
    except Exception as e:
        db.close()
        return False, f"Error rejecting claim: {str(e)}"
        
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
        
        # Get called numbers from session or query parameter
        called_numbers = session.get('called_numbers', [])
        called_numbers_param = request.args.get('called_numbers', '')
        if called_numbers_param:
            called_numbers = [int(num) for num in called_numbers_param.split(',') if num.isdigit()]
            session['called_numbers'] = called_numbers
        
        # Check completed patterns
        patterns = check_ticket_patterns(ticket, called_numbers)
        
        # Get user's prize claims
        db = get_db()
        user_prizes = db.execute(
            'SELECT prize_type, status, claimed_at FROM prizes WHERE user_id = ? ORDER BY claimed_at DESC',
            [user['id']]
        ).fetchall()
        
        # Get all approved winners to show on ticket
        approved_winners = db.execute('''
            SELECT prize_type, user_name, ticket_code 
            FROM prizes 
            WHERE status = "approved" 
            ORDER BY approved_at DESC
        ''').fetchall()
        db.close()
        
        # Store in session for future access
        session['device_id'] = user['device_id']
        session['ticket_code'] = user['ticket_code']
        
        return render_template('ticket.html', 
                             ticket=ticket, 
                             user_name=user['name'], 
                             total_numbers=total_numbers,
                             ticket_code=user['ticket_code'],
                             called_numbers=called_numbers,
                             patterns=patterns,
                             user_prizes=user_prizes,
                             approved_winners=approved_winners,
                             now=current_time)
    except Exception as e:
        print(f"Error loading ticket: {e}")
        return "Error loading ticket. Please register again."
   
@app.route('/prizes')
def show_prizes():
    """Public page showing all prize claims"""
    prize_claims = get_prize_claims()
    return render_template('prizes.html', prize_claims=prize_claims)
    
@app.route('/recover', methods=['GET', 'POST'])
def recover_ticket():
    if request.method == 'POST':
        ticket_code = request.form['ticket_code'].strip().upper()
        if ticket_code:
            return redirect(f'/ticket?code={ticket_code}')
        else:
            return render_template('recover.html', error='Please enter your ticket code')
    
    return render_template('recover.html')
    
@app.route('/admin/export')
def export_data():
    """Export user data as JSON"""
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    
    export_data = []
    for user in users:
        try:
            ticket_data = json.loads(user['ticket_data'])
            export_data.append({
                'name': user['name'],
                'ticket_code': user['ticket_code'],
                'device_id': user['device_id'],
                'created_at': user['created_at'],
                'ticket_data': ticket_data
            })
        except:
            continue
    
    return json.dumps(export_data, indent=2)
    
@app.route('/admin')
def admin():
    try:
        db = get_db()
        
        # Get all users with their tickets
        users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
        
        # Get statistics with error handling
        try:
            total_tickets = db.execute('SELECT COUNT(*) as count FROM used_tickets').fetchone()['count']
        except:
            total_tickets = 0
            
        try:
            total_users = db.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        except:
            total_users = 0
        
        # Get prize claims with error handling
        pending_claims = []
        approved_claims = []
        
        try:
            pending_claims = db.execute('''
                SELECT p.*, u.name 
                FROM prizes p 
                JOIN users u ON p.user_id = u.id 
                WHERE p.status = "pending"
                ORDER BY p.claimed_at ASC
            ''').fetchall()
        except Exception as e:
            print(f"Error getting pending claims: {e}")
        
        try:
            approved_claims = db.execute('''
                SELECT p.*, u.name 
                FROM prizes p 
                JOIN users u ON p.user_id = u.id 
                WHERE p.status = "approved"
                ORDER BY p.approved_at DESC
            ''').fetchall()
        except Exception as e:
            print(f"Error getting approved claims: {e}")
        
        db.close()
        
        user_list = []
        for user in users:
            try:
                ticket_data = json.loads(user['ticket_data'])
                user_list.append({
                    'id': user['id'],
                    'name': user['name'],
                    'ticket': ticket_data,
                    'ticket_code': user['ticket_code'],
                    'device_id': user['device_id'],
                    'created_at': user['created_at'],
                    'numbers_count': count_ticket_numbers(ticket_data),
                    'ticket_url': f"/ticket?code={user['ticket_code']}"
                })
            except Exception as e:
                print(f"Error processing user {user['id']}: {e}")
                continue
        
        # Show admin message if any
        admin_message = session.pop('admin_message', None)
        admin_success = session.pop('admin_success', None)
        
        return render_template('admin.html', 
                             users=user_list, 
                             total_tickets=total_tickets,
                             total_users=total_users,
                             pending_claims=pending_claims,
                             approved_claims=approved_claims,
                             admin_message=admin_message,
                             admin_success=admin_success)
                             
    except Exception as e:
        print(f"Admin page error: {e}")
        return f"Error loading admin page: {str(e)}", 500

def check_prize_claim(ticket_code, prize_type):
    """Check if a prize type has already been approved"""
    db = get_db()
    existing = db.execute(
        'SELECT * FROM prizes WHERE prize_type = ? AND status = "approved"', 
        [prize_type]
    ).fetchone()
    db.close()
    return existing is not None

@app.route('/claim_prize', methods=['POST'])
def claim_prize_route():
    if 'device_id' not in session:
        return redirect('/')
    
    ticket_code = request.form.get('ticket_code')
    prize_type = request.form.get('prize_type')
    
    if not ticket_code or not prize_type:
        return redirect('/ticket')
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE ticket_code = ? AND device_id = ?', 
                     [ticket_code, session['device_id']]).fetchone()
    
    if not user:
        db.close()
        return redirect('/ticket')
    
    success, message = claim_prize(user['id'], ticket_code, prize_type, user['name'])
    db.close()
    
    # Store message in session to display on redirect
    session['claim_message'] = message
    session['claim_success'] = success
    
    return redirect(f'/ticket?code={ticket_code}')

@app.route('/admin/approve_claim/<int:claim_id>')
def approve_claim(claim_id):
    """Admin route to approve a prize claim"""
    try:
        success, message = approve_prize_claim(claim_id)
        session['admin_message'] = message
        session['admin_success'] = success
    except Exception as e:
        session['admin_message'] = f"Error approving claim: {str(e)}"
        session['admin_success'] = False
    return redirect('/admin')

@app.route('/admin/reject_claim/<int:claim_id>')
def reject_claim(claim_id):
    """Admin route to reject a prize claim"""
    try:
        success, message = reject_prize_claim(claim_id)
        session['admin_message'] = message
        session['admin_success'] = success
    except Exception as e:
        session['admin_message'] = f"Error rejecting claim: {str(e)}"
        session['admin_success'] = False
    return redirect('/admin')

@app.route('/admin/clear_claims')
def clear_claims():
    """Clear all prize claims (for testing)"""
    db = get_db()
    db.execute('DELETE FROM prizes')
    db.commit()
    db.close()
    session['admin_message'] = "All claims cleared!"
    return redirect('/admin')
    
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
    
def initialize_prizes_table():
    """Ensure prizes table is properly initialized"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    
    # Check if prizes table has the correct structure
    try:
        c.execute("SELECT * FROM prizes LIMIT 1")
    except sqlite3.OperationalError:
        # Table doesn't exist or has wrong structure, recreate it
        c.execute('DROP TABLE IF EXISTS prizes')
        c.execute('''CREATE TABLE prizes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      ticket_code TEXT,
                      prize_type TEXT NOT NULL,
                      claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (user_id) REFERENCES users (id))''')
        conn.commit()
    
    conn.close()
    
@app.route('/admin/reset-db')
def reset_database():
    """Reset database (for development only)"""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute('DROP TABLE IF EXISTS prizes')
    c.execute('DROP TABLE IF EXISTS used_tickets')
    c.execute('DROP TABLE IF EXISTS users')
    conn.commit()
    conn.close()
    
    init_db()
    return "Database reset successfully"
    
@app.route('/admin/fix-db')
def fix_database():
    """Fix database schema issues"""
    try:
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        
        # Check if prizes table exists and has correct structure
        try:
            c.execute("SELECT * FROM prizes LIMIT 1")
        except sqlite3.OperationalError:
            # Recreate prizes table
            c.execute('DROP TABLE IF EXISTS prizes')
            c.execute('''CREATE TABLE prizes
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_id INTEGER,
                          ticket_code TEXT,
                          user_name TEXT,
                          prize_type TEXT NOT NULL,
                          status TEXT DEFAULT 'pending',
                          claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          approved_at TIMESTAMP NULL,
                          approved_by TEXT NULL,
                          FOREIGN KEY (user_id) REFERENCES users (id))''')
        
        # Check if called_numbers table exists
        try:
            c.execute("SELECT * FROM called_numbers LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS called_numbers
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          number INTEGER NOT NULL,
                          called_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          called_by TEXT DEFAULT 'system')''')
        
        # Check if game_state table exists
        try:
            c.execute("SELECT * FROM game_state LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS game_state
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          key TEXT UNIQUE NOT NULL,
                          value TEXT NOT NULL,
                          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        conn.commit()
        conn.close()
        return "Database fixed successfully!"
    except Exception as e:
        return f"Error fixing database: {str(e)}"
@app.route('/caller')
def caller_dashboard():
    """Number caller dashboard"""
    called_numbers = get_called_numbers()
    recent_numbers = called_numbers[-10:]  # Last 10 numbers
    return render_template('caller.html', 
                         called_numbers=called_numbers,
                         recent_numbers=recent_numbers,
                         total_called=len(called_numbers),
                         remaining=90 - len(called_numbers))

@app.route('/call_number', methods=['POST'])
def call_number_route():
    """Call a number (manual or auto)"""
    number = request.form.get('number', type=int)
    auto = request.form.get('auto') == 'true'
    
    if auto:
        number, message = call_number()  # Auto-call
    else:
        number, message = call_number(number)  # Manual call
    
    if number:
        # Get audio/text for the number
        number_text = get_number_text(number)
        return jsonify({
            'success': True,
            'number': number,
            'number_text': number_text,
            'message': message,
            'total_called': len(get_called_numbers())
        })
    else:
        return jsonify({
            'success': False,
            'message': message
        })

@app.route('/called_numbers')
def get_called_numbers_route():
    """API to get called numbers"""
    numbers = get_called_numbers()
    return jsonify({'called_numbers': numbers})

@app.route('/reset_numbers', methods=['POST'])
def reset_numbers_route():
    """Reset all called numbers"""
    if reset_called_numbers():
        return jsonify({'success': True, 'message': 'All numbers reset!'})
    else:
        return jsonify({'success': False, 'message': 'Error resetting numbers'})

@app.route('/last_number')
def get_last_number():
    """Get the last called number"""
    db = get_db()
    last = db.execute(
        'SELECT number FROM called_numbers ORDER BY called_at DESC LIMIT 1'
    ).fetchone()
    db.close()
    
    if last:
        number_text = get_number_text(last['number'])
        return jsonify({
            'number': last['number'],
            'number_text': number_text
        })
    else:
        return jsonify({'number': None})
ALL_TAMBOLA_NUMBERS = list(range(1, 91))

def get_called_numbers():
    """Get all called numbers in order"""
    db = get_db()
    numbers = db.execute(
        'SELECT number FROM called_numbers ORDER BY called_at ASC'
    ).fetchall()
    db.close()
    return [row['number'] for row in numbers]

def call_number(number=None):
    """Call a number (manual or auto)"""
    db = get_db()
    
    if number is None:
        # Auto-call: get next random number
        called_numbers = get_called_numbers()
        available_numbers = [n for n in ALL_TAMBOLA_NUMBERS if n not in called_numbers]
        
        if not available_numbers:
            db.close()
            return None, "All numbers have been called!"
        
        number = random.choice(available_numbers)
    
    # Check if number already called
    existing = db.execute(
        'SELECT * FROM called_numbers WHERE number = ?', [number]
    ).fetchone()
    
    if existing:
        db.close()
        return None, f"Number {number} has already been called!"
    
    # Add the number
    try:
        db.execute(
            'INSERT INTO called_numbers (number) VALUES (?)',
            [number]
        )
        db.commit()
        db.close()
        return number, f"Number {number} called successfully!"
    except Exception as e:
        db.close()
        return None, f"Error calling number: {str(e)}"

def reset_called_numbers():
    """Reset all called numbers"""
    db = get_db()
    db.execute('DELETE FROM called_numbers')
    db.commit()
    db.close()
    return True

def get_number_text(number):
    """Convert number to spoken text"""
    if number <= 90:
        tens = number // 10
        units = number % 10
        
        if number in [11, 12]:
            return f"eleven" if number == 11 else "twelve"
        elif tens == 0:
            return ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"][units]
        elif tens == 1:
            return ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"][units]
        elif tens in [2, 3, 4, 5, 8]:
            tens_words = ["twenty", "thirty", "forty", "fifty", "eighty"]
            word = tens_words[tens-2]
            if units > 0:
                word += " " + ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"][units-1]
            return word
        elif tens == 9:
            return "ninety" if units == 0 else f"ninety {['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'][units-1]}"
        else:
            return str(number)
    return str(number)
    
@app.route('/health')
def health():
    return 'OK'

# Initialize database
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
