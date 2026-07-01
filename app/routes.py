import uuid  # Para generar el código único de la firma
from datetime import datetime
from urllib.parse import urlparse
from functools import wraps

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.forms import (
    ClienteForm,
    ExpedienteAdministrativoForm,
    ExpedienteJudicialForm,
    LoginForm,
    UsuarioForm,
)
from app.models import (
    AlertaPlazoAudiencia,
    Cliente,
    Documento,
    Expediente,
    ExpedienteAdministrativo,
    ExpedienteJudicial,
    FacturaHonorario,
    Usuario,
    rd_now,
    BitacoraTiempoTarea,
    VersionDocumento,
    BitacoraAuditoria,
)


def _serialize_clientes(clientes):
    return [
        {
            "id": c.id,
            "nombre": f"{c.nombres} {c.apellidos}",  # ← corregido
            "rnc_cedula": c.rnc_cedula,
            "telefono": c.telefono,
            "email_contacto": c.email_contacto,
            "consentimiento_datos": bool(c.consentimiento_datos),
            "tipo_cliente": c.tipo_cliente,
            "direccion": c.direccion,
            "fecha_nacimiento": c.fecha_nacimiento.strftime("%Y-%m-%d")
            if c.fecha_nacimiento
            else None,
        }
        for c in clientes
    ]


def _serialize_expedientes(expedientes):
    data = []
    for exp in expedientes:
        item = {
            "id": exp.id,
            "codigo_firma": exp.codigo_firma,
            "cliente_id": exp.cliente_id,
            "cliente_nombre": exp.cliente.nombre_completo if exp.cliente else "Desconocido",
            "abogado_responsable_id": exp.abogado_responsable_id,
            "abogado_responsable_nombre": exp.abogado_responsable.nombre if exp.abogado_responsable else "No asignado",
            "nombre_caso": exp.nombre_caso,
            "rol_firma": exp.rol_firma,
            "tipo_tramite": exp.tipo_tramite,
            "estado": exp.estado,
            "fecha_apertura": exp.fecha_apertura.strftime("%Y-%m-%d") if exp.fecha_apertura else None,
            "fecha_cierre": exp.fecha_cierre.strftime("%Y-%m-%d") if exp.fecha_cierre else None,
        }
        if exp.tipo_tramite == 'Judicial':
            item.update({
                "rama_derecho": exp.rama_derecho,
                "sub_categoria": exp.sub_categoria,
                "tipo_accion": exp.tipo_accion,
                "jurisdiccion_actual": exp.jurisdiccion_actual,
                "tribunal_asignado": exp.tribunal_asignado,
                "numero_expediente_tribunal": exp.numero_expediente_tribunal,
                "juez_asignado": exp.juez_asignado,
                "nombre_contraparte": exp.nombre_contraparte,
                "contacto_contraparte": exp.contacto_contraparte,
                "abogado_contraparte": exp.abogado_contraparte,
                "contacto_abogado_contraparte": exp.contacto_abogado_contraparte,
                "monto_demanda": float(exp.monto_demanda) if exp.monto_demanda is not None else None,
                "fecha_audiencia": exp.fecha_audiencia.strftime("%Y-%m-%d") if exp.fecha_audiencia else None,
                "hora_audiencia": exp.hora_audiencia.strftime("%H:%M") if exp.hora_audiencia else None,
            })
        elif exp.tipo_tramite == 'Administrativo':
            item.update({
                "tipo_proceso": exp.tipo_proceso,
                "sub_proceso": exp.sub_proceso,
                "institucion_encargada": exp.institucion_encargada,
                "numero_solicitud_oficial": exp.numero_solicitud_oficial,
                "descripcion_tramite": exp.descripcion_tramite,
                "monto_tasas_impuestos": float(exp.monto_tasas_impuestos) if exp.monto_tasas_impuestos is not None else None,
            })
        data.append(item)
    return data


