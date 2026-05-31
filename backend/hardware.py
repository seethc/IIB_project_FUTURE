import hashlib
import hmac
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

SERIAL_EXCEPTIONS = (OSError,)
if serial is not None:
    SERIAL_EXCEPTIONS = (serial.SerialException, OSError)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKEN_BAUD = int(os.environ.get("TOKEN_BAUD", "9600"))
DEFAULT_ADAPTER_BAUD = int(os.environ.get("ADAPTER_BAUD", "115200"))
HARDWARE_MOCK = os.environ.get("HARDWARE_MOCK", "").lower() in {"1", "true", "yes"}
ADAPTER_REQUIRE_ACK = os.environ.get("ADAPTER_REQUIRE_ACK", "").lower() in {
    "1",
    "true",
    "yes",
}
ADAPTER_OPEN_DELAY_SECONDS = float(os.environ.get("ADAPTER_OPEN_DELAY_SECONDS", "1.0"))
UPDI_SETTLE_SECONDS = float(os.environ.get("UPDI_SETTLE_SECONDS", "1.5"))
TOKEN_UART_RTS = os.environ.get("TOKEN_UART_RTS", "auto").strip().lower()
SERIAL_OPEN_ATTEMPTS = max(1, int(os.environ.get("SERIAL_OPEN_ATTEMPTS", "4")))
SERIAL_OPEN_RETRY_DELAY_SECONDS = float(
    os.environ.get("SERIAL_OPEN_RETRY_DELAY_SECONDS", "0.25")
)
MAIN2_FLASH_TARGET = "main2"
ARDUINO_FQBN = os.environ.get(
    "ARDUINO_FQBN",
    "megaTinyCore:megaavr:atxy6:"
    "chip=3216,"
    "clock=20internal,"
    "millis=enabled,"
    "startuptime=8,"
    "bodvoltage=1v8,"
    "bodmode=disabled,"
    "eesave=enable,"
    "resetpin=UPDI,"
    "printf=default,"
    "wiremode=mors,"
    "WDTtimeout=disabled,"
    "WDTwindow=disabled,"
    "PWMmux=A_default,"
    "attach=allenabled",
)
ARDUINO_PROGRAMMER = os.environ.get("ARDUINO_PROGRAMMER", "serialupdi57k")
ARDUINO_VERIFY_UPLOAD = os.environ.get("ARDUINO_VERIFY_UPLOAD", "").lower() in {
    "1",
    "true",
    "yes",
}
FIRMWARE_TARGETS = {
    "main2": {
        "source": "src/main2.cpp",
        "sketch": "main2",
        "label": "main2.cpp - TOTP token",
        "description": "Production token firmware with TOTP, PB0 LCD power, UART provisioning, and low-power sleep.",
    },
    "main3": {
        "source": "src/main3.cpp",
        "sketch": "main3",
        "label": "main3.cpp - 3-profile token",
        "description": "Experimental three-profile token firmware with blank defaults and reset-mode-only provisioning.",
    },
    "main3_rtc_sync_test": {
        "source": "src/main3_rtc_sync_test.cpp",
        "sketch": "main3_rtc_sync_test",
        "label": "main3_rtc_sync_test.cpp - main3 clock sync test",
        "description": "Low-power RTC count sync test based on main3 board setup; emits UART SYNC samples on button wake.",
    },
    "rtc_sync_test": {
        "source": "src/rtc_sync_test_elapsed.cpp",
        "sketch": "rtc_sync_test_elapsed",
        "label": "rtc_sync_test_elapsed.cpp - RTC elapsed test",
        "description": "Low-power RTC elapsed-count test with PB0 LCD power and UART status.",
    },
}
FIRMWARE_TARGET_ALIASES = {
    "main2.cpp": "main2",
    "main3.cpp": "main3",
    "main3_rtc_sync_test.cpp": "main3_rtc_sync_test",
    "rtc_sync_test_elapsed.cpp": "rtc_sync_test",
    "rtc_sync_test_serial": "rtc_sync_test",
    "rtc_sync_test_serial.cpp": "rtc_sync_test",
}
_RAW_DEFAULT_FLASH_TARGET = os.environ.get("FLASH_TARGET", MAIN2_FLASH_TARGET)


