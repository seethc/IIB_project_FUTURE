import os
import secrets

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from database import (
    add_device,
    delete_device,
    get_all_devices,
    get_device,
    init_db,
    update_device,
    update_device_name,
    update_patient_info,
)
from hardware import (
    DEFAULT_ADAPTER_BAUD,
    DEFAULT_FLASH_TARGET,
    DEFAULT_TOKEN_BAUD,
    HARDWARE_MOCK,
    FlashJobManager,
    HardwareError,
    ProtocolError,
    list_firmware_envs,
    list_serial_ports,
    read_serial_lines,
    switch_adapter_mode,
    token_challenge,
    token_hello,
    token_read_rtc,
    token_reset_arm,
    token_reset_all,
    token_reset_time,
    token_status,
    token_unregister,
)
from totp_utils import (
    DEFAULT_TIMESTEP_SECONDS,
    generate_challenge_response,
    generate_totp,
    get_rtc_timestamp,
    secret_hex_to_bytes,
)


app = Flask(__name__, static_folder="static", template_folder="templates")
flash_jobs = FlashJobManager()

DEFAULT_UPLOAD_PORT = os.environ.get("UPLOAD_PORT", "COM4")
DEFAULT_UART_PORT = os.environ.get(
    "UART_PORT", DEFAULT_UPLOAD_PORT if os.name == "nt" else "/dev/serial0"
)
DEFAULT_ADAPTER_PORT = os.environ.get("ADAPTER_CONTROL_PORT", DEFAULT_UPLOAD_PORT)
DEFAULT_SECRET_HEX = b"12345678901234567890".hex()


with app.app_context():
    init_db()


def generate_secret_hex():
    return secrets.token_bytes(20).hex()


def request_json():
    return request.get_json(silent=True) or {}


def selected_timestep(data, fallback=DEFAULT_TIMESTEP_SECONDS):
    try:
        timestep = int(data.get("timestep", fallback))
    except (TypeError, ValueError):
        timestep = fallback

    if timestep <= 0:
        timestep = fallback
    return timestep


def selected_uart_port(data):
    return data.get("uart_port") or data.get("token_port") or DEFAULT_UART_PORT


def public_device(device):
    return {
        "id": device["id"],
        "name": device["name"],
        "sync_time": device["sync_time"],
        "timestep": device.get("timestep") or DEFAULT_TIMESTEP_SECONDS,
        **patient_info_from_device(device),
    }


def patient_info_from_device(device):
    return {
        "patient_name": device.get("patient_name") or "",
        "patient_age": device.get("patient_age"),
        "patient_phone": device.get("patient_phone") or "",
        "patient_emergency_contact": device.get("patient_emergency_contact") or "",
        "patient_allergies": device.get("patient_allergies") or "",
        "patient_notes": device.get("patient_notes") or "",
    }


def parse_patient_info(data):
    def clean_text(field, max_length):
        value = str(data.get(field, "") or "").strip()
        if len(value) > max_length:
            raise ValueError(f"{field.replace('_', ' ').title()} is too long")
        return value

    raw_age = data.get("patient_age", None)
    patient_age = None
    if raw_age is not None and raw_age != "":
        try:
            patient_age = int(raw_age)
        except (TypeError, ValueError) as exc:
            raise ValueError("Patient age must be a number") from exc
        if patient_age < 0 or patient_age > 130:
            raise ValueError("Patient age must be between 0 and 130")

    return {
        "patient_name": clean_text("patient_name", 120),
        "patient_age": patient_age,
        "patient_phone": clean_text("patient_phone", 60),
        "patient_emergency_contact": clean_text("patient_emergency_contact", 160),
        "patient_allergies": clean_text("patient_allergies", 500),
        "patient_notes": clean_text("patient_notes", 4000),
    }


def match_device_by_challenge(challenge_hex, digest):
    for device in get_all_devices():
        expected = generate_challenge_response(device["secret_key"], challenge_hex)
        if secrets.compare_digest(expected, digest):
            return device
    return None


def verify_connected_device(device, uart_port, baud=DEFAULT_TOKEN_BAUD):
    challenge_hex = secrets.token_bytes(16).hex()
    proof = token_challenge(uart_port, challenge_hex, baud=baud)
    expected = generate_challenge_response(device["secret_key"], challenge_hex)
    if not proof["provisioned"] or not secrets.compare_digest(expected, proof["digest"]):
        raise ProtocolError("Connected pendant does not match this saved token.")
    return proof


def hardware_error_response(exc):
    status_code = 400 if isinstance(exc, ValueError) else 502
    return jsonify({"success": False, "error": str(exc)}), status_code


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    if request.path.startswith("/api/"):
        return (
            jsonify(
                {
                    "success": False,
                    "error": exc.description or exc.name,
                }
            ),
            exc.code,
        )
    return exc


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if request.path.startswith("/api/"):
        app.logger.exception("Unhandled API error")
        return jsonify({"success": False, "error": str(exc)}), 500
    raise exc


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/hardware/ports", methods=["GET"])
def hardware_ports():
    return jsonify(
        {
            "ports": list_serial_ports(),
            "defaults": {
                "adapter_port": DEFAULT_ADAPTER_PORT,
                "token_port": DEFAULT_UART_PORT,
                "upload_port": DEFAULT_UPLOAD_PORT,
                "token_baud": DEFAULT_TOKEN_BAUD,
                "adapter_baud": DEFAULT_ADAPTER_BAUD,
                "timestep": DEFAULT_TIMESTEP_SECONDS,
                "mock": HARDWARE_MOCK,
            },
        }
    )


