from database import engine, Base
# We must import models so the script knows what to build
import models 

print("Connecting to Heroku Database...")

# This line does the magic: it creates the tables
Base.metadata.create_all(bind=engine)

print("Success! Tables created.")