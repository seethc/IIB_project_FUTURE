from flask import Flask, jsonify, request, render_template
import serial
import string
import random
import os
import time

from database import init_db, get_all_devices, get_device, add_device, delete_device, update_device
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

def verify_hardware_sync(expected_secret):
    """
    Asks the ATtiny3216 to return its current secret key to verify hardware presence.
    Returns True if the attached token's secret matches the expected_secret.
    """
    try:
        with serial.Serial(UART_PORT, UART_BAUD, timeout=2) as ser:
            ser.write(b"READ_SECRET\n")
            
            # Wait a brief moment and read the response
            time.sleep(0.1)
            response = ser.readline().decode('utf-8').strip()
            
            # We expect the token to return "SECRET,..." or similar based on your firmware logic.
            # Here we just check if the expected secret is anywhere in the response line.
            if response and expected_secret in response:
                print(f"Hardware verified successfully for secret: {expected_secret}")
                return True
            else:
                print(f"Hardware verification failed. Got: '{response}', expected: '{expected_secret}'")
                return False
    except Exception as e:
        print(f"Failed to read from UART ({UART_PORT}): {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices', methods=['GET'])
def list_devices():
    devices = get_all_devices()
    
    # Calculate elapsed time for each so the admin view can display it easily on load
    current_time = get_rtc_timestamp()
    for d in devices:
        elapsed = current_time - d['sync_time']
        d['elapsed'] = elapsed if elapsed >= 0 else 0
        
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

@app.route('/api/devices/<int:device_id>/verify', methods=['POST'])
def verify_device_admin(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
        
    verified = verify_hardware_sync(device['secret_key'])
    return jsonify({"verified": verified})

@app.route('/api/devices/<int:device_id>/reset', methods=['POST'])
def reset_device(device_id):
    """
    Resets the token. 
    If body contains 'new_key': true, generates a new secret.
    Otherwise, just syncs the clock with the existing key.
    """
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
        
    data = request.json or {}
    new_key = data.get('new_key', False)
    
    secret_key = generate_random_secret() if new_key else device['secret_key']
    sync_time = get_rtc_timestamp()
    
    # Update Database
    update_device(device_id, secret_key, sync_time)
    
    # Transmit via UART
    uart_success = transmit_provisioning_data(secret_key, sync_time)
    
    return jsonify({"success": True, "uart_success": uart_success, "secret_key": secret_key, "sync_time": sync_time})

@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
def remove_device(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404
        
    verified = verify_hardware_sync(device['secret_key'])
    if not verified:
        return jsonify({"error": "Hardware verification failed. Please connect the token that matches this device down to the UART."}), 403
        
    delete_device(device_id)
    return jsonify({"success": True})

if __name__ == '__main__':
    # host='0.0.0.0' makes the server accessible across the local network
    app.run(host='0.0.0.0', port=5000, debug=True)
