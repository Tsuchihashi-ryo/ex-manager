import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with a real secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'  # SQLite database file
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads') # Path for file uploads
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

# Import routes and models here to avoid circular imports
# For now, we'll define a simple model and route here for initial setup
# and move them to separate files later.

# Class User is now defined in app/models.py

# The routes are now defined in app/routes.py

# The following is to create the database tables
# It should be run once, perhaps from a separate script or Flask shell
# For now, we can include it here for simplicity during initial setup.

# Import models FIRST
from app import models 

# Create tables AFTER models are defined and imported
with app.app_context():
    db.create_all()

# Import routes LAST (after db.create_all() and models import)
from app import routes 

# @login_manager.user_loader # Removed
# def load_user(user_id): # Removed
#     return models.User.query.get(int(user_id)) # Removed
