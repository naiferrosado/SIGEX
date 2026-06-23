from app import create_app

app = create_app()

if __name__ == '__main__':
# Arranca el servidor local en modo debug para ver los cambios en tiempo real
    app.run(debug=True)