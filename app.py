from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import json
import random
from database import init_db, get_db_connection, get_or_create_device_id
import qrcode
import io
import base64
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize database
init_db()

def generate_tambola_ticket():
    """Generate a Tambola ticket with 3 rows and 9 columns"""
    ticket = [[0]*9 for _ in range(3)]
    
    # Generate numbers for each column
    for col in range(9):
        start_num = col * 10 + 1
        end_num = start_num + 9
        if col == 0:
            start_num = 1
            end_num = 9
        elif col == 8:
            start_num = 80
            end_num = 90
        
        numbers = random.sample(range(start_num, end_num + 1), 3)
        numbers.sort()
        
        # Place numbers in random rows
        positions = random.sample(range(3), 3)
        for i, pos in enumerate(positions):
            ticket[pos][col] = numbers[i]
    
    # Ensure each row has exactly 5 numbers
    for row in range(3):
        non_zero = [i for i, num in enumerate(ticket[row]) if num != 0]
        if len(non_zero) > 5:
            # Remove extra numbers
            to_remove = random.sample(non_zero, len(non_zero) - 5)
            for col in to_remove:
                ticket[row][col] = 0
        elif len(non_zero) < 5:
            # Add numbers if needed
            zero_cols = [i for i in range(9) if ticket[row][i] == 0]
            to_add = random.sample(zero_cols, 5 - len(non_zero))
            for col in to_add:
                start_num = col * 10 + 1
                end_num = start_num + 9
                if col == 0:
                    start_num = 1
                    end_num = 9
                elif col == 8:
                    start_num = 80
                    end_num = 90
                
                # Find a unique number for this column
                existing_numbers = [ticket[r][col] for r in range(3)]
                available_numbers = [n for n in range(start_num, end_num + 1) 
                                   if n not in existing_numbers]
                if available_numbers:
                    ticket[row][col] = random.choice(available_numbers)
    
    return ticket

def generate_qr_code(url):
    """Generate QR code as base64 string"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.getvalue()).decode()

@app.route('/')
def index():
    if 'device_id' not in session:
        session['device_id'] = get_or_create_device_id()
    
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE device_id = ?', 
        (session['device_id'],)
    ).fetchone()
    conn.close()
    
    if user:
        return redirect(url_for('show_ticket'))
    
    # Generate QR code for registration
    base_url = request.url_root
    qr_url = base_url + url_for('register')[1:] if base_url.endswith('/') else base_url + url_for('register')
    qr_code = generate_qr_code(qr_url)
    
    return render_template('index.html', qr_code=qr_code, qr_url=qr_url)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'device_id' not in session:
        session['device_id'] = get_or_create_device_id()
    
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE device_id = ?', 
        (session['device_id'],)
    ).fetchone()
    
    if user:
        conn.close()
        return redirect(url_for('show_ticket'))
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        
        if not name:
            return render_template('register.html', error='Please enter your name')
        
        # Generate ticket
        ticket = generate_tambola_ticket()
        ticket_json = json.dumps(ticket)
        
        # Save user and ticket
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO users (name, device_id, ticket_data) VALUES (?, ?, ?)',
            (name, session['device_id'], ticket_json)
        )
        user_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return redirect(url_for('show_ticket'))
    
    conn.close()
    return render_template('register.html')

@app.route('/ticket')
def show_ticket():
    if 'device_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE device_id = ?', 
        (session['device_id'],)
    ).fetchone()
    conn.close()
    
    if not user:
        return redirect(url_for('register'))
    
    ticket = json.loads(user['ticket_data'])
    return render_template('ticket.html', ticket=ticket, user_name=user['name'])

@app.route('/admin')
def admin():
    conn = get_db_connection()
    users = conn.execute('''
        SELECT name, device_id, ticket_data, created_at 
        FROM users ORDER BY created_at DESC
    ''').fetchall()
    conn.close()
    
    user_data = []
    for user in users:
        user_data.append({
            'name': user['name'],
            'device_id': user['device_id'],
            'ticket': json.loads(user['ticket_data']),
            'created_at': user['created_at']
        })
    
    return render_template('admin.html', users=user_data)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # Set debug=False for production