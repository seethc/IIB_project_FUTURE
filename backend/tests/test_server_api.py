import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


try:
    import flask  # noqa: F401

    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, "Flask is not installed in this Python environment")
class ServerApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["TOKEN_DB_PATH"] = str(Path(self.tempdir.name) / "devices.db")
        os.environ["HARDWARE_MOCK"] = "1"

        for name in ["server", "database", "hardware"]:
            sys.modules.pop(name, None)

        self.server = importlib.import_module("server")
        import hardware

        hardware.HARDWARE_MOCK = True
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_register_and_reset_device_in_mock_mode(self):
        register = self.client.post(
            "/api/register",
            json={"name": "Mock Token", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(register.status_code, 201)
        body = register.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["reply"], "OK RESET_ALL")
        device_id = body["device"]["id"]

        identify = self.client.post("/api/token/identify", json={"uart_port": "MOCK"})
        self.assertEqual(identify.status_code, 200)
        identify_body = identify.get_json()
        self.assertTrue(identify_body["matched"])
        self.assertTrue(identify_body["reset_armed"])
        self.assertEqual(identify_body["device"]["id"], device_id)

        reset = self.client.post(
            f"/api/devices/{device_id}/reset",
            json={"action": "reset_time", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.get_json()["reply"], "OK RESET_TIME")

        default_key = self.client.post(
            f"/api/devices/{device_id}/reset",
            json={"action": "reset_default_key", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(default_key.status_code, 200)
        default_body = default_key.get_json()
        self.assertEqual(default_body["reply"], "OK RESET_ALL")
        self.assertEqual(
            default_body["secret_key"],
            "3132333435363738393031323334353637383930",
        )

        rtc = self.client.post("/api/token/read-rtc", json={"uart_port": "MOCK"})
        self.assertEqual(rtc.status_code, 200)
        rtc_body = rtc.get_json()["rtc"]
        self.assertEqual(rtc_body["raw_seconds"], 1234)
        self.assertEqual(rtc_body["clock"], "EXT")

        verify = self.client.post(
            f"/api/devices/{device_id}/verify", json={"uart_port": "MOCK"}
        )
        self.assertEqual(verify.status_code, 200)
        self.assertTrue(verify.get_json()["verified"])

        delete = self.client.delete(
            f"/api/devices/{device_id}", json={"uart_port": "MOCK"}
        )
        self.assertEqual(delete.status_code, 200)
        self.assertTrue(delete.get_json()["success"])

        identify_after_delete = self.client.post(
            "/api/token/identify", json={"uart_port": "MOCK"}
        )
        self.assertEqual(identify_after_delete.status_code, 200)
        self.assertEqual(identify_after_delete.get_json()["state"], "unregistered")

    def test_developer_delete_can_skip_hardware_verification(self):
        register = self.client.post(
            "/api/register",
            json={"name": "Local Only", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(register.status_code, 201)
        device_id = register.get_json()["device"]["id"]

        delete = self.client.delete(
            f"/api/devices/{device_id}",
            json={
                "uart_port": "MOCK",
                "require_hardware_verification": False,
            },
        )
        self.assertEqual(delete.status_code, 200)
        body = delete.get_json()
        self.assertTrue(body["success"])
        self.assertFalse(body["hardware_unregistered"])

        identify_after_delete = self.client.post(
            "/api/token/identify", json={"uart_port": "MOCK"}
        )
        self.assertEqual(identify_after_delete.status_code, 200)
        self.assertEqual(
            identify_after_delete.get_json()["state"],
            "unknown_registered",
        )

    def test_rename_device(self):
        register = self.client.post(
            "/api/register",
            json={"name": "Before", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(register.status_code, 201)
        device_id = register.get_json()["device"]["id"]

        rename = self.client.patch(
            f"/api/devices/{device_id}",
            json={"name": "After"},
        )
        self.assertEqual(rename.status_code, 200)
        self.assertTrue(rename.get_json()["success"])
        self.assertEqual(rename.get_json()["device"]["name"], "After")

        devices = self.client.get("/api/devices")
        self.assertEqual(devices.status_code, 200)
        self.assertEqual(devices.get_json()["devices"][0]["name"], "After")

    def test_update_patient_info(self):
        register = self.client.post(
            "/api/register",
            json={"name": "Patient Pendant", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(register.status_code, 201)
        device_id = register.get_json()["device"]["id"]

        update = self.client.patch(
            f"/api/devices/{device_id}/patient",
            json={
                "patient_name": "Aisha Patel",
                "patient_age": 42,
                "patient_phone": "07123 456789",
                "patient_emergency_contact": "Sam Patel, 07111 222333",
                "patient_allergies": "Penicillin",
                "patient_notes": "Initial fitting completed.",
            },
        )
        self.assertEqual(update.status_code, 200)
        body = update.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["patient"]["patient_name"], "Aisha Patel")
        self.assertEqual(body["patient"]["patient_age"], 42)

        devices = self.client.get("/api/devices")
        saved = devices.get_json()["devices"][0]
        self.assertEqual(saved["patient_phone"], "07123 456789")
        self.assertEqual(saved["patient_allergies"], "Penicillin")

    def test_update_patient_info_validates_age(self):
        register = self.client.post(
            "/api/register",
            json={"name": "Patient Pendant", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(register.status_code, 201)
        device_id = register.get_json()["device"]["id"]

        update = self.client.patch(
            f"/api/devices/{device_id}/patient",
            json={"patient_age": 180},
        )
        self.assertEqual(update.status_code, 400)
        self.assertFalse(update.get_json()["success"])

    def test_token_unregister_endpoint_resets_unknown_registered_profile(self):
        register = self.client.post(
            "/api/register",
            json={"name": "External Cleanup", "uart_port": "MOCK", "timestep": 30},
        )
        self.assertEqual(register.status_code, 201)
        device_id = register.get_json()["device"]["id"]

        local_delete = self.client.delete(
            f"/api/devices/{device_id}",
            json={
                "uart_port": "MOCK",
                "require_hardware_verification": False,
            },
        )
        self.assertEqual(local_delete.status_code, 200)

        unknown = self.client.post("/api/token/identify", json={"uart_port": "MOCK"})
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.get_json()["state"], "unknown_registered")

        unregister = self.client.post("/api/token/unregister", json={"uart_port": "MOCK"})
        self.assertEqual(unregister.status_code, 200)
        self.assertEqual(unregister.get_json()["reply"], "OK UNREGISTER")

        identify_after_unregister = self.client.post(
            "/api/token/identify", json={"uart_port": "MOCK"}
        )
        self.assertEqual(identify_after_unregister.status_code, 200)
        self.assertEqual(identify_after_unregister.get_json()["state"], "unregistered")


if __name__ == "__main__":
    unittest.main()
