from app import app, db
# Ensure all models are imported so db.create_all() knows about them
# app.models should already be imported by app.__init__ which itself imports models
# but to be absolutely sure, especially if User model might be accessed directly:
from app.models import User 

print(f"Current User model in create_initial_db.py: {User.__table__.columns.keys()}")

with app.app_context():
    # Remove old db file first
    import os
    if os.path.exists('site.db'):
        os.remove('site.db')
        print("Removed existing site.db")
    
    # Remove migrations directory if it exists, to ensure flask db init starts fresh
    if os.path.exists('migrations'):
        import shutil
        shutil.rmtree('migrations')
        print("Removed existing migrations directory.")

    print("Creating all tables...")
    db.create_all()
    print("Database tables created (should include email column in user table).")
