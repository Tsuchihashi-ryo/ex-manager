import os
from app import app, db
from app.models import User # Ensures User model (with email) is used

print(f"User model columns for DB creation: {User.__table__.columns.keys()}")

with app.app_context():
    instance_folder = app.instance_path
    db_path = os.path.join(instance_folder, 'site.db')
    
    if not os.path.exists(instance_folder):
        os.makedirs(instance_folder)
        print(f"Created instance folder: {instance_folder}")

    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database at {db_path}")
    
    print("Creating all database tables (User table should include 'email' column)...")
    db.create_all()
    print("Database tables created.")
