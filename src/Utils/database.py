import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Get the URL from your .env file
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix Heroku's URL if it starts with "postgres://"
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create the connection engine
engine = create_engine(DATABASE_URL)

# Create the session tool
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# The base class for your models
Base = declarative_base()