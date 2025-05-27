import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with a real secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'  # SQLite database file
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads') # Path for file uploads
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' # route function name for login
login_manager.login_message_category = 'info'


# Import routes and models here to avoid circular imports
# For now, we'll define a simple model and route here for initial setup
# and move them to separate files later.

# Class User is now defined in app/models.py

# The routes are now defined in app/routes.py

# The following is to create the database tables
# It should be run once, perhaps from a separate script or Flask shell
# For now, we can include it here for simplicity during initial setup.
from app import models # This import is for the user_loader and db.create_all()
# Import routes after db and models to avoid circularity if routes import db/models
from app import routes 

@login_manager.user_loader
def load_user(user_id):
    return models.User.query.get(int(user_id))

with app.app_context():
    db.create_all() # This needs models to be imported
