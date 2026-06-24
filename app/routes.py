from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user, logout_user, login_required
from app.models import Usuario
from app.forms import LoginForm
from werkzeug.security import check_password_hash

def register_routes(app):
    
    @app.route('/', methods=['GET', 'POST'])
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        # Si el usuario ya tiene una sesión activa, mandar directo al dashboard
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        form = LoginForm()
        
        # validate_on_submit() verifica que sea una petición POST y que el Token CSRF sea válido
        if form.validate_on_submit():
            # 1. Buscar al usuario por el correo
            usuario = Usuario.query.filter_by(email=form.email.data).first()
            
            # 2. Comparar el hash de la BD con la contraseña ingresada
            if usuario and check_password_hash(usuario.password_hash, form.password.data):
                # 3. Abrimos la sesión segura
                login_user(usuario, remember=form.recordarme.data)
                
                # Redirigir a la página que intentaba ver antes del login, o al dashboard
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('dashboard'))
            else:
                flash('Credenciales incorrectas. Verifique su correo institucional y contraseña.', 'danger')
                
        return render_template('auth/login.html', form=form)

    @app.route('/dashboard')
    @login_required
    def dashboard():
        # Ruta temporal para comprobar que entramos con éxito
        return f"¡Acceso autorizado! Bienvenido, {current_user.nombre}. Rol: {current_user.rol}"
        
    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('login'))