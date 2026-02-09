"""
Migration script to add metadata column to conversations table.
Run this once to update existing database.
"""
from sqlalchemy import text
from database.database import engine

def migrate():
    with engine.connect() as conn:
        # Add extra_data column (metadata is reserved in SQLAlchemy)
        try:
            conn.execute(text("""
                ALTER TABLE conversations 
                ADD COLUMN extra_data JSON
            """))
            conn.commit()
            print("✅ Migration successful: Added extra_data column to conversations table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️  Column extra_data already exists, skipping migration")
            else:
                print(f"❌ Migration failed: {e}")
                raise

if __name__ == "__main__":
    migrate()
