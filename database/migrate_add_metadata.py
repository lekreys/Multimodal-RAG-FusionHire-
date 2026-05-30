"""
Migration script to add extra_data column to conversations table.
Run this once to update existing database.
"""
from sqlalchemy import text

from database.database import engine
from utils.logger import get_logger, setup_root_logger

setup_root_logger()
logger = get_logger(__name__)


def migrate():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN extra_data JSON"))
            conn.commit()
            logger.info("Migration successful: added extra_data column to conversations")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column name" in msg or "already exists" in msg:
                logger.info("Column extra_data already exists, skipping migration")
            else:
                logger.error("Migration failed: %s", e)
                raise


if __name__ == "__main__":
    migrate()
