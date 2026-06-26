from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user, logout_user, login_required
from app import db
from app.models import Usuario, Cliente, Expediente, Documento, AlertaPlazoAudiencia, FacturaHonorario
from app.forms import LoginForm, ClienteForm, UsuarioForm
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime


def _serialize_clientes(clientes):
    return [{
        'id': c.id,
        'nombre': c.nombre,
        'rnc_cedula': c.rnc_cedula,
        'telefono': c.telefono,
        'email_contacto': c.email_contacto,
        'consentimiento_datos': bool(c.consentimiento_datos),
        # Nuevos datos serializados:
        'tipo_cliente': c.tipo_cliente,
        'direccion': c.direccion,
        'fecha_nacimiento': c.fecha_nacimiento.strftime('%Y-%m-%d') if c.fecha_nacimiento else None
    } for c in clientes]


def register_routes(app):
    
    @app.route('/', methods=['GET', 'POST'])
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        form = LoginForm()
        
        if form.validate_on_submit():
            usuario = Usuario.query.filter_by(email=form.email.data).first()
            
            if usuario and check_password_hash(usuario.password_hash, form.password.data):
                login_user(usuario, remember=form.recordarme.data)
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
                'clientes': 0, 'expedientes': 0, 'alertas': 0, 'documentos': 0,
                'facturas': 0, 'usuarios': 0, 'total_general': 1,
                'porcentaje_expedientes': 0, 'porcentaje_clientes': 0,
                'porcentaje_documentos': 0, 'porcentaje_alertas': 0,
                'porcentaje_facturas': 0, 'porcentaje_usuarios': 0,
            }

        return render_template('dashboard/dashboard.html', usuario=current_user, estadisticas=estadisticas, current_date=datetime.now())

    @app.route('/clientes')
    @login_required
    def clientes():
        # 1. Instanciamos el formulario vacío para pasarlo a la vista (para el Modal de Agregar)
        form = ClienteForm()
        clientes_db = Cliente.query.order_by(Cliente.nombre.asc()).all()
        clientes_data = _serialize_clientes(clientes_db)
        return render_template('clientes/clientes.html', form=form, usuario=current_user, clientes=clientes_db, clientes_data=clientes_data, current_date=datetime.now())

    @app.route('/clientes/agregar', methods=['POST'])
    @login_required
    def agregar_cliente():
        # Flask-WTF toma automáticamente los datos de request.form
        form = ClienteForm()
        
        if form.validate_on_submit():
            nombre_completo = f"{form.nombre.data.strip()} {form.apellido.data.strip()}".strip()
            
            # Verificación de duplicados
            if Cliente.query.filter_by(rnc_cedula=form.rnc_cedula.data).first():
                flash('Ya existe un cliente registrado con esa cédula o RNC.', 'warning')
                return redirect(url_for('clientes'))

            # Inserción segura a la BD
            cliente = Cliente(
                nombre=nombre_completo,
                rnc_cedula=form.rnc_cedula.data,
                tipo_cliente=form.tipo_cliente.data,
                fecha_nacimiento=form.fecha_nacimiento.data,
                direccion=form.direccion.data,
                telefono=form.telefono.data or None,
                email_contacto=form.email_contacto.data,
                consentimiento_datos=form.consentimiento.data
            )
            db.session.add(cliente)
            db.session.commit()
            flash('Cliente agregado correctamente.', 'success')
        else:
            # Si el hacker (o el usuario) evade el HTML, WTForms lo atrapa aquí y muestra el error
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'Error en el formulario: {error}', 'danger')

        return redirect(url_for('clientes'))

    @app.route('/clientes/<int:cliente_id>/editar', methods=['POST'])
    @login_required
    def editar_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        form = ClienteForm()

        if form.validate_on_submit():
            nombre_completo = f"{form.nombre.data.strip()} {form.apellido.data.strip()}".strip()

            # Verificar si se está intentando usar una cédula que ya tiene OTRO cliente
            duplicado = Cliente.query.filter_by(rnc_cedula=form.rnc_cedula.data).first()
            if duplicado and duplicado.id != cliente.id:
                flash('Ya existe un cliente con esa cédula o RNC.', 'warning')
                return redirect(url_for('clientes'))

            # Actualización
            cliente.nombre = nombre_completo
            cliente.rnc_cedula = form.rnc_cedula.data
            cliente.tipo_cliente = form.tipo_cliente.data
            cliente.fecha_nacimiento = form.fecha_nacimiento.data
            cliente.direccion = form.direccion.data
            cliente.telefono = form.telefono.data or None
            cliente.email_contacto = form.email_contacto.data
            cliente.consentimiento_datos = form.consentimiento.data
            db.session.commit()
            flash('Datos del cliente actualizados correctamente.', 'success')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'Error al editar: {error}', 'danger')

        return redirect(url_for('clientes'))

    @app.route('/clientes/<int:cliente_id>/desactivar', methods=['POST'])
    @login_required
    def desactivar_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        
        # Alternar el estado lógico
        cliente.consentimiento_datos = not cliente.consentimiento_datos
        db.session.commit()
        
        estado = "reactivado" if cliente.consentimiento_datos else "desactivado"
        flash(f'Cliente {estado} en el sistema.', 'success')
        return redirect(url_for('clientes'))
        
    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
