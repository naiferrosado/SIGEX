from app import create_app, db
app = create_app()
with app.app_context():
    print("App created and database connected successfully!")
