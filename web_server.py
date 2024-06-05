import os
import subprocess
import paramiko
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
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
    return redirect("https://f4f.gitbook.io/getting-started-f4f/")  # Replace with the actual documentation URL

@app.route('/terminal')
@login_required
def terminal():
    return render_template('terminal.html')

@app.route('/drone_info')
@login_required
def drone_info():
    global uav_type
    return jsonify({
        'ip': '192.168.1.1',
        'model': uav_type
    })

def generate_netplan_configuration(data):
    netplan_config = [
        "network:",
        "  version: 2",
        "  renderer: networkd",
        "  ethernets:"
    ]

    if 'use_dhcp_eth' in data and data['use_dhcp_eth'] == 'yes':
        netplan_config.append(f"    {data['eth_name']}:")
        netplan_config.append("      dhcp4: yes")
        netplan_config.append("      dhcp6: no")
    else:
        netplan_config.append(f"    {data['eth_name']}:")
        netplan_config.append("      dhcp4: no")
        netplan_config.append("      dhcp6: no")
        netplan_config.append(f"      addresses: [{data['eth_static_ip']}/24]")

    netplan_config.append("  wifis:")
    netplan_config.append(f"    {data['wifi_name']}:")

    if 'use_dhcp_wifi' in data and data['use_dhcp_wifi'] == 'yes':
        netplan_config.append("      dhcp4: yes")
        netplan_config.append("      dhcp6: no")
    else:
        netplan_config.append("      dhcp4: no")
        netplan_config.append("      dhcp6: no")
        netplan_config.append(f"      addresses: [{data['wifi_static_ip']}/24]")
        netplan_config.append(f"      gateway4: {data['wifi_gateway']}")

    netplan_config.append("      access-points:")
    netplan_config.append(f"        \"{data['wifi_ap_name']}\":")
    netplan_config.append(f"          password: \"{data['wifi_password']}\"")

    if 'use_dhcp_wifi' not in data or data['use_dhcp_wifi'] != 'yes':
        netplan_config.append("      nameservers:")
        netplan_config.append(f"        addresses: [{data['wifi_dns']}]")

    return "\n".join(netplan_config)

@app.route('/configure_wifi', methods=['GET', 'POST'])
@login_required
def configure_wifi():
    if request.method == 'POST':
        data = request.form.to_dict()
        try:
            result = apply_netplan_configuration(data)
            return jsonify({'message': result})
        except Exception as e:
            return jsonify({'message': f"Failed to apply netplan configuration: {str(e)}"}), 500
    else:
        return render_template('configure_wifi.html')

@app.route('/preview_netplan', methods=['POST'])
@login_required
def preview_netplan():
    data = request.form.to_dict()
    netplan_config = generate_netplan_configuration(data)
    return jsonify({'netplan': netplan_config})

def apply_netplan_configuration(data):
    filename = "/tmp/01-netcfg.yaml"
    netplan_config = generate_netplan_configuration(data)
    with open(filename, 'w') as file:
        file.write(netplan_config)

    try:
        password = "f4f"
        result_cp = subprocess.run(['sudo', '-S', 'cp', filename, '/etc/netplan/01-netcfg.yaml'], check=True, text=True, input=password + '\n', capture_output=True)
        result_netplan = subprocess.run(['sudo', '-S', 'netplan', 'apply'], check=True, text=True, input=password + '\n', capture_output=True)
        return "Netplan configuration applied successfully."
    except subprocess.CalledProcessError as e:
        raise Exception(e.stderr)
    
# Establish SSH connection
def ssh_connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('localhost', username='uav', password='f4f')
    return client

# Initialize SSH shell
ssh_client = ssh_connect()
ssh_shell = ssh_client.invoke_shell()

# Retrieve UAV_TYPE environment variable
stdin, stdout, stderr = ssh_client.exec_command('echo $UAV_TYPE')
uav_type = stdout.read().decode().strip()

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
def handle_input(data):
    # Handle the input from the terminal and execute the command
    try:
        ssh_shell.send(data)
    except Exception as e:
        emit('output', str(e))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
