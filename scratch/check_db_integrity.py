from app import create_app
from app.models import Usuario

app = create_app()
with app.app_context():
    users = Usuario.query.all()
    for u in users:
        print(f"User: {u.email} | Rol: {u.rol}")
