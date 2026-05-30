"""
Migration: add liveness-tracking columns to data_skripsi.

- is_active            BOOLEAN  DEFAULT TRUE
- last_verified_at     TIMESTAMP NULL
- failed_check_count   INTEGER  DEFAULT 0

These columns power the optional job-availability verifier
(see scrapping/verifier.py). Retrieval only filters on `is_active`
when the env flag FILTER_INACTIVE_JOBS=true, so this migration
is safe to apply without changing current behaviour.

Run once: `python -m database.migrate_add_active_status`
Safe to re-run (uses IF NOT EXISTS).
"""
from sqlalchemy import text

from database.database import engine
from utils.logger import get_logger, setup_root_logger

setup_root_logger()
logger = get_logger(__name__)


STATEMENTS = [
    "ALTER TABLE data_skripsi ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE data_skripsi ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP NULL",
    "ALTER TABLE data_skripsi ADD COLUMN IF NOT EXISTS failed_check_count INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS ix_data_skripsi_is_active ON data_skripsi (is_active)",
]


def migrate():
    with engine.connect() as conn:
        for sql in STATEMENTS:
            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info("OK: %s", sql)
            except Exception as e:
                conn.rollback()
                logger.error("FAILED: %s\n  -> %s", sql, e)
                raise
    logger.info("Migration complete.")


if __name__ == "__main__":
    migrate()