def normalize_firmware_target(target=None):
    name = str(target or _RAW_DEFAULT_FLASH_TARGET).strip()
    name = FIRMWARE_TARGET_ALIASES.get(name, name)
    if name not in FIRMWARE_TARGETS:
        choices = ", ".join(sorted(FIRMWARE_TARGETS))
        raise ValueError(f"Unknown firmware target '{target}'. Choose one of: {choices}")
    return name


DEFAULT_FLASH_TARGET = normalize_firmware_target(_RAW_DEFAULT_FLASH_TARGET)
_MOCK_TOKEN_SECRET_HEX = "00" * 20
_MOCK_TOKEN_PROVISIONED = True
_PORT_LOCKS = {}
_PORT_LOCKS_GUARD = threading.Lock()


class HardwareError(RuntimeError):
    pass


class ProtocolError(HardwareError):
    pass


def _require_serial():
    if serial is None:
        raise HardwareError(
            "pyserial is not installed. Install backend requirements first."
        )


def _port_lock(port):
    key = str(port or "").upper()
    with _PORT_LOCKS_GUARD:
        lock = _PORT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PORT_LOCKS[key] = lock
        return lock


def _is_access_denied_error(exc):
    message = str(exc)
    return (
        "Access is denied" in message
        or "PermissionError(13" in message
        or "PermissionError: [Errno 13]" in message
    )


def open_serial_port(port, baud, timeout=0.2, dtr=False, rts=False):
    _require_serial()
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = timeout
    ser.write_timeout = 2
    ser.dtr = bool(dtr)
    ser.rts = bool(rts)
    ser.open()
    ser.dtr = bool(dtr)
    ser.rts = bool(rts)
    return ser


def token_uart_rts_candidates():
    if TOKEN_UART_RTS in {"1", "true", "yes", "high", "on"}:
        return [True]
    if TOKEN_UART_RTS in {"0", "false", "no", "low", "off"}:
        return [False]
    return [False, True]


def list_serial_ports():
    if HARDWARE_MOCK:
        return [
            {
                "device": "MOCK",
                "description": "Mock serial device",
                "hwid": "HARDWARE_MOCK=1",
            }
        ]

    if list_ports is None:
        return []

    ports = []
    for port in list_ports.comports():
        ports.append(
            {
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid,
            }
        )
    return ports


def list_firmware_envs(platformio_ini_path=None):
    envs = []
    for name, config in FIRMWARE_TARGETS.items():
        envs.append(
            {
                "name": name,
                "label": config["label"],
                "source": config["source"],
                "description": config["description"],
                "fqbn": ARDUINO_FQBN,
                "programmer": ARDUINO_PROGRAMMER,
                "recommended": name == DEFAULT_FLASH_TARGET,
                "dev": name != "main2",
            }
        )
    return envs


def resolve_arduino_cli_exe():
    configured = os.environ.get("ARDUINO_CLI_EXE")
    if configured:
        return configured

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        bundled_cli = (
            Path(local_app_data)
            / "Programs"
            / "Arduino IDE"
            / "resources"
            / "app"
            / "lib"
            / "backend"
            / "resources"
            / "arduino-cli.exe"
        )
        if bundled_cli.exists():
            return str(bundled_cli)

    return "arduino-cli"


