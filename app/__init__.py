from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# IMPORTACIÓN DIRECTA DE CONFIGURACIÓN
from config import Config

# Inicializamos las extensiones globales
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

# Configuraciones de seguridad para Flask-Login
login_manager.login_view = 'login'  # Le dice a Flask a qué ruta mandar a los intrusos
login_manager.login_message = 'Por favor, inicie sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'

def create_app():
    app = Flask(__name__)
    
    # ¡ESTA ES LA LÍNEA CLAVE! Carga la configuración del objeto importado
    app.config.from_object(Config)

    # Vinculamos las extensiones con la aplicación fabricada
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Le enseñamos a Flask-Login cómo buscar usuarios en PostgreSQL
    from app.models import Usuario

    @login_manager.user_loader
    def load_user(user_id):
        # Esta función busca el ID del usuario en la base de datos para mantener su sesión
        return Usuario.query.get(int(user_id))

    # Registrar las rutas centralizadas
    from app.routes import register_routes
    register_routes(app)

    return app