@app.route("/api/hardware/firmware-envs", methods=["GET"])
def firmware_envs():
    return jsonify({"envs": list_firmware_envs()})


@app.route("/api/adapter/mode", methods=["POST"])
def set_adapter_mode():
    data = request_json()
    try:
        reply = switch_adapter_mode(
            data.get("port") or DEFAULT_ADAPTER_PORT,
            data.get("mode", ""),
            baud=int(data.get("baud", DEFAULT_ADAPTER_BAUD)),
        )
        return jsonify({"success": True, "reply": reply})
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)


@app.route("/api/flash", methods=["POST"])
def start_flash():
    data = request_json()
    upload_port = data.get("upload_port") or DEFAULT_UPLOAD_PORT
    adapter_port = data.get("adapter_port") or None
    switch_mode = bool(data.get("switch_mode", False))
    target = data.get("target") or DEFAULT_FLASH_TARGET

    try:
        job = flash_jobs.start_flash(
            target,
            upload_port=upload_port,
            adapter_port=adapter_port,
            switch_mode=switch_mode,
        )
        return jsonify({"success": True, "job": job}), 202
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    job = flash_jobs.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"job": job})


@app.route("/api/token/hello", methods=["POST"])
def token_hello_route():
    data = request_json()
    try:
        reply = token_hello(selected_uart_port(data), baud=int(data.get("baud", DEFAULT_TOKEN_BAUD)))
        return jsonify({"success": True, "reply": reply})
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)


@app.route("/api/token/status", methods=["POST"])
def token_status_route():
    data = request_json()
    try:
        status = token_status(selected_uart_port(data), baud=int(data.get("baud", DEFAULT_TOKEN_BAUD)))
        return jsonify({"success": True, "status": status})
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)


@app.route("/api/token/read-rtc", methods=["POST"])
def token_read_rtc_route():
    data = request_json()
    try:
        rtc = token_read_rtc(selected_uart_port(data), baud=int(data.get("baud", DEFAULT_TOKEN_BAUD)))
        return jsonify({"success": True, "rtc": rtc})
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)


@app.route("/api/token/unregister", methods=["POST"])
def token_unregister_route():
    data = request_json()
    try:
        reply = token_unregister(
            selected_uart_port(data), baud=int(data.get("baud", DEFAULT_TOKEN_BAUD))
        )
        return jsonify({"success": True, "reply": reply})
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)


@app.route("/api/token/identify", methods=["POST"])
def token_identify_route():
    data = request_json()
    challenge_hex = secrets.token_bytes(16).hex()
    uart_port = selected_uart_port(data)
    baud = int(data.get("baud", DEFAULT_TOKEN_BAUD))

    try:
        proof = token_challenge(
            uart_port,
            challenge_hex,
            baud=baud,
        )
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)

    reset_armed = False
    try:
        token_reset_arm(uart_port, baud=baud)
        reset_armed = True
    except (HardwareError, ProtocolError, ValueError):
        reset_armed = False

    matched_device = (
        match_device_by_challenge(challenge_hex, proof["digest"])
        if proof["provisioned"]
        else None
    )
    if matched_device:
        return jsonify(
            {
                "success": True,
                "state": "matched",
                "matched": True,
                "provisioned": True,
                "reset_armed": reset_armed,
                "device": public_device(matched_device),
            }
        )

    return jsonify(
        {
            "success": True,
            "state": "unknown_registered" if proof["provisioned"] else "unregistered",
            "matched": False,
            "provisioned": proof["provisioned"],
            "reset_armed": reset_armed,
        }
    )


@app.route("/api/token/serial-read", methods=["POST"])
def token_serial_read_route():
    data = request_json()
    try:
        lines = read_serial_lines(
            selected_uart_port(data),
            baud=int(data.get("baud", DEFAULT_TOKEN_BAUD)),
            duration=float(data.get("duration", 2.0)),
        )
        return jsonify({"success": True, "lines": lines})
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)


@app.route("/api/devices", methods=["GET"])
def list_devices():
    devices = get_all_devices()
    current_time = get_rtc_timestamp()
    for device in devices:
        elapsed = current_time - device["sync_time"]
        device["elapsed"] = elapsed if elapsed >= 0 else 0
        device["timestep"] = device.get("timestep") or DEFAULT_TIMESTEP_SECONDS

    return jsonify({"devices": devices})


