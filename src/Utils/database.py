from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from src.config import DB_URL

# Create the connection engine
engine = create_engine(DB_URL)

# Create the session tool
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# The base class for your models
Base = declarative_base()
