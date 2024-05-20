import paramiko
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Ensure to use a strong secret key

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
socketio = SocketIO(app)

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'password':
            user = User(id=1)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials. Please try again.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/start_sensors_evaluation')
@login_required
def start_sensors_evaluation():
    return render_template('start_sensors_evaluation.html')

@app.route('/documentation')
@login_required
def documentation():
    return render_template('documentation.html')

@app.route('/configure_wifi', methods=['GET', 'POST'])
@login_required
def configure_wifi():
    if request.method == 'POST':
        result = "Configuration applied successfully"
        return render_template('configure_wifi.html', result=result)
    return render_template('configure_wifi.html')

@app.route('/terminal')
@login_required
def terminal():
    return render_template('terminal.html')

# Establish SSH connection
def ssh_connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('192.168.11.149', username='uav', password='f4f')
    return client

# Initialize SSH shell
ssh_client = ssh_connect()
ssh_shell = ssh_client.invoke_shell()

# Read from SSH shell
def read_ssh_output():
    while True:
        data = ssh_shell.recv(1024).decode('utf-8')
        if data:
            socketio.emit('output', data)
        socketio.sleep(0.1)

@socketio.on('connect')
def on_connect():
    print('Client connected')
    socketio.start_background_task(target=read_ssh_output)

@socketio.on('disconnect')
def on_disconnect():
    print('Client disconnected')

@socketio.on('input')
def on_input(data):
    ssh_shell.send(data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
