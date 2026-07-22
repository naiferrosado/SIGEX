import os
import uuid  # Para generar el código único de la firma
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import flash, jsonify, redirect, render_template, request, url_for, send_from_directory, current_app
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from email_validator import validate_email, EmailNotValidError

from app import db
from app.forms import (
    ClienteForm,
    ExpedienteAdministrativoForm,
    ExpedienteJudicialForm,
    LoginForm,
    UsuarioForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    TareaForm,
    UserProfileForm,
    ChangePasswordForm,
    RequiredChangePasswordForm,
)
from app.utils import (
    generate_reset_token,
    verify_reset_token,
    enviar_email_restablecimiento,
    enviar_email_alerta_preventiva,
    enviar_email_credenciales_cliente,
)
from app.models import (
    AlertaPlazoAudiencia,
    BitacoraAuditoria,
    BitacoraTiempoTarea,
    Cliente,
    Documento,
    TipoDocumento,
    Carpeta,
    Expediente,
    ExpedienteAdministrativo,
    ExpedienteJudicial,
    FacturaHonorario,
    Usuario,
    VersionDocumento,
    rd_now,
    Tarea,
    NotificacionInterna,
    RegistroEnvioAlerta,
)

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "rtf", "odt", "png", "jpg", "jpeg", "gif", "webp",
    "zip", "rar", "7z", "tar", "gz"
}

