import os
from app import app, db

# Ensure all models are imported so db.create_all() knows about them.
# This is usually handled by app/__init__.py importing models,
# but explicit import here can prevent issues if User model is needed directly.
from app.models import User

print(f"Current User model columns for temp_create_db.py: {User.__table__.columns.keys()}")

with app.app_context():
    db_path = os.path.join(app.instance_path, 'site.db')
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database at {db_path}")
    
    print("Creating all database tables (should include email column in user table)...")
    db.create_all()
    print("Database tables created.")
