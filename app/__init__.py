from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config

# Instanciar las extensiones globalmente
db = SQLAlchemy()
migrate = Migrate()

def create_app(config_class=Config):
    # Inicializar la aplicación Flask
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Vincular las extensiones con la app
    db.init_app(app)
    migrate.init_app(app, db)

    # Importar las rutas y modelos al final para evitar importaciones circulares
    with app.app_context():
        from app import models
        from app import routes
        
    return app