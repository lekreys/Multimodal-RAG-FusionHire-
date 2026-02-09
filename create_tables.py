from database.database import engine
from database.models import Base

# Import all models to ensure they are registered
from database.models import Job

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
