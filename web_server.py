from flask import Flask, jsonify, render_template, Response, stream_with_context
from flask_httpauth import HTTPBasicAuth
import subprocess
import threading

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

def start_roslaunch(package, launch_file):
    if 'roslaunch' in processes:
        return "roslaunch is already running."
    command = ['roslaunch', package, launch_file]
    processes['roslaunch'] = subprocess.Popen(command)
    return "roslaunch started."

def run_rosnode(package, node_name):
    if 'rosnode' in processes:
        return "rosnode is already running."
    global parameter_status
    command = ['rosrun', package, node_name]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    processes['rosnode'] = process
    for line in iter(process.stdout.readline, ''):
        print(line)
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
        
        # Add more parsing logic for other parameters here

        yield f"data: {output}\n\n"
    process.stdout.close()
    process.wait()

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')

@app.route('/start_roslaunch')
@auth.login_required
def start_launch():
    message = start_roslaunch('mrs_uav_deployment', 'sensors.launch')
    return jsonify(message=message)

@app.route('/start_rosnode')
@auth.login_required
def start_node():
    return Response(stream_with_context(run_rosnode('mavros_diagnostic', 'mavros_diagnostic')), content_type='text/event-stream')

@app.route('/status_parameters')
@auth.login_required
def status_parameters():
    return jsonify(parameter_status)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
