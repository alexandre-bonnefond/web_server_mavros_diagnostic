from flask import Flask, jsonify, render_template, Response, stream_with_context, request, redirect
from flask_httpauth import HTTPBasicAuth
import paramiko
import subprocess
import threading
import time
import json

app = Flask(__name__)
auth = HTTPBasicAuth()

# Replace with your username and password
users = {
    "uav": "f4f"
}

@auth.verify_password
def verify_password(username, password):
    if username in users and users[username] == password:
        return username
    return None

processes = {}
parameter_status = {
    "FCU": {"Connected": "Fail", "Heartbeat": "0Hz"},
    "System": {
        "3D Gyro": "Fail",
        "3D Accelerometer": "Fail",
        "3D Magnetometer": "Fail",
        "GPS State": "Fail",
        "GPS Satellites": "0",
        "RC Receiver": "Fail",
        "AHRS": "Fail",
        "Battery State": "Fail",
        "Battery Voltage": "0V",
        "Battery Current": "0A",
        "Pre-Arm Check": "Fail",
        "CPU Load": "0%"
    }
}

def start_sensors_evaluation():
    global parameter_status
    if 'sensors_evaluation' in processes:
        return "Sensors evaluation is already running."

    def run_evaluation():
        command = ['roslaunch', 'mrs_uav_deployment', 'sensors.launch']
        processes['sensors_evaluation'] = subprocess.Popen(command)
        time.sleep(5)  # Wait for 5 seconds before starting the node

        command = ['rosrun', 'mavros_diagnostic', 'mavros_diagnostic']
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes['rosnode'] = process
        for line in iter(process.stdout.readline, ''):
            output = line.split()
            # Simulate updating parameter statuses based on the ROS node output
            if "FCU" in output:
                parameter_status["FCU"]["Connected"] = output[-1]
            if "Heartbeat" in output:
                parameter_status["FCU"]["Heartbeat"] = output[-1] + 'Hz'
            if "gyro:" in output:
                parameter_status["System"]["3D Gyro"] = output[-1]
            if "accelerometer:" in output:
                parameter_status["System"]["3D Accelerometer"] = output[-1]
            if "magnetometer:" in output:
                parameter_status["System"]["3D Magnetometer"] = output[-1]
            if "GPS:" in output:
                parameter_status["System"]["GPS State"] = output[-1]
            if "Satellites" in output:
                parameter_status["System"]["GPS Satellites"] = output[-1]
            if "rc" in output:
                parameter_status["System"]["RC Receiver"] = output[-1]
            if "AHRS:" in output:
                parameter_status["System"]["AHRS"] = output[-1]
            if "Battery:" in output:
                parameter_status["System"]["Battery State"] = output[-1]
            if "Voltage" in output:
                parameter_status["System"]["Battery Voltage"] = output[-1] + 'V'
            if "Current" in output:
                parameter_status["System"]["Battery Current"] = output[-1] + 'A'
            if "pre-arm" in output:
                parameter_status["System"]["Pre-Arm Check"] = output[-1]
            if "CPU" in output:
                parameter_status["System"]["CPU Load"] = output[-1] + '%'
            
            # Convert the parameter_status to JSON and yield it
            yield f"data: {json.dumps(parameter_status)}\n\n"
        process.stdout.close()
        process.wait()

    threading.Thread(target=run_evaluation).start()
    return "Sensors evaluation started."

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')

@app.route('/start_sensors_evaluation', methods=['GET'])
@auth.login_required
def start_sensors():
    return render_template('start_sensors_evaluation.html')

@app.route('/start_sensors_stream')
@auth.login_required
def start_sensors_stream():
    return Response(stream_with_context(start_sensors_evaluation()), content_type='text/event-stream')


@app.route('/documentation')
@auth.login_required
def documentation():
    return redirect("https://fly4future.com/")  # Replace with the actual documentation URL

@app.route('/configure_wifi', methods=['GET', 'POST'])
@auth.login_required
def configure_wifi():
    if request.method == 'POST':
        data = request.form
        config_result = apply_netplan_configuration(data)
        return render_template('configure_wifi.html', result=config_result)
    return render_template('configure_wifi.html')

def apply_netplan_configuration(data):
    filename = "/tmp/01-netcfg_old.yaml"
    with open(filename, 'w') as file:
        file.write("network:\n")
        file.write("  version: 2\n")
        file.write("  renderer: networkd\n")
        file.write("  ethernets:\n")
        
        if 'use_dhcp_eth' in data and data['use_dhcp_eth'] == 'yes':
            file.write(f"    {data['eth_name']}:\n")
            file.write("      dhcp4: yes\n")
            file.write("      dhcp6: no\n")
        else:
            file.write(f"    {data['eth_name']}:\n")
            file.write("      dhcp4: no\n")
            file.write("      dhcp6: no\n")
            file.write(f"      addresses: [{data['eth_static_ip']}/24]\n")
        
        file.write("  wifis:\n")
        file.write(f"    {data['wifi_name']}:\n")
        if 'use_dhcp_wifi' in data and data['use_dhcp_wifi'] == 'yes':
            file.write("      dhcp4: yes\n")
            file.write("      dhcp6: no\n")
        else:
            file.write("      dhcp4: no\n")
            file.write("      dhcp6: no\n")
            file.write(f"      addresses: [{data['wifi_static_ip']}/24]\n")
            file.write(f"      gateway4: {data['wifi_gateway']}\n")
        
        file.write("      access-points:\n")
        file.write(f"        \"{data['wifi_ap_name']}\":\n")
        file.write(f"          password: \"{data['wifi_password']}\"\n")

        if 'use_dhcp_wifi' not in data or data['use_dhcp_wifi'] != 'yes':
            file.write("      nameservers:\n")
            file.write(f"        addresses: [{data['wifi_dns']}]\n")

    # Copy the configuration file to /etc/netplan and apply it
    try:
        # subprocess.run('echo', 'test')
        subprocess.run(['sudo', 'cp', filename, '/etc/netplan/'], check=True)
        subprocess.run(['sudo', 'netplan', 'apply'], check=True)
        return "Netplan configuration applied successfully."
    except subprocess.CalledProcessError as e:
        return f"Failed to apply netplan configuration: {e}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
