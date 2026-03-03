from flask import Flask, jsonify, request, render_template
import serial
import string
import random
import os
import time

from database import init_db, get_all_devices, get_device, add_device, delete_device
from app import get_rtc_timestamp, generate_totp

app = Flask(__name__, static_folder="static", template_folder="templates")

# On a Raspberry Pi, UART is typically /dev/serial0 or /dev/ttyAMA0 or /dev/ttyS0
# On Windows, it could be COM3, etc. We'll set a default for the Pi.
UART_PORT = os.environ.get('UART_PORT', '/dev/serial0')
UART_BAUD = 9600

# Initialize Database
with app.app_context():
    init_db()

def generate_random_secret(length=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def transmit_provisioning_data(secret_key, sync_time):
    """
    Sends the provisioning data over UART to the ATtiny3216.
    Format is "PROV,<secret>,<sync_time>\n"
    """
    try:
        with serial.Serial(UART_PORT, UART_BAUD, timeout=2) as ser:
            payload = f"PROV,{secret_key},{sync_time}\n"
            ser.write(payload.encode('utf-8'))
            print(f"Successfully transmitted UART payload: {payload.strip()}")
            return True
    except Exception as e:
        print(f"Failed to transmit over UART ({UART_PORT}): {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices', methods=['GET'])
def list_devices():
    devices = get_all_devices()
    return jsonify({"devices": devices})

@app.route('/api/register', methods=['POST'])
def register_device():
    data = request.json or {}
    name = data.get('name', 'Unknown Device')
    
    # 1. Generate provisioning material
    secret_key = generate_random_secret()
    sync_time = get_rtc_timestamp()
    
    # 2. Store in Database
    device_id = add_device(name, secret_key, sync_time)
    
    # 3. Transmit to ATtiny3216 via UART
    uart_success = transmit_provisioning_data(secret_key, sync_time)
    
    return jsonify({
        "success": True,
        "device": {
            "id": device_id,
            "name": name,
            "secret_key": secret_key,
            "sync_time": sync_time,
            "uart_success": uart_success
        }
    }), 201

@app.route('/api/devices/<int:device_id>/totp', methods=['GET'])
def get_device_totp(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
        
    current_time = get_rtc_timestamp()
    elapsed = current_time - device['sync_time']
    
    if elapsed < 0:
        elapsed = 0
        
    # App.py generate_totp expects bytes as the secret
    secret_bytes = device['secret_key'].encode('utf-8')
    code = generate_totp(secret_bytes, elapsed)
    
    # Calculate progress for circular timer (30-second window)
    TIMESTEP = 30
    remaining_seconds = TIMESTEP - (elapsed % TIMESTEP)
    
    return jsonify({
        "totp": f"{code:06d}",
        "elapsed": elapsed,
        "remaining": remaining_seconds,
        "current_time": current_time,
        "device_id": device_id
    })

@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
def remove_device(device_id):
    delete_device(device_id)
    return jsonify({"success": True})

if __name__ == '__main__':
    # host='0.0.0.0' makes the server accessible across the local network
    app.run(host='0.0.0.0', port=5000, debug=True)
