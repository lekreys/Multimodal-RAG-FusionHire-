"""
Run this script ONCE to apply schema changes to the existing database.
  python -m database.migrate
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine
from utils.logger import get_logger, setup_root_logger
import sqlalchemy as sa

setup_root_logger()
logger = get_logger(__name__)


def run():
    with engine.connect() as conn:
        # 1. Add role column to users (default 'user' for all existing rows)
        try:
            conn.execute(sa.text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
            ))
            conn.commit()
            logger.info("Added 'role' column to users table.")
        except Exception as e:
            conn.rollback()
            logger.warning("'role' column already exists or error: %s", e)

        # 2. Add user_id column to conversations (nullable, FK to users.id)
        try:
            conn.execute(sa.text(
                "ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
            ))
            conn.commit()
            logger.info("Added 'user_id' column to conversations table.")
        except Exception as e:
            conn.rollback()
            logger.warning("'user_id' column already exists or error: %s", e)

        # 3. Add index on conversations.user_id
        try:
            conn.execute(sa.text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations(user_id)"
            ))
            conn.commit()
            logger.info("Created index on conversations.user_id.")
        except Exception as e:
            conn.rollback()
            logger.warning("Index creation skipped: %s", e)

    logger.info("Migration complete.")


if __name__ == "__main__":
    run()