def roles_permitidos(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.rol not in roles:
                flash("Acceso denegado. No tiene permisos para acceder a esta sección o realizar esta acción.", "danger")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def register_routes(app):

    @app.route("/", methods=["GET", "POST"])
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        form = LoginForm()

        if form.validate_on_submit():
            usuario = Usuario.query.filter_by(email=form.email.data).first()

            if usuario and check_password_hash(
                usuario.password_hash, form.password.data
            ):
                if not usuario.activo:
                    flash(
                        "Su cuenta está suspendida. Por favor, póngase en contacto con el administrador.",
                        "danger",
                    )
                    return render_template("auth/login.html", form=form)

                login_user(usuario, remember=form.recordarme.data)
                next_page = request.args.get("next")
                if next_page:
                    parsed_url = urlparse(next_page)
                    # Si tiene netloc o no comienza con /, se invalida la redirección externa
                    if parsed_url.netloc or not next_page.startswith("/"):
                        next_page = None

                return (
                    redirect(next_page) if next_page else redirect(url_for("dashboard"))
                )
            else:
                flash(
                    "Credenciales incorrectas. Verifique su correo institucional y contraseña.",
                    "danger",
                )

        return render_template("auth/login.html", form=form)

    @app.route("/dashboard")
    @login_required
    def dashboard():
        try:
            rol = current_user.rol
            now_dt = datetime.utcnow()
            start_of_month = datetime(now_dt.year, now_dt.month, 1)
            
            # --- SOCIO ---
            if rol == "Socio":
                total_clientes = Cliente.query.count()
                total_expedientes = Expediente.query.count()
                total_alertas = AlertaPlazoAudiencia.query.count()
                total_documentos = Documento.query.count()
                total_facturas = FacturaHonorario.query.count()
                total_usuarios = Usuario.query.count()
                
                total_general = max(1, total_expedientes + total_clientes + total_documentos + total_alertas + total_facturas + total_usuarios)
                
                # Aprobaciones pendientes (tiempos reportados por asociados/paralegales en estado 'Abierto')
                tiempos_pendientes = BitacoraTiempoTarea.query.filter_by(estado_cierre="Abierto").limit(5).all()
                total_tiempos_pendientes_count = BitacoraTiempoTarea.query.filter_by(estado_cierre="Abierto").count()
                
                # Facturas y finanzas
                facturas_pendientes_monto = db.session.query(db.func.sum(FacturaHonorario.monto_total)).filter_by(estado_pago="Pendiente").scalar() or 0.00
                facturas_emitidas_mes = FacturaHonorario.query.filter(FacturaHonorario.fecha_emision >= start_of_month).count()
                
                # Horas facturables aprobadas
                horas_facturables_mes = db.session.query(db.func.sum(BitacoraTiempoTarea.horas_trabajadas)).filter_by(estado_cierre="Aprobado").filter(BitacoraTiempoTarea.fecha_tarea >= start_of_month.date()).scalar() or 0.00
                
                # Coberturas y porcentajes
                estadisticas = {
                    "clientes": total_clientes,
                    "expedientes": total_expedientes,
                    "alertas": total_alertas,
                    "documentos": total_documentos,
                    "facturas": total_facturas,
                    "usuarios": total_usuarios,
                    "total_general": total_general,
                    "porcentaje_expedientes": round((total_expedientes / total_general) * 100, 1),
                    "porcentaje_clientes": round((total_clientes / total_general) * 100, 1),
                    "porcentaje_documentos": round((total_documentos / total_general) * 100, 1),
                    "porcentaje_alertas": round((total_alertas / total_general) * 100, 1),
                    "porcentaje_facturas": round((total_facturas / total_general) * 100, 1),
                    "porcentaje_usuarios": round((total_usuarios / total_general) * 100, 1),
                    "tiempos_pendientes": tiempos_pendientes,
                    "total_tiempos_pendientes_count": total_tiempos_pendientes_count,
                    "facturas_pendientes_monto": float(facturas_pendientes_monto),
                    "facturas_emitidas_mes": facturas_emitidas_mes,
                    "horas_facturables_mes": float(horas_facturables_mes)
                }
                return render_template(
                    "dashboard/dashboard_socio.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now()
                )
                
            # --- ASOCIADO ---
            elif rol == "Asociado":
                # Filtrar métricas de sus expedientes asignados
                mis_expedientes_activos = Expediente.query.filter_by(abogado_responsable_id=current_user.id).filter(Expediente.estado != "Archivado").count()
                
                # Obtener IDs de sus expedientes para alertas
                mis_expedientes_ids = [e.id for e in Expediente.query.filter_by(abogado_responsable_id=current_user.id).all()]
                
                mis_alertas_semana = AlertaPlazoAudiencia.query.filter(AlertaPlazoAudiencia.expediente_id.in_(mis_expedientes_ids)).filter(AlertaPlazoAudiencia.estado_alerta == "Pendiente").count() if mis_expedientes_ids else 0
                mis_vencimientos_proximos = AlertaPlazoAudiencia.query.filter(AlertaPlazoAudiencia.expediente_id.in_(mis_expedientes_ids)).filter(AlertaPlazoAudiencia.estado_alerta == "Pendiente").count() if mis_expedientes_ids else 0
                
                # Horas del mes
                mis_horas_mes = db.session.query(db.func.sum(BitacoraTiempoTarea.horas_trabajadas)).filter_by(usuario_id=current_user.id).filter(BitacoraTiempoTarea.fecha_tarea >= start_of_month.date()).scalar() or 0.00
                mis_horas_pendientes = db.session.query(db.func.sum(BitacoraTiempoTarea.horas_trabajadas)).filter_by(usuario_id=current_user.id, estado_cierre="Abierto").scalar() or 0.00
                
                # Actividades del asociado
                mis_tareas_recientes = BitacoraTiempoTarea.query.filter_by(usuario_id=current_user.id).order_by(BitacoraTiempoTarea.fecha_tarea.desc()).limit(5).all()
                mis_expedientes_todos = Expediente.query.filter_by(abogado_responsable_id=current_user.id).order_by(Expediente.fecha_apertura.desc()).limit(5).all()
                
                # Calcular total facturable proyectado para este mes (supongamos tarifa de RD$ 5,000 por hora)
                total_facturable_proyectado = float(mis_horas_mes) * 5000.0
                
                estadisticas = {
                    "expedientes_activos": mis_expedientes_activos,
                    "alertas_semana": mis_alertas_semana,
                    "vencimientos_proximos": mis_vencimientos_proximos,
                    "horas_mes": float(mis_horas_mes),
                    "horas_pendientes": float(mis_horas_pendientes),
                    "tareas_recientes": mis_tareas_recientes,
                    "expedientes": mis_expedientes_todos,
                    "total_facturable_proyectado": total_facturable_proyectado
                }
                return render_template(
                    "dashboard/dashboard_asociado.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now()
                )
                
            # --- PARALEGAL ---
            elif rol == "Paralegal":
                # El paralegal ve tareas administrativas y soporte
                expedientes_activos = Expediente.query.filter(Expediente.estado != "Archivado").count()
                total_tareas_pendientes = BitacoraTiempoTarea.query.filter_by(usuario_id=current_user.id, estado_cierre="Abierto").count()
                mis_documentos_cargados = VersionDocumento.query.filter_by(usuario_id=current_user.id).count()
                
                # Tareas de apoyo reportadas y aprobadas este mes
                tareas_completadas = BitacoraTiempoTarea.query.filter_by(usuario_id=current_user.id, estado_cierre="Aprobado").filter(BitacoraTiempoTarea.fecha_tarea >= start_of_month.date()).count()
                
                documentos_recientes = VersionDocumento.query.order_by(VersionDocumento.fecha_carga.desc()).limit(5).all()
                tareas_proximas = BitacoraTiempoTarea.query.filter_by(usuario_id=current_user.id).order_by(BitacoraTiempoTarea.fecha_tarea.desc()).limit(5).all()

                estadisticas = {
                    "expedientes_activos": expedientes_activos,
                    "tareas_pendientes": total_tareas_pendientes,
                    "documentos_cargados": mis_documentos_cargados,
                    "tareas_completadas": tareas_completadas,
                    "documentos_recientes": documentos_recientes,
                    "tareas_proximas": tareas_proximas
                }
                return render_template(
                    "dashboard/dashboard_paralegal.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now()
                )
                
            # --- ADMINISTRADOR ---
            elif rol == "Administrador":
                usuarios_activos = Usuario.query.filter_by(activo=True).count()
                expedientes_totales = Expediente.query.count()
                documentos_almacenados = Documento.query.count()
                horas_registradas = db.session.query(db.func.sum(BitacoraTiempoTarea.horas_trabajadas)).scalar() or 0.00
                facturacion_total = db.session.query(db.func.sum(FacturaHonorario.monto_total)).scalar() or 0.00
                
                # Logs de auditoría de hoy
                eventos_auditoria_hoy = BitacoraAuditoria.query.filter(db.func.date(BitacoraAuditoria.fecha_hora) == db.func.current_date()).count()
                auditorias_recientes = BitacoraAuditoria.query.order_by(BitacoraAuditoria.fecha_hora.desc()).limit(8).all()
                
                # Distribución de usuarios
                socios_count = Usuario.query.filter_by(rol="Socio").count()
                asociados_count = Usuario.query.filter_by(rol="Asociado").count()
                paralegales_count = Usuario.query.filter_by(rol="Paralegal").count()
                administradores_count = Usuario.query.filter_by(rol="Administrador").count()
                clientes_count = Usuario.query.filter_by(rol="Cliente").count()
                
                estadisticas = {
                    "usuarios_activos": usuarios_activos,
                    "expedientes_totales": expedientes_totales,
                    "documentos_almacenados": documentos_almacenados,
                    "horas_registradas": float(horas_registradas),
                    "facturacion_total": float(facturacion_total),
                    "eventos_auditoria_hoy": eventos_auditoria_hoy,
                    "auditorias_recientes": auditorias_recientes,
                    "socios_count": socios_count,
                    "asociados_count": asociados_count,
                    "paralegales_count": paralegales_count,
                    "administradores_count": administradores_count,
                    "clientes_count": clientes_count
                }
                return render_template(
                    "dashboard/dashboard_admin.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now()
                )
                
            # --- CLIENTE ---
            elif rol == "Cliente":
                cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
                if not cliente_db:
                    estadisticas = {
                        "expedientes_activos_count": 0,
                        "audiencia_proxima": None,
                        "documentos_disponibles_count": 0,
                        "expedientes": [],
                        "documentos": [],
                        "actividades": []
                    }
                    return render_template(
                        "dashboard/dashboard_cliente.html",
                        usuario=current_user,
                        estadisticas=estadisticas,
                        current_date=rd_now()
                    )
                
                expedientes_cliente = Expediente.query.filter_by(cliente_id=cliente_db.id).all()
                expedientes_activos_count = sum(1 for e in expedientes_cliente if e.estado != "Archivado")
                
                exp_ids = [e.id for e in expedientes_cliente]
                audiencia_proxima = None
                if exp_ids:
                    audiencia_proxima = AlertaPlazoAudiencia.query.filter(AlertaPlazoAudiencia.expediente_id.in_(exp_ids)).filter(AlertaPlazoAudiencia.estado_alerta == "Pendiente").order_by(AlertaPlazoAudiencia.fecha_vencimiento.asc()).first()
                
                documentos_compartidos = []
                if exp_ids:
                    documentos_compartidos = Documento.query.filter(Documento.expediente_id.in_(exp_ids)).filter_by(visibilidad="Compartido").all()
                
                alertas_recientes = []
                if exp_ids:
                    alertas_recientes = AlertaPlazoAudiencia.query.filter(AlertaPlazoAudiencia.expediente_id.in_(exp_ids)).order_by(AlertaPlazoAudiencia.fecha_vencimiento.desc()).limit(5).all()
                
                caso_activo_principal = None
                for e in expedientes_cliente:
                    if e.estado != "Archivado":
                        caso_activo_principal = e
                        break
                
                # Fases del caso principal
                progreso_fase = 1
                if caso_activo_principal:
                    if caso_activo_principal.estado == "Archivado":
                        progreso_fase = 5
                    else:
                        has_hearing = False
                        if caso_activo_principal.tipo_tramite == "Judicial":
                            has_hearing = (caso_activo_principal.fecha_audiencia is not None)
                        if has_hearing:
                            progreso_fase = 3
                        elif len(caso_activo_principal.documentos) > 2:
                            progreso_fase = 2
                        else:
                            progreso_fase = 1
                
                estadisticas = {
                    "expedientes_activos_count": expedientes_activos_count,
                    "audiencia_proxima": audiencia_proxima,
                    "documentos_disponibles_count": len(documentos_compartidos),
                    "expedientes": expedientes_cliente,
                    "documentos": documentos_compartidos,
                    "actividades": alertas_recientes,
                    "caso_activo_principal": caso_activo_principal,
                    "progreso_fase": progreso_fase
                }
                return render_template(
                    "dashboard/dashboard_cliente.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now()
                )
            else:
                flash("Rol no identificado.", "danger")
                return redirect(url_for("login"))
                
        except SQLAlchemyError as e:
            flash(f"Error al cargar el Dashboard: {str(e)}", "danger")
            return redirect(url_for("login"))

    @app.route("/clientes")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def clientes():
        # 1. Instanciamos el formulario vacío para pasarlo a la vista (para el Modal de Agregar)
        form = ClienteForm()
        clientes_db = Cliente.query.order_by(Cliente.nombres.asc()).all()
        clientes_data = _serialize_clientes(clientes_db)
        return render_template(
            "clientes/clientes.html",
            form=form,
            usuario=current_user,
            clientes=clientes_db,
            clientes_data=clientes_data,
            current_date=datetime.now(),
        )

    @app.route("/clientes/agregar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agregar_cliente():
        # Flask-WTF toma automáticamente los datos de request.form
        form = ClienteForm()

        if form.validate_on_submit():
            nombre_completo = (
                f"{form.nombre.data.strip()} {form.apellido.data.strip()}".strip()
            )

            # Verificación de duplicados
            if Cliente.query.filter_by(rnc_cedula=form.rnc_cedula.data).first():
                flash(
                    "Ya existe un cliente registrado con esa cédula o RNC.", "warning"
                )
                return redirect(url_for("clientes"))

            # Inserción segura a la BD
            cliente = Cliente(
                nombres=form.nombre.data.strip(),
                apellidos=form.apellido.data.strip(),
                rnc_cedula=form.rnc_cedula.data,
                tipo_cliente=form.tipo_cliente.data,
                fecha_nacimiento=form.fecha_nacimiento.data,
                direccion=form.direccion.data,
                telefono=form.telefono.data or None,
                email_contacto=form.email_contacto.data,
                consentimiento_datos=form.consentimiento.data,
            )
            try:
                db.session.add(cliente)
                db.session.commit()
                flash("Cliente agregado correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar el cliente: {str(e)}", "danger")
        else:
            # Si el hacker (o el usuario) evade el HTML, WTForms lo atrapa aquí y muestra el error
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error en el formulario: {error}", "danger")

        return redirect(url_for("clientes"))

    @app.route("/clientes/<int:cliente_id>/editar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def editar_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        form = ClienteForm()

        if form.validate_on_submit():
            nombre_completo = (
                f"{form.nombre.data.strip()} {form.apellido.data.strip()}".strip()
            )

            # Verificar si se está intentando usar una cédula que ya tiene OTRO cliente
            duplicado = Cliente.query.filter_by(rnc_cedula=form.rnc_cedula.data).first()
            if duplicado and duplicado.id != cliente.id:
                flash("Ya existe un cliente con esa cédula o RNC.", "warning")
                return redirect(url_for("clientes"))

            # Actualización
            cliente.nombres = form.nombre.data.strip()
            cliente.apellidos = form.apellido.data.strip()
            cliente.rnc_cedula = form.rnc_cedula.data
            cliente.tipo_cliente = form.tipo_cliente.data
            cliente.fecha_nacimiento = form.fecha_nacimiento.data
            cliente.direccion = form.direccion.data
            cliente.telefono = form.telefono.data or None
            cliente.email_contacto = form.email_contacto.data
            cliente.consentimiento_datos = form.consentimiento.data
            try:
                db.session.commit()
                flash("Datos del cliente actualizados correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar cambios del cliente: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error al editar: {error}", "danger")

        return redirect(url_for("clientes"))

    @app.route("/clientes/<int:cliente_id>/desactivar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def desactivar_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)

        # Alternar el estado lógico
        cliente.consentimiento_datos = not cliente.consentimiento_datos
        try:
            db.session.commit()
            estado = "reactivado" if cliente.consentimiento_datos else "desactivado"
            flash(f"Cliente {estado} en el sistema.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al cambiar el consentimiento del cliente: {str(e)}", "danger")
        return redirect(url_for("clientes"))

    @app.route("/logout")
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # --- HELPER PARA USUARIOS ---
    def _serialize_usuarios(usuarios):
        return [
            {
                "id": u.id,
                "nombre": u.nombre,
                "email": u.email,
                "rol": u.rol,
                "activo": bool(u.activo),
                "requiere_cambio": bool(u.requiere_cambio_password),
            }
            for u in usuarios
        ]

    # --- RUTAS DE USUARIOS ---
    @app.route("/usuarios")
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def usuarios():
        form = UsuarioForm()
        usuarios_db = Usuario.query.order_by(Usuario.nombre.asc()).all()
        usuarios_data = _serialize_usuarios(usuarios_db)
        return render_template(
            "usuarios/usuarios.html",
            form=form,
            usuario=current_user,
            usuarios=usuarios_db,
            usuarios_data=usuarios_data,
            current_date=datetime.now(),
        )

    @app.route("/usuarios/agregar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def agregar_usuario():
        form = UsuarioForm()

        if form.validate_on_submit():
            # Validación manual de clave para usuarios nuevos
            if not form.password.data:
                flash("La contraseña es obligatoria para usuarios nuevos.", "danger")
                return redirect(url_for("usuarios"))

            if Usuario.query.filter_by(email=form.email.data).first():
                flash("Ya existe un usuario con ese correo electrónico.", "warning")
                return redirect(url_for("usuarios"))

            nuevo_usuario = Usuario(
                nombre=form.nombre.data.strip(),
                email=form.email.data.strip(),
                rol=form.rol.data,
                password_hash=generate_password_hash(form.password.data),
                activo=True,
                requiere_cambio_password=True,  # Fuerza al usuario a cambiarla al entrar
            )
            try:
                db.session.add(nuevo_usuario)
                db.session.commit()
                flash("Usuario creado exitosamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar el usuario: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(
                        f"Error en {getattr(form, field).label.text}: {error}", "danger"
                    )

        return redirect(url_for("usuarios"))

    @app.route("/usuarios/<int:usuario_id>/editar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def editar_usuario(usuario_id):
        usuario = Usuario.query.get_or_404(usuario_id)
        form = UsuarioForm()

        if form.validate_on_submit():
            duplicado = Usuario.query.filter_by(email=form.email.data).first()
            if duplicado and duplicado.id != usuario.id:
                flash("Ese correo ya está en uso por otro usuario.", "warning")
                return redirect(url_for("usuarios"))

            usuario.nombre = form.nombre.data.strip()
            usuario.email = form.email.data.strip()
            usuario.rol = form.rol.data

            # Solo actualizamos la contraseña si el admin escribió una nueva
            if form.password.data:
                usuario.password_hash = generate_password_hash(form.password.data)
                usuario.requiere_cambio_password = (
                    True  # Si el admin se la cambia, debe volver a actualizarla
                )

            try:
                db.session.commit()
                flash("Usuario actualizado correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar cambios del usuario: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error al editar: {error}", "danger")

        return redirect(url_for("usuarios"))

    @app.route("/usuarios/<int:usuario_id>/desactivar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def desactivar_usuario(usuario_id):
        # Evitar que el administrador se desactive a sí mismo
        if usuario_id == current_user.id:
            flash("No puedes desactivar tu propia cuenta.", "danger")
            return redirect(url_for("usuarios"))

        usuario = Usuario.query.get_or_404(usuario_id)
        usuario.activo = not usuario.activo
        try:
            db.session.commit()
            estado = "reactivado" if usuario.activo else "suspendido"
            flash(f"Acceso de usuario {estado}.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al cambiar el estado del usuario: {str(e)}", "danger")
        return redirect(url_for("usuarios"))

    # --- LISTADO DE EXPEDIENTES ---
    @app.route("/expedientes")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def expedientes():
        # Gracias al polimorfismo, esto trae TODOS los expedientes (Judiciales y Administrativos)
        lista_expedientes = Expediente.query.order_by(
            Expediente.fecha_apertura.desc()
        ).all()
        expedientes_data = _serialize_expedientes(lista_expedientes)
        return render_template(
            "expedientes/index.html",
            expedientes=lista_expedientes,
            expedientes_data=expedientes_data,
        )

    # --- CREAR NUEVO EXPEDIENTE ---
    @app.route("/expedientes/nuevo", methods=["GET", "POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def nuevo_expediente():
        # Instanciamos ambos formularios
        form_judicial = ExpedienteJudicialForm()
        form_admin = ExpedienteAdministrativoForm()

        # LLENAR LOS SELECTORES DINÁMICAMENTE (Para ambos formularios)
        clientes_db = Cliente.query.all()
        opciones_clientes = [(c.id, f"{c.nombres} {c.apellidos}") for c in clientes_db]

        abogados_db = Usuario.query.filter(
            Usuario.rol.in_(["Asociado", "Socio", "Administrador"])
        ).all()
        opciones_abogados = [(a.id, a.nombre) for a in abogados_db]

        # Asignamos las opciones — usamos 0 como placeholder (no '') para evitar ValueError con coerce=int
        form_judicial.cliente_id.choices = [
            (0, "Seleccione un cliente...")
        ] + opciones_clientes
        form_judicial.abogado_responsable_id.choices = [
            (0, "Seleccione un abogado...")
        ] + opciones_abogados

        form_admin.cliente_id.choices = [
            (0, "Seleccione un cliente...")
        ] + opciones_clientes
        form_admin.abogado_responsable_id.choices = [
            (0, "Seleccione un abogado...")
        ] + opciones_abogados

        # PROCESAR EL FORMULARIO ENVIADO (POST)
        if request.method == "POST":
            codigo_generado = f"EXP-{uuid.uuid4().hex[:6].upper()}"

            # FORMULARIO JUDICIAL
            if (
                form_judicial.submit_judicial.name in request.form
                and form_judicial.validate_on_submit()
            ):
                # Validar que hayan seleccionado cliente (no el placeholder 0)
                if (
                    not form_judicial.cliente_id.data
                    or form_judicial.cliente_id.data == 0
                ):
                    flash("Debe seleccionar un cliente para el expediente.", "danger")
                    return render_template(
                        "expedientes/nuevo.html",
                        form_judicial=form_judicial,
                        form_admin=form_admin,
                    )

                # Validar abogado responsable
                if (
                    not form_judicial.abogado_responsable_id.data
                    or form_judicial.abogado_responsable_id.data == 0
                ):
                    flash("Debe seleccionar un abogado responsable.", "danger")
                    return render_template(
                        "expedientes/nuevo.html",
                        form_judicial=form_judicial,
                        form_admin=form_admin,
                    )

                nuevo_caso = ExpedienteJudicial(
                    codigo_firma=codigo_generado,
                    cliente_id=form_judicial.cliente_id.data,
                    abogado_responsable_id=form_judicial.abogado_responsable_id.data,
                    nombre_caso=form_judicial.nombre_caso.data,
                    rol_firma=form_judicial.rol_firma.data,
                    # Campos específicos judiciales
                    rama_derecho=form_judicial.rama_derecho.data,
                    sub_categoria=form_judicial.sub_categoria.data,
                    tipo_accion=form_judicial.tipo_accion.data,
                    jurisdiccion_actual=form_judicial.jurisdiccion_actual.data,
                    tribunal_asignado=form_judicial.tribunal_asignado.data,
                    numero_expediente_tribunal=form_judicial.numero_expediente_tribunal.data,
                    juez_asignado=form_judicial.juez_asignado.data,
                    nombre_contraparte=form_judicial.nombre_contraparte.data,
                    contacto_contraparte=form_judicial.contacto_contraparte.data,
                    abogado_contraparte=form_judicial.abogado_contraparte.data,
                    contacto_abogado_contraparte=form_judicial.contacto_abogado_contraparte.data,
                    monto_demanda=form_judicial.monto_demanda.data,
                    fecha_audiencia=form_judicial.fecha_audiencia.data,
                    hora_audiencia=form_judicial.hora_audiencia.data,
                    tipo_tramite="Judicial",
                )

                try:
                    db.session.add(nuevo_caso)
                    db.session.commit()
                    flash("Expediente judicial creado exitosamente.", "success")
                    return redirect(url_for("expedientes"))
                except Exception as e:
                    db.session.rollback()
                    flash(f"Error al guardar el expediente: {str(e)}", "danger")

            # FORMULARIO ADMINISTRATIVO
            elif (
                form_admin.submit_admin.name in request.form
                and form_admin.validate_on_submit()
            ):
                # Validar que hayan seleccionado cliente
                if not form_admin.cliente_id.data or form_admin.cliente_id.data == 0:
                    flash("Debe seleccionar un cliente para el trámite.", "danger")
                    return render_template(
                        "expedientes/nuevo.html",
                        form_judicial=form_judicial,
                        form_admin=form_admin,
                    )

                # Validar abogado responsable
                if (
                    not form_admin.abogado_responsable_id.data
                    or form_admin.abogado_responsable_id.data == 0
                ):
                    flash("Debe seleccionar un abogado responsable.", "danger")
                    return render_template(
                        "expedientes/nuevo.html",
                        form_judicial=form_judicial,
                        form_admin=form_admin,
                    )

                nuevo_tramite = ExpedienteAdministrativo(
                    codigo_firma=codigo_generado,
                    cliente_id=form_admin.cliente_id.data,
                    abogado_responsable_id=form_admin.abogado_responsable_id.data,
                    nombre_caso=form_admin.nombre_caso.data,
                    rol_firma=form_admin.rol_firma.data,
                    # Campos específicos administrativos
                    tipo_proceso=form_admin.tipo_proceso.data,
                    sub_proceso=form_admin.sub_proceso.data,
                    institucion_encargada=form_admin.institucion_encargada.data,
                    numero_solicitud_oficial=form_admin.numero_solicitud_oficial.data,
                    descripcion_tramite=form_admin.descripcion_tramite.data,
                    monto_tasas_impuestos=form_admin.monto_tasas_impuestos.data,
                    tipo_tramite="Administrativo",
                )

                try:
                    db.session.add(nuevo_tramite)
                    db.session.commit()
                    flash("Expediente administrativo creado exitosamente.", "success")
                    return redirect(url_for("expedientes"))
                except Exception as e:
                    db.session.rollback()
                    flash(f"Error al guardar el trámite: {str(e)}", "danger")

        # RENDERIZAR LA VISTA (GET o si hay errores de validación)
        return render_template(
            "expedientes/nuevo.html", form_judicial=form_judicial, form_admin=form_admin
        )

    @app.route("/expedientes/<int:expediente_id>/editar", methods=["GET", "POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def editar_expediente(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)
        
        # Instanciar el formulario según el tipo
        if exp.tipo_tramite == "Judicial":
            form = ExpedienteJudicialForm()
        else:
            form = ExpedienteAdministrativoForm()
            
        # Llenar selectores
        clientes_db = Cliente.query.all()
        opciones_clientes = [(c.id, f"{c.nombres} {c.apellidos}") for c in clientes_db]
        
        abogados_db = Usuario.query.filter(
            Usuario.rol.in_(["Asociado", "Socio", "Administrador"])
        ).all()
        opciones_abogados = [(a.id, a.nombre) for a in abogados_db]
        
        form.cliente_id.choices = opciones_clientes
        form.abogado_responsable_id.choices = [(0, "Seleccione un abogado...")] + opciones_abogados
        
        if request.method == "GET":
            # Pre-poblar los campos
            form.cliente_id.data = exp.cliente_id
            form.abogado_responsable_id.data = exp.abogado_responsable_id or 0
            form.nombre_caso.data = exp.nombre_caso
            form.rol_firma.data = exp.rol_firma
            
            if exp.tipo_tramite == "Judicial":
                form.rama_derecho.data = exp.rama_derecho
                form.sub_categoria.data = exp.sub_categoria
                form.tipo_accion.data = exp.tipo_accion
                form.jurisdiccion_actual.data = exp.jurisdiccion_actual
                form.tribunal_asignado.data = exp.tribunal_asignado
                form.numero_expediente_tribunal.data = exp.numero_expediente_tribunal
                form.juez_asignado.data = exp.juez_asignado
                form.nombre_contraparte.data = exp.nombre_contraparte
                form.contacto_contraparte.data = exp.contacto_contraparte
                form.abogado_contraparte.data = exp.abogado_contraparte
                form.contacto_abogado_contraparte.data = exp.contacto_abogado_contraparte
                form.monto_demanda.data = exp.monto_demanda
                form.fecha_audiencia.data = exp.fecha_audiencia
                form.hora_audiencia.data = exp.hora_audiencia
            else:
                form.tipo_proceso.data = exp.tipo_proceso
                form.sub_proceso.data = exp.sub_proceso
                form.institucion_encargada.data = exp.institucion_encargada
                form.numero_solicitud_oficial.data = exp.numero_solicitud_oficial
                form.descripcion_tramite.data = exp.descripcion_tramite
                form.monto_tasas_impuestos.data = exp.monto_tasas_impuestos
                
        if form.validate_on_submit():
            # Actualizar datos comunes
            exp.cliente_id = form.cliente_id.data
            exp.abogado_responsable_id = form.abogado_responsable_id.data if form.abogado_responsable_id.data != 0 else None
            exp.nombre_caso = form.nombre_caso.data.strip()
            exp.rol_firma = form.rol_firma.data
            
            if exp.tipo_tramite == "Judicial":
                exp.rama_derecho = form.rama_derecho.data
                exp.sub_categoria = form.sub_categoria.data.strip() if form.sub_categoria.data else None
                exp.tipo_accion = form.tipo_accion.data.strip() if form.tipo_accion.data else None
                exp.jurisdiccion_actual = form.jurisdiccion_actual.data
                exp.tribunal_asignado = form.tribunal_asignado.data.strip() if form.tribunal_asignado.data else None
                exp.numero_expediente_tribunal = form.numero_expediente_tribunal.data.strip() if form.numero_expediente_tribunal.data else None
                exp.juez_asignado = form.juez_asignado.data.strip() if form.juez_asignado.data else None
                exp.nombre_contraparte = form.nombre_contraparte.data.strip() if form.nombre_contraparte.data else None
                exp.contacto_contraparte = form.contacto_contraparte.data.strip() if form.contacto_contraparte.data else None
                exp.abogado_contraparte = form.abogado_contraparte.data.strip() if form.abogado_contraparte.data else None
                exp.contacto_abogado_contraparte = form.contacto_abogado_contraparte.data.strip() if form.contacto_abogado_contraparte.data else None
                exp.monto_demanda = form.monto_demanda.data
                exp.fecha_audiencia = form.fecha_audiencia.data
                exp.hora_audiencia = form.hora_audiencia.data
            else:
                exp.tipo_proceso = form.tipo_proceso.data
                exp.sub_proceso = form.sub_proceso.data.strip() if form.sub_proceso.data else None
                exp.institucion_encargada = form.institucion_encargada.data.strip() if form.institucion_encargada.data else None
                exp.numero_solicitud_oficial = form.numero_solicitud_oficial.data.strip() if form.numero_solicitud_oficial.data else None
                exp.descripcion_tramite = form.descripcion_tramite.data.strip() if form.descripcion_tramite.data else None
                exp.monto_tasas_impuestos = form.monto_tasas_impuestos.data
                
            try:
                db.session.commit()
                flash("Expediente actualizado exitosamente.", "success")
                return redirect(url_for("expedientes"))
            except Exception as e:
                db.session.rollback()
                flash(f"Error al actualizar el expediente: {str(e)}", "danger")
                
        return render_template(
            "expedientes/editar.html",
            form=form,
            exp=exp
        )

    @app.route("/expedientes/<int:expediente_id>/cambiar_estado/<string:nuevo_estado>", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def cambiar_estado_expediente(expediente_id, nuevo_estado):
        if nuevo_estado not in ["Abierto", "Suspendido", "Archivado"]:
            flash("Estado inválido.", "danger")
            return redirect(url_for("expedientes"))

        exp = Expediente.query.get_or_404(expediente_id)
        exp.estado = nuevo_estado
        
        if nuevo_estado == "Archivado":
            exp.fecha_cierre = datetime.utcnow()
        else:
            exp.fecha_cierre = None
            
        try:
            db.session.commit()
            flash(f"Estado del expediente cambiado a {nuevo_estado}.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al cambiar el estado del expediente: {str(e)}", "danger")
            
        return redirect(url_for("expedientes"))

    @app.route("/expedientes/<int:expediente_id>/eliminar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def eliminar_expediente(expediente_id):

        exp = Expediente.query.get_or_404(expediente_id)
        try:
            db.session.delete(exp)
            db.session.commit()
            flash("Expediente eliminado correctamente del sistema.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al eliminar el expediente. Puede que tenga tareas o documentos vinculados. Detalle: {str(e)}", "danger")
            
        return redirect(url_for("expedientes"))
