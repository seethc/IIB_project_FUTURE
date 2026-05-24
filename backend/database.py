import os
import sqlite3
from pathlib import Path

from totp_utils import DEFAULT_TIMESTEP_SECONDS


DB_PATH = Path(
    os.environ.get("TOKEN_DB_PATH", Path(__file__).with_name("devices.db"))
)


def get_db_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            secret_key TEXT NOT NULL,
            sync_time INTEGER NOT NULL,
            timestep INTEGER NOT NULL DEFAULT 30,
            patient_name TEXT NOT NULL DEFAULT '',
            patient_age INTEGER,
            patient_phone TEXT NOT NULL DEFAULT '',
            patient_emergency_contact TEXT NOT NULL DEFAULT '',
            patient_allergies TEXT NOT NULL DEFAULT '',
            patient_notes TEXT NOT NULL DEFAULT ''
        )
        """
    )

    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(devices)").fetchall()
    }
    if "timestep" not in columns:
        conn.execute(
            "ALTER TABLE devices ADD COLUMN timestep INTEGER NOT NULL DEFAULT 30"
        )
    if "patient_name" not in columns:
        conn.execute(
            "ALTER TABLE devices ADD COLUMN patient_name TEXT NOT NULL DEFAULT ''"
        )
    if "patient_age" not in columns:
        conn.execute("ALTER TABLE devices ADD COLUMN patient_age INTEGER")
    if "patient_phone" not in columns:
        conn.execute(
            "ALTER TABLE devices ADD COLUMN patient_phone TEXT NOT NULL DEFAULT ''"
        )
    if "patient_emergency_contact" not in columns:
        conn.execute(
            "ALTER TABLE devices ADD COLUMN patient_emergency_contact TEXT NOT NULL DEFAULT ''"
        )
    if "patient_allergies" not in columns:
        conn.execute(
            "ALTER TABLE devices ADD COLUMN patient_allergies TEXT NOT NULL DEFAULT ''"
        )
    if "patient_notes" not in columns:
        conn.execute(
            "ALTER TABLE devices ADD COLUMN patient_notes TEXT NOT NULL DEFAULT ''"
        )

    conn.commit()
    conn.close()


def get_all_devices():
    conn = get_db_connection()
    devices = conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
    conn.close()
    return [dict(device) for device in devices]


def get_device(device_id):
    conn = get_db_connection()
    device = conn.execute(
        "SELECT * FROM devices WHERE id = ?", (device_id,)
    ).fetchone()
    conn.close()
    return dict(device) if device else None


def add_device(name, secret_key, sync_time, timestep=DEFAULT_TIMESTEP_SECONDS):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO devices (name, secret_key, sync_time, timestep)
        VALUES (?, ?, ?, ?)
        """,
        (name, secret_key, sync_time, int(timestep)),
    )
    conn.commit()
    device_id = cursor.lastrowid
    conn.close()
    return device_id


def update_device(device_id, secret_key, sync_time, timestep=None):
    conn = get_db_connection()
    if timestep is None:
        conn.execute(
            "UPDATE devices SET secret_key = ?, sync_time = ? WHERE id = ?",
            (secret_key, sync_time, device_id),
        )
    else:
        conn.execute(
            """
            UPDATE devices
            SET secret_key = ?, sync_time = ?, timestep = ?
            WHERE id = ?
            """,
            (secret_key, sync_time, int(timestep), device_id),
        )
    conn.commit()
    conn.close()


def update_device_name(device_id, name):
    conn = get_db_connection()
    conn.execute("UPDATE devices SET name = ? WHERE id = ?", (name, device_id))
    conn.commit()
    conn.close()


def update_patient_info(device_id, patient_info):
    conn = get_db_connection()
    conn.execute(
        """
        UPDATE devices
        SET patient_name = ?,
            patient_age = ?,
            patient_phone = ?,
            patient_emergency_contact = ?,
            patient_allergies = ?,
            patient_notes = ?
        WHERE id = ?
        """,
        (
            patient_info["patient_name"],
            patient_info["patient_age"],
            patient_info["patient_phone"],
            patient_info["patient_emergency_contact"],
            patient_info["patient_allergies"],
            patient_info["patient_notes"],
            device_id,
        ),
    )
    conn.commit()
    conn.close()


def delete_device(device_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.commit()
    conn.close()