def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _serialize_clientes(clientes):
    return [
        {
            "id": c.id,
            "nombre": f"{c.nombres} {c.apellidos}",
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
            "cliente_nombre": exp.cliente.nombre_completo
            if exp.cliente
            else "Desconocido",
            "abogado_responsable_id": exp.abogado_responsable_id,
            "abogado_responsable_nombre": exp.abogado_responsable.nombre
            if exp.abogado_responsable
            else "No asignado",
            "nombre_caso": exp.nombre_caso,
            "rol_firma": exp.rol_firma,
            "tipo_tramite": exp.tipo_tramite,
            "estado": exp.estado,
            "fecha_apertura": exp.fecha_apertura.strftime("%Y-%m-%d")
            if exp.fecha_apertura
            else None,
            "fecha_cierre": exp.fecha_cierre.strftime("%Y-%m-%d")
            if exp.fecha_cierre
            else None,
        }
        if exp.tipo_tramite == "Judicial":
            next_hearing = (
                AlertaPlazoAudiencia.query.filter_by(expediente_id=exp.id, es_audiencia=True, estado_alerta="Pendiente")
                .order_by(AlertaPlazoAudiencia.fecha_vencimiento.asc())
                .first()
            )
            item.update(
                {
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
                    "fecha_audiencia": next_hearing.fecha_vencimiento.strftime("%Y-%m-%d") if next_hearing else None,
                    "hora_audiencia": next_hearing.fecha_vencimiento.strftime("%H:%M") if next_hearing else None,
                }
            )
        elif exp.tipo_tramite == "Administrativo":
            item.update(
                {
                    "tipo_proceso": exp.tipo_proceso,
                    "sub_proceso": exp.sub_proceso,
                    "institucion_encargada": exp.institucion_encargada,
                    "numero_solicitud_oficial": exp.numero_solicitud_oficial,
                    "descripcion_tramite": exp.descripcion_tramite,
                    "monto_tasas_impuestos": float(exp.monto_tasas_impuestos)
                    if exp.monto_tasas_impuestos is not None
                    else None,
                }
            )
        data.append(item)
    return data


def registrar_auditoria(usuario_id, accion, detalles, cliente_id=None, expediente_id=None):
    try:
        ip = request.remote_addr or "127.0.0.1"
        dispositivo = request.user_agent.string[:255] if request.user_agent and request.user_agent.string else "Desconocido"
        log = BitacoraAuditoria(
            usuario_id=usuario_id,
            accion_realizada=accion[:50],
            detalles_tecnicos=detalles,
            ip_direccion=ip,
            dispositivo_info=dispositivo,
            cliente_id=cliente_id,
            expediente_id=expediente_id,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # En caso de error, no interrumpimos la app, solo imprimimos
        print(f"Error al registrar auditoría: {str(e)}")


def roles_permitidos(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if current_user.rol not in roles:
                flash(
                    "Acceso denegado. No tiene permisos para acceder a esta sección o realizar esta acción.",
                    "danger",
                )
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def register_routes(app):

    @app.before_request
    def force_password_change():
        if not request.endpoint:
            return
        if request.endpoint in ["static", "logout", "cambiar_password_obligatorio"]:
            return

        if current_user.is_authenticated and current_user.requiere_cambio_password:
            return redirect(url_for("cambiar_password_obligatorio"))

    @app.route("/", methods=["GET", "POST"])
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        form = LoginForm()

        if form.validate_on_submit():
            usuario = Usuario.query.filter_by(email=form.email.data).first()

            if usuario:
                ahora = rd_now()
                # 1. Verificar si la cuenta está bloqueada temporalmente
                if usuario.bloqueado_hasta and ahora < usuario.bloqueado_hasta:
                    tiempo_restante = usuario.bloqueado_hasta - ahora
                    minutos_restantes = int(tiempo_restante.total_seconds() / 60) + 1
                    flash(
                        f"Su cuenta está bloqueada temporalmente debido a múltiples intentos fallidos. Intente de nuevo en {minutos_restantes} minuto(s).",
                        "danger",
                    )
                    return render_template("auth/login.html", form=form)

                # 2. Verificar contraseña
                if check_password_hash(usuario.password_hash, form.password.data):
                    if not usuario.activo:
                        flash(
                            "Su cuenta está suspendida. Por favor, póngase en contacto con el administrador.",
                            "danger",
                        )
                        return render_template("auth/login.html", form=form)

                    # Resetear contador e intentos fallidos al iniciar sesión exitosamente
                    usuario.intentos_fallidos = 0
                    usuario.bloqueado_hasta = None
                    db.session.commit()

                    login_user(usuario, remember=form.recordarme.data)
                    next_page = request.args.get("next")
                    if next_page:
                        parsed_url = urlparse(next_page)
                        if parsed_url.netloc or not next_page.startswith("/"):
                            next_page = None

                    return (
                        redirect(next_page) if next_page else redirect(url_for("dashboard"))
                    )
                else:
                    # Contraseña incorrecta
                    if usuario.bloqueado_hasta and ahora >= usuario.bloqueado_hasta:
                        # Si el bloqueo ya expiró pero no se limpió, reiniciamos a 1
                        usuario.intentos_fallidos = 1
                        usuario.bloqueado_hasta = None
                    else:
                        usuario.intentos_fallidos += 1

                    if usuario.intentos_fallidos >= 5:
                        usuario.bloqueado_hasta = ahora + timedelta(minutes=30)
                        flash(
                            "Ha superado el límite de 5 intentos fallidos. Su cuenta ha sido bloqueada temporalmente por 30 minutos.",
                            "danger",
                        )
                    else:
                        intentos_restantes = 5 - usuario.intentos_fallidos
                        flash(
                            f"Credenciales incorrectas. Le quedan {intentos_restantes} intento(s) antes de bloquear su cuenta.",
                            "danger",
                        )
                    db.session.commit()
            else:
                # Mostrar error genérico si el correo no coincide con ningún usuario
                flash(
                    "Credenciales incorrectas. Verifique su correo institucional y contraseña.",
                    "danger",
                )

        return render_template("auth/login.html", form=form)

    @app.route("/olvidaste-password", methods=["GET", "POST"])
    def reset_password_request():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        form = ForgotPasswordForm()
        if form.validate_on_submit():
            usuario = Usuario.query.filter_by(email=form.email.data).first()
            if usuario:
                token = generate_reset_token(usuario.id)
                reset_url = url_for("reset_password", token=token, _external=True)
                enviar_email_restablecimiento(usuario, reset_url)
            flash(
                "Si el correo electrónico ingresado está registrado, recibirás un mensaje con las instrucciones para restablecer tu contraseña.",
                "success"
            )
            return redirect(url_for("login"))
        return render_template("auth/reset_password_request.html", form=form)

    @app.route("/restablecer-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        user_id = verify_reset_token(token)
        if not user_id:
            flash("El enlace de restablecimiento es inválido o ha expirado.", "danger")
            return redirect(url_for("reset_password_request"))
        
        usuario = Usuario.query.get(user_id)
        if not usuario:
            flash("El usuario no existe.", "danger")
            return redirect(url_for("reset_password_request"))

        form = ResetPasswordForm()
        if form.validate_on_submit():
            usuario.password_hash = generate_password_hash(form.password.data)
            usuario.requiere_cambio_password = False
            try:
                db.session.commit()
                flash("Tu contraseña ha sido restablecida con éxito. Ya puedes iniciar sesión.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar la nueva contraseña: {str(e)}", "danger")
        return render_template("auth/reset_password.html", form=form)

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

                total_general = max(
                    1,
                    total_expedientes
                    + total_clientes
                    + total_documentos
                    + total_alertas
                    + total_facturas
                    + total_usuarios,
                )

                # Aprobaciones pendientes (tiempos reportados por asociados/paralegales en estado 'Abierto')
                tiempos_pendientes = (
                    BitacoraTiempoTarea.query.filter_by(estado_cierre="Abierto")
                    .limit(5)
                    .all()
                )
                total_tiempos_pendientes_count = BitacoraTiempoTarea.query.filter_by(
                    estado_cierre="Abierto"
                ).count()

                # Facturas y finanzas
                facturas_pendientes_monto = (
                    db.session.query(db.func.sum(FacturaHonorario.monto_total))
                    .filter_by(estado_pago="Pendiente")
                    .scalar()
                    or 0.00
                )
                facturas_emitidas_mes = FacturaHonorario.query.filter(
                    FacturaHonorario.fecha_emision >= start_of_month
                ).count()

                # Horas facturables aprobadas
                horas_facturables_mes = (
                    db.session.query(db.func.sum(BitacoraTiempoTarea.horas_trabajadas))
                    .filter_by(estado_cierre="Aprobado")
                    .filter(BitacoraTiempoTarea.fecha_tarea >= start_of_month.date())
                    .scalar()
                    or 0.00
                )

                # Coberturas y porcentajes
                estadisticas = {
                    "clientes": total_clientes,
                    "expedientes": total_expedientes,
                    "alertas": total_alertas,
                    "documentos": total_documentos,
                    "facturas": total_facturas,
                    "usuarios": total_usuarios,
                    "total_general": total_general,
                    "porcentaje_expedientes": round(
                        (total_expedientes / total_general) * 100, 1
                    ),
                    "porcentaje_clientes": round(
                        (total_clientes / total_general) * 100, 1
                    ),
                    "porcentaje_documentos": round(
                        (total_documentos / total_general) * 100, 1
                    ),
                    "porcentaje_alertas": round(
                        (total_alertas / total_general) * 100, 1
                    ),
                    "porcentaje_facturas": round(
                        (total_facturas / total_general) * 100, 1
                    ),
                    "porcentaje_usuarios": round(
                        (total_usuarios / total_general) * 100, 1
                    ),
                    "tiempos_pendientes": tiempos_pendientes,
                    "total_tiempos_pendientes_count": total_tiempos_pendientes_count,
                    "facturas_pendientes_monto": float(facturas_pendientes_monto),
                    "facturas_emitidas_mes": facturas_emitidas_mes,
                    "horas_facturables_mes": float(horas_facturables_mes),
                }
                return render_template(
                    "dashboard/dashboard_socio.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now(),
                )

            # --- ASOCIADO ---
            elif rol == "Asociado":
                # Filtrar métricas de sus expedientes asignados
                mis_expedientes_activos = (
                    Expediente.query.filter_by(abogado_responsable_id=current_user.id)
                    .filter(Expediente.estado != "Archivado")
                    .count()
                )

                # Obtener IDs de sus expedientes para alertas
                mis_expedientes_ids = [
                    e.id
                    for e in Expediente.query.filter_by(
                        abogado_responsable_id=current_user.id
                    ).all()
                ]

                mis_alertas_semana = (
                    AlertaPlazoAudiencia.query.filter(
                        AlertaPlazoAudiencia.expediente_id.in_(mis_expedientes_ids)
                    )
                    .filter(AlertaPlazoAudiencia.estado_alerta == "Pendiente")
                    .count()
                    if mis_expedientes_ids
                    else 0
                )
                mis_vencimientos_proximos = (
                    AlertaPlazoAudiencia.query.filter(
                        AlertaPlazoAudiencia.expediente_id.in_(mis_expedientes_ids)
                    )
                    .filter(AlertaPlazoAudiencia.estado_alerta == "Pendiente")
                    .count()
                    if mis_expedientes_ids
                    else 0
                )

                # Horas del mes
                mis_horas_mes = (
                    db.session.query(db.func.sum(BitacoraTiempoTarea.horas_trabajadas))
                    .filter_by(usuario_id=current_user.id)
                    .filter(BitacoraTiempoTarea.fecha_tarea >= start_of_month.date())
                    .scalar()
                    or 0.00
                )
                mis_horas_pendientes = (
                    db.session.query(db.func.sum(BitacoraTiempoTarea.horas_trabajadas))
                    .filter_by(usuario_id=current_user.id, estado_cierre="Abierto")
                    .scalar()
                    or 0.00
                )

                # Actividades del asociado
                mis_tareas_recientes = (
                    BitacoraTiempoTarea.query.filter_by(usuario_id=current_user.id)
                    .order_by(BitacoraTiempoTarea.fecha_tarea.desc())
                    .limit(5)
                    .all()
                )
                mis_expedientes_todos = (
                    Expediente.query.filter_by(abogado_responsable_id=current_user.id)
                    .order_by(Expediente.fecha_apertura.desc())
                    .limit(5)
                    .all()
                )

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
                    "total_facturable_proyectado": total_facturable_proyectado,
                }
                return render_template(
                    "dashboard/dashboard_asociado.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now(),
                )

            # --- PARALEGAL ---
            elif rol == "Paralegal":
                # El paralegal ve tareas administrativas y soporte
                expedientes_activos = Expediente.query.filter(
                    Expediente.estado != "Archivado"
                ).count()
                total_tareas_pendientes = Tarea.query.filter(
                    Tarea.estado != "Completada"
                ).filter(
                    db.or_(
                        Tarea.asignado_a_id == current_user.id,
                        Tarea.asignado_a_id == None
                    )
                ).count()
                mis_documentos_cargados = VersionDocumento.query.filter_by(
                    usuario_id=current_user.id
                ).count()

                # Tareas de apoyo reportadas y aprobadas este mes
                tareas_completadas = (
                    BitacoraTiempoTarea.query.filter_by(
                        usuario_id=current_user.id, estado_cierre="Aprobado"
                    )
                    .filter(BitacoraTiempoTarea.fecha_tarea >= start_of_month.date())
                    .count()
                )

                documentos_recientes = (
                    VersionDocumento.query.order_by(VersionDocumento.fecha_carga.desc())
                    .limit(5)
                    .all()
                )
                tareas_proximas = (
                    BitacoraTiempoTarea.query.filter_by(usuario_id=current_user.id)
                    .order_by(BitacoraTiempoTarea.fecha_tarea.desc())
                    .limit(5)
                    .all()
                )

                estadisticas = {
                    "expedientes_activos": expedientes_activos,
                    "tareas_pendientes": total_tareas_pendientes,
                    "documentos_cargados": mis_documentos_cargados,
                    "tareas_completadas": tareas_completadas,
                    "documentos_recientes": documentos_recientes,
                    "tareas_proximas": tareas_proximas,
                }
                return render_template(
                    "dashboard/dashboard_paralegal.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now(),
                )

            # --- ADMINISTRADOR ---
            elif rol == "Administrador":
                usuarios_activos = Usuario.query.filter_by(activo=True).count()
                expedientes_totales = Expediente.query.count()
                documentos_almacenados = Documento.query.count()
                horas_registradas = (
                    db.session.query(
                        db.func.sum(BitacoraTiempoTarea.horas_trabajadas)
                    ).scalar()
                    or 0.00
                )
                facturacion_total = (
                    db.session.query(db.func.sum(FacturaHonorario.monto_total)).scalar()
                    or 0.00
                )

                # Logs de auditoría de hoy
                eventos_auditoria_hoy = BitacoraAuditoria.query.filter(
                    db.func.date(BitacoraAuditoria.fecha_hora) == db.func.current_date()
                ).count()
                auditorias_recientes = (
                    BitacoraAuditoria.query.order_by(
                        BitacoraAuditoria.fecha_hora.desc()
                    )
                    .limit(8)
                    .all()
                )

                # Distribución de usuarios
                socios_count = Usuario.query.filter_by(rol="Socio").count()
                asociados_count = Usuario.query.filter_by(rol="Asociado").count()
                paralegales_count = Usuario.query.filter_by(rol="Paralegal").count()
                administradores_count = Usuario.query.filter_by(
                    rol="Administrador"
                ).count()
                clientes_count = Usuario.query.filter_by(rol="Cliente").count()

                # 1. Obtener versión real de PostgreSQL
                try:
                    db_version_row = db.session.execute(db.text("SHOW server_version;")).first()
                    db_version = f"PostgreSQL {db_version_row[0].split()[0]}" if db_version_row else "PostgreSQL 15"
                except Exception:
                    db_version = "PostgreSQL 15"

                # 2. Obtener almacenamiento libre de la carpeta uploads
                import shutil
                try:
                    uploads_path = os.path.join(current_app.root_path, 'uploads')
                    if not os.path.exists(uploads_path):
                        os.makedirs(uploads_path)
                    total, used, free = shutil.disk_usage(uploads_path)
                    free_gb = free / (1024 ** 3)
                    almacenamiento_status = f"{free_gb:.1f} GB Libres"
                except Exception:
                    almacenamiento_status = "Operativo"

                # 3. Verificar estado del servicio de correos (SMTP)
                import socket
                mail_server = current_app.config.get('MAIL_SERVER')
                mail_port = current_app.config.get('MAIL_PORT')
                mail_username = current_app.config.get('MAIL_USERNAME')
                mail_password = current_app.config.get('MAIL_PASSWORD')

                if not mail_username or not mail_password:
                    mail_status = "No configurado"
                    mail_badge_class = "bg-warning text-dark"
                else:
                    try:
                        # Test de conexión rápido (timeout de 1.0 segundos)
                        s = socket.create_connection((mail_server, mail_port), timeout=1.0)
                        s.close()
                        mail_status = "Activo"
                        mail_badge_class = "bg-success"
                    except Exception:
                        mail_status = "Error de Conexión"
                        mail_badge_class = "bg-danger"

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
                    "clientes_count": clientes_count,
                    "db_version": db_version,
                    "almacenamiento_status": almacenamiento_status,
                    "mail_status": mail_status,
                    "mail_badge_class": mail_badge_class,
                }
                return render_template(
                    "dashboard/dashboard_admin.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now(),
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
                        "actividades": [],
                    }
                    return render_template(
                        "dashboard/dashboard_cliente.html",
                        usuario=current_user,
                        estadisticas=estadisticas,
                        current_date=rd_now(),
                    )

                expedientes_cliente = Expediente.query.filter_by(
                    cliente_id=cliente_db.id
                ).all()
                expedientes_activos_count = sum(
                    1 for e in expedientes_cliente if e.estado != "Archivado"
                )

                exp_ids = [e.id for e in expedientes_cliente]
                
                # 1. Buscar caso activo principal primero
                caso_activo_principal = None
                for e in expedientes_cliente:
                    if e.estado in ["Abierto", "Suspendido"]:
                        caso_activo_principal = e
                        break
                if not caso_activo_principal:
                    for e in expedientes_cliente:
                        if e.estado == "Finalizado":
                            caso_activo_principal = e
                            break

                # 2. Obtener próximo evento según tipo de trámite
                audiencia_proxima = None
                if exp_ids:
                    query_audiencia = AlertaPlazoAudiencia.query.filter(
                        AlertaPlazoAudiencia.expediente_id.in_(exp_ids)
                    ).filter(
                        AlertaPlazoAudiencia.estado_alerta.in_(["Pending", "Pendiente"])
                    )

                    # Si es Judicial, buscar específicamente audiencias. Si es Administrativo, buscar cualquier hito/plazo pendiente.
                    if caso_activo_principal and caso_activo_principal.tipo_tramite == "Judicial":
                        query_audiencia = query_audiencia.filter(AlertaPlazoAudiencia.es_audiencia == True)

                    audiencia_proxima = query_audiencia.order_by(AlertaPlazoAudiencia.fecha_vencimiento.asc()).first()

                documentos_compartidos = []
                if cliente_db:
                    if exp_ids:
                        documentos_compartidos = (
                            Documento.query.filter(Documento.visibilidad == "Compartido")
                            .filter(
                                db.or_(
                                    Documento.expediente_id.in_(exp_ids),
                                    Documento.cliente_id == cliente_db.id
                                )
                            ).all()
                        )
                    else:
                        documentos_compartidos = (
                            Documento.query.filter_by(
                                visibilidad="Compartido",
                                cliente_id=cliente_db.id
                            ).all()
                        )

                alertas_recientes = []
                if exp_ids:
                    alertas_recientes = (
                        AlertaPlazoAudiencia.query.filter(
                            AlertaPlazoAudiencia.expediente_id.in_(exp_ids)
                        )
                        .order_by(AlertaPlazoAudiencia.fecha_vencimiento.desc())
                        .limit(5)
                        .all()
                    )

                # Fases del caso principal (Leídas de base de datos)
                progreso_fase = 1
                if caso_activo_principal:
                    if caso_activo_principal.estado in ["Archivado", "Finalizado"]:
                        progreso_fase = 5
                    else:
                        progreso_fase = caso_activo_principal.fase_actual or 1

                estadisticas = {
                    "expedientes_activos_count": expedientes_activos_count,
                    "audiencia_proxima": audiencia_proxima,
                    "documentos_disponibles_count": len(documentos_compartidos),
                    "expedientes": expedientes_cliente,
                    "documentos": documentos_compartidos,
                    "actividades": alertas_recientes,
                    "caso_activo_principal": caso_activo_principal,
                    "progreso_fase": progreso_fase,
                }
                return render_template(
                    "dashboard/dashboard_cliente.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now(),
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
        return render_template(
            "clientes/clientes.html",
            form=form,
            usuario=current_user,
            current_date=datetime.now(),
        )

    @app.route("/clientes/buscar")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def buscar_clientes():
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "Todos").strip()
        tipo = request.args.get("tipo", "Todos").strip()

        # Si no hay término de búsqueda, no se muestra nada (según requerimiento)
        if not q:
            return jsonify([])

        search_pattern = f"%{q}%"
        query = Cliente.query.filter(
            db.or_(
                Cliente.nombres.ilike(search_pattern),
                Cliente.apellidos.ilike(search_pattern),
                Cliente.rnc_cedula.ilike(search_pattern),
                Cliente.email_contacto.ilike(search_pattern),
            )
        )

        if status == "Activo":
            query = query.filter_by(consentimiento_datos=True)
        elif status == "Inactivo":
            query = query.filter_by(consentimiento_datos=False)

        if tipo != "Todos":
            query = query.filter_by(tipo_cliente=tipo)

        clientes_db = query.order_by(Cliente.nombres.asc()).all()

        results = [
            {
                "id": c.id,
                "nombre": f"{c.nombres} {c.apellidos}",
                "consentimiento_datos": bool(c.consentimiento_datos)
            }
            for c in clientes_db
        ]
        return jsonify(results)

    @app.route("/clientes/<int:cliente_id>/detalle")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def detalle_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)

        # 1. Registrar auditoría de visualización
        registrar_auditoria(
            usuario_id=current_user.id,
            accion="Visualización",
            detalles="Consultó la información detallada del cliente.",
            cliente_id=cliente.id,
        )

        # 2. Obtener auditorías asociadas a este cliente (solo para Administrador)
        auditorias_data = []
        if current_user.rol == "Administrador":
            auditorias_db = (
                BitacoraAuditoria.query.filter_by(cliente_id=cliente.id)
                .order_by(BitacoraAuditoria.fecha_hora.desc())
                .all()
            )

            auditorias_data = [
                {
                    "id": log.id,
                    "fecha_hora": log.fecha_hora.strftime("%d/%m/%Y %I:%M %p"),
                    "usuario": log.usuario.nombre if log.usuario else "Desconocido",
                    "accion": log.accion_realizada,
                    "detalles": log.detalles_tecnicos,
                    "ip": log.ip_direccion,
                    "dispositivo": log.dispositivo_info,
                }
                for log in auditorias_db
            ]

        # 3. Obtener información de usuario vinculado
        usuario_info = None
        if cliente.usuario_id:
            user = Usuario.query.get(cliente.usuario_id)
            if user:
                usuario_info = {
                    "id": user.id,
                    "email": user.email,
                    "activo": user.activo
                }

        # 4. Retornar detalles con auditorías
        return jsonify(
            {
                "id": cliente.id,
                "nombre": f"{cliente.nombres} {cliente.apellidos}",
                "nombres": cliente.nombres,
                "apellidos": cliente.apellidos,
                "rnc_cedula": cliente.rnc_cedula,
                "telefono": cliente.telefono or "",
                "email_contacto": cliente.email_contacto,
                "consentimiento_datos": bool(cliente.consentimiento_datos),
                "tipo_cliente": cliente.tipo_cliente,
                "direccion": cliente.direccion or "",
                "fecha_nacimiento": cliente.fecha_nacimiento.strftime("%Y-%m-%d")
                if cliente.fecha_nacimiento
                else "",
                "razon_desactivacion": cliente.razon_desactivacion or "",
                "auditorias": auditorias_data,
                "usuario_info": usuario_info,
            }
        )

    @app.route("/clientes/<int:cliente_id>/habilitar_acceso", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def habilitar_acceso_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        if cliente.usuario_id:
            flash("El cliente ya posee una cuenta de acceso vinculada.", "warning")
            return redirect(url_for("clientes", id=cliente.id))

        email_limpio = cliente.email_contacto.strip().lower()
        if not email_limpio:
            flash("El cliente debe tener un correo de contacto configurado para habilitar acceso.", "danger")
            return redirect(url_for("clientes", id=cliente.id))

        # Validar la entregabilidad del correo de forma estricta (realiza consulta DNS MX)
        try:
            validate_email(email_limpio, check_deliverability=True)
        except EmailNotValidError as e:
            flash(f"El correo electrónico no es válido o no tiene un servidor de correo real: {str(e)}", "danger")
            return redirect(url_for("clientes", id=cliente.id))

        existente = Usuario.query.filter_by(email=email_limpio).first()
        if existente:
            if existente.rol == "Cliente":
                cliente.usuario_id = existente.id
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Activación",
                    detalles=f"Vinculó la cuenta de acceso existente del cliente {cliente.nombre_completo}.",
                    cliente_id=cliente.id
                )
                flash("Cuenta de acceso existente vinculada con éxito.", "success")
            else:
                flash(f"El correo electrónico '{email_limpio}' ya está en uso por un miembro de la firma.", "danger")
            return redirect(url_for("clientes", id=cliente.id))

        clave_inicial = cliente.rnc_cedula.strip()
        if not clave_inicial:
            flash("El cliente debe poseer cédula o RNC para usar de contraseña inicial.", "danger")
            return redirect(url_for("clientes", id=cliente.id))

        nuevo_usuario = Usuario(
            nombre=cliente.nombre_completo,
            email=email_limpio,
            rol="Cliente",
            password_hash=generate_password_hash(clave_inicial),
            activo=True,
            requiere_cambio_password=True
        )

        try:
            db.session.add(nuevo_usuario)
            db.session.flush()
            cliente.usuario_id = nuevo_usuario.id
 
            # Enviar credenciales por correo antes de confirmar en BD
            email_enviado = enviar_email_credenciales_cliente(cliente, email_limpio, clave_inicial)
            if not email_enviado:
                raise Exception("El servidor de correo rechazó el envío o la dirección de correo no es válida.")
 
            db.session.commit()
 
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Creación",
                detalles=f"Habilitó acceso al portal del cliente. Creada cuenta de usuario '{email_limpio}' con clave inicial y notificado por correo.",
                cliente_id=cliente.id
            )
            flash("Acceso al portal habilitado con éxito. Se ha enviado un correo con las credenciales al cliente para verificar la validez de la cuenta.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al verificar correo o habilitar acceso: {str(e)}", "danger")

        return redirect(url_for("clientes", id=cliente.id))

    @app.route("/clientes/<int:cliente_id>/desactivar_acceso", methods=["POST"])
    @login_required
    @roles_permitidos("Administrador")
    def desactivar_acceso_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        if not cliente.usuario_id:
            flash("El cliente no tiene una cuenta de acceso vinculada.", "warning")
            return redirect(url_for("clientes", id=cliente.id))

        user = Usuario.query.get(cliente.usuario_id)
        if user:
            user.activo = False
            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Desactivación",
                    detalles=f"Desactivó la cuenta de acceso del cliente ({user.email}).",
                    cliente_id=cliente.id
                )
                flash("Acceso al portal desactivado temporalmente para este cliente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al suspender cuenta de acceso: {str(e)}", "danger")
        else:
            flash("No se encontró la cuenta de acceso.", "danger")

        return redirect(url_for("clientes", id=cliente.id))

    @app.route("/clientes/<int:cliente_id>/reactivar_acceso", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def reactivar_acceso_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        if not cliente.usuario_id:
            flash("El cliente no tiene una cuenta de acceso vinculada.", "warning")
            return redirect(url_for("clientes", id=cliente.id))

        user = Usuario.query.get(cliente.usuario_id)
        if user:
            user.activo = True
            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Activación",
                    detalles=f"Reactivó la cuenta de acceso del cliente ({user.email}).",
                    cliente_id=cliente.id
                )
                flash("Acceso al portal reactivado con éxito para este cliente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al reactivar cuenta de acceso: {str(e)}", "danger")
        else:
            flash("No se encontró la cuenta de acceso.", "danger")

        return redirect(url_for("clientes", id=cliente.id))

    @app.route("/clientes/<int:cliente_id>/restablecer_clave_acceso", methods=["POST"])
    @login_required
    @roles_permitidos("Administrador")
    def restablecer_clave_acceso_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)
        if not cliente.usuario_id:
            flash("El cliente no tiene una cuenta de acceso vinculada.", "warning")
            return redirect(url_for("clientes", id=cliente.id))

        user = Usuario.query.get(cliente.usuario_id)
        if user:
            clave_inicial = cliente.rnc_cedula.strip()
            if not clave_inicial:
                flash("El cliente debe poseer cédula o RNC para restablecer la contraseña.", "danger")
                return redirect(url_for("clientes", id=cliente.id))

            user.password_hash = generate_password_hash(clave_inicial)
            user.requiere_cambio_password = True
            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles=f"Restableció la contraseña de acceso del cliente a su cédula/RNC inicial.",
                    cliente_id=cliente.id
                )
                flash("Contraseña restablecida con éxito a la cédula/RNC del cliente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al restablecer contraseña: {str(e)}", "danger")
        else:
            flash("No se encontró la cuenta de acceso.", "danger")

        return redirect(url_for("clientes", id=cliente.id))

    @app.route("/clientes/agregar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agregar_cliente():
        # Flask-WTF toma automáticamente los datos de request.form
        form = ClienteForm()

        if form.validate_on_submit():
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
                # Registrar en auditoría
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Creación",
                    detalles=f"Creó el cliente {cliente.nombre_completo}.",
                    cliente_id=cliente.id,
                )
                flash("Cliente agregado correctamente.", "success")
                return redirect(url_for("clientes", id=cliente.id))
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
            # Verificar si se está intentando usar una cédula que ya tiene OTRO cliente
            duplicado = Cliente.query.filter_by(rnc_cedula=form.rnc_cedula.data).first()
            if duplicado and duplicado.id != cliente.id:
                flash("Ya existe un cliente con esa cédula o RNC.", "warning")
                return redirect(url_for("clientes", id=cliente.id))

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
                # Registrar en auditoría
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles=f"Modificó los datos del cliente {cliente.nombre_completo}.",
                    cliente_id=cliente.id,
                )
                flash("Datos del cliente actualizados correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar cambios del cliente: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error al editar: {error}", "danger")

        return redirect(url_for("clientes", id=cliente.id))

    @app.route("/clientes/<int:cliente_id>/desactivar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def desactivar_cliente(cliente_id):
        cliente = Cliente.query.get_or_404(cliente_id)

        if cliente.consentimiento_datos:
            # Desactivar requiere razón
            razon = request.form.get("razon", "").strip()
            if not razon:
                flash("Debe especificar una razón para desactivar al cliente.", "danger")
                return redirect(url_for("clientes", id=cliente.id))

            cliente.consentimiento_datos = False
            cliente.razon_desactivacion = razon
            try:
                db.session.commit()
                # Registrar en auditoría
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Desactivación",
                    detalles=f"Cliente desactivado. Razón: {razon}",
                    cliente_id=cliente.id,
                )
                flash("Cliente desactivado correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al desactivar el cliente: {str(e)}", "danger")
        else:
            # Reactivar
            cliente.consentimiento_datos = True
            cliente.razon_desactivacion = None
            try:
                db.session.commit()
                # Registrar en auditoría
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Activación",
                    detalles="Cliente reactivado en el sistema.",
                    cliente_id=cliente.id,
                )
                flash("Cliente reactivado correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al activar el cliente: {str(e)}", "danger")

        return redirect(url_for("clientes", id=cliente.id))

    @app.route("/logout")
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/perfil/cambiar-password-obligatorio", methods=["GET", "POST"])
    @login_required
    def cambiar_password_obligatorio():
        if not current_user.requiere_cambio_password:
            return redirect(url_for("dashboard"))

        form = RequiredChangePasswordForm()
        if form.validate_on_submit():
            current_user.password_hash = generate_password_hash(form.new_password.data)
            current_user.requiere_cambio_password = False
            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles="Estableció una contraseña nueva por requerimiento de primer inicio de sesión."
                )
                flash("Contraseña actualizada con éxito. Bienvenido al sistema.", "success")
                return redirect(url_for("dashboard"))
            except Exception as e:
                db.session.rollback()
                flash(f"Error al actualizar la contraseña: {str(e)}", "danger")

        return render_template("perfil/cambio_obligatorio.html", form=form)

    @app.route("/perfil", methods=["GET"])
    @login_required
    def ver_perfil():
        profile_form = UserProfileForm(obj=current_user)
        password_form = ChangePasswordForm()
        return render_template(
            "perfil/ver.html",
            usuario=current_user,
            profile_form=profile_form,
            password_form=password_form,
            current_date=rd_now()
        )

    @app.route("/perfil/editar", methods=["POST"])
    @login_required
    def editar_perfil():
        form = UserProfileForm()
        if form.validate_on_submit():
            existente = Usuario.query.filter(Usuario.email == form.email.data, Usuario.id != current_user.id).first()
            if existente:
                flash("El correo electrónico ya está registrado por otro usuario.", "danger")
                return redirect(url_for("ver_perfil"))

            old_nombre = current_user.nombre
            old_email = current_user.email
            current_user.nombre = form.nombre.data
            current_user.email = form.email.data

            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles=f"Actualizó sus datos personales de perfil: Nombre '{old_nombre}' -> '{current_user.nombre}', Correo '{old_email}' -> '{current_user.email}'."
                )
                flash("Datos personales actualizados correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al actualizar los datos: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error en {getattr(form, field).label.text}: {error}", "danger")

        return redirect(url_for("ver_perfil"))

    @app.route("/perfil/cambiar-password", methods=["POST"])
    @login_required
    def cambiar_password_perfil():
        form = ChangePasswordForm()
        if form.validate_on_submit():
            if not check_password_hash(current_user.password_hash, form.current_password.data):
                flash("La contraseña actual es incorrecta.", "danger")
                return redirect(url_for("ver_perfil"))

            current_user.password_hash = generate_password_hash(form.new_password.data)
            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles="Cambió voluntariamente su contraseña de acceso desde su perfil de usuario."
                )
                flash("Su contraseña ha sido modificada con éxito.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al cambiar la contraseña: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error en {getattr(form, field).label.text}: {error}", "danger")

        return redirect(url_for("ver_perfil"))

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
    @roles_permitidos("Administrador")
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
    @roles_permitidos("Administrador")
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
    @roles_permitidos("Administrador")
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
    @roles_permitidos("Administrador")
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

    # --- BITÁCORA DE AUDITORÍA GENERAL ---
    @app.route("/auditoria")
    @login_required
    @roles_permitidos("Administrador")
    def auditoria():
        page = request.args.get("page", 1, type=int)
        q = request.args.get("q", "").strip()
        accion = request.args.get("accion", "Todos").strip()
        usuario_filtro = request.args.get("usuario", "Todos").strip()

        query = BitacoraAuditoria.query

        if q:
            search_pattern = f"%{q}%"
            # Unir con Usuario para buscar por nombre
            query = query.join(Usuario, isouter=True).filter(
                db.or_(
                    BitacoraAuditoria.detalles_tecnicos.ilike(search_pattern),
                    BitacoraAuditoria.accion_realizada.ilike(search_pattern),
                    BitacoraAuditoria.ip_direccion.ilike(search_pattern),
                    Usuario.nombre.ilike(search_pattern)
                )
            )

        if accion != "Todos":
            query = query.filter(BitacoraAuditoria.accion_realizada == accion)

        if usuario_filtro != "Todos":
            try:
                u_id = int(usuario_filtro)
                query = query.filter(BitacoraAuditoria.usuario_id == u_id)
            except ValueError:
                pass

        # Paginar resultados (30 por página)
        pagination = query.order_by(BitacoraAuditoria.fecha_hora.desc()).paginate(
            page=page, per_page=30, error_out=False
        )

        # Obtener listado de acciones únicas para los filtros
        acciones_query = db.session.query(BitacoraAuditoria.accion_realizada).distinct().all()
        acciones_disponibles = [a[0] for a in acciones_query if a[0]]

        # Obtener listado de todos los usuarios para los filtros
        usuarios_disponibles = Usuario.query.order_by(Usuario.nombre.asc()).all()

        return render_template(
            "auditoria/index.html",
            pagination=pagination,
            acciones_disponibles=acciones_disponibles,
            usuarios_disponibles=usuarios_disponibles,
            q=q,
            accion_actual=accion,
            usuario_actual=usuario_filtro,
            usuario=current_user,
        )

    # --- LISTADO DE EXPEDIENTES ---
    @app.route("/expedientes")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def expedientes():
        return render_template(
            "expedientes/index.html",
            usuario=current_user,
        )

    @app.route("/expedientes/buscar")
    @login_required
    def buscar_expedientes():
        q = request.args.get("q", "").strip()
        status = request.args.get("status", "Todos").strip()
        tipo = request.args.get("tipo", "Todos").strip()

        # Si no hay término de búsqueda, no se muestra nada (según requerimiento)
        if not q:
            return jsonify([])

        search_pattern = f"%{q}%"
        query = Expediente.query.join(Cliente).filter(
            db.or_(
                Expediente.codigo_firma.ilike(search_pattern),
                Expediente.nombre_caso.ilike(search_pattern),
                Cliente.rnc_cedula.ilike(search_pattern),
                Cliente.nombres.ilike(search_pattern),
                Cliente.apellidos.ilike(search_pattern),
            )
        )

        if current_user.rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if not cliente_db:
                return jsonify([])
            exp_ids = [e.id for e in cliente_db.expedientes]
            query = query.filter(Expediente.id.in_(exp_ids))

        if status != "Todos":
            query = query.filter_by(estado=status)

        if tipo != "Todos":
            query = query.filter_by(tipo_tramite=tipo)

        lista_exp = query.order_by(Expediente.fecha_apertura.desc()).all()

        results = [
            {
                "id": exp.id,
                "codigo_firma": exp.codigo_firma,
                "nombre_caso": exp.nombre_caso,
                "cliente": exp.cliente.nombre_completo if exp.cliente else "N/A"
            }
            for exp in lista_exp
        ]
        return jsonify(results)

    @app.route("/expedientes/historial")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def historial_expedientes_finalizados():
        from sqlalchemy import extract
        anios = db.session.query(extract('year', Expediente.fecha_cierre)).filter(
            Expediente.estado == "Finalizado",
            Expediente.fecha_cierre.isnot(None)
        ).distinct().order_by(extract('year', Expediente.fecha_cierre).asc()).all()
        
        lista_anios = [int(a[0]) for a in anios if a[0] is not None]
        anio_actual = datetime.now().year
        if anio_actual not in lista_anios:
            lista_anios.append(anio_actual)
        lista_anios.sort()
        
        return render_template("expedientes/historial.html", anios=lista_anios)

    @app.route("/api/expedientes/finalizados")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def api_expedientes_finalizados():
        q = request.args.get("q", "").strip()
        anio_desde = request.args.get("anio_desde", type=int)
        anio_hasta = request.args.get("anio_hasta", type=int)
        tipo_finalizacion = request.args.get("tipo_finalizacion", "").strip()
        tipo_tramite = request.args.get("tipo_tramite", "").strip()

        query = Expediente.query.filter(Expediente.estado == "Finalizado")

        if q:
            query = query.join(Cliente, isouter=True).filter(
                db.or_(
                    Expediente.codigo_firma.ilike(f"%{q}%"),
                    Expediente.nombre_caso.ilike(f"%{q}%"),
                    Cliente.nombres.ilike(f"%{q}%"),
                    Cliente.apellidos.ilike(f"%{q}%"),
                    Cliente.rnc_cedula.ilike(f"%{q}%"),
                )
            )

        if anio_desde:
            from sqlalchemy import extract
            query = query.filter(extract('year', Expediente.fecha_cierre) >= anio_desde)
        if anio_hasta:
            from sqlalchemy import extract
            query = query.filter(extract('year', Expediente.fecha_cierre) <= anio_hasta)

        if tipo_finalizacion:
            query = query.filter(Expediente.tipo_finalizacion == tipo_finalizacion)

        if tipo_tramite:
            query = query.filter(Expediente.tipo_tramite == tipo_tramite)

        expedientes = query.order_by(Expediente.fecha_cierre.desc()).all()

        results = []
        for exp in expedientes:
            next_hearing = None
            if exp.tipo_tramite == "Judicial":
                next_hearing = (
                    AlertaPlazoAudiencia.query.filter_by(expediente_id=exp.id, es_audiencia=True, estado_alerta="Pendiente")
                    .order_by(AlertaPlazoAudiencia.fecha_vencimiento.asc())
                    .first()
                )
            
            item = {
                "id": exp.id,
                "codigo_firma": exp.codigo_firma,
                "nombre_caso": exp.nombre_caso,
                "tipo_tramite": exp.tipo_tramite,
                "cliente_nombre": exp.cliente.nombre_completo if exp.cliente else "N/A",
                "abogado_responsable_nombre": exp.abogado_responsable.nombre if exp.abogado_responsable else "No asignado",
                "rol_firma": exp.rol_firma,
                "fecha_apertura": exp.fecha_apertura.strftime("%Y-%m-%d") if exp.fecha_apertura else None,
                "fecha_cierre": exp.fecha_cierre.strftime("%Y-%m-%d") if exp.fecha_cierre else None,
                "tipo_finalizacion": exp.tipo_finalizacion,
                "razon_estado": exp.razon_estado,
                "fase_actual": exp.fase_actual,
                "fase_nota": exp.fase_nota,
            }

            if exp.tipo_tramite == "Judicial":
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
                    "fecha_audiencia": next_hearing.fecha_vencimiento.strftime("%Y-%m-%d") if next_hearing else None,
                    "hora_audiencia": next_hearing.fecha_vencimiento.strftime("%H:%M") if next_hearing else None,
                })
            else:
                item.update({
                    "tipo_proceso": exp.tipo_proceso,
                    "sub_proceso": exp.sub_proceso,
                    "institucion_encargada": exp.institucion_encargada,
                    "numero_solicitud_oficial": exp.numero_solicitud_oficial,
                    "descripcion_tramite": exp.descripcion_tramite,
                    "monto_tasas_impuestos": float(exp.monto_tasas_impuestos) if exp.monto_tasas_impuestos is not None else None,
                })

            results.append(item)

        return jsonify(results)

    @app.route("/expedientes/<int:expediente_id>/detalle")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def detalle_expediente(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)

        # 1. Registrar auditoría de visualización
        registrar_auditoria(
            usuario_id=current_user.id,
            accion="Visualización",
            detalles="Consultó la información detallada del expediente.",
            expediente_id=exp.id,
        )

        # 2. Obtener auditorías asociadas a este expediente (solo para Administrador)
        auditorias_data = []
        if current_user.rol == "Administrador":
            auditorias_db = (
                BitacoraAuditoria.query.filter_by(expediente_id=exp.id)
                .order_by(BitacoraAuditoria.fecha_hora.desc())
                .all()
            )

            auditorias_data = [
                {
                    "id": log.id,
                    "fecha_hora": log.fecha_hora.strftime("%d/%m/%Y %I:%M %p"),
                    "usuario": log.usuario.nombre if log.usuario else "Desconocido",
                    "accion": log.accion_realizada,
                    "detalles": log.detalles_tecnicos,
                    "ip": log.ip_direccion,
                    "dispositivo": log.dispositivo_info,
                }
                for log in auditorias_db
            ]

        # 2b. Obtener el historial de proceso (bitácora visible para todos los roles)
        historial_db = (
            BitacoraAuditoria.query.filter_by(expediente_id=exp.id)
            .order_by(BitacoraAuditoria.fecha_hora.desc())
            .all()
        )
        historial_data = [
            {
                "fecha": log.fecha_hora.strftime("%d/%m/%Y %I:%M %p"),
                "usuario": log.usuario.nombre if log.usuario else "Sistema",
                "accion": log.accion_realizada,
                "detalles": log.detalles_tecnicos
            }
            for log in historial_db if log.accion_realizada != "Visualización"
        ]

        # 3. Serializar expediente
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
            "razon_estado": exp.razon_estado or "",
            "tipo_finalizacion": exp.tipo_finalizacion or "",
            "fase_actual": exp.fase_actual,
            "fase_nota": exp.fase_nota or "",
            "auditorias": auditorias_data,
            "historial": historial_data,
        }

        if exp.tipo_tramite == "Judicial":
            next_hearing = (
                AlertaPlazoAudiencia.query.filter_by(expediente_id=exp.id, es_audiencia=True, estado_alerta="Pendiente")
                .order_by(AlertaPlazoAudiencia.fecha_vencimiento.asc())
                .first()
            )
            item.update(
                {
                    "rama_derecho": exp.rama_derecho,
                    "sub_categoria": exp.sub_categoria or "",
                    "tipo_accion": exp.tipo_accion or "",
                    "jurisdiccion_actual": exp.jurisdiccion_actual or "",
                    "tribunal_asignado": exp.tribunal_asignado or "",
                    "numero_expediente_tribunal": exp.numero_expediente_tribunal or "",
                    "juez_asignado": exp.juez_asignado or "",
                    "nombre_contraparte": exp.nombre_contraparte or "",
                    "contacto_contraparte": exp.contacto_contraparte or "",
                    "abogado_contraparte": exp.abogado_contraparte or "",
                    "contacto_abogado_contraparte": exp.contacto_abogado_contraparte or "",
                    "monto_demanda": float(exp.monto_demanda) if exp.monto_demanda is not None else None,
                    "fecha_audiencia": next_hearing.fecha_vencimiento.strftime("%Y-%m-%d") if next_hearing else None,
                    "hora_audiencia": next_hearing.fecha_vencimiento.strftime("%H:%M") if next_hearing else None,
                }
            )
        elif exp.tipo_tramite == "Administrativo":
            item.update(
                {
                    "tipo_proceso": exp.tipo_proceso or "",
                    "sub_proceso": exp.sub_proceso or "",
                    "institucion_encargada": exp.institucion_encargada or "",
                    "numero_solicitud_oficial": exp.numero_solicitud_oficial or "",
                    "descripcion_tramite": exp.descripcion_tramite or "",
                    "monto_tasas_impuestos": float(exp.monto_tasas_impuestos) if exp.monto_tasas_impuestos is not None else None,
                }
            )
        return jsonify(item)

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
                    tipo_tramite="Judicial",
                )

                try:
                    db.session.add(nuevo_caso)
                    db.session.commit()
                    # Registrar en auditoría
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Creación",
                        detalles=f"Creó el expediente judicial '{nuevo_caso.nombre_caso}' ({nuevo_caso.codigo_firma}).",
                        expediente_id=nuevo_caso.id,
                    )
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
                    # Registrar en auditoría
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Creación",
                        detalles=f"Creó el expediente administrativo '{nuevo_tramite.nombre_caso}' ({nuevo_tramite.codigo_firma}).",
                        expediente_id=nuevo_tramite.id,
                    )
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
        form.abogado_responsable_id.choices = [
            (0, "Seleccione un abogado...")
        ] + opciones_abogados

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
                form.contacto_abogado_contraparte.data = (
                    exp.contacto_abogado_contraparte
                )
                form.monto_demanda.data = exp.monto_demanda
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
            exp.abogado_responsable_id = (
                form.abogado_responsable_id.data
                if form.abogado_responsable_id.data != 0
                else None
            )
            exp.nombre_caso = form.nombre_caso.data.strip()
            exp.rol_firma = form.rol_firma.data

            if exp.tipo_tramite == "Judicial":
                exp.rama_derecho = form.rama_derecho.data
                exp.sub_categoria = (
                    form.sub_categoria.data.strip() if form.sub_categoria.data else None
                )
                exp.tipo_accion = (
                    form.tipo_accion.data.strip() if form.tipo_accion.data else None
                )
                exp.jurisdiccion_actual = form.jurisdiccion_actual.data
                exp.tribunal_asignado = (
                    form.tribunal_asignado.data.strip()
                    if form.tribunal_asignado.data
                    else None
                )
                exp.numero_expediente_tribunal = (
                    form.numero_expediente_tribunal.data.strip()
                    if form.numero_expediente_tribunal.data
                    else None
                )
                exp.juez_asignado = (
                    form.juez_asignado.data.strip() if form.juez_asignado.data else None
                )
                exp.nombre_contraparte = (
                    form.nombre_contraparte.data.strip()
                    if form.nombre_contraparte.data
                    else None
                )
                exp.contacto_contraparte = (
                    form.contacto_contraparte.data.strip()
                    if form.contacto_contraparte.data
                    else None
                )
                exp.abogado_contraparte = (
                    form.abogado_contraparte.data.strip()
                    if form.abogado_contraparte.data
                    else None
                )
                exp.contacto_abogado_contraparte = (
                    form.contacto_abogado_contraparte.data.strip()
                    if form.contacto_abogado_contraparte.data
                    else None
                )
                exp.monto_demanda = form.monto_demanda.data
            else:
                exp.tipo_proceso = form.tipo_proceso.data
                exp.sub_proceso = (
                    form.sub_proceso.data.strip() if form.sub_proceso.data else None
                )
                exp.institucion_encargada = (
                    form.institucion_encargada.data.strip()
                    if form.institucion_encargada.data
                    else None
                )
                exp.numero_solicitud_oficial = (
                    form.numero_solicitud_oficial.data.strip()
                    if form.numero_solicitud_oficial.data
                    else None
                )
                exp.descripcion_tramite = (
                    form.descripcion_tramite.data.strip()
                    if form.descripcion_tramite.data
                    else None
                )
                exp.monto_tasas_impuestos = form.monto_tasas_impuestos.data

            try:
                db.session.commit()
                # Registrar en auditoría
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles=f"Modificó los datos del expediente '{exp.nombre_caso}' ({exp.codigo_firma}).",
                    expediente_id=exp.id,
                )
                flash("Expediente actualizado exitosamente.", "success")
                return redirect(url_for("expedientes", id=exp.id))
            except Exception as e:
                db.session.rollback()
                flash(f"Error al actualizar el expediente: {str(e)}", "danger")

        return render_template("expedientes/editar.html", form=form, exp=exp)

    @app.route(
        "/expedientes/<int:expediente_id>/cambiar_estado/<string:nuevo_estado>",
        methods=["POST"],
    )
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def cambiar_estado_expediente(expediente_id, nuevo_estado):
        if nuevo_estado not in ["Abierto", "Suspendido", "Finalizado", "Archivado"]:
            flash("Estado inválido.", "danger")
            return redirect(url_for("expedientes"))

        exp = Expediente.query.get_or_404(expediente_id)

        # Requiere justificación/razón
        razon = request.form.get("razon", "").strip()
        if not razon:
            flash("Debe especificar una razón para cambiar el estado del expediente.", "danger")
            return redirect(url_for("expedientes", id=exp.id))

        tipo_finalizacion = None
        if nuevo_estado == "Finalizado":
            tipo_finalizacion = request.form.get("tipo_finalizacion", "").strip()
            if not tipo_finalizacion:
                flash("Debe especificar el tipo de finalización del expediente.", "danger")
                return redirect(url_for("expedientes", id=exp.id))

        estado_anterior = exp.estado
        exp.estado = nuevo_estado
        exp.razon_estado = razon
        exp.tipo_finalizacion = tipo_finalizacion

        if nuevo_estado in ["Archivado", "Finalizado"]:
            exp.fecha_cierre = datetime.utcnow()
            if nuevo_estado == "Finalizado":
                # Si se finaliza, por defecto lo colocamos en fase 5 (Finalizado/Sentencia)
                exp.fase_actual = 5
        else:
            exp.fecha_cierre = None
            if nuevo_estado == "Abierto" and estado_anterior in ["Finalizado", "Archivado"]:
                exp.tipo_finalizacion = None

        try:
            db.session.commit()
            # Registrar en auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Estado cambiado",
                detalles=f"Cambió el estado de '{estado_anterior}' a '{nuevo_estado}'. Razón: {razon}",
                expediente_id=exp.id,
            )
            flash(f"Estado del expediente cambiado a {nuevo_estado}.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al cambiar el estado del expediente: {str(e)}", "danger")

        return redirect(url_for("expedientes", id=exp.id))

    @app.route("/expedientes/<int:expediente_id>/actualizar_fase", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def actualizar_fase_expediente(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)
        if current_user.rol == "Asociado" and exp.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("expedientes", id=exp.id))

        fase = request.form.get("fase_actual", type=int)
        nota = request.form.get("fase_nota", "").strip()

        if fase is not None and (fase < 1 or fase > 5):
            flash("Fase de progreso inválida.", "danger")
            return redirect(url_for("expedientes", id=exp.id))

        fase_anterior = exp.fase_actual
        if fase is not None:
            exp.fase_actual = fase
        
        exp.fase_nota = nota if nota else None

        try:
            db.session.commit()
            # Registrar en auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Fase actualizada",
                detalles=f"Cambió la fase de progreso de '{fase_anterior}' a '{fase}'. Nota: {nota or 'Sin nota'}",
                expediente_id=exp.id,
            )
            flash("Progreso del expediente actualizado correctamente.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al actualizar el progreso del expediente: {str(e)}", "danger")

        return redirect(url_for("expedientes", id=exp.id))

    @app.route("/expedientes/<int:expediente_id>/eliminar", methods=["POST"])
    @login_required
    @roles_permitidos("Administrador")
    def eliminar_expediente(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)

        # Requiere justificación/razón
        razon = request.form.get("razon", "").strip()
        if not razon:
            flash("Debe especificar una razón para eliminar el expediente.", "danger")
            return redirect(url_for("expedientes"))

        codigo = exp.codigo_firma
        nombre = exp.nombre_caso

        try:
            # Registrar auditoría ANTES de borrar para poder conservar el registro de eliminación
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Eliminación",
                detalles=f"Expediente {codigo} ({nombre}) eliminado. Razón: {razon}",
                expediente_id=None,
            )

            db.session.delete(exp)
            db.session.commit()
            flash("Expediente eliminado correctamente del sistema.", "success")
        except Exception as e:
            db.session.rollback()
            flash(
                f"Error al eliminar el expediente. Puede que tenga tareas o documentos vinculados. Detalle: {str(e)}",
                "danger",
            )

        return redirect(url_for("expedientes"))

    # --- RUTAS DE MOTOR DOCUMENTAL ---
    @app.route("/documentos")
    @login_required
    def documentos():
        expediente_id = request.args.get("expediente_id", type=int)
        cliente_id = request.args.get("cliente_id", type=int)
        
        rol = current_user.rol
        if rol == "Cliente":
            flash("Acceso denegado. No tiene permisos para acceder al gestor documental.", "danger")
            return redirect(url_for("dashboard"))
        
        # Cargar lista de expedientes para el selector
        expedientes_select = []
        if rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if cliente_db:
                expedientes_select = [e for e in cliente_db.expedientes if e.estado != "Archivado"]
        elif rol == "Asociado":
            expedientes_select = Expediente.query.filter(
                Expediente.estado != "Archivado",
                Expediente.abogado_responsable_id == current_user.id
            ).order_by(Expediente.nombre_caso.asc()).all()
        else:
            expedientes_select = Expediente.query.filter(Expediente.estado != "Archivado").order_by(Expediente.nombre_caso.asc()).all()

        # Validar permisos de Cliente si se provee expediente_id
        if rol == "Cliente" and expediente_id:
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if not cliente_db:
                flash("No posee un registro de cliente asociado.", "danger")
                return redirect(url_for("dashboard"))
            exp_ids = [e.id for e in cliente_db.expedientes]
            if expediente_id not in exp_ids:
                flash("No tiene permisos para acceder a este expediente.", "danger")
                return redirect(url_for("documentos"))

        # Cargar expediente preseleccionado
        expediente_preseleccionado = None
        if expediente_id:
            expediente_preseleccionado = Expediente.query.get(expediente_id)
            if expediente_preseleccionado and rol == "Asociado" and expediente_preseleccionado.abogado_responsable_id != current_user.id:
                flash("Acceso denegado. No está asignado a este expediente.", "danger")
                return redirect(url_for("documentos"))
        
        documentos_lista = []
        audit_logs = []
        usuarios_audit_select = []
        q = request.args.get("q", "").strip()
        tipo_filtro = request.args.get("tipo", "Todos")
        visibilidad_filtro = request.args.get("visibilidad", "Todos")
        
        audit_doc = ""
        audit_action = "Todos"
        audit_user = "Todos"
        audit_desde = ""
        audit_hasta = ""

        carpeta_filtro = request.args.get("carpeta_id", "")
        carpetas = []

        # Solo si se ha seleccionado un expediente, cargar documentos y bitácora
        if expediente_preseleccionado:
            carpetas = Carpeta.query.filter_by(expediente_id=expediente_id).order_by(Carpeta.nombre.asc()).all()
            query = Documento.query.filter_by(expediente_id=expediente_id)

            # Filtro por carpeta
            if carpeta_filtro != "" and carpeta_filtro is not None:
                if carpeta_filtro == "0":
                    query = query.filter(Documento.carpeta_id == None)
                else:
                    try:
                        c_id = int(carpeta_filtro)
                        query = query.filter(Documento.carpeta_id == c_id)
                    except ValueError:
                        pass

            if rol == "Cliente":
                cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
                if cliente_db:
                    query = query.filter(
                        Documento.visibilidad == "Compartido"
                    ).filter(
                        db.or_(
                            Documento.cliente_id == None,
                            Documento.cliente_id == cliente_db.id
                        )
                    )
                else:
                    query = query.filter(False)

            if q:
                search_pattern = f"%{q}%"
                query = query.join(VersionDocumento).filter(
                    db.or_(
                        VersionDocumento.descripcion.ilike(search_pattern),
                        VersionDocumento.ruta_almacenamiento.ilike(search_pattern)
                    )
                )
                
            if tipo_filtro != "Todos":
                try:
                    tipo_id = int(tipo_filtro)
                    query = query.filter(Documento.tipo_documento_id == tipo_id)
                except ValueError:
                    pass
                    
            if visibilidad_filtro != "Todos" and rol != "Cliente":
                query = query.filter(Documento.visibilidad == visibilidad_filtro)

            documentos_lista = query.order_by(Documento.id.desc()).all()

            # Cargar bitácora de auditoría asociada a los accesos de este expediente (solo para Administrador)
            audit_logs = []
            usuarios_audit_select = []
            audit_doc = ""
            audit_action = "Todos"
            audit_user = "Todos"
            audit_desde = ""
            audit_hasta = ""

            if current_user.rol == "Administrador":
                audit_query = BitacoraAuditoria.query.filter_by(expediente_id=expediente_id)
                
                # Filtros de bitácora
                audit_doc = request.args.get("audit_doc", "").strip()
                audit_action = request.args.get("audit_action", "Todos").strip()
                audit_user = request.args.get("audit_user", "Todos").strip()
                audit_desde = request.args.get("audit_desde", "").strip()
                audit_hasta = request.args.get("audit_hasta", "").strip()

                if audit_doc:
                    audit_query = audit_query.filter(BitacoraAuditoria.detalles_tecnicos.ilike(f"%{audit_doc}%"))
                if audit_action != "Todos":
                    audit_query = audit_query.filter(BitacoraAuditoria.accion_realizada == audit_action)
                if audit_user != "Todos":
                    try:
                        u_id = int(audit_user)
                        audit_query = audit_query.filter(BitacoraAuditoria.usuario_id == u_id)
                    except ValueError:
                        pass
                if audit_desde:
                    try:
                        desde_dt = datetime.strptime(audit_desde, "%Y-%m-%d")
                        audit_query = audit_query.filter(BitacoraAuditoria.fecha_hora >= desde_dt)
                    except ValueError:
                        pass
                if audit_hasta:
                    try:
                        hasta_dt = datetime.strptime(audit_hasta, "%Y-%m-%d")
                        from datetime import timedelta
                        audit_query = audit_query.filter(BitacoraAuditoria.fecha_hora < hasta_dt + timedelta(days=1))
                    except ValueError:
                        pass

                audit_logs = audit_query.order_by(BitacoraAuditoria.fecha_hora.desc()).all()
                usuarios_audit_select = Usuario.query.order_by(Usuario.nombre.asc()).all()

        # Datos para los selectores del modal de subida (solo para internos)
        clientes_select = []
        tipos_documentos = []

        if rol != "Cliente":
            clientes_select = Cliente.query.order_by(Cliente.nombres.asc()).all()
            tipos_documentos = TipoDocumento.query.order_by(TipoDocumento.nombre_tipo.asc()).all()

        # Estadísticas rápidas
        total_docs = len(documentos_lista)
        compartidos_docs = sum(1 for d in documentos_lista if d.visibilidad == "Compartido")
        internos_docs = sum(1 for d in documentos_lista if d.visibilidad == "Interno")

        # Conteos no filtrados para el listado de carpetas
        unfiltered_total_docs = 0
        unfiltered_raiz_docs = 0
        if expediente_preseleccionado:
            base_q = Documento.query.filter_by(expediente_id=expediente_id)
            if rol == "Cliente":
                base_q = base_q.filter_by(visibilidad="Compartido")
            unfiltered_total_docs = base_q.count()
            unfiltered_raiz_docs = base_q.filter(Documento.carpeta_id == None).count()

        return render_template(
            "documentos/index.html",
            documentos=documentos_lista,
            expedientes_select=expedientes_select,
            clientes_select=clientes_select,
            tipos_documentos=tipos_documentos,
            expediente_id=expediente_id,
            cliente_id=cliente_id,
            expediente_preseleccionado=expediente_preseleccionado,
            q=q,
            tipo_filtro=tipo_filtro,
            visibilidad_filtro=visibilidad_filtro,
            
            # Auditoría
            audit_logs=audit_logs,
            usuarios_audit_select=usuarios_audit_select,
            audit_doc=audit_doc,
            audit_action=audit_action,
            audit_user=audit_user,
            audit_desde=audit_desde,
            audit_hasta=audit_hasta,

            total_docs=total_docs,
            compartidos_docs=compartidos_docs,
            internos_docs=internos_docs,
            unfiltered_total_docs=unfiltered_total_docs,
            unfiltered_raiz_docs=unfiltered_raiz_docs,
            carpetas=carpetas,
            carpeta_filtro=carpeta_filtro,
            usuario=current_user,
            current_date=datetime.now()
        )

    @app.route("/documentos/subir", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def subir_documento():
        expediente_id = request.form.get("expediente_id", type=int)
        tipo_documento_id = request.form.get("tipo_documento_id", type=int)
        visibilidad = request.form.get("visibilidad", "Interno")
        descripcion = request.form.get("descripcion", "").strip()
        carpeta_id = request.form.get("carpeta_id", type=int)
        compartir_cliente_id = request.form.get("compartir_cliente_id", type=int)

        # Validar si el cliente existe si se especificó
        if visibilidad == "Compartido" and compartir_cliente_id:
            dest_cliente = Cliente.query.get(compartir_cliente_id)
            if not dest_cliente:
                flash("El cliente seleccionado no existe.", "danger")
                return redirect(url_for("documentos", expediente_id=expediente_id))

        if "archivo" not in request.files:
            flash("No se seleccionó ningún archivo.", "danger")
            return redirect(url_for("documentos"))

        archivo = request.files["archivo"]
        if archivo.filename == "":
            flash("El nombre de archivo está vacío.", "danger")
            return redirect(url_for("documentos", expediente_id=expediente_id))

        if not allowed_file(archivo.filename):
            flash("Extensión de archivo no permitida. Solo se admiten documentos estándar, imágenes y comprimidos.", "danger")
            return redirect(url_for("documentos", expediente_id=expediente_id))

        # Validaciones de relaciones
        exp = Expediente.query.get(expediente_id)
        if not exp:
            flash("El expediente seleccionado no existe.", "danger")
            return redirect(url_for("documentos"))

        if current_user.rol == "Asociado" and exp.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))

        tipo = TipoDocumento.query.get(tipo_documento_id)
        if not tipo:
            flash("El tipo de documento seleccionado no existe.", "danger")
            return redirect(url_for("documentos"))

        try:
            # Nombre físico único
            sec_filename = secure_filename(archivo.filename)
            unique_filename = f"{uuid.uuid4().hex}_{sec_filename}"
            filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_filename)
            
            # Guardar archivo físico
            archivo.save(filepath)
            tamano = os.path.getsize(filepath)

            # Validar carpeta si se seleccionó una
            if carpeta_id:
                carpeta = Carpeta.query.get(carpeta_id)
                if not carpeta or carpeta.expediente_id != expediente_id:
                    flash("La carpeta seleccionada no es válida para este expediente.", "danger")
                    return redirect(url_for("documentos", expediente_id=expediente_id))

            # Crear Documento lógico
            nuevo_doc = Documento(
                expediente_id=expediente_id,
                tipo_documento_id=tipo_documento_id,
                visibilidad=visibilidad,
                carpeta_id=carpeta_id if carpeta_id else None,
                cliente_id=compartir_cliente_id if (visibilidad == "Compartido" and compartir_cliente_id) else None
            )
            db.session.add(nuevo_doc)
            db.session.flush() # Para obtener el ID del documento lógico

            # Crear primera VersionDocumento
            nueva_version = VersionDocumento(
                documento_id=nuevo_doc.id,
                usuario_id=current_user.id,
                version_numero="1.0",
                descripcion=descripcion or f"Carga inicial de {sec_filename}",
                tamano_bytes=tamano,
                ruta_almacenamiento=unique_filename,
                es_firmado=False
            )
            db.session.add(nueva_version)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Carga Documento",
                detalles=f"Subió el documento '{sec_filename}' para el expediente '{exp.nombre_caso}'. Visibilidad: {visibilidad}.",
                expediente_id=exp.id,
                cliente_id=exp.cliente_id
            )

            flash(f"Documento '{sec_filename}' subido exitosamente como versión 1.0.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al subir el archivo: {str(e)}", "danger")

        # Mantener los filtros de contexto si existían
        return redirect(url_for("documentos", expediente_id=expediente_id))

    @app.route("/documentos/<int:documento_id>/nueva_version", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def nueva_version_documento(documento_id):
        doc = Documento.query.get_or_404(documento_id)
        if current_user.rol == "Asociado" and doc.expediente.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))
        version_input = request.form.get("version_numero", "").strip()
        descripcion = request.form.get("descripcion", "").strip()

        if "archivo" not in request.files:
            flash("No se seleccionó ningún archivo.", "danger")
            return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        archivo = request.files["archivo"]
        if archivo.filename == "":
            flash("El nombre de archivo está vacío.", "danger")
            return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        if not allowed_file(archivo.filename):
            flash("Extensión de archivo no permitida. Solo se admiten documentos estándar, imágenes y comprimidos.", "danger")
            return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        try:
            # Obtener última versión para auto-calcular si no se provee
            ult_version = VersionDocumento.query.filter_by(documento_id=doc.id).order_by(VersionDocumento.fecha_carga.desc()).first()
            if not version_input:
                if ult_version:
                    try:
                        v_num = float(ult_version.version_numero)
                        version_input = f"{v_num + 0.1:.1f}"
                    except ValueError:
                        version_input = "2.0"
                else:
                    version_input = "1.0"

            sec_filename = secure_filename(archivo.filename)
            unique_filename = f"{uuid.uuid4().hex}_{sec_filename}"
            filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_filename)
            
            # Guardar archivo físico
            archivo.save(filepath)
            tamano = os.path.getsize(filepath)

            # Crear nueva VersionDocumento
            nueva_version = VersionDocumento(
                documento_id=doc.id,
                usuario_id=current_user.id,
                version_numero=version_input,
                descripcion=descripcion or f"Actualización a versión {version_input}",
                tamano_bytes=tamano,
                ruta_almacenamiento=unique_filename,
                es_firmado=False
            )
            db.session.add(nueva_version)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Nueva Versión",
                detalles=f"Subió la versión {version_input} del documento ID {doc.id} ({sec_filename}).",
                expediente_id=doc.expediente_id,
                cliente_id=doc.expediente.cliente_id
            )

            flash(f"Nueva versión {version_input} del documento cargada con éxito.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al subir la versión: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=doc.expediente_id))

    @app.route("/documentos/descargar/<int:version_id>")
    @login_required
    def descargar_documento(version_id):
        version = VersionDocumento.query.get_or_404(version_id)
        doc = version.documento_maestro

        if current_user.rol == "Asociado" and doc.expediente.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))

        # Permisos
        if current_user.rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if not cliente_db or doc.visibilidad != "Compartido":
                flash("No tiene permisos para descargar este documento.", "danger")
                return redirect(url_for("dashboard"))
            
            tiene_acceso = (doc.expediente.cliente_id == cliente_db.id) or (doc.cliente_id == cliente_db.id)
            if not tiene_acceso:
                flash("No tiene permisos para descargar este documento.", "danger")
                return redirect(url_for("dashboard"))

        # Verificar si el archivo existe físicamente
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], version.ruta_almacenamiento)
        if not os.path.exists(filepath):
            flash("El archivo físico no se encuentra en el servidor. Puede que haya sido eliminado del almacenamiento local.", "danger")
            return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        # Reconstruir nombre de descarga original quitando el UUID prefijo
        orig_filename = version.ruta_almacenamiento.split("_", 1)[-1] if "_" in version.ruta_almacenamiento else version.ruta_almacenamiento

        # Auditoría
        registrar_auditoria(
            usuario_id=current_user.id,
            accion="Descarga",
            detalles=f"Descargó el documento '{orig_filename}' (versión {version.version_numero}).",
            expediente_id=doc.expediente_id,
            cliente_id=doc.expediente.cliente_id
        )

        return send_from_directory(
            current_app.config["UPLOAD_FOLDER"],
            version.ruta_almacenamiento,
            as_attachment=True,
            download_name=orig_filename
        )

    @app.route("/documentos/ver/<int:version_id>")
    @login_required
    def ver_documento(version_id):
        version = VersionDocumento.query.get_or_404(version_id)
        doc = version.documento_maestro

        if current_user.rol == "Asociado" and doc.expediente.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))

        # Permisos
        if current_user.rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if not cliente_db or doc.visibilidad != "Compartido":
                flash("No tiene permisos para ver este documento.", "danger")
                return redirect(url_for("dashboard"))

            tiene_acceso = (doc.expediente.cliente_id == cliente_db.id) or (doc.cliente_id == cliente_db.id)
            if not tiene_acceso:
                flash("No tiene permisos para ver este documento.", "danger")
                return redirect(url_for("dashboard"))

        # Verificar si el archivo existe físicamente (vista previa cargada en iframe)
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], version.ruta_almacenamiento)
        if not os.path.exists(filepath):
            return """
            <!DOCTYPE html>
            <html lang="es">
            <head>
                <meta charset="UTF-8">
                <title>Archivo no encontrado</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
                <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
                <style>
                    body { background-color: #f8f9fa; color: #333; font-family: system-ui, -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                    .error-container { text-align: center; max-width: 450px; padding: 30px; border-radius: 12px; background: white; box-shadow: 0 4px 20px rgba(0,0,0,0.05); }
                    .error-icon { font-size: 3.5rem; color: #dc3545; margin-bottom: 15px; }
                </style>
            </head>
            <body>
                <div class="error-container">
                    <i class="bi bi-file-earmark-x-fill error-icon"></i>
                    <h4 class="fw-bold mb-2">Archivo no disponible</h4>
                    <p class="text-muted small mb-4">El archivo físico de este documento no está disponible en este servidor local. Esto suele ocurrir porque la carpeta de subidas (<code>uploads</code>) está excluida en el archivo <code>.gitignore</code>, por lo que los archivos subidos por otros usuarios no se descargan de GitHub.</p>
                    <div class="text-center">
                        <button onclick="window.parent.bootstrap.Modal.getInstance(window.parent.document.getElementById('modalVistaPrevia')).hide();" class="btn btn-secondary btn-sm fw-semibold">Cerrar Vista Previa</button>
                    </div>
                </div>
            </body>
            </html>
            """, 404

        # Reconstruir nombre de descarga original quitando el UUID prefijo
        orig_filename = version.ruta_almacenamiento.split("_", 1)[-1] if "_" in version.ruta_almacenamiento else version.ruta_almacenamiento

        # Auditoría
        registrar_auditoria(
            usuario_id=current_user.id,
            accion="Visualización",
            detalles=f"Visualizó el documento '{orig_filename}' (versión {version.version_numero}).",
            expediente_id=doc.expediente_id,
            cliente_id=doc.expediente.cliente_id
        )

        return send_from_directory(
            current_app.config["UPLOAD_FOLDER"],
            version.ruta_almacenamiento,
            as_attachment=False
        )

    @app.route("/documentos/<int:documento_id>/cambiar_visibilidad", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def cambiar_visibilidad_documento(documento_id):
        doc = Documento.query.get_or_404(documento_id)
        if current_user.rol == "Asociado" and doc.expediente.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))
        nueva_vis = request.form.get("visibilidad", "Interno")
        compartir_cliente_id = request.form.get("compartir_cliente_id", type=int)

        if nueva_vis not in ["Interno", "Compartido"]:
            flash("Visibilidad inválida.", "danger")
            return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        if nueva_vis == "Compartido" and compartir_cliente_id:
            dest_cliente = Cliente.query.get(compartir_cliente_id)
            if not dest_cliente:
                flash("El cliente seleccionado no existe.", "danger")
                return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        vis_anterior = doc.visibilidad
        doc.visibilidad = nueva_vis
        doc.cliente_id = compartir_cliente_id if (nueva_vis == "Compartido" and compartir_cliente_id) else None
        try:
            db.session.commit()
            
            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Editar Visibilidad",
                detalles=f"Cambió la visibilidad del documento ID {doc.id} de '{vis_anterior}' a '{nueva_vis}'.",
                expediente_id=doc.expediente_id,
                cliente_id=doc.expediente.cliente_id
            )
            flash(f"La visibilidad del documento se cambió a {nueva_vis}.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al cambiar la visibilidad: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=doc.expediente_id))

    @app.route("/documentos/<int:documento_id>/eliminar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def eliminar_documento(documento_id):
        doc = Documento.query.get_or_404(documento_id)
        if current_user.rol == "Asociado" and doc.expediente.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))
        exp_id = doc.expediente_id
        cli_id = doc.expediente.cliente_id
        
        razon = request.form.get("razon_eliminacion", "").strip()
        if not razon:
            flash("Debe proporcionar una razón para eliminar el documento.", "danger")
            return redirect(url_for("documentos", expediente_id=exp_id))

        # Eliminar archivos físicos asociados
        for version in doc.versiones:
            try:
                filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], version.ruta_almacenamiento)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                # Loggear y continuar para evitar atascar la base de datos
                print(f"Error al eliminar archivo físico {version.ruta_almacenamiento}: {str(e)}")

        try:
            db.session.delete(doc)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Eliminar Documento",
                detalles=f"Eliminó permanentemente el documento ID {documento_id}. Razón: {razon}",
                expediente_id=exp_id,
                cliente_id=cli_id
            )
            flash("Documento eliminado correctamente del sistema.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al eliminar el documento: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=exp_id))

    @app.route("/documentos/tipologias", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def listar_tipologias():
        tipologias = TipoDocumento.query.order_by(TipoDocumento.nombre_tipo.asc()).all()
        return render_template(
            "documentos/tipologias.html",
            tipologias=tipologias,
            usuario=current_user
        )

    @app.route("/documentos/tipologias/crear", methods=["POST"])
    @login_required
    @roles_permitidos("Administrador")
    def crear_tipologia():
        nombre_tipo = request.form.get("nombre_tipo", "").strip()
        if not nombre_tipo:
            flash("El nombre de la tipología no puede estar vacío.", "danger")
            return redirect(url_for("listar_tipologias"))

        # Validar si ya existe
        existente = TipoDocumento.query.filter(TipoDocumento.nombre_tipo.ilike(nombre_tipo)).first()
        if existente:
            flash(f"La tipología '{nombre_tipo}' ya existe.", "danger")
            return redirect(url_for("listar_tipologias"))

        try:
            nueva_tipologia = TipoDocumento(nombre_tipo=nombre_tipo)
            db.session.add(nueva_tipologia)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Crear Tipología",
                detalles=f"Creó la tipología de documento '{nombre_tipo}'."
            )
            flash(f"Tipología '{nombre_tipo}' creada con éxito.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al crear la tipología: {str(e)}", "danger")

        return redirect(url_for("listar_tipologias"))

    @app.route("/documentos/tipologias/<int:tipo_id>/editar", methods=["POST"])
    @login_required
    @roles_permitidos("Administrador")
    def editar_tipologia(tipo_id):
        tipologia = TipoDocumento.query.get_or_404(tipo_id)
        nombre_tipo = request.form.get("nombre_tipo", "").strip()
        if not nombre_tipo:
            flash("El nombre de la tipología no puede estar vacío.", "danger")
            return redirect(url_for("listar_tipologias"))

        # Validar si ya existe otra con el mismo nombre
        existente = TipoDocumento.query.filter(
            TipoDocumento.nombre_tipo.ilike(nombre_tipo), 
            TipoDocumento.id != tipo_id
        ).first()
        if existente:
            flash(f"Ya existe otra tipología con el nombre '{nombre_tipo}'.", "danger")
            return redirect(url_for("listar_tipologias"))

        nombre_anterior = tipologia.nombre_tipo
        tipologia.nombre_tipo = nombre_tipo
        try:
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Editar Tipología",
                detalles=f"Modificó la tipología ID {tipo_id} de '{nombre_anterior}' a '{nombre_tipo}'."
            )
            flash(f"Tipología modificada a '{nombre_tipo}' con éxito.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al editar la tipología: {str(e)}", "danger")

        return redirect(url_for("listar_tipologias"))

    @app.route("/documentos/tipologias/<int:tipo_id>/eliminar", methods=["POST"])
    @login_required
    @roles_permitidos("Administrador")
    def eliminar_tipologia(tipo_id):
        tipologia = TipoDocumento.query.get_or_404(tipo_id)
        
        # Validar si hay documentos asociados
        documentos_asociados = Documento.query.filter_by(tipo_documento_id=tipo_id).count()
        if documentos_asociados > 0:
            flash(f"No se puede eliminar la tipología '{tipologia.nombre_tipo}' porque tiene {documentos_asociados} documentos asociados.", "danger")
            return redirect(url_for("listar_tipologias"))

        nombre_tipo = tipologia.nombre_tipo
        try:
            db.session.delete(tipologia)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Eliminar Tipología",
                detalles=f"Eliminó la tipología de documento '{nombre_tipo}' (ID {tipo_id})."
            )
            flash(f"Tipología '{nombre_tipo}' eliminada correctamente.", "success")
        except Exception as e:
            flash(f"Error al eliminar la tipología: {str(e)}", "danger")

        return redirect(url_for("listar_tipologias"))

    @app.route("/documentos/carpetas", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def listar_carpetas():
        filtro_q = request.args.get("q", "").strip()
        filtro_expediente = request.args.get("expediente_id", "Todos")

        query = Carpeta.query

        # Filtrar por expediente
        if filtro_expediente != "Todos":
            try:
                e_id = int(filtro_expediente)
                query = query.filter_by(expediente_id=e_id)
            except ValueError:
                pass

        # Filtrar por búsqueda de texto
        if filtro_q:
            query = query.filter(Carpeta.nombre.ilike(f"%{filtro_q}%"))

        carpetas = query.order_by(Carpeta.fecha_creacion.desc()).all()

        # Estadísticas globales
        total_carpetas = Carpeta.query.count()
        total_docs_en_carpetas = Documento.query.filter(Documento.carpeta_id != None).count()
        total_docs_sin_carpeta = Documento.query.filter(Documento.carpeta_id == None).count()
        expedientes_con_carpetas = db.session.query(db.func.count(db.distinct(Carpeta.expediente_id))).scalar()

        # Expedientes para el selector de filtro
        expedientes_select = Expediente.query.filter(Expediente.estado != "Archivado").order_by(Expediente.nombre_caso.asc()).all()

        # Auditorías recientes relacionadas con carpetas
        auditorias_carpetas = (
            BitacoraAuditoria.query.filter(
                db.or_(
                    BitacoraAuditoria.accion_realizada.ilike("%Carpeta%"),
                    BitacoraAuditoria.detalles_tecnicos.ilike("%carpeta%")
                )
            )
            .order_by(BitacoraAuditoria.fecha_hora.desc())
            .limit(30)
            .all()
        )

        return render_template(
            "documentos/carpetas.html",
            carpetas=carpetas,
            filtro_q=filtro_q,
            filtro_expediente=filtro_expediente,
            total_carpetas=total_carpetas,
            total_docs_en_carpetas=total_docs_en_carpetas,
            total_docs_sin_carpeta=total_docs_sin_carpeta,
            expedientes_con_carpetas=expedientes_con_carpetas,
            expedientes_select=expedientes_select,
            auditorias_carpetas=auditorias_carpetas,
            usuario=current_user,
            current_date=datetime.now()
        )

    @app.route("/documentos/carpetas/crear", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def crear_carpeta():
        expediente_id = request.form.get("expediente_id", type=int)
        nombre = request.form.get("nombre", "").strip()

        if not nombre:
            flash("El nombre de la carpeta no puede estar vacío.", "danger")
            return redirect(url_for("documentos", expediente_id=expediente_id))

        exp = Expediente.query.get_or_404(expediente_id)
        if current_user.rol == "Asociado" and exp.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))

        # Validar duplicados
        existente = Carpeta.query.filter(
            Carpeta.expediente_id == expediente_id,
            Carpeta.nombre.ilike(nombre)
        ).first()

        if existente:
            flash(f"Ya existe una carpeta con el nombre '{nombre}' en este expediente.", "danger")
            return redirect(url_for("documentos", expediente_id=expediente_id))

        try:
            nueva_carpeta = Carpeta(nombre=nombre, expediente_id=expediente_id)
            db.session.add(nueva_carpeta)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Crear Carpeta",
                detalles=f"Creó la carpeta '{nombre}' para el expediente '{exp.codigo_firma}'.",
                expediente_id=expediente_id,
                cliente_id=exp.cliente_id
            )
            flash(f"Carpeta '{nombre}' creada con éxito.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al crear la carpeta: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=expediente_id))

    @app.route("/documentos/carpetas/<int:carpeta_id>/editar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def editar_carpeta(carpeta_id):
        carpeta = Carpeta.query.get_or_404(carpeta_id)
        if current_user.rol == "Asociado" and carpeta.expediente.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))
        nombre = request.form.get("nombre", "").strip()

        if not nombre:
            flash("El nombre de la carpeta no puede estar vacío.", "danger")
            return redirect(url_for("documentos", expediente_id=carpeta.expediente_id))

        # Validar duplicados
        existente = Carpeta.query.filter(
            Carpeta.expediente_id == carpeta.expediente_id,
            Carpeta.nombre.ilike(nombre),
            Carpeta.id != carpeta_id
        ).first()

        if existente:
            flash(f"Ya existe otra carpeta con el nombre '{nombre}' en este expediente.", "danger")
            return redirect(url_for("documentos", expediente_id=carpeta.expediente_id))

        nombre_anterior = carpeta.nombre
        try:
            carpeta.nombre = nombre
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Editar Carpeta",
                detalles=f"Modificó el nombre de la carpeta de '{nombre_anterior}' a '{nombre}' (Carpeta ID {carpeta_id}).",
                expediente_id=carpeta.expediente_id,
                cliente_id=carpeta.expediente.cliente_id
            )
            flash(f"Carpeta renombrada a '{nombre}' con éxito.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al renombrar la carpeta: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=carpeta.expediente_id))

    @app.route("/documentos/carpetas/<int:carpeta_id>/eliminar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def eliminar_carpeta(carpeta_id):
        carpeta = Carpeta.query.get_or_404(carpeta_id)
        expediente_id = carpeta.expediente_id
        nombre = carpeta.nombre

        try:
            db.session.delete(carpeta)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Eliminar Carpeta",
                detalles=f"Eliminó la carpeta '{nombre}' (ID {carpeta_id}). Los documentos asociados fueron movidos a la raíz.",
                expediente_id=expediente_id,
                cliente_id=carpeta.expediente.cliente_id
            )
            flash(f"Carpeta '{nombre}' eliminada con éxito. Los documentos contenidos fueron movidos a la raíz.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al eliminar la carpeta: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=expediente_id))

    @app.route("/documentos/<int:documento_id>/mover", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def mover_documento(documento_id):
        doc = Documento.query.get_or_404(documento_id)
        if current_user.rol == "Asociado" and doc.expediente.abogado_responsable_id != current_user.id:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))
        carpeta_id = request.form.get("carpeta_id")

        if carpeta_id == "" or carpeta_id == "0" or carpeta_id is None:
            c_id = None
            dest_nombre = "Raíz"
        else:
            try:
                c_id = int(carpeta_id)
                carpeta = Carpeta.query.get_or_404(c_id)
                if carpeta.expediente_id != doc.expediente_id:
                    flash("La carpeta seleccionada no pertenece al expediente de este documento.", "danger")
                    return redirect(url_for("documentos", expediente_id=doc.expediente_id))
                dest_nombre = carpeta.nombre
            except ValueError:
                flash("Carpeta de destino no válida.", "danger")
                return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        try:
            doc.carpeta_id = c_id
            db.session.commit()

            # Obtener nombre original
            ult_version = doc.versiones[0] if doc.versiones else None
            orig_filename = ult_version.ruta_almacenamiento.split("_", 1)[-1] if ult_version and "_" in ult_version.ruta_almacenamiento else (ult_version.ruta_almacenamiento if ult_version else "Documento")

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Mover Documento",
                detalles=f"Movió el documento '{orig_filename}' a la carpeta '{dest_nombre}'.",
                expediente_id=doc.expediente_id,
                cliente_id=doc.expediente.cliente_id
            )
            flash(f"Documento movido a '{dest_nombre}' con éxito.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al mover el documento: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=doc.expediente_id))

    @app.route("/tareas", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def listar_tareas():
        # Capturar filtros de búsqueda
        filtro_q = request.args.get("q", "").strip()
        filtro_estado = request.args.get("estado", "Activas")
        filtro_prioridad = request.args.get("prioridad", "Todas")
        filtro_expediente = request.args.get("expediente_id", "Todos")
        filtro_asignado = request.args.get("asignado_a_id", "Todos")
        filtro_rango_fecha = request.args.get("rango_fecha", "Todos")

        query = Tarea.query
        hoy = rd_now().date()

        # Filtrar por rol (Asociado/Paralegal solo ven las asignadas a ellos o a todos)
        if current_user.rol in ["Asociado", "Paralegal"]:
            query = query.filter(db.or_(
                Tarea.asignado_a_id == current_user.id,
                Tarea.asignado_a_id == None
            ))
        elif filtro_asignado != "Todos":
            if filtro_asignado == "General":
                query = query.filter_by(asignado_a_id=None)
            else:
                try:
                    a_id = int(filtro_asignado)
                    query = query.filter_by(asignado_a_id=a_id)
                except ValueError:
                    pass

        if filtro_estado == "Activas":
            query = query.filter(Tarea.estado != "Completada")
        elif filtro_estado == "Vencidas":
            query = query.filter(Tarea.estado != "Completada", Tarea.fecha_limite < hoy)
        elif filtro_estado != "Todos":
            query = query.filter_by(estado=filtro_estado)
        
        if filtro_prioridad != "Todas":
            query = query.filter_by(prioridad=filtro_prioridad)
            
        if filtro_expediente != "Todos":
            try:
                e_id = int(filtro_expediente)
                query = query.filter_by(expediente_id=e_id)
            except ValueError:
                pass

        # Filtrar por texto de búsqueda en título o descripción
        if filtro_q:
            query = query.filter(db.or_(
                Tarea.titulo.ilike(f"%{filtro_q}%"),
                Tarea.descripcion.ilike(f"%{filtro_q}%")
            ))

        # Filtrar por fecha de creación (rango)
        if filtro_rango_fecha != "Todos":
            now_dt = rd_now()
            if filtro_rango_fecha == "Hoy":
                start_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(Tarea.fecha_creacion >= start_dt)
            elif filtro_rango_fecha == "Semana":
                start_dt = now_dt - timedelta(days=7)
                query = query.filter(Tarea.fecha_creacion >= start_dt)
            elif filtro_rango_fecha == "Mes":
                start_dt = now_dt - timedelta(days=30)
                query = query.filter(Tarea.fecha_creacion >= start_dt)
            elif filtro_rango_fecha == "Anio":
                start_dt = now_dt - timedelta(days=365)
                query = query.filter(Tarea.fecha_creacion >= start_dt)

        tareas = query.order_by(Tarea.estado.desc(), Tarea.fecha_limite.asc(), Tarea.prioridad.asc()).all()

        # Datos para los selectores del formulario de creación/edición
        expedientes_list = Expediente.query.filter(Expediente.estado != "Archivado").order_by(Expediente.nombre_caso.asc()).all()
        usuarios_list = Usuario.query.filter(Usuario.activo == True).order_by(Usuario.nombre.asc()).all()

        # Instanciar el formulario
        form = TareaForm()
        # Cargar opciones dinámicas (0 representa "Todo el equipo")
        form.expediente_id.choices = [(0, "-- Seleccione un expediente --")] + [(e.id, f"{e.nombre_caso} ({e.codigo_firma})") for e in expedientes_list]
        form.asignado_a_id.choices = [(0, "Todo el equipo")] + [(u.id, u.nombre) for u in usuarios_list]

        # Calcular estadísticas rápidas
        stat_query = Tarea.query
        if current_user.rol in ["Asociado", "Paralegal"]:
            stat_query = stat_query.filter(db.or_(
                Tarea.asignado_a_id == current_user.id,
                Tarea.asignado_a_id == None
            ))

        if filtro_rango_fecha != "Todos":
            now_dt = rd_now()
            if filtro_rango_fecha == "Hoy":
                start_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                stat_query = stat_query.filter(Tarea.fecha_creacion >= start_dt)
            elif filtro_rango_fecha == "Semana":
                start_dt = now_dt - timedelta(days=7)
                stat_query = stat_query.filter(Tarea.fecha_creacion >= start_dt)
            elif filtro_rango_fecha == "Mes":
                start_dt = now_dt - timedelta(days=30)
                stat_query = stat_query.filter(Tarea.fecha_creacion >= start_dt)
            elif filtro_rango_fecha == "Anio":
                start_dt = now_dt - timedelta(days=365)
                stat_query = stat_query.filter(Tarea.fecha_creacion >= start_dt)

        stat_pendientes = stat_query.filter_by(estado="Pendiente").count()
        stat_progreso = stat_query.filter_by(estado="En Progreso").count()
        stat_completadas = stat_query.filter_by(estado="Completada").count()
        
        # Calcular tareas vencidas (no completadas y con fecha_limite menor a hoy)
        stat_vencidas = stat_query.filter(Tarea.estado != "Completada", Tarea.fecha_limite < hoy).count()

        # Obtener auditorías relacionadas con movimientos en tareas
        auditorias_tareas = (
            BitacoraAuditoria.query.filter(
                db.or_(
                    BitacoraAuditoria.accion_realizada.ilike("%tarea%"),
                    BitacoraAuditoria.detalles_tecnicos.ilike("%tarea%")
                )
            )
            .order_by(BitacoraAuditoria.fecha_hora.desc())
            .limit(50)
            .all()
        )

        return render_template(
            "tareas/index.html",
            tareas=tareas,
            form=form,
            expedientes_list=expedientes_list,
            usuarios_list=usuarios_list,
            filtro_q=filtro_q,
            filtro_estado=filtro_estado,
            filtro_prioridad=filtro_prioridad,
            filtro_expediente=filtro_expediente,
            filtro_asignado=filtro_asignado,
            filtro_rango_fecha=filtro_rango_fecha,
            stat_pendientes=stat_pendientes,
            stat_progreso=stat_progreso,
            stat_vencidas=stat_vencidas,
            stat_completadas=stat_completadas,
            auditorias_tareas=auditorias_tareas,
            current_date=rd_now(),
            usuario=current_user
        )

    @app.route("/tareas/crear", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def crear_tarea():
        form = TareaForm()
        # Cargar opciones para pasar validaciones
        expedientes_list = Expediente.query.filter(Expediente.estado != "Archivado").all()
        usuarios_list = Usuario.query.filter(Usuario.activo == True).all()
        form.expediente_id.choices = [(0, "-- Seleccione un expediente --")] + [(e.id, e.nombre_caso) for e in expedientes_list]
        form.asignado_a_id.choices = [(0, "Todo el equipo")] + [(u.id, u.nombre) for u in usuarios_list]

        if form.validate_on_submit():
            exp_id = form.expediente_id.data
            asignado_id = form.asignado_a_id.data
            if asignado_id == 0:
                asignado_id = None
                
            nueva_tarea = Tarea(
                titulo=form.titulo.data.strip(),
                descripcion=form.descripcion.data.strip() if form.descripcion.data else None,
                fecha_limite=form.fecha_limite.data,
                prioridad=form.prioridad.data,
                estado=form.estado.data,
                expediente_id=exp_id,
                asignado_a_id=asignado_id,
                creado_por_id=current_user.id
            )
            try:
                db.session.add(nueva_tarea)
                db.session.commit()

                # Auditoría
                nombre_asignado = "Todo el equipo" if asignado_id is None else nueva_tarea.asignado_a.nombre
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Creación Tarea",
                    detalles=f"Creó la tarea '{form.titulo.data}' asignada a: {nombre_asignado}.",
                    expediente_id=exp_id,
                    cliente_id=nueva_tarea.expediente.cliente_id
                )
                flash(f"Tarea '{form.titulo.data}' creada exitosamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar la tarea: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error en {getattr(form, field).label.text}: {error}", "danger")

        return redirect(url_for("listar_tareas"))

    @app.route("/tareas/<int:tarea_id>/editar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def editar_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)
        
        # Validar permisos
        if current_user.rol in ["Asociado", "Paralegal"] and tarea.asignado_a_id is not None and tarea.asignado_a_id != current_user.id:
            flash("No tiene permisos para modificar esta tarea.", "danger")
            return redirect(url_for("listar_tareas"))

        form = TareaForm()
        # Cargar opciones para pasar validaciones
        expedientes_list = Expediente.query.filter(Expediente.estado != "Archivado").all()
        usuarios_list = Usuario.query.filter(Usuario.activo == True).all()
        form.expediente_id.choices = [(0, "-- Seleccione un expediente --")] + [(e.id, e.nombre_caso) for e in expedientes_list]
        form.asignado_a_id.choices = [(0, "Todo el equipo")] + [(u.id, u.nombre) for u in usuarios_list]

        if form.validate_on_submit():
            exp_id = form.expediente_id.data
            
            if current_user.rol in ["Asociado", "Paralegal"]:
                # Asociado/Paralegal no pueden reasignar
                asignado_id = tarea.asignado_a_id
            else:
                asignado_id = form.asignado_a_id.data
                if asignado_id == 0:
                    asignado_id = None

            tarea.titulo = form.titulo.data.strip()
            tarea.descripcion = form.descripcion.data.strip() if form.descripcion.data else None
            tarea.fecha_limite = form.fecha_limite.data
            tarea.prioridad = form.prioridad.data
            
            estado_anterior = tarea.estado
            tarea.estado = form.estado.data
            if tarea.estado == "Completada" and estado_anterior != "Completada":
                tarea.fecha_completada = rd_now()
            elif tarea.estado != "Completada":
                tarea.fecha_completada = None

            tarea.expediente_id = exp_id
            tarea.asignado_a_id = asignado_id

            try:
                db.session.commit()

                # Auditoría
                nombre_asignado = "Todo el equipo" if asignado_id is None else tarea.asignado_a.nombre
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Editar Tarea",
                    detalles=f"Modificó la tarea ID {tarea_id} ('{tarea.titulo}'). Asignado: {nombre_asignado}.",
                    expediente_id=exp_id,
                    cliente_id=tarea.expediente.cliente_id
                )
                flash(f"Tarea '{tarea.titulo}' modificada con éxito.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al actualizar la tarea: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error en {getattr(form, field).label.text}: {error}", "danger")

        return redirect(url_for("listar_tareas"))

    @app.route("/tareas/<int:tarea_id>/completar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def completar_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)

        # Validar permisos
        if current_user.rol in ["Asociado", "Paralegal"] and tarea.asignado_a_id != current_user.id:
            flash("No tiene permisos para modificar esta tarea.", "danger")
            return redirect(url_for("listar_tareas"))

        # Alternar estado
        if tarea.estado == "Completada":
            tarea.estado = "Pendiente"
            tarea.fecha_completada = None
            accion_aud = "Reabrir Tarea"
            detalles_aud = f"Marcó la tarea ID {tarea_id} ('{tarea.titulo}') como Pendiente."
            msg = f"Tarea '{tarea.titulo}' reabierta."
        else:
            tarea.estado = "Completada"
            tarea.fecha_completada = rd_now()
            accion_aud = "Completar Tarea"
            detalles_aud = f"Marcó la tarea ID {tarea_id} ('{tarea.titulo}') como Completada."
            msg = f"Tarea '{tarea.titulo}' completada exitosamente."

        try:
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion=accion_aud,
                detalles=detalles_aud,
                expediente_id=tarea.expediente_id,
                cliente_id=tarea.expediente.cliente_id if tarea.expediente_id else None
            )
            flash(msg, "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al actualizar estado de la tarea: {str(e)}", "danger")

        return redirect(url_for("listar_tareas"))

    @app.route("/tareas/<int:tarea_id>/eliminar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def eliminar_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)

        # Validar permisos
        puede_eliminar = (current_user.rol in ["Socio", "Administrador"]) or (tarea.creado_por_id == current_user.id)
        if not puede_eliminar:
            flash("No tiene permisos para eliminar esta tarea.", "danger")
            return redirect(url_for("listar_tareas"))

        titulo = tarea.titulo
        exp_id = tarea.expediente_id
        cli_id = tarea.expediente.cliente_id if exp_id else None

        try:
            db.session.delete(tarea)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Eliminar Tarea",
                detalles=f"Eliminó permanentemente la tarea ID {tarea_id} ('{titulo}').",
                expediente_id=exp_id,
                cliente_id=cli_id
            )
            flash(f"Tarea '{titulo}' eliminada del sistema.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al eliminar la tarea: {str(e)}", "danger")

        return redirect(url_for("listar_tareas"))

    @app.route("/tareas/<int:tarea_id>/cambiar-estado", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def cambiar_estado_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)

        # Validar permisos
        if current_user.rol in ["Asociado", "Paralegal"] and tarea.asignado_a_id != current_user.id:
            flash("No tiene permisos para modificar esta tarea.", "danger")
            return redirect(url_for("listar_tareas"))

        nuevo_estado = request.form.get("nuevo_estado")
        estados_validos = ["Pendiente", "En Progreso", "Completada"]
        if nuevo_estado not in estados_validos:
            flash("Estado no válido.", "danger")
            return redirect(url_for("listar_tareas"))

        estado_anterior = tarea.estado
        tarea.estado = nuevo_estado

        try:
            db.session.commit()
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Cambiar Estado Tarea",
                detalles=f"Cambió el estado de la tarea ID {tarea_id} ('{tarea.titulo}') de '{estado_anterior}' a '{nuevo_estado}'.",
                expediente_id=tarea.expediente_id,
                cliente_id=tarea.expediente.cliente_id if tarea.expediente_id else None
            )
            flash(f"Estado de '{tarea.titulo}' cambiado a <strong>{nuevo_estado}</strong>.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al cambiar el estado: {str(e)}", "danger")

        return redirect(url_for("listar_tareas"))

    # === RUTAS DE LA AGENDA ===
    @app.route("/agenda")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda():
        expedientes_select = Expediente.query.filter(Expediente.estado == "Abierto").all()
        usuarios_select = Usuario.query.filter(Usuario.activo == True).all()
        return render_template("agenda/index.html", expedientes_select=expedientes_select, usuarios_select=usuarios_select)

    @app.route("/agenda/eventos")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda_eventos():
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        categories_str = request.args.get("categories", "")
        
        categories = categories_str.split(",") if categories_str else []
        
        start_date = None
        end_date = None
        if start_str:
            try:
                if "T" in start_str:
                    start_date = datetime.fromisoformat(start_str)
                else:
                    start_date = datetime.strptime(start_str, "%Y-%m-%d")
            except ValueError:
                pass
        if end_str:
            try:
                if "T" in end_str:
                    end_date = datetime.fromisoformat(end_str)
                else:
                    end_date = datetime.strptime(end_str, "%Y-%m-%d")
            except ValueError:
                pass

        events = []

        # Tareas
        if "tarea-pendiente" in categories or "tarea-completada" in categories:
            tareas_query = Tarea.query
            if start_date:
                tareas_query = tareas_query.filter(Tarea.fecha_limite >= start_date.date())
            if end_date:
                tareas_query = tareas_query.filter(Tarea.fecha_limite <= end_date.date())
            
            for t in tareas_query.all():
                is_completed = t.estado == "Completada"
                cat = "tarea-completada" if is_completed else "tarea-pendiente"
                if cat not in categories:
                    continue
                
                if current_user.rol == "Asociado" and t.expediente.abogado_responsable_id != current_user.id:
                    continue
                
                events.append({
                    "id": f"tarea_{t.id}",
                    "title": f"[Tarea] {t.titulo}",
                    "start": t.fecha_limite.isoformat() if t.fecha_limite else "",
                    "backgroundColor": "#10b981" if is_completed else "#3b82f6",
                    "borderColor": "#10b981" if is_completed else "#3b82f6",
                    "textColor": "#ffffff",
                    "extendedProps": {
                        "id": t.id,
                        "type": cat,
                        "title": t.titulo,
                        "expediente_id": t.expediente_id,
                        "expediente_codigo": t.expediente.codigo_firma if t.expediente else "",
                        "expediente_nombre": t.expediente.nombre_caso if t.expediente else "",
                        "asignado_nombre": t.asignado_a.nombre if t.asignado_a else "Todo el equipo",
                        "asignado_id": t.asignado_a_id or 0,
                        "prioridad": t.prioridad,
                        "descripcion": t.descripcion or "",
                        "start": t.fecha_limite.isoformat() if t.fecha_limite else ""
                    }
                })

        # Audiencias
        if "audiencia" in categories:
            aud_query = AlertaPlazoAudiencia.query.filter_by(es_audiencia=True)
            if start_date:
                aud_query = aud_query.filter(AlertaPlazoAudiencia.fecha_vencimiento >= start_date)
            if end_date:
                aud_query = aud_query.filter(AlertaPlazoAudiencia.fecha_vencimiento <= end_date)
            
            for a in aud_query.all():
                if current_user.rol == "Asociado" and a.expediente.abogado_responsable_id != current_user.id:
                    continue
                
                events.append({
                    "id": f"audiencia_{a.id}",
                    "title": f"[Audiencia] {a.titulo_hito}",
                    "start": a.fecha_vencimiento.isoformat() if a.fecha_vencimiento else "",
                    "backgroundColor": "#8b5cf6",
                    "borderColor": "#8b5cf6",
                    "textColor": "#ffffff",
                    "extendedProps": {
                        "id": a.id,
                        "type": "audiencia",
                        "title": a.titulo_hito,
                        "expediente_id": a.expediente_id,
                        "expediente_codigo": a.expediente.codigo_firma if a.expediente else "",
                        "expediente_nombre": a.expediente.nombre_caso if a.expediente else "",
                        "hora": a.fecha_vencimiento.strftime("%H:%M") if a.fecha_vencimiento else "",
                        "fecha_vencimiento": a.fecha_vencimiento.isoformat() if a.fecha_vencimiento else ""
                    }
                })

        # Plazos
        if "plazo" in categories:
            plazo_query = AlertaPlazoAudiencia.query.filter_by(es_audiencia=False)
            if start_date:
                plazo_query = plazo_query.filter(AlertaPlazoAudiencia.fecha_vencimiento >= start_date)
            if end_date:
                plazo_query = plazo_query.filter(AlertaPlazoAudiencia.fecha_vencimiento <= end_date)
            
            for p in plazo_query.all():
                if current_user.rol == "Asociado" and p.expediente.abogado_responsable_id != current_user.id:
                    continue
                
                events.append({
                    "id": f"plazo_{p.id}",
                    "title": f"[Plazo] {p.titulo_hito}",
                    "start": p.fecha_vencimiento.date().isoformat() if p.fecha_vencimiento else "",
                    "backgroundColor": "#f97316",
                    "borderColor": "#f97316",
                    "textColor": "#ffffff",
                    "extendedProps": {
                        "id": p.id,
                        "type": "plazo",
                        "title": p.titulo_hito,
                        "expediente_id": p.expediente_id,
                        "expediente_codigo": p.expediente.codigo_firma if p.expediente else "",
                        "expediente_nombre": p.expediente.nombre_caso if p.expediente else "",
                        "fecha_vencimiento": p.fecha_vencimiento.date().isoformat() if p.fecha_vencimiento else ""
                    }
                })

        return jsonify(events)

    @app.route("/agenda/crear_evento", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda_crear_evento():
        data = request.get_json() or {}
        tipo = data.get("tipo")
        expediente_id = data.get("expediente_id")
        titulo = data.get("titulo", "").strip()
        descripcion = data.get("descripcion", "").strip()
        fecha_str = data.get("fecha", "")
        hora_str = data.get("hora", "")
        asignado_a_id = data.get("asignado_a_id")
        prioridad = data.get("prioridad", "Media")

        if not tipo or not expediente_id or not fecha_str:
            return jsonify({"success": False, "error": "Faltan campos requeridos."})

        expediente = Expediente.query.get_or_404(expediente_id)
        if current_user.rol == "Asociado" and expediente.abogado_responsable_id != current_user.id:
            return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."})

        try:
            if tipo == "tarea":
                if not titulo:
                    return jsonify({"success": False, "error": "El título de la tarea es obligatorio."})
                fecha_limite = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                asignado_id = None if asignado_a_id == 0 else asignado_a_id
                
                tarea = Tarea(
                    expediente_id=expediente_id,
                    titulo=titulo,
                    descripcion=descripcion if descripcion else None,
                    fecha_limite=fecha_limite,
                    prioridad=prioridad,
                    estado="Pendiente",
                    asignado_a_id=asignado_id,
                    creado_por_id=current_user.id
                )
                db.session.add(tarea)
                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Crear Tarea desde Agenda",
                    detalles=f"Creó la tarea '{titulo}' (ID {tarea.id}) para el expediente '{expediente.nombre_caso}'.",
                    expediente_id=expediente_id,
                    cliente_id=expediente.cliente_id
                )
                return jsonify({"success": True, "message": "Tarea creada con éxito en la agenda."})

            elif tipo == "audiencia":
                if not hora_str:
                    return jsonify({"success": False, "error": "La hora de la audiencia es obligatoria."})
                
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                hora = datetime.strptime(hora_str, "%H:%M").time()
                fecha_vencimiento = datetime.combine(fecha, hora)

                alerta = AlertaPlazoAudiencia(
                    expediente_id=expediente_id,
                    titulo_hito=f"Audiencia de {expediente.nombre_caso}",
                    fecha_vencimiento=fecha_vencimiento,
                    estado_alerta="Pending",
                    fuente_origen="Firma",
                    es_audiencia=True
                )
                db.session.add(alerta)
                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Crear Audiencia desde Agenda",
                    detalles=f"Creó la audiencia ID {alerta.id} para el expediente '{expediente.nombre_caso}' programada para el {fecha_vencimiento.strftime('%d/%m/%Y %H:%M')}.",
                    expediente_id=expediente_id,
                    cliente_id=expediente.cliente_id
                )
                return jsonify({"success": True, "message": "Audiencia programada con éxito en la agenda."})

            elif tipo == "plazo":
                if not titulo:
                    return jsonify({"success": False, "error": "El título del plazo es obligatorio."})
                
                fecha_venc = datetime.strptime(fecha_str, "%Y-%m-%d")

                alerta = AlertaPlazoAudiencia(
                    expediente_id=expediente_id,
                    titulo_hito=titulo,
                    fecha_vencimiento=fecha_venc,
                    estado_alerta="Pending",
                    fuente_origen="Firma",
                    es_audiencia=False
                )
                db.session.add(alerta)
                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Crear Plazo desde Agenda",
                    detalles=f"Creó el plazo '{titulo}' (ID {alerta.id}) para el expediente '{expediente.nombre_caso}' con vencimiento el {fecha_venc.strftime('%d/%m/%Y')}.",
                    expediente_id=expediente_id,
                    cliente_id=expediente.cliente_id
                )
                return jsonify({"success": True, "message": "Plazo registrado con éxito en la agenda."})

            else:
                return jsonify({"success": False, "error": "Tipo de evento inválido."})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Error de base de datos: {str(e)}"})

    @app.route("/agenda/evento/<string:tipo>/<int:evento_id>/editar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda_editar_evento(tipo, evento_id):
        data = request.get_json() or {}
        titulo = data.get("titulo", "").strip()
        descripcion = data.get("descripcion", "").strip()
        fecha_str = data.get("fecha", "")
        hora_str = data.get("hora", "")
        asignado_a_id = data.get("asignado_a_id")
        prioridad = data.get("prioridad", "Media")

        if not fecha_str:
            return jsonify({"success": False, "error": "La fecha es obligatoria."})

        try:
            if tipo == "tarea-pendiente" or tipo == "tarea-completada":
                tarea = Tarea.query.get_or_404(evento_id)
                if current_user.rol == "Asociado" and tarea.expediente.abogado_responsable_id != current_user.id:
                    return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."})

                if not titulo:
                    return jsonify({"success": False, "error": "El título de la tarea es obligatorio."})

                fecha_limite = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                asignado_id = None if asignado_a_id == 0 else asignado_a_id

                cambios = []
                if tarea.titulo != titulo:
                    cambios.append(f"título: '{tarea.titulo}' -> '{titulo}'")
                    tarea.titulo = titulo
                if (tarea.descripcion or "") != descripcion:
                    cambios.append(f"descripción: '{tarea.descripcion}' -> '{descripcion}'")
                    tarea.descripcion = descripcion if descripcion else None
                if tarea.fecha_limite != fecha_limite:
                    cambios.append(f"fecha límite: '{tarea.fecha_limite}' -> '{fecha_limite}'")
                    tarea.fecha_limite = fecha_limite
                if tarea.prioridad != prioridad:
                    cambios.append(f"prioridad: '{tarea.prioridad}' -> '{prioridad}'")
                    tarea.prioridad = prioridad
                if tarea.asignado_a_id != asignado_id:
                    anterior_nom = tarea.asignado_a.nombre if tarea.asignado_a else "Todo el equipo"
                    tarea.asignado_a_id = asignado_id
                    nuevo_nom = tarea.asignado_a.nombre if tarea.asignado_a else "Todo el equipo"
                    cambios.append(f"asignado a: '{anterior_nom}' -> '{nuevo_nom}'")

                if cambios:
                    db.session.commit()
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Editar Tarea desde Agenda",
                        detalles=f"Editó la tarea ID {evento_id} ('{tarea.titulo}'). Cambios: {', '.join(cambios)}.",
                        expediente_id=tarea.expediente_id,
                        cliente_id=tarea.expediente.cliente_id
                    )
                return jsonify({"success": True, "message": "Tarea modificada con éxito."})

            elif tipo == "audiencia":
                audiencia = AlertaPlazoAudiencia.query.get_or_404(evento_id)
                if current_user.rol == "Asociado" and audiencia.expediente.abogado_responsable_id != current_user.id:
                    return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."})

                if not hora_str:
                    return jsonify({"success": False, "error": "La hora de la audiencia es obligatoria."})

                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                hora = datetime.strptime(hora_str, "%H:%M").time()
                fecha_vencimiento = datetime.combine(fecha, hora)

                cambios = []
                if audiencia.fecha_vencimiento != fecha_vencimiento:
                    cambios.append(f"fecha/hora: '{audiencia.fecha_vencimiento}' -> '{fecha_vencimiento}'")
                    audiencia.fecha_vencimiento = fecha_vencimiento

                if cambios:
                    db.session.commit()
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Editar Audiencia desde Agenda",
                        detalles=f"Modificó la fecha/hora de la audiencia ID {evento_id} para el caso '{audiencia.expediente.nombre_caso}'. Cambios: {', '.join(cambios)}.",
                        expediente_id=audiencia.expediente_id,
                        cliente_id=audiencia.expediente.cliente_id
                    )
                return jsonify({"success": True, "message": "Audiencia judicial modificada con éxito."})

            elif tipo == "plazo":
                plazo = AlertaPlazoAudiencia.query.get_or_404(evento_id)
                if current_user.rol == "Asociado" and plazo.expediente.abogado_responsable_id != current_user.id:
                    return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."})

                if not titulo:
                    return jsonify({"success": False, "error": "El título del plazo es obligatorio."})

                fecha_venc = datetime.strptime(fecha_str, "%Y-%m-%d")

                cambios = []
                if plazo.titulo_hito != titulo:
                    cambios.append(f"título: '{plazo.titulo_hito}' -> '{titulo}'")
                    plazo.titulo_hito = titulo
                if plazo.fecha_vencimiento != fecha_venc:
                    cambios.append(f"vencimiento: '{plazo.fecha_vencimiento}' -> '{fecha_venc}'")
                    plazo.fecha_vencimiento = fecha_venc

                if cambios:
                    db.session.commit()
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Editar Plazo desde Agenda",
                        detalles=f"Modificó el plazo administrativo ID {evento_id} ('{plazo.titulo_hito}'). Cambios: {', '.join(cambios)}.",
                        expediente_id=plazo.expediente_id,
                        cliente_id=plazo.expediente.cliente_id
                    )
                return jsonify({"success": True, "message": "Plazo administrativo modificado con éxito."})

            else:
                return jsonify({"success": False, "error": "Tipo de evento inválido."})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Error al modificar el evento: {str(e)}"})

    @app.route("/agenda/evento/<string:tipo>/<int:evento_id>/eliminar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda_eliminar_evento(tipo, evento_id):
        data = request.get_json() or {}
        justificacion = data.get("justificacion", "").strip()

        if not justificacion:
            return jsonify({"success": False, "error": "La justificación de la eliminación es obligatoria."})

        try:
            if tipo == "tarea-pendiente" or tipo == "tarea-completada":
                tarea = Tarea.query.get_or_404(evento_id)
                if current_user.rol == "Asociado" and tarea.expediente.abogado_responsable_id != current_user.id:
                    return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."})

                titulo = tarea.titulo
                exp_id = tarea.expediente_id
                cliente_id = tarea.expediente.cliente_id if tarea.expediente else None

                db.session.delete(tarea)
                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Eliminar Tarea desde Agenda",
                    detalles=f"Eliminó la tarea ID {evento_id} ('{titulo}'). Justificación: {justificacion}",
                    expediente_id=exp_id,
                    cliente_id=cliente_id
                )
                return jsonify({"success": True, "message": "Tarea eliminada con éxito de la agenda."})

            elif tipo == "audiencia" or tipo == "plazo":
                alerta = AlertaPlazoAudiencia.query.get_or_404(evento_id)
                if current_user.rol == "Asociado" and alerta.expediente.abogado_responsable_id != current_user.id:
                    return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."})

                titulo = alerta.titulo_hito
                exp_id = alerta.expediente_id
                cliente_id = alerta.expediente.cliente_id if alerta.expediente else None
                es_aud = alerta.es_audiencia

                db.session.delete(alerta)
                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Eliminar Audiencia desde Agenda" if es_aud else "Eliminar Plazo desde Agenda",
                    detalles=f"Eliminó la {'audiencia' if es_aud else 'alerta de plazo'} ID {evento_id} ('{titulo}'). Justificación: {justificacion}",
                    expediente_id=exp_id,
                    cliente_id=cliente_id
                )
                return jsonify({"success": True, "message": f"{'Audiencia' if es_aud else 'Plazo'} eliminado con éxito de la agenda."})

            else:
                return jsonify({"success": False, "error": "Tipo de evento inválido."})

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Error al eliminar el evento: {str(e)}"})

    @app.route("/agenda/evento/tarea/<int:tarea_id>/completar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda_completar_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)
        if current_user.rol == "Asociado" and tarea.expediente.abogado_responsable_id != current_user.id:
            return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."})

        tarea.estado = "Completada"
        tarea.fecha_completada = datetime.now()
        try:
            db.session.commit()
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Completar Tarea desde Agenda",
                detalles=f"Marcó como completada la tarea '{tarea.titulo}' (ID {tarea_id}).",
                expediente_id=tarea.expediente_id,
                cliente_id=tarea.expediente.cliente_id if tarea.expediente else None
            )
            return jsonify({"success": True, "message": f"Tarea '{tarea.titulo}' marcada como completada."})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Error al actualizar la tarea: {str(e)}"})

    # === RUTAS DE NOTIFICACIONES ===
    @app.context_processor
    def inject_notificaciones():
        if current_user.is_authenticated:
            try:
                from app.models import NotificacionInterna
                unreads_count = NotificacionInterna.query.filter_by(usuario_id=current_user.id, leida=False).count()
                return dict(notificaciones_pendientes_count=unreads_count)
            except Exception:
                pass
        return dict(notificaciones_pendientes_count=0)

    @app.route("/agenda/procesar_alertas_cron", methods=["GET", "POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def trigger_procesar_alertas_cron():
        try:
            procesar_alertas_preventivas()
            return jsonify({"success": True, "message": "Procesamiento de alertas ejecutado con éxito."})
        except Exception as e:
            return jsonify({"success": False, "error": f"Error al procesar alertas: {str(e)}"})

    @app.route("/notificaciones")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def ver_notificaciones():
        notificaciones = NotificacionInterna.query.filter_by(usuario_id=current_user.id).order_by(NotificacionInterna.fecha_creacion.desc()).all()
        return render_template("notificaciones/index.html", notificaciones=notificaciones, current_date=rd_now())

    @app.route("/notificaciones/<int:notificacion_id>/leer", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def marcar_notificacion_leida(notificacion_id):
        notif = NotificacionInterna.query.filter_by(id=notificacion_id, usuario_id=current_user.id).first_or_404()
        notif.leida = True
        try:
            db.session.commit()
            return jsonify({"success": True, "message": "Notificación marcada como leída."})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Error al marcar como leída: {str(e)}"})

    @app.route("/notificaciones/leer_todas", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def marcar_todas_notificaciones_leidas():
        notifs = NotificacionInterna.query.filter_by(usuario_id=current_user.id, leida=False).all()
        for notif in notifs:
            notif.leida = True
        try:
            db.session.commit()
            return jsonify({"success": True, "message": "Todas las notificaciones marcadas como leídas."})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": f"Error al actualizar notificaciones: {str(e)}"})


def procesar_alertas_preventivas():
    """
    Calcula y despacha alertas internas y notificaciones por correo para
    plazos procesales, trámites administrativos, audiencias y tareas pendientes con 30, 15 y 3 días de anticipación.
    """
    from datetime import datetime, date
    import pytz
    from app import db
    from app.models import AlertaPlazoAudiencia, Tarea, Usuario, NotificacionInterna, RegistroEnvioAlerta
    from app.utils import enviar_email_alerta_preventiva

    print("[PLANIFICADOR] Iniciando procesamiento de alertas preventivas...")
    tz_rd = pytz.timezone('America/Santo_Domingo')
    now_local = datetime.now(tz_rd).date()
    
    # === 1. PROCESAR ALERTAS, PLAZOS Y AUDIENCIAS ===
    plazos = AlertaPlazoAudiencia.query.filter_by(estado_alerta='Pending').all()
    for plazo in plazos:
        if not plazo.fecha_vencimiento:
            continue
            
        try:
            venc_local = plazo.fecha_vencimiento.astimezone(tz_rd).date()
        except Exception:
            venc_local = plazo.fecha_vencimiento.date()
            
        dias_restantes = (venc_local - now_local).days
        
        anticipacion = None
        if 15 < dias_restantes <= 30:
            anticipacion = 30
        elif 3 < dias_restantes <= 15:
            anticipacion = 15
        elif 0 <= dias_restantes <= 3:
            anticipacion = 3
            
        if not anticipacion:
            continue
            
        # Verificar envío previo
        envio_previo = RegistroEnvioAlerta.query.filter_by(
            alerta_id=plazo.id,
            dias_anticipacion=anticipacion
        ).first()
        
        if envio_previo:
            continue
            
        # Determinar destinatarios
        exp = plazo.expediente
        abogados = []
        if exp and exp.abogado_responsable:
            abogados.append(exp.abogado_responsable)
        else:
            abogados = Usuario.query.filter_by(rol='Socio', activo=True).all()
            
        if not abogados:
            print(f"[PLANIFICADOR] Sin destinatarios válidos para el hito ID {plazo.id}")
            continue
            
        tipo_nombre = "audiencia" if plazo.es_audiencia else "plazo procesal"
        for abogado in abogados:
            try:
                enviar_email_alerta_preventiva(abogado, plazo, anticipacion)
                
                msj = f"[Alerta {anticipacion} días] La {tipo_nombre} '{plazo.titulo_hito}' del expediente '{exp.nombre_caso if exp else 'N/A'}' vence/ocurre el {venc_local.strftime('%d/%m/%Y')}."
                notif = NotificacionInterna(
                    usuario_id=abogado.id,
                    mensaje=msj,
                    leida=False,
                    expediente_id=exp.id if exp else None
                )
                db.session.add(notif)
            except Exception as e:
                print(f"[PLANIFICADOR] Error al despachar alerta al usuario {abogado.id}: {e}")
                
        try:
            registro = RegistroEnvioAlerta(
                alerta_id=plazo.id,
                dias_anticipacion=anticipacion
            )
            db.session.add(registro)
            db.session.commit()
            print(f"[PLANIFICADOR] Alerta de {anticipacion} días enviada para hito ID {plazo.id} ({plazo.titulo_hito})")
        except Exception as e:
            db.session.rollback()
            print(f"[PLANIFICADOR] Error al guardar registro de envío para hito ID {plazo.id}: {e}")

    # === 2. PROCESAR TAREAS PENDIENTES ===
    tareas = Tarea.query.filter(Tarea.estado != 'Completada', Tarea.fecha_limite != None).all()
    for tarea in tareas:
        venc_local = tarea.fecha_limite
        dias_restantes = (venc_local - now_local).days
        
        anticipacion = None
        if 15 < dias_restantes <= 30:
            anticipacion = 30
        elif 3 < dias_restantes <= 15:
            anticipacion = 15
        elif 0 <= dias_restantes <= 3:
            anticipacion = 3
            
        if not anticipacion:
            continue
            
        # Verificar envío previo
        envio_previo = RegistroEnvioAlerta.query.filter_by(
            tarea_id=tarea.id,
            dias_anticipacion=anticipacion
        ).first()
        
        if envio_previo:
            continue
            
        # Determinar destinatario
        abogados = []
        if tarea.asignado_a:
            abogados.append(tarea.asignado_a)
        elif tarea.creado_por:
            abogados.append(tarea.creado_por)
        elif tarea.expediente and tarea.expediente.abogado_responsable:
            abogados.append(tarea.expediente.abogado_responsable)
        else:
            abogados = Usuario.query.filter_by(rol='Socio', activo=True).all()
            
        if not abogados:
            print(f"[PLANIFICADOR] Sin destinatarios válidos para la tarea ID {tarea.id}")
            continue
            
        exp = tarea.expediente
        for abogado in abogados:
            try:
                enviar_email_alerta_preventiva(abogado, tarea, anticipacion)
                
                msj = f"[Alerta {anticipacion} días] La tarea pendiente '{tarea.titulo}' del expediente '{exp.nombre_caso if exp else 'N/A'}' vence el {venc_local.strftime('%d/%m/%Y')}."
                notif = NotificacionInterna(
                    usuario_id=abogado.id,
                    mensaje=msj,
                    leida=False,
                    expediente_id=exp.id if exp else None
                )
                db.session.add(notif)
            except Exception as e:
                print(f"[PLANIFICADOR] Error al despachar alerta de tarea al usuario {abogado.id}: {e}")
                
        try:
            registro = RegistroEnvioAlerta(
                tarea_id=tarea.id,
                dias_anticipacion=anticipacion
            )
            db.session.add(registro)
            db.session.commit()
            print(f"[PLANIFICADOR] Alerta de {anticipacion} días enviada para tarea ID {tarea.id} ({tarea.titulo})")
        except Exception as e:
            db.session.rollback()
            print(f"[PLANIFICADOR] Error al guardar registro de envío para tarea ID {tarea.id}: {e}")
            
    print("[PLANIFICADOR] Fin del procesamiento de alertas preventivas.")
