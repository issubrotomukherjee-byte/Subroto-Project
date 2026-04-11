"""
Data migration: Populate ``quantity_units`` for existing inventory rows.

Run this script ONCE after applying the new model columns:

    python3 scripts/migrate_units.py

For each batch:
  - If units_per_strip is NULL → use 10 as default
  - Set quantity_units = quantity × units_per_strip

Safe to run multiple times (idempotent).
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal
from models.inventory import Inventory


def migrate():
    db = SessionLocal()
    try:
        batches = db.query(Inventory).all()
        migrated = 0

        for batch in batches:
            # Set units_per_strip if missing
            if batch.units_per_strip is None:
                batch.units_per_strip = 10

            # Compute quantity_units from strips × units_per_strip
            old_units = batch.quantity_units
            batch.quantity_units = batch.quantity * batch.units_per_strip

            if old_units != batch.quantity_units:
                migrated += 1
                print(
                    f"  Batch {batch.batch_no} (inv_id={batch.id}): "
                    f"qty={batch.quantity} strips × {batch.units_per_strip} ups "
                    f"→ {batch.quantity_units} units"
                )

        db.commit()
        print(f"\nMigration complete. {migrated} batches updated, {len(batches)} total.")

    except Exception as exc:
        db.rollback()
        print(f"Migration failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=== NeoMeds: Strip → Unit Migration ===\n")
    migrate()
