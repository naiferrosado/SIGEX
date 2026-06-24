from app import create_app, db
from app.models import Usuario
from werkzeug.security import generate_password_hash


app = create_app()

with app.app_context():
    # Verificar si el usuario ya existe
    admin_existente = Usuario.query.filter_by(email='naiferrosado@rosadomendez.com').first()
    
    if not admin_existente:
        nuevo_admin = Usuario(
            nombre='Naifer Rosado',
            email='naiferrosado@rosadomendez.com',
            password_hash=generate_password_hash('naiferrosado123'),
            rol='Administrador',
            activo=True,
            requiere_cambio_password=False
        )
        db.session.add(nuevo_admin)
        db.session.commit()
        print("Usuario Administrador creado exitosamente en PostgreSQL.")
    else:
        print("El usuario ya existe en la base de datos.")