# --- HELPER PARA USUARIOS ---
    def _serialize_usuarios(usuarios):
        return [{
            'id': u.id,
            'nombre': u.nombre,
            'email': u.email,
            'rol': u.rol,
            'activo': bool(u.activo),
            'requiere_cambio': bool(u.requiere_cambio_password)
        } for u in usuarios]

    # --- RUTAS DE USUARIOS ---
    @app.route('/usuarios')
    @login_required
    def usuarios():
        # Por seguridad, puedes agregar: if current_user.rol != 'Administrador': return redirect(url_for('dashboard'))
        form = UsuarioForm()
        usuarios_db = Usuario.query.order_by(Usuario.nombre.asc()).all()
        usuarios_data = _serialize_usuarios(usuarios_db)
        return render_template('usuarios/usuarios.html', form=form, usuario=current_user, usuarios=usuarios_db, usuarios_data=usuarios_data, current_date=datetime.now())

    @app.route('/usuarios/agregar', methods=['POST'])
    @login_required
    def agregar_usuario():
        form = UsuarioForm()
        
        if form.validate_on_submit():
            # Validación manual de clave para usuarios nuevos
            if not form.password.data:
                flash('La contraseña es obligatoria para usuarios nuevos.', 'danger')
                return redirect(url_for('usuarios'))

            if Usuario.query.filter_by(email=form.email.data).first():
                flash('Ya existe un usuario con ese correo electrónico.', 'warning')
                return redirect(url_for('usuarios'))

            nuevo_usuario = Usuario(
                nombre=form.nombre.data.strip(),
                email=form.email.data.strip(),
                rol=form.rol.data,
                password_hash=generate_password_hash(form.password.data),
                activo=True,
                requiere_cambio_password=True # Fuerza al usuario a cambiarla al entrar
            )
            db.session.add(nuevo_usuario)
            db.session.commit()
            flash('Usuario creado exitosamente.', 'success')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'Error en {getattr(form, field).label.text}: {error}', 'danger')

        return redirect(url_for('usuarios'))

    @app.route('/usuarios/<int:usuario_id>/editar', methods=['POST'])
    @login_required
    def editar_usuario(usuario_id):
        usuario = Usuario.query.get_or_404(usuario_id)
        form = UsuarioForm()

        if form.validate_on_submit():
            duplicado = Usuario.query.filter_by(email=form.email.data).first()
            if duplicado and duplicado.id != usuario.id:
                flash('Ese correo ya está en uso por otro usuario.', 'warning')
                return redirect(url_for('usuarios'))

            usuario.nombre = form.nombre.data.strip()
            usuario.email = form.email.data.strip()
            usuario.rol = form.rol.data
            
            # Solo actualizamos la contraseña si el admin escribió una nueva
            if form.password.data:
                usuario.password_hash = generate_password_hash(form.password.data)
                usuario.requiere_cambio_password = True # Si el admin se la cambia, debe volver a actualizarla

            db.session.commit()
            flash('Usuario actualizado correctamente.', 'success')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'Error al editar: {error}', 'danger')

        return redirect(url_for('usuarios'))

    @app.route('/usuarios/<int:usuario_id>/desactivar', methods=['POST'])
    @login_required
    def desactivar_usuario(usuario_id):
        # Evitar que el administrador se desactive a sí mismo
        if usuario_id == current_user.id:
            flash('No puedes desactivar tu propia cuenta.', 'danger')
            return redirect(url_for('usuarios'))

        usuario = Usuario.query.get_or_404(usuario_id)
        usuario.activo = not usuario.activo
        db.session.commit()
        
        estado = "reactivado" if usuario.activo else "suspendido"
        flash(f'Acceso de usuario {estado}.', 'success')
        return redirect(url_for('usuarios'))