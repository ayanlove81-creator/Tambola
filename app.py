import os
import sqlite3
import uuid
import random
import json
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

def generate_ticket():
    ticket = [[0]*9 for _ in range(3)]
    
    for col in range(9):
        start_num = col * 10 + 1
        end_num = start_num + 9
        if col == 0:
            start_num, end_num = 1, 9
        elif col == 8:
            start_num, end_num = 80, 90
            
        numbers = random.sample(range(start_num, end_num+1), 3)
        numbers.sort()
        positions = random.sample([0,1,2], 3)
        
        for i, pos in enumerate(positions):
            ticket[pos][col] = numbers[i]
    
    return ticket

@app.route('/')
def index():
    if 'device_id' not in session:
        session['device_id'] = str(uuid.uuid4())
    
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE device_id = ?', [session['device_id']]).fetchone()
    db.close()
    
    if user:
        return redirect('/ticket')
    
    # Simple link instead of QR code
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tambola Tickets</title>
        <style>
            body { font-family: Arial; text-align: center; padding: 20px; }
            .btn { background: blue; color: white; padding: 15px; text-decoration: none; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>Tambola Ticket Generator</h1>
        <p>Click below to get your ticket:</p>
        <a href="/register" class="btn">Get Your Ticket</a>
    </body>
    </html>
    '''

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
            ticket = generate_ticket()
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
    return '''
    <form method="POST" style="text-align: center; padding: 20px;">
        <h1>Register for Tambola</h1>
        <input type="text" name="name" placeholder="Enter your name" required>
        <br><br>
        <button type="submit">Get Ticket</button>
    </form>
    '''

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
    
    # Generate HTML table for ticket
    ticket_html = '<table style="border-collapse: collapse; margin: 20px auto; border: 2px solid black;">'
    for row in ticket:
        ticket_html += '<tr>'
        for number in row:
            if number == 0:
                ticket_html += '<td style="width: 50px; height: 50px; border: 1px solid #ccc; background: #f0f0f0;"></td>'
            else:
                ticket_html += f'<td style="width: 50px; height: 50px; border: 1px solid black; text-align: center; font-weight: bold;">{number}</td>'
        ticket_html += '</tr>'
    ticket_html += '</table>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Your Ticket</title>
        <style>
            body {{ font-family: Arial; text-align: center; padding: 20px; }}
        </style>
    </head>
    <body>
        <h1>Your Tambola Ticket</h1>
        <h2>Player: {user['name']}</h2>
        {ticket_html}
        <br>
        <button onclick="window.print()">Print Ticket</button>
        <a href="/">Home</a>
    </body>
    </html>
    '''

@app.route('/admin')
def admin():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    
    users_html = ''
    for user in users:
        ticket = json.loads(user['ticket_data'])
        ticket_preview = '<table style="border-collapse: collapse; font-size: 10px; display: inline-block;">'
        for row in ticket:
            ticket_preview += '<tr>'
            for number in row:
                if number == 0:
                    ticket_preview += '<td style="width: 20px; height: 20px; border: 1px solid #ccc; background: #f0f0f0;"></td>'
                else:
                    ticket_preview += f'<td style="width: 20px; height: 20px; border: 1px solid black; text-align: center;">{number}</td>'
            ticket_preview += '</tr>'
        ticket_preview += '</table>'
        
        users_html += f'''
        <div style="border: 1px solid #ccc; padding: 10px; margin: 10px;">
            <h3>{user['name']}</h3>
            <p>Registered: {user['created_at']}</p>
            {ticket_preview}
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin</title>
    </head>
    <body>
        <h1>Admin Panel</h1>
        <p>Total Players: {len(users)}</p>
        {users_html}
        <a href="/">Home</a>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    return 'OK'

# Initialize database
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
