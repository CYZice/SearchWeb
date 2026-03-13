from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database URL
# In Docker, this will be mounted to /app/data/inscriptions.db
# Locally, it's relative to the project root
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/inscriptions.db"

# Ensure the directory exists
os.makedirs("./data", exist_ok=True)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
