import sys
from app import create_app
from app.models import Cliente, Expediente, FacturaHonorario, Usuario

app = create_app()
with app.app_context():
    try:
        users = Usuario.query.all()
        print(f"Success! Users count: {len(users)}")
        clients = Cliente.query.all()
        print(f"Clients count: {len(clients)}")
        for c in clients:
            exps = Expediente.query.filter_by(cliente_id=c.id).all()
            print(f"Client: {c.nombre}, Expedientes count: {len(exps)}")
    except Exception as e:
        print(f"Database error: {e}")
