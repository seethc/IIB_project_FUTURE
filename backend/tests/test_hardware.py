import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hardware
from hardware import (
    build_token_command,
    is_secret_hex,
    parse_challenge_response,
    list_firmware_envs,
    parse_rtc_response,
    parse_status_response,
    ProtocolError,
    token_reset_all,
    token_unregister,
)


class HardwareProtocolTest(unittest.TestCase):
    def test_build_token_command(self):
        secret = "00" * 20

        self.assertEqual(build_token_command("HELLO"), "HELLO")
        self.assertEqual(build_token_command("READ_RTC"), "READ_RTC")
        self.assertEqual(build_token_command("RESET_ARM"), "RESET_ARM")
        self.assertEqual(build_token_command("UNREGISTER"), "UNREGISTER")
        self.assertEqual(
            build_token_command("CHALLENGE", challenge_hex="aa" * 16),
            f"CHALLENGE {'aa' * 16}",
        )
        self.assertEqual(
            build_token_command("RESET_ALL", secret, 30),
            f"RESET_ALL {secret} 30",
        )

    def test_secret_hex_validation(self):
        self.assertTrue(is_secret_hex("a1" * 20))
        self.assertFalse(is_secret_hex("a1" * 19))
        self.assertFalse(is_secret_hex("zz" * 20))

    def test_parse_status_response(self):
        status = parse_status_response("OK STATUS STEP=30 ELAPSED=42 PROVISIONED=1")

        self.assertEqual(status["step"], 30)
        self.assertEqual(status["elapsed"], 42)
        self.assertTrue(status["provisioned"])

    def test_parse_read_rtc_response(self):
        rtc = parse_rtc_response(
            "OK RTC RAW=7212 ELAPSED=45 CNT=7212 OVF=0 STATUS=0 FLAGS=0 CLK=EXT"
        )

        self.assertEqual(rtc["raw_seconds"], 7212)
        self.assertEqual(rtc["elapsed"], 45)
        self.assertEqual(rtc["counter"], 7212)
        self.assertEqual(rtc["overflow_seconds"], 0)
        self.assertEqual(rtc["clock"], "EXT")

    def test_parse_challenge_response(self):
        proof = parse_challenge_response(
            f"OK CHALLENGE {'12' * 20} PROVISIONED=1"
        )

        self.assertEqual(proof["digest"], "12" * 20)
        self.assertTrue(proof["provisioned"])

    def test_mock_token_reset_all(self):
        old_mock = hardware.HARDWARE_MOCK
        hardware.HARDWARE_MOCK = True
        try:
            self.assertEqual(token_reset_all("MOCK", "11" * 20, 30), "OK RESET_ALL")
            self.assertEqual(token_unregister("MOCK"), "OK UNREGISTER")
        finally:
            hardware.HARDWARE_MOCK = old_mock

    def test_flash_command_uses_arduino_cli_serialupdi_for_main2(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project_root = Path(tempdir)
            (project_root / "src").mkdir()
            (project_root / "lib").mkdir()
            (project_root / "src" / "main2.cpp").write_text(
                "#include <Arduino.h>\nvoid setup() {}\nvoid loop() {}\n",
                encoding="utf-8",
            )
            (project_root / "src" / "rtc_sync_test_elapsed.cpp").write_text(
                "#include <Arduino.h>\nvoid setup() {}\nvoid loop() {}\n",
                encoding="utf-8",
            )
            (project_root / "src" / "main3.cpp").write_text(
                "#include <Arduino.h>\nvoid setup() {}\nvoid loop() {}\n",
                encoding="utf-8",
            )

            manager = hardware.FlashJobManager(
                project_root=project_root,
                arduino_cli_exe="arduino-cli",
                fqbn="megaTinyCore:megaavr:atxy6:chip=3216,clock=20internal",
                programmer="serialupdi57k",
            )
            compile_command = manager._compile_command("job123", "main2")
            upload_command = manager._upload_command("job123", "main2", "COM4")

            self.assertEqual(compile_command[:2], ["arduino-cli", "compile"])
            self.assertIn("--clean", compile_command)
            self.assertNotIn("--upload", compile_command)
            self.assertEqual(upload_command[:2], ["arduino-cli", "upload"])
            self.assertIn("--programmer", upload_command)
            self.assertIn("serialupdi57k", upload_command)
            self.assertNotIn("--verify", upload_command)
            self.assertIn("--port", upload_command)
            self.assertIn("COM4", upload_command)
            sketch = project_root / ".arduino-build" / "job123" / "main2" / "main2.ino"
            self.assertTrue(sketch.exists())

    def test_firmware_targets_include_rtc_sync_test(self):
        targets = {target["name"]: target for target in list_firmware_envs()}

        self.assertIn("main2", targets)
        self.assertIn("main3", targets)
        self.assertIn("rtc_sync_test", targets)
        self.assertTrue(targets["main2"]["recommended"])
        self.assertEqual(targets["main3"]["source"], "src/main3.cpp")
        self.assertEqual(targets["rtc_sync_test"]["source"], "src/rtc_sync_test_elapsed.cpp")

    def test_flash_command_can_prepare_rtc_sync_test(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project_root = Path(tempdir)
            (project_root / "src").mkdir()
            (project_root / "lib").mkdir()
            (project_root / "src" / "rtc_sync_test_elapsed.cpp").write_text(
                "#include <Arduino.h>\nvoid setup() {}\nvoid loop() {}\n",
                encoding="utf-8",
            )

            manager = hardware.FlashJobManager(
                project_root=project_root,
                arduino_cli_exe="arduino-cli",
                fqbn="megaTinyCore:megaavr:atxy6:chip=3216,clock=20internal",
                programmer="serialupdi57k",
            )
            compile_command = manager._compile_command("job456", "rtc_sync_test")
            upload_command = manager._upload_command("job456", "rtc_sync_test", "COM4")

            self.assertEqual(compile_command[:2], ["arduino-cli", "compile"])
            self.assertEqual(upload_command[:2], ["arduino-cli", "upload"])
            sketch = (
                project_root
                / ".arduino-build"
                / "job456"
                / "rtc_sync_test_elapsed"
                / "rtc_sync_test_elapsed.ino"
            )
            self.assertTrue(sketch.exists())

    def test_flash_command_can_prepare_main3(self):
        with tempfile.TemporaryDirectory() as tempdir:
            project_root = Path(tempdir)
            (project_root / "src").mkdir()
            (project_root / "lib").mkdir()
            (project_root / "src" / "main3.cpp").write_text(
                "#include <Arduino.h>\nvoid setup() {}\nvoid loop() {}\n",
                encoding="utf-8",
            )

            manager = hardware.FlashJobManager(
                project_root=project_root,
                arduino_cli_exe="arduino-cli",
                fqbn="megaTinyCore:megaavr:atxy6:chip=3216,clock=20internal",
                programmer="serialupdi57k",
            )
            compile_command = manager._compile_command("job789", "main3")
            upload_command = manager._upload_command("job789", "main3", "COM4")

            self.assertEqual(compile_command[:2], ["arduino-cli", "compile"])
            self.assertEqual(upload_command[:2], ["arduino-cli", "upload"])
            sketch = project_root / ".arduino-build" / "job789" / "main3" / "main3.ino"
            self.assertTrue(sketch.exists())

    def test_mock_flash_job_fails_instead_of_claiming_success(self):
        old_mock = hardware.HARDWARE_MOCK
        hardware.HARDWARE_MOCK = True
        try:
            manager = hardware.FlashJobManager(arduino_cli_exe="arduino-cli")
            job = manager.start_flash("main2", upload_port="COM4")

            deadline = time.monotonic() + 2
            current = manager.get_job(job["id"])
            while current["status"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(0.02)
                current = manager.get_job(job["id"])

            self.assertEqual(current["status"], "failed")
            self.assertIn(
                "real Arduino SerialUPDI upload is disabled",
                "\n".join(current["logs"]),
            )
        finally:
            hardware.HARDWARE_MOCK = old_mock

    def test_token_command_reports_serial_loopback(self):
        class FakeSerial:
            def __init__(self):
                self.lines = [b"HELLO\n", b""]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def reset_input_buffer(self):
                pass

            def write(self, data):
                self.written = data

            def flush(self):
                pass

            def readline(self):
                return self.lines.pop(0) if self.lines else b""

        old_open = hardware.open_serial_port
        old_mock = hardware.HARDWARE_MOCK
        hardware.HARDWARE_MOCK = False
        hardware.open_serial_port = lambda *args, **kwargs: FakeSerial()
        try:
            with self.assertRaisesRegex(ProtocolError, "Serial loopback detected"):
                hardware.send_token_command("COM4", "HELLO", timeout=0.01)
        finally:
            hardware.open_serial_port = old_open
            hardware.HARDWARE_MOCK = old_mock

    def test_read_rtc_accepts_ok_rtc_response(self):
        class FakeSerial:
            def __init__(self):
                self.lines = [
                    b"READ_RTC\n",
                    b"OK RTC RAW=10 ELAPSED=2 CNT=10 OVF=0 STATUS=0 FLAGS=0 CLK=EXT\n",
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def reset_input_buffer(self):
                pass

            def write(self, data):
                self.written = data

            def flush(self):
                pass

            def readline(self):
                return self.lines.pop(0) if self.lines else b""

        old_open = hardware.open_serial_port
        old_mock = hardware.HARDWARE_MOCK
        hardware.HARDWARE_MOCK = False
        hardware.open_serial_port = lambda *args, **kwargs: FakeSerial()
        try:
            self.assertEqual(
                hardware.send_token_command("COM4", "READ_RTC", timeout=0.01),
                "OK RTC RAW=10 ELAPSED=2 CNT=10 OVF=0 STATUS=0 FLAGS=0 CLK=EXT",
            )
        finally:
            hardware.open_serial_port = old_open
            hardware.HARDWARE_MOCK = old_mock

    def test_token_command_retries_access_denied_open(self):
        class FakeSerial:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def reset_input_buffer(self):
                pass

            def write(self, data):
                self.written = data

            def flush(self):
                pass

            def readline(self):
                return b"OK HELLO TOKEN retry-test\n"

        calls = {"count": 0}

        def fake_open(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("PermissionError(13, 'Access is denied.', None, 5)")
            return FakeSerial()

        old_open = hardware.open_serial_port
        old_mock = hardware.HARDWARE_MOCK
        old_attempts = hardware.SERIAL_OPEN_ATTEMPTS
        old_delay = hardware.SERIAL_OPEN_RETRY_DELAY_SECONDS
        hardware.HARDWARE_MOCK = False
        hardware.SERIAL_OPEN_ATTEMPTS = 2
        hardware.SERIAL_OPEN_RETRY_DELAY_SECONDS = 0
        hardware.open_serial_port = fake_open
        try:
            self.assertEqual(
                hardware.send_token_command("COM4", "HELLO", timeout=0.01),
                "OK HELLO TOKEN retry-test",
            )
            self.assertEqual(calls["count"], 2)
        finally:
            hardware.open_serial_port = old_open
            hardware.HARDWARE_MOCK = old_mock
            hardware.SERIAL_OPEN_ATTEMPTS = old_attempts
            hardware.SERIAL_OPEN_RETRY_DELAY_SECONDS = old_delay


if __name__ == "__main__":
    unittest.main()