@app.route("/api/register", methods=["POST"])
def register_device():
    data = request_json()
    name = data.get("name", "Unknown Device")
    timestep = selected_timestep(data)
    secret_key = generate_secret_hex()
    uart_port = selected_uart_port(data)

    try:
        reply = token_reset_all(uart_port, secret_key, timestep)
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)

    sync_time = get_rtc_timestamp()
    device_id = add_device(name, secret_key, sync_time, timestep)

    return (
        jsonify(
            {
                "success": True,
                "reply": reply,
                "device": {
                    "id": device_id,
                    "name": name,
                    "secret_key": secret_key,
                    "sync_time": sync_time,
                    "timestep": timestep,
                },
            }
        ),
        201,
    )


@app.route("/api/devices/<int:device_id>/totp", methods=["GET"])
def get_device_totp(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404

    timestep = int(device.get("timestep") or DEFAULT_TIMESTEP_SECONDS)
    current_time = get_rtc_timestamp()
    elapsed = current_time - device["sync_time"]
    if elapsed < 0:
        elapsed = 0

    secret_bytes = secret_hex_to_bytes(device["secret_key"])
    code = generate_totp(secret_bytes, elapsed, timestep)
    remaining_seconds = timestep - (elapsed % timestep)

    return jsonify(
        {
            "totp": f"{code:06d}",
            "elapsed": elapsed,
            "remaining": remaining_seconds,
            "timestep": timestep,
            "current_time": current_time,
            "device_id": device_id,
        }
    )


@app.route("/api/devices/<int:device_id>/verify", methods=["POST"])
def verify_device_admin(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404

    data = request_json()
    try:
        proof = verify_connected_device(
            device,
            selected_uart_port(data),
            baud=int(data.get("baud", DEFAULT_TOKEN_BAUD)),
        )
        status = token_status(
            selected_uart_port(data), baud=int(data.get("baud", DEFAULT_TOKEN_BAUD))
        )
        return jsonify({"verified": True, "proof": proof, "status": status})
    except (HardwareError, ProtocolError, ValueError) as exc:
        return jsonify({"verified": False, "error": str(exc)}), 502


@app.route("/api/devices/<int:device_id>", methods=["PATCH"])
def rename_device(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404

    data = request_json()
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"success": False, "error": "Pendant name is required"}), 400
    if len(name) > 80:
        return jsonify({"success": False, "error": "Pendant name is too long"}), 400

    update_device_name(device_id, name)
    updated = get_device(device_id)
    return jsonify({"success": True, "device": public_device(updated)})


@app.route("/api/devices/<int:device_id>/patient", methods=["PATCH"])
def update_device_patient_info(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404

    try:
        patient_info = parse_patient_info(request_json())
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    update_patient_info(device_id, patient_info)
    updated = get_device(device_id)
    return jsonify(
        {
            "success": True,
            "patient": patient_info_from_device(updated),
            "device": public_device(updated),
        }
    )


@app.route("/api/devices/<int:device_id>/reset", methods=["POST"])
def reset_device(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404

    data = request_json()
    action = data.get("action") or ("reset_pendant" if data.get("new_key") else "reset_time")
    timestep = selected_timestep(data, device.get("timestep") or DEFAULT_TIMESTEP_SECONDS)
    uart_port = selected_uart_port(data)
    baud = int(data.get("baud", DEFAULT_TOKEN_BAUD))
    secret_key = device["secret_key"]
    sync_time = device["sync_time"]

    try:
        verify_connected_device(device, uart_port, baud=baud)
        if action == "reset_pendant":
            secret_key = generate_secret_hex()
            reply = token_reset_all(uart_port, secret_key, timestep, baud=baud)
            sync_time = get_rtc_timestamp()
        elif action == "reset_default_key":
            secret_key = DEFAULT_SECRET_HEX
            reply = token_reset_all(uart_port, secret_key, timestep, baud=baud)
            sync_time = get_rtc_timestamp()
        else:
            reply = token_reset_time(uart_port, baud=baud)
            sync_time = get_rtc_timestamp()
    except (HardwareError, ProtocolError, ValueError) as exc:
        return hardware_error_response(exc)

    update_device(device_id, secret_key, sync_time, timestep)

    return jsonify(
        {
            "success": True,
            "reply": reply,
            "secret_key": secret_key,
            "sync_time": sync_time,
            "timestep": timestep,
        }
    )


@app.route("/api/devices/<int:device_id>", methods=["DELETE"])
def remove_device(device_id):
    device = get_device(device_id)
    if not device:
        return jsonify({"error": "Device not found"}), 404

    data = request_json()
    require_hardware_verification = bool(
        data.get("require_hardware_verification", True)
    )
    hardware_unregistered = False
    if require_hardware_verification:
        uart_port = selected_uart_port(data)
        baud = int(data.get("baud", DEFAULT_TOKEN_BAUD))
        try:
            verify_connected_device(device, uart_port, baud=baud)
            token_unregister(uart_port, baud=baud)
            hardware_unregistered = True
        except (HardwareError, ProtocolError, ValueError) as exc:
            return hardware_error_response(exc)

    delete_device(device_id)
    return jsonify(
        {
            "success": True,
            "hardware_unregistered": hardware_unregistered,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
