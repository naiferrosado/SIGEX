import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db

app = create_app()
with app.app_context():
    db.create_all()
    print("Database tables created successfully!")