def _read_protocol_line(ser, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if line:
            return line
    raise ProtocolError("Timed out waiting for serial response")


def _read_optional_protocol_line(ser, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if line:
            return line
    return None


def switch_adapter_mode(
    port,
    mode,
    baud=DEFAULT_ADAPTER_BAUD,
    timeout=2,
    require_ack=ADAPTER_REQUIRE_ACK,
    open_delay=ADAPTER_OPEN_DELAY_SECONDS,
):
    mode = str(mode).strip().upper()
    if mode not in {"UPDI", "UART"}:
        raise ValueError("mode must be UPDI or UART")

    if HARDWARE_MOCK:
        return f"OK MODE {mode}"

    if not port:
        raise HardwareError("No adapter control port selected")

    _require_serial()
    with _port_lock(port):
        try:
            with open_serial_port(port, baud, timeout=0.2) as ser:
                if open_delay > 0:
                    time.sleep(open_delay)
                ser.reset_input_buffer()
                ser.write(f"MODE {mode}\n".encode("ascii"))
                ser.flush()

                if not require_ack:
                    line = _read_optional_protocol_line(ser, timeout)
                    if not line:
                        return f"SENT MODE {mode} (no adapter acknowledgement)"
                    if line.startswith("ERR "):
                        raise ProtocolError(line)
                    accepted = {
                        "OK",
                        f"OK {mode}",
                        f"OK MODE {mode}",
                    }
                    if line in accepted:
                        return f"OK MODE {mode}"
                    if line in {mode, f"MODE {mode}"}:
                        return (
                            f"SENT MODE {mode}; saw serial echo only, not an adapter "
                            "acknowledgement"
                        )
                    return f"SENT MODE {mode}; adapter replied: {line}"

                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    line = _read_protocol_line(
                        ser, max(0.1, deadline - time.monotonic())
                    )
                    if line == f"OK MODE {mode}":
                        return line
                    if line.startswith("ERR "):
                        raise ProtocolError(line)
        except ProtocolError:
            raise
        except SERIAL_EXCEPTIONS as exc:
            raise HardwareError(f"Could not use adapter port {port}: {exc}") from exc

    raise ProtocolError(f"Adapter did not confirm MODE {mode}")


def build_token_command(command, secret_hex=None, timestep=None, challenge_hex=None):
    command = command.strip().upper()
    if command in {
        "HELLO",
        "STATUS",
        "READ_RTC",
        "RESET_TIME",
        "RESET_ARM",
        "UNREGISTER",
    }:
        return command

    if command == "CHALLENGE":
        if not is_challenge_hex(challenge_hex):
            raise ValueError("challenge_hex must be 32 hex characters")
        return f"CHALLENGE {challenge_hex.lower()}"

    if command not in {"PROVISION", "RESET_ALL"}:
        raise ValueError(f"Unknown token command: {command}")

    if not is_secret_hex(secret_hex):
        raise ValueError("secret_hex must be 40 hex characters")

    timestep = int(timestep)
    if timestep <= 0:
        raise ValueError("timestep must be positive")

    return f"{command} {secret_hex.lower()} {timestep}"


def is_secret_hex(value):
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", str(value or "")))


def is_challenge_hex(value):
    return bool(re.fullmatch(r"[0-9a-fA-F]{32}", str(value or "")))


def parse_status_response(line):
    match = re.fullmatch(
        r"OK STATUS STEP=(?P<step>\d+) ELAPSED=(?P<elapsed>\d+) "
        r"PROVISIONED=(?P<provisioned>[01])",
        line.strip(),
    )
    if not match:
        raise ProtocolError(f"Unexpected STATUS response: {line}")

    return {
        "step": int(match.group("step")),
        "elapsed": int(match.group("elapsed")),
        "provisioned": match.group("provisioned") == "1",
    }


def parse_rtc_response(line):
    match = re.fullmatch(
        r"OK RTC RAW=(?P<raw>\d+) ELAPSED=(?P<elapsed>\d+) "
        r"CNT=(?P<cnt>\d+) OVF=(?P<ovf>\d+) STATUS=(?P<status>\d+) "
        r"FLAGS=(?P<flags>\d+) CLK=(?P<clk>EXT|INT)",
        line.strip(),
    )
    if not match:
        raise ProtocolError(f"Unexpected READ_RTC response: {line}")

    return {
        "raw_seconds": int(match.group("raw")),
        "elapsed": int(match.group("elapsed")),
        "counter": int(match.group("cnt")),
        "overflow_seconds": int(match.group("ovf")),
        "status": int(match.group("status")),
        "flags": int(match.group("flags")),
        "clock": match.group("clk"),
    }


def parse_challenge_response(line):
    match = re.fullmatch(
        r"OK CHALLENGE (?P<digest>[0-9a-fA-F]{40}) "
        r"PROVISIONED=(?P<provisioned>[01])",
        line.strip(),
    )
    if not match:
        raise ProtocolError(f"Unexpected CHALLENGE response: {line}")

    return {
        "digest": match.group("digest").lower(),
        "provisioned": match.group("provisioned") == "1",
    }


def _mock_token_response(command_line):
    global _MOCK_TOKEN_SECRET_HEX, _MOCK_TOKEN_PROVISIONED

    command = command_line.split(" ", 1)[0].upper()
    if command == "HELLO":
        return "OK HELLO TOKEN mock-1.0"
    if command == "STATUS":
        return (
            "OK STATUS STEP=30 ELAPSED=0 "
            f"PROVISIONED={1 if _MOCK_TOKEN_PROVISIONED else 0}"
        )
    if command == "READ_RTC":
        return "OK RTC RAW=1234 ELAPSED=0 CNT=1234 OVF=0 STATUS=0 FLAGS=0 CLK=EXT"
    if command == "CHALLENGE":
        _, challenge_hex = command_line.split(" ", 1)
        digest = hmac.new(
            bytes.fromhex(_MOCK_TOKEN_SECRET_HEX),
            bytes.fromhex(challenge_hex),
            hashlib.sha1,
        ).hexdigest()
        return (
            f"OK CHALLENGE {digest} "
            f"PROVISIONED={1 if _MOCK_TOKEN_PROVISIONED else 0}"
        )
    if command in {"PROVISION", "RESET_ALL"}:
        parts = command_line.split()
        if len(parts) >= 3 and is_secret_hex(parts[1]):
            _MOCK_TOKEN_SECRET_HEX = parts[1].lower()
            _MOCK_TOKEN_PROVISIONED = True
        return f"OK {command}"
    if command == "RESET_TIME":
        return f"OK {command}"
    if command == "RESET_ARM":
        return f"OK {command}"
    if command == "UNREGISTER":
        _MOCK_TOKEN_PROVISIONED = False
        return "OK UNREGISTER"
    return "ERR UNKNOWN Unsupported mock command"


def _expected_ok_prefixes(expected_command):
    prefixes = [f"OK {expected_command}"]
    if expected_command == "HELLO":
        prefixes.append("OK HELLO TOKEN ")
    if expected_command == "READ_RTC":
        prefixes.append("OK RTC ")
    return tuple(prefixes)


def _serial_loopback_error(expected_command, rts_attempts):
    attempted = ", ".join("RTS high" if value else "RTS low" for value in rts_attempts)
    return ProtocolError(
        "Serial loopback detected while waiting for "
        f"{expected_command}. The adapter echoed the command back, but the ATtiny "
        f"did not reply after trying {attempted}. Make sure the adapter is on the "
        "UART path, the selected serial port is the adapter/token COM port, the "
        "latest firmware has been flashed, and the token is awake. If it has been "
        "idle for a while, press the token button once and try again."
    )


def _send_token_command_once(port, command_line, baud, timeout, rts):
    expected_command = command_line.split(" ", 1)[0].upper()
    saw_serial_echo = False
    try:
        with open_serial_port(port, baud, timeout=0.2, rts=rts) as ser:
            ser.reset_input_buffer()
            ser.write((command_line + "\n").encode("ascii"))
            ser.flush()

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    line = _read_protocol_line(
                        ser, max(0.1, deadline - time.monotonic())
                    )
                except ProtocolError:
                    if saw_serial_echo:
                        raise _serial_loopback_error(expected_command, [rts])
                    raise
                if line == command_line or line == expected_command:
                    saw_serial_echo = True
                    continue
                if line.startswith("ERR "):
                    raise ProtocolError(line)
                if line.startswith(_expected_ok_prefixes(expected_command)):
                    return line

            if saw_serial_echo:
                raise _serial_loopback_error(expected_command, [rts])
            raise ProtocolError(f"Timed out waiting for OK {expected_command}")
    except ProtocolError:
        raise
    except SERIAL_EXCEPTIONS as exc:
        raise HardwareError(f"Could not use token UART port {port}: {exc}") from exc


def _send_token_command_unlocked(port, command_line, baud, timeout):
    expected_command = command_line.split(" ", 1)[0].upper()
    rts_attempts = token_uart_rts_candidates()
    loopback_attempts = []
    last_error = None

    for rts in rts_attempts:
        try:
            return _send_token_command_once(port, command_line, baud, timeout, rts)
        except ProtocolError as exc:
            last_error = exc
            if "Serial loopback detected" not in str(exc):
                raise
            loopback_attempts.append(rts)

    if loopback_attempts:
        raise _serial_loopback_error(expected_command, loopback_attempts)
    raise last_error or ProtocolError(f"Timed out waiting for OK {expected_command}")


def send_token_command(port, command_line, baud=DEFAULT_TOKEN_BAUD, timeout=3):
    if HARDWARE_MOCK:
        return _mock_token_response(command_line)

    if not port:
        raise HardwareError("No token UART port selected")

    _require_serial()
    with _port_lock(port):
        last_error = None
        for attempt in range(SERIAL_OPEN_ATTEMPTS):
            try:
                return _send_token_command_unlocked(port, command_line, baud, timeout)
            except HardwareError as exc:
                last_error = exc
                if (
                    not _is_access_denied_error(exc)
                    or attempt >= SERIAL_OPEN_ATTEMPTS - 1
                ):
                    raise
                time.sleep(SERIAL_OPEN_RETRY_DELAY_SECONDS * (attempt + 1))

    raise last_error or HardwareError(f"Could not use token UART port {port}")


def token_hello(port, baud=DEFAULT_TOKEN_BAUD):
    return send_token_command(port, build_token_command("HELLO"), baud=baud)


def token_status(port, baud=DEFAULT_TOKEN_BAUD):
    line = send_token_command(port, build_token_command("STATUS"), baud=baud)
    return {"raw": line, **parse_status_response(line)}


def token_read_rtc(port, baud=DEFAULT_TOKEN_BAUD):
    line = send_token_command(port, build_token_command("READ_RTC"), baud=baud)
    return {"reply": line, **parse_rtc_response(line)}


def token_challenge(port, challenge_hex, baud=DEFAULT_TOKEN_BAUD):
    line = send_token_command(
        port,
        build_token_command("CHALLENGE", challenge_hex=challenge_hex),
        baud=baud,
    )
    return {"reply": line, **parse_challenge_response(line)}


def token_provision(port, secret_hex, timestep, baud=DEFAULT_TOKEN_BAUD):
    command = build_token_command("PROVISION", secret_hex, timestep)
    return send_token_command(port, command, baud=baud)


def token_reset_time(port, baud=DEFAULT_TOKEN_BAUD):
    return send_token_command(port, build_token_command("RESET_TIME"), baud=baud)


def token_reset_arm(port, baud=DEFAULT_TOKEN_BAUD):
    return send_token_command(port, build_token_command("RESET_ARM"), baud=baud)


def token_reset_all(port, secret_hex, timestep, baud=DEFAULT_TOKEN_BAUD):
    command = build_token_command("RESET_ALL", secret_hex, timestep)
    return send_token_command(port, command, baud=baud)


def token_unregister(port, baud=DEFAULT_TOKEN_BAUD):
    return send_token_command(port, build_token_command("UNREGISTER"), baud=baud)


def read_serial_lines(port, baud=DEFAULT_TOKEN_BAUD, duration=2.0):
    if HARDWARE_MOCK:
        return ["OK STATUS STEP=30 ELAPSED=123 PROVISIONED=1"]

    if not port:
        raise HardwareError("No token UART port selected")

    _require_serial()
    lines = []
    deadline = time.monotonic() + max(0.2, float(duration))

    with _port_lock(port):
        try:
            with open_serial_port(port, baud, timeout=0.1) as ser:
                while time.monotonic() < deadline:
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        lines.append(line)
        except SERIAL_EXCEPTIONS as exc:
            raise HardwareError(f"Could not read token UART port {port}: {exc}") from exc

    return lines


class FlashJobManager:
    def __init__(
        self,
        project_root=PROJECT_ROOT,
        arduino_cli_exe=None,
        fqbn=None,
        programmer=None,
    ):
        self.project_root = Path(project_root)
        self.arduino_cli_exe = arduino_cli_exe or resolve_arduino_cli_exe()
        self.fqbn = fqbn or ARDUINO_FQBN
        self.programmer = programmer or ARDUINO_PROGRAMMER
        self.library_dir = self.project_root / "lib"
        self.build_root = self.project_root / ".arduino-build"
        self.jobs = {}
        self._lock = threading.Lock()

    def start_flash(
        self,
        target=DEFAULT_FLASH_TARGET,
        upload_port=None,
        adapter_port=None,
        switch_mode=False,
    ):
        target = normalize_firmware_target(target)
        target_config = self._target_config(target)
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "status": "queued",
            "target": target,
            "env": target,
            "source": target_config["source"],
            "label": target_config["label"],
            "upload_port": upload_port,
            "adapter_port": adapter_port,
            "switch_mode": bool(switch_mode),
            "tool": "arduino-cli",
            "fqbn": self.fqbn,
            "programmer": self.programmer,
            "logs": [],
            "returncode": None,
            "started_at": time.time(),
            "finished_at": None,
        }

        with self._lock:
            self.jobs[job_id] = job

        thread = threading.Thread(target=self._run_flash, args=(job_id,), daemon=True)
        thread.start()
        return job

    def get_job(self, job_id):
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            return dict(job, logs=list(job["logs"]))

    def _append_log(self, job_id, line):
        with self._lock:
            job = self.jobs.get(job_id)
            if job:
                job["logs"].append(line.rstrip())
                job["logs"] = job["logs"][-400:]

    def _set_status(self, job_id, status, returncode=None):
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job["status"] = status
            if returncode is not None:
                job["returncode"] = returncode
            if status in {"succeeded", "failed"}:
                job["finished_at"] = time.time()

    def _target_config(self, target):
        name = normalize_firmware_target(target)
        config = dict(FIRMWARE_TARGETS[name])
        config["name"] = name
        config["source_file"] = self.project_root / config["source"]
        return config

    def _prepare_arduino_sketch(self, job_id, target=DEFAULT_FLASH_TARGET):
        target_config = self._target_config(target)
        source_file = target_config["source_file"]
        if not source_file.exists():
            raise HardwareError(f"Firmware source not found: {source_file}")

        job_root = self.build_root / job_id
        sketch_dir = job_root / target_config["sketch"]
        build_dir = job_root / "build"
        sketch_dir.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, sketch_dir / f"{target_config['sketch']}.ino")
        return sketch_dir, build_dir

    def _microchip_logging_config(self):
        config_path = self.build_root / "pymcuprog-console-logging.yaml"
        if not config_path.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "disable_existing_loggers: False",
                        "formatters:",
                        "  detailed:",
                        '    format: "%(name)s - %(levelname)s - %(message)s"',
                        "handlers:",
                        "  console:",
                        "    class: logging.StreamHandler",
                        "    level: WARNING",
                        "    formatter: detailed",
                        "    stream: ext://sys.stdout",
                        "loggers:",
                        "  pyedbglib:",
                        "    level: ERROR",
                        "    handlers: [console]",
                        "    propagate: no",
                        "root:",
                        "  level: WARNING",
                        "  handlers: [console]",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        return config_path

    def _compile_command(self, job_id, target=DEFAULT_FLASH_TARGET):
        sketch_dir, build_dir = self._prepare_arduino_sketch(job_id, target)
        return [
            self.arduino_cli_exe,
            "compile",
            "--clean",
            "--fqbn",
            self.fqbn,
            "--libraries",
            str(self.library_dir),
            "--build-path",
            str(build_dir),
            str(sketch_dir),
        ]

    def _upload_command(self, job_id, target=DEFAULT_FLASH_TARGET, upload_port=None):
        target_config = self._target_config(target)
        sketch_dir = self.build_root / job_id / target_config["sketch"]
        build_dir = self.build_root / job_id / "build"
        command = [
            self.arduino_cli_exe,
            "upload",
            "--fqbn",
            self.fqbn,
            "--input-dir",
            str(build_dir),
            "--programmer",
            self.programmer,
        ]
        if ARDUINO_VERIFY_UPLOAD:
            command.append("--verify")
        if upload_port:
            command.extend(["--port", upload_port])
        command.append(str(sketch_dir))
        return command

    def _find_hex_file(self, job_id):
        build_dir = self.build_root / job_id / "build"
        candidates = sorted(build_dir.glob("*.hex"))
        if not candidates:
            candidates = sorted(build_dir.rglob("*.hex"))
        return candidates[0] if candidates else None

    def _run_command(self, job_id, command, phase):
        self._append_log(job_id, f"{phase}: " + subprocess.list2cmdline(command))
        env = os.environ.copy()
        env["MICROCHIP_PYTHONTOOLS_CONFIG"] = str(self._microchip_logging_config())
        process = subprocess.Popen(
            command,
            cwd=self.project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        assert process.stdout is not None
        for line in process.stdout:
            self._append_log(job_id, line)

        returncode = process.wait()
        self._append_log(job_id, f"{phase} exit code: {returncode}")
        return returncode

    def _run_flash(self, job_id):
        job = self.get_job(job_id)
        if not job:
            return

        self._set_status(job_id, "running")
        try:
            target = normalize_firmware_target(job.get("target"))
            target_config = self._target_config(target)
            if job.get("adapter_port") and job.get("switch_mode"):
                self._append_log(job_id, "Switching adapter to UPDI mode...")
                reply = switch_adapter_mode(job["adapter_port"], "UPDI")
                self._append_log(job_id, reply)
                if UPDI_SETTLE_SECONDS > 0:
                    self._append_log(
                        job_id,
                        f"Waiting {UPDI_SETTLE_SECONDS:g}s for the UPDI path to settle...",
                    )
                    time.sleep(UPDI_SETTLE_SECONDS)
            elif job.get("adapter_port"):
                self._append_log(
                    job_id,
                    "Using the currently selected adapter mode. Switch to UPDI before flashing.",
                )

            if HARDWARE_MOCK:
                self._append_log(
                    job_id,
                    "HARDWARE_MOCK=1: real Arduino SerialUPDI upload is disabled.",
                )
                self._append_log(
                    job_id,
                    "Restart the backend without HARDWARE_MOCK to flash physical hardware.",
                )
                self._set_status(job_id, "failed", 1)
                return

            self._append_log(
                job_id,
                f"Flashing {target_config['source']} with Arduino CLI, megaTinyCore, and SerialUPDI SLOW.",
            )
            self._append_log(job_id, f"FQBN: {self.fqbn}")
            self._append_log(job_id, f"Programmer: {self.programmer}")
            self._append_log(job_id, f"Upload port: {job.get('upload_port') or '(auto)'}")

            compile_command = self._compile_command(job_id, target)
            compile_returncode = self._run_command(job_id, compile_command, "Compile")
            if compile_returncode != 0:
                self._set_status(job_id, "failed", compile_returncode)
                return

            hex_file = self._find_hex_file(job_id)
            self._append_log(
                job_id,
                f"Compiled hex: {hex_file if hex_file else 'not found in build folder'}",
            )

            upload_command = self._upload_command(
                job_id, target, job.get("upload_port")
            )
            upload_returncode = self._run_command(job_id, upload_command, "Upload")

            self._set_status(
                job_id,
                "succeeded" if upload_returncode == 0 else "failed",
                upload_returncode,
            )
        except Exception as exc:
            self._append_log(job_id, f"ERROR: {exc}")
            self._set_status(job_id, "failed", 1)
