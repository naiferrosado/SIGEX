from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user, logout_user, login_required
from app import db
from app.models import Usuario, Cliente, Expediente, Documento, AlertaPlazoAudiencia, FacturaHonorario
from app.forms import LoginForm
from werkzeug.security import check_password_hash
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime


def _serialize_clientes(clientes):
    return [{
        'id': c.id,
        'nombre': c.nombre,
        'rnc_cedula': c.rnc_cedula,
        'telefono': c.telefono,
        'email_contacto': c.email_contacto,
        'consentimiento_datos': bool(c.consentimiento_datos)
    } for c in clientes]


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
        try:
            total_clientes = Cliente.query.count()
            total_expedientes = Expediente.query.count()
            total_alertas = AlertaPlazoAudiencia.query.count()
            total_documentos = Documento.query.count()
            total_facturas = FacturaHonorario.query.count()
            total_usuarios = Usuario.query.count()

            total_general = max(1, total_expedientes + total_clientes + total_documentos + total_alertas + total_facturas + total_usuarios)

            estadisticas = {
                'clientes': total_clientes,
                'expedientes': total_expedientes,
                'alertas': total_alertas,
                'documentos': total_documentos,
                'facturas': total_facturas,
                'usuarios': total_usuarios,
                'total_general': total_general,
                'porcentaje_expedientes': round((total_expedientes / total_general) * 100, 1),
                'porcentaje_clientes': round((total_clientes / total_general) * 100, 1),
                'porcentaje_documentos': round((total_documentos / total_general) * 100, 1),
                'porcentaje_alertas': round((total_alertas / total_general) * 100, 1),
                'porcentaje_facturas': round((total_facturas / total_general) * 100, 1),
                'porcentaje_usuarios': round((total_usuarios / total_general) * 100, 1),
            }
        except SQLAlchemyError:
            estadisticas = {
                'clientes': 0,
                'expedientes': 0,
                'alertas': 0,
                'documentos': 0,
                'facturas': 0,
                'usuarios': 0,
                'total_general': 1,
                'porcentaje_expedientes': 0,
                'porcentaje_clientes': 0,
                'porcentaje_documentos': 0,
                'porcentaje_alertas': 0,
                'porcentaje_facturas': 0,
                'porcentaje_usuarios': 0,
            }

        return render_template('dashboard/dashboard.html', usuario=current_user, estadisticas=estadisticas, current_date=datetime.now())

    @app.route('/clientes')
    @login_required
    def clientes():
        clientes_db = Cliente.query.order_by(Cliente.nombre.asc()).all()
        clientes_data = _serialize_clientes(clientes_db)
        return render_template('clientes/clientes.html', usuario=current_user, clientes=clientes_db, clientes_data=clientes_data, current_date=datetime.now())

    @app.route('/clientes/agregar', methods=['GET', 'POST'])
    @login_required
    def agregar_cliente():
        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()
            apellido = request.form.get('apellido', '').strip()
            nombre_completo = f"{nombre} {apellido}".strip()
            rnc_cedula = request.form.get('rnc_cedula', '').strip()
            telefono = request.form.get('telefono', '').strip()
            email = request.form.get('email_contacto', '').strip()
            consentimiento = request.form.get('consentimiento') == 'on'

            if not nombre_completo or not rnc_cedula or not email:
                flash('Complete al menos el nombre, la cédula/RNC y el correo.', 'danger')
                return redirect(url_for('clientes'))

            if Cliente.query.filter_by(rnc_cedula=rnc_cedula).first():
                flash('Ya existe un cliente con esa cédula o RNC.', 'warning')
                return redirect(url_for('clientes'))

            cliente = Cliente(
                nombre=nombre_completo,
                rnc_cedula=rnc_cedula,
                telefono=telefono or None,
                email_contacto=email,
                consentimiento_datos=consentimiento
            )
            db.session.add(cliente)
            db.session.commit()
            flash('Cliente agregado correctamente.', 'success')
            return redirect(url_for('clientes'))

        return redirect(url_for('clientes'))

    @app.route('/clientes/<int:cliente_id>/editar', methods=['POST'])
    @login_required
    def editar_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        nombre_completo = f"{nombre} {apellido}".strip()
        rnc_cedula = request.form.get('rnc_cedula', '').strip()
        telefono = request.form.get('telefono', '').strip()
        email = request.form.get('email_contacto', '').strip()
        consentimiento = request.form.get('consentimiento') == 'on'

        if not nombre_completo or not rnc_cedula or not email:
            flash('Complete al menos el nombre, la cédula/RNC y el correo.', 'danger')
            return redirect(url_for('clientes'))

        duplicado = Cliente.query.filter_by(rnc_cedula=rnc_cedula).first()
        if duplicado and duplicado.id != cliente.id:
            flash('Ya existe un cliente con esa cédula o RNC.', 'warning')
            return redirect(url_for('clientes'))

        cliente.nombre = nombre_completo
        cliente.rnc_cedula = rnc_cedula
        cliente.telefono = telefono or None
        cliente.email_contacto = email
        cliente.consentimiento_datos = consentimiento
        db.session.commit()
        flash('Cliente actualizado correctamente.', 'success')
        return redirect(url_for('clientes'))

    @app.route('/clientes/<int:cliente_id>/desactivar', methods=['POST'])
    @login_required
    def desactivar_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        cliente.consentimiento_datos = False
        db.session.commit()
        flash('Cliente desactivado correctamente.', 'success')
        return redirect(url_for('clientes'))
        
    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('login'))