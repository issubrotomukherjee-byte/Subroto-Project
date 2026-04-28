"""
Safe migration: add new columns to the existing 'medicines' table.

Adds columns only if they don't already exist — idempotent and data-safe.
Run once:  python scripts/migrate_medicine_columns.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "neomeds.db")

COLUMNS_TO_ADD = [
    ("brand_name", "TEXT"),
    ("manufacturer", "TEXT"),
    ("dosage_form", "TEXT"),
    ("strength", "TEXT"),
    ("hsn_code", "TEXT"),
    ("schedule_type", "TEXT"),
    ("is_active", "BOOLEAN DEFAULT 1"),
]


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get existing column names
    cursor.execute("PRAGMA table_info(medicines)")
    existing = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in COLUMNS_TO_ADD:
        if col_name not in existing:
            stmt = f"ALTER TABLE medicines ADD COLUMN {col_name} {col_type}"
            cursor.execute(stmt)
            print(f"  ✓ Added column: {col_name}")
        else:
            print(f"  — Column already exists: {col_name}")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
