import os
import uuid  # Para generar el código único de la firma
from decimal import Decimal
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

from email_validator import EmailNotValidError, validate_email
from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app import db
from app.forms import (
    ChangePasswordForm,
    ClienteForm,
    ExpedienteAdministrativoForm,
    ExpedienteJudicialForm,
    ForgotPasswordForm,
    LoginForm,
    RequiredChangePasswordForm,
    ResetPasswordForm,
    TareaForm,
    UserProfileForm,
    UsuarioForm,
)
from app.models import (
    AlertaPlazoAudiencia,
    BitacoraAuditoria,
    BitacoraTiempoTarea,
    Carpeta,
    Cliente,
    DetalleFactura,
    Documento,
    Expediente,
    ExpedienteAdministrativo,
    ExpedienteJudicial,
    FacturaHonorario,
    NotificacionInterna,
    PartidaPagoFactura,
    RegistroEnvioAlerta,
    Tarea,
    TipoDocumento,
    Usuario,
    VersionDocumento,
    MateriaLegal,
    ProcedimientoLegal,
    rd_now,
    rd_today,
    ParametroFiscal,
    ContratoHonorarios,
    CronogramaCobro,
    ReciboInterno,
    TransaccionPago,
    GastoReembolsable,
    Presupuesto,
    PresupuestoDetalle,
)
from app.dynamic_fields import DYNAMIC_FIELDS_BY_PROCEDURE
from app.services.billing_service import BillingService
from app.utils import (
    enviar_email_alerta_preventiva,
    enviar_email_credenciales_cliente,
    enviar_email_restablecimiento,
    generate_reset_token,
    verify_reset_token,
)

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
    "rtf",
    "odt",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "zip",
    "rar",
    "7z",
    "tar",
    "gz",
}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
            "abogado_responsable_nombre": ", ".join([a.nombre for a in exp.abogados]) if exp.abogados else "No asignado",
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
            "materia_id": exp.materia_id,
            "procedimiento_id": exp.procedimiento_id,
            "materia_nombre": exp.materia.nombre if exp.materia else "",
            "procedimiento_nombre": exp.procedimiento.nombre if exp.procedimiento else "",
            "prioridad": exp.prioridad or "",
            "nivel_riesgo": exp.nivel_riesgo or "",
            "probabilidad_exito": exp.probabilidad_exito or "",
            "origen_cliente": exp.origen_cliente or "",
            "fecha_contratacion": exp.fecha_contratacion.strftime("%Y-%m-%d") if exp.fecha_contratacion else None,
            "valor_estimado_caso": float(exp.valor_estimado_caso) if exp.valor_estimado_caso is not None else None,
            "datos_dinamicos": exp.datos_dinamicos or {},
            "resumen_financiero": BillingService.obtener_resumen_expediente(exp.id),
        }
        if exp.tipo_tramite == "Judicial":
            next_hearing = (
                AlertaPlazoAudiencia.query.filter_by(
                    expediente_id=exp.id, es_audiencia=True, estado_alerta="Pendiente"
                )
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
                    "monto_demanda": float(exp.monto_demanda)
                    if exp.monto_demanda is not None
                    else None,
                    "fecha_audiencia": next_hearing.fecha_vencimiento.strftime(
                        "%Y-%m-%d"
                    )
                    if next_hearing
                    else None,
                    "hora_audiencia": next_hearing.fecha_vencimiento.strftime("%H:%M")
                    if next_hearing
                    else None,
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


def registrar_auditoria(
    usuario_id, accion, detalles, cliente_id=None, expediente_id=None
):
    try:
        ip = request.remote_addr or "127.0.0.1"
        dispositivo = (
            request.user_agent.string[:255]
            if request.user_agent and request.user_agent.string
            else "Desconocido"
        )
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
                        redirect(next_page)
                        if next_page
                        else redirect(url_for("dashboard"))
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
                "success",
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
                flash(
                    "Tu contraseña ha sido restablecida con éxito. Ya puedes iniciar sesión.",
                    "success",
                )
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
                    Expediente.query.filter(Expediente.abogados.any(Usuario.id == current_user.id))
                    .filter(Expediente.estado != "Archivado")
                    .count()
                )

                # Obtener IDs de sus expedientes para alertas
                mis_expedientes_ids = [
                    e.id
                    for e in Expediente.query.filter(
                        Expediente.abogados.any(Usuario.id == current_user.id)
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
                    Expediente.query.filter(Expediente.abogados.any(Usuario.id == current_user.id))
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
                total_tareas_pendientes = (
                    Tarea.query.filter(Tarea.estado != "Completada")
                    .filter(
                        db.or_(
                            Tarea.asignado_a_id == current_user.id,
                            Tarea.asignado_a_id.is_(None),
                        )
                    )
                    .count()
                )
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
                    db_version_row = db.session.execute(
                        db.text("SHOW server_version;")
                    ).first()
                    db_version = (
                        f"PostgreSQL {db_version_row[0].split()[0]}"
                        if db_version_row
                        else "PostgreSQL 15"
                    )
                except Exception:
                    db_version = "PostgreSQL 15"

                # 2. Obtener almacenamiento libre de la carpeta uploads
                import shutil

                try:
                    uploads_path = os.path.join(current_app.root_path, "uploads")
                    if not os.path.exists(uploads_path):
                        os.makedirs(uploads_path)
                    total, used, free = shutil.disk_usage(uploads_path)
                    free_gb = free / (1024**3)
                    almacenamiento_status = f"{free_gb:.1f} GB Libres"
                except Exception:
                    almacenamiento_status = "Operativo"

                # 3. Verificar estado del servicio de correos (SMTP)
                import socket

                mail_server = current_app.config.get("MAIL_SERVER")
                mail_port = current_app.config.get("MAIL_PORT")
                mail_username = current_app.config.get("MAIL_USERNAME")
                mail_password = current_app.config.get("MAIL_PASSWORD")

                if not mail_username or not mail_password:
                    mail_status = "No configurado"
                    mail_badge_class = "bg-warning text-dark"
                else:
                    try:
                        # Test de conexión rápido (timeout de 1.0 segundos)
                        s = socket.create_connection(
                            (mail_server, mail_port), timeout=1.0
                        )
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
                tipos_documentos = TipoDocumento.query.order_by(
                    TipoDocumento.nombre_tipo.asc()
                ).all()
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
                        tipos_documentos=tipos_documentos,
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
                        AlertaPlazoAudiencia.estado_alerta.in_(
                            ["Pending", "Pendiente"]
                        ),
                        AlertaPlazoAudiencia.fecha_vencimiento >= rd_now(),
                    )

                    # Si es Judicial, buscar específicamente audiencias. Si es Administrativo, buscar cualquier hito/plazo pendiente.
                    if (
                        caso_activo_principal
                        and caso_activo_principal.tipo_tramite == "Judicial"
                    ):
                        query_audiencia = query_audiencia.filter(
                            AlertaPlazoAudiencia.es_audiencia
                        )

                    audiencia_proxima = query_audiencia.order_by(
                        AlertaPlazoAudiencia.fecha_vencimiento.asc()
                    ).first()

                documentos_compartidos = []
                if cliente_db:
                    if exp_ids:
                        documentos_compartidos = (
                            Documento.query.filter(
                                Documento.visibilidad == "Compartido"
                            )
                            .filter(
                                db.or_(
                                    Documento.expediente_id.in_(exp_ids),
                                    Documento.cliente_id == cliente_db.id,
                                )
                            )
                            .all()
                        )
                    else:
                        documentos_compartidos = Documento.query.filter_by(
                            visibilidad="Compartido", cliente_id=cliente_db.id
                        ).all()

                # Fases del caso principal (Leídas de base de datos)
                progreso_fase = 1
                if caso_activo_principal:
                    if caso_activo_principal.estado in ["Archivado", "Finalizado"]:
                        progreso_fase = 5
                    else:
                        progreso_fase = caso_activo_principal.fase_actual or 1

                # Cargar todas las audiencias/hitos de este caso específico
                hitostotal = []
                if caso_activo_principal:
                    hitostotal = (
                        AlertaPlazoAudiencia.query.filter_by(
                            expediente_id=caso_activo_principal.id
                        )
                        .order_by(AlertaPlazoAudiencia.fecha_vencimiento.asc())
                        .all()
                    )

                # Obtener facturas y cuotas (partidas) de pago del cliente
                facturas_cli = FacturaHonorario.query.filter_by(cliente_id=cliente_db.id).all()
                cuotas_pendientes = []
                for f in facturas_cli:
                    for p in f.partidas:
                        if p.estado_pago in ["Pendiente", "Mora"]:
                            cuotas_pendientes.append(p)
                
                cuotas_pendientes.sort(key=lambda x: x.fecha_vencimiento)
                total_pendiente_cliente = sum(float(f.total_pendiente) for f in facturas_cli if f.estado_pago != 'Anulado')

                estadisticas = {
                    "expedientes_activos_count": expedientes_activos_count,
                    "audiencia_proxima": audiencia_proxima,
                    "documentos_disponibles_count": len(documentos_compartidos),
                    "expedientes": expedientes_cliente,
                    "documentos": documentos_compartidos,
                    "caso_activo_principal": caso_activo_principal,
                    "progreso_fase": progreso_fase,
                    "hitostotal": hitostotal,
                    "cuotas_pendientes": cuotas_pendientes,
                    "total_pendiente_cliente": total_pendiente_cliente,
                }
                return render_template(
                    "dashboard/dashboard_cliente.html",
                    usuario=current_user,
                    estadisticas=estadisticas,
                    current_date=rd_now(),
                    tipos_documentos=tipos_documentos,
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

        query = Cliente.query

        if q:
            search_pattern = f"%{q}%"
            query = query.filter(
                db.or_(
                    db.func.unaccent(Cliente.nombres).ilike(db.func.unaccent(search_pattern)),
                    db.func.unaccent(Cliente.apellidos).ilike(db.func.unaccent(search_pattern)),
                    db.func.unaccent(db.func.concat(Cliente.nombres, ' ', Cliente.apellidos)).ilike(db.func.unaccent(search_pattern)),
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
                "rnc_cedula": c.rnc_cedula,
                "consentimiento_datos": bool(c.consentimiento_datos),
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
                    "activo": user.activo,
                }

        # 4. Obtener información financiera (facturas)
        facturas = FacturaHonorario.query.filter_by(cliente_id=cliente.id).all()
        total_facturado = sum(float(f.monto_total) for f in facturas)
        total_pagado = sum(float(f.total_pagado) for f in facturas)
        total_pendiente = sum(float(f.total_pendiente) for f in facturas)
        
        facturas_list = []
        for f in facturas:
            facturas_list.append({
                "id": f.id,
                "ncf": f.ncf or "N/A",
                "monto_total": float(f.monto_total),
                "total_pagado": float(f.total_pagado),
                "total_pendiente": float(f.total_pendiente),
                "estado_pago": f.estado_pago,
                "fecha_emision": f.fecha_emision.strftime("%d/%m/%Y") if f.fecha_emision else "N/A",
            })

        # 5. Retornar detalles con auditorías y datos financieros
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
                "facturas": facturas_list,
                "total_facturado": total_facturado,
                "total_pagado": total_pagado,
                "total_pendiente": total_pendiente,
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
            flash(
                "El cliente debe tener un correo de contacto configurado para habilitar acceso.",
                "danger",
            )
            return redirect(url_for("clientes", id=cliente.id))

        # Validar la entregabilidad del correo de forma estricta (realiza consulta DNS MX)
        try:
            validate_email(email_limpio, check_deliverability=True)
        except EmailNotValidError as e:
            flash(
                f"El correo electrónico no es válido o no tiene un servidor de correo real: {str(e)}",
                "danger",
            )
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
                    cliente_id=cliente.id,
                )
                flash("Cuenta de acceso existente vinculada con éxito.", "success")
            else:
                flash(
                    f"El correo electrónico '{email_limpio}' ya está en uso por un miembro de la firma.",
                    "danger",
                )
            return redirect(url_for("clientes", id=cliente.id))

        clave_inicial = cliente.rnc_cedula.strip()
        if not clave_inicial:
            flash(
                "El cliente debe poseer cédula o RNC para usar de contraseña inicial.",
                "danger",
            )
            return redirect(url_for("clientes", id=cliente.id))

        nuevo_usuario = Usuario(
            nombre=cliente.nombre_completo,
            email=email_limpio,
            rol="Cliente",
            password_hash=generate_password_hash(clave_inicial),
            activo=True,
            requiere_cambio_password=True,
        )

        try:
            db.session.add(nuevo_usuario)
            db.session.flush()
            cliente.usuario_id = nuevo_usuario.id

            # Enviar credenciales por correo antes de confirmar en BD
            email_enviado = enviar_email_credenciales_cliente(
                cliente, email_limpio, clave_inicial
            )
            if not email_enviado:
                raise Exception(
                    "El servidor de correo rechazó el envío o la dirección de correo no es válida."
                )

            db.session.commit()

            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Creación",
                detalles=f"Habilitó acceso al portal del cliente. Creada cuenta de usuario '{email_limpio}' con clave inicial y notificado por correo.",
                cliente_id=cliente.id,
            )
            flash(
                "Acceso al portal habilitado con éxito. Se ha enviado un correo con las credenciales al cliente para verificar la validez de la cuenta.",
                "success",
            )
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
                    cliente_id=cliente.id,
                )
                flash(
                    "Acceso al portal desactivado temporalmente para este cliente.",
                    "success",
                )
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
                    cliente_id=cliente.id,
                )
                flash(
                    "Acceso al portal reactivado con éxito para este cliente.",
                    "success",
                )
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
                flash(
                    "El cliente debe poseer cédula o RNC para restablecer la contraseña.",
                    "danger",
                )
                return redirect(url_for("clientes", id=cliente.id))

            user.password_hash = generate_password_hash(clave_inicial)
            user.requiere_cambio_password = True
            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles="Restableció la contraseña de acceso del cliente a su cédula/RNC inicial.",
                    cliente_id=cliente.id,
                )
                flash(
                    "Contraseña restablecida con éxito a la cédula/RNC del cliente.",
                    "success",
                )
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
                flash(
                    "Debe especificar una razón para desactivar al cliente.", "danger"
                )
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
                    detalles="Estableció una contraseña nueva por requerimiento de primer inicio de sesión.",
                )
                flash(
                    "Contraseña actualizada con éxito. Bienvenido al sistema.",
                    "success",
                )
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
            current_date=rd_now(),
        )

    @app.route("/perfil/editar", methods=["POST"])
    @login_required
    def editar_perfil():
        form = UserProfileForm()
        if form.validate_on_submit():
            existente = Usuario.query.filter(
                Usuario.email == form.email.data, Usuario.id != current_user.id
            ).first()
            if existente:
                flash(
                    "El correo electrónico ya está registrado por otro usuario.",
                    "danger",
                )
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
                    detalles=f"Actualizó sus datos personales de perfil: Nombre '{old_nombre}' -> '{current_user.nombre}', Correo '{old_email}' -> '{current_user.email}'.",
                )
                flash("Datos personales actualizados correctamente.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al actualizar los datos: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(
                        f"Error en {getattr(form, field).label.text}: {error}", "danger"
                    )

        return redirect(url_for("ver_perfil"))

    @app.route("/perfil/cambiar-password", methods=["POST"])
    @login_required
    def cambiar_password_perfil():
        form = ChangePasswordForm()
        if form.validate_on_submit():
            if not check_password_hash(
                current_user.password_hash, form.current_password.data
            ):
                flash("La contraseña actual es incorrecta.", "danger")
                return redirect(url_for("ver_perfil"))

            current_user.password_hash = generate_password_hash(form.new_password.data)
            try:
                db.session.commit()
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Edición",
                    detalles="Cambió voluntariamente su contraseña de acceso desde su perfil de usuario.",
                )
                flash("Su contraseña ha sido modificada con éxito.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error al cambiar la contraseña: {str(e)}", "danger")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(
                        f"Error en {getattr(form, field).label.text}: {error}", "danger"
                    )

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
                "salario_base": float(u.salario_base or 0.00),
                "porcentaje_comision": float(u.porcentaje_comision or 0.00),
                "cedula": u.cedula or "",
                "fecha_nacimiento": u.fecha_nacimiento.strftime('%Y-%m-%d') if u.fecha_nacimiento else "",
                "telefono": u.telefono or "",
                "direccion": u.direccion or "",
            }
            for u in usuarios
        ]

    # --- RUTAS DE USUARIOS ---
    @app.route("/usuarios")
    @login_required
    @roles_permitidos("Administrador", "Socio")
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
    @roles_permitidos("Administrador", "Socio")
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
                salario_base=form.salario_base.data,
                porcentaje_comision=form.porcentaje_comision.data,
                cedula=form.cedula.data.strip() if form.cedula.data else None,
                fecha_nacimiento=form.fecha_nacimiento.data,
                telefono=form.telefono.data.strip() if form.telefono.data else None,
                direccion=form.direccion.data.strip() if form.direccion.data else None,
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
    @roles_permitidos("Administrador", "Socio")
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
            usuario.salario_base = form.salario_base.data
            usuario.porcentaje_comision = form.porcentaje_comision.data
            usuario.cedula = form.cedula.data.strip() if form.cedula.data else None
            usuario.fecha_nacimiento = form.fecha_nacimiento.data
            usuario.telefono = form.telefono.data.strip() if form.telefono.data else None
            usuario.direccion = form.direccion.data.strip() if form.direccion.data else None

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
    @roles_permitidos("Administrador", "Socio")
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
                    Usuario.nombre.ilike(search_pattern),
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
        acciones_query = (
            db.session.query(BitacoraAuditoria.accion_realizada).distinct().all()
        )
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
        cliente_id = request.args.get("cliente_id", type=int)

        # Si no hay término de búsqueda ni cliente, no se muestra nada
        if not q and not cliente_id:
            return jsonify([])

        query = Expediente.query
        if q:
            search_pattern = f"%{q}%"
            query = query.join(Cliente).filter(
                db.or_(
                    Expediente.codigo_firma.ilike(search_pattern),
                    Expediente.nombre_caso.ilike(search_pattern),
                    Cliente.rnc_cedula.ilike(search_pattern),
                    Cliente.nombres.ilike(search_pattern),
                    Cliente.apellidos.ilike(search_pattern),
                )
            )

        if cliente_id:
            query = query.filter(Expediente.cliente_id == cliente_id)

        if current_user.rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if not cliente_db:
                return jsonify([])
            exp_ids = [e.id for e in cliente_db.expedientes]
            query = query.filter(Expediente.id.in_(exp_ids))

        if current_user.rol == "Asociado":
            query = query.filter(Expediente.abogados.any(Usuario.id == current_user.id))

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
                "cliente": exp.cliente.nombre_completo if exp.cliente else "N/A",
            }
            for exp in lista_exp
        ]
        return jsonify(results)

    @app.route("/expedientes/historial")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def historial_expedientes_finalizados():
        from sqlalchemy import extract

        anios = (
            db.session.query(extract("year", Expediente.fecha_cierre))
            .filter(
                Expediente.estado == "Finalizado", Expediente.fecha_cierre.isnot(None)
            )
            .distinct()
            .order_by(extract("year", Expediente.fecha_cierre).asc())
            .all()
        )

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

            query = query.filter(extract("year", Expediente.fecha_cierre) >= anio_desde)
        if anio_hasta:
            from sqlalchemy import extract

            query = query.filter(extract("year", Expediente.fecha_cierre) <= anio_hasta)

        if tipo_finalizacion:
            query = query.filter(Expediente.tipo_finalizacion == tipo_finalizacion)

        if tipo_tramite:
            query = query.filter(Expediente.tipo_tramite == tipo_tramite)

        if current_user.rol == "Asociado":
            query = query.filter(Expediente.abogados.any(Usuario.id == current_user.id))

        expedientes = query.order_by(Expediente.fecha_cierre.desc()).all()

        results = []
        for exp in expedientes:
            next_hearing = None
            if exp.tipo_tramite == "Judicial":
                next_hearing = (
                    AlertaPlazoAudiencia.query.filter_by(
                        expediente_id=exp.id,
                        es_audiencia=True,
                        estado_alerta="Pendiente",
                    )
                    .order_by(AlertaPlazoAudiencia.fecha_vencimiento.asc())
                    .first()
                )

            item = {
                "id": exp.id,
                "codigo_firma": exp.codigo_firma,
                "nombre_caso": exp.nombre_caso,
                "tipo_tramite": exp.tipo_tramite,
                "cliente_nombre": exp.cliente.nombre_completo if exp.cliente else "N/A",
                "abogado_responsable_nombre": exp.abogado_responsable.nombre
                if exp.abogado_responsable
                else "No asignado",
                "rol_firma": exp.rol_firma,
                "fecha_apertura": exp.fecha_apertura.strftime("%Y-%m-%d")
                if exp.fecha_apertura
                else None,
                "fecha_cierre": exp.fecha_cierre.strftime("%Y-%m-%d")
                if exp.fecha_cierre
                else None,
                "tipo_finalizacion": exp.tipo_finalizacion,
                "razon_estado": exp.razon_estado,
                "fase_actual": exp.fase_actual,
                "fase_nota": exp.fase_nota,
                "materia_id": exp.materia_id,
                "procedimiento_id": exp.procedimiento_id,
                "materia_nombre": exp.materia.nombre if exp.materia else "",
                "procedimiento_nombre": exp.procedimiento.nombre if exp.procedimiento else "",
                "prioridad": exp.prioridad or "",
                "nivel_riesgo": exp.nivel_riesgo or "",
                "probabilidad_exito": exp.probabilidad_exito or "",
                "origen_cliente": exp.origen_cliente or "",
                "fecha_contratacion": exp.fecha_contratacion.strftime("%Y-%m-%d") if exp.fecha_contratacion else None,
                "valor_estimado_caso": float(exp.valor_estimado_caso) if exp.valor_estimado_caso is not None else None,
                "datos_dinamicos": exp.datos_dinamicos or {},
            }

            if exp.tipo_tramite == "Judicial":
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
                        "monto_demanda": float(exp.monto_demanda)
                        if exp.monto_demanda is not None
                        else None,
                        "fecha_audiencia": next_hearing.fecha_vencimiento.strftime(
                            "%Y-%m-%d"
                        )
                        if next_hearing
                        else None,
                        "hora_audiencia": next_hearing.fecha_vencimiento.strftime(
                            "%H:%M"
                        )
                        if next_hearing
                        else None,
                    }
                )
            else:
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

            results.append(item)

        return jsonify(results)

    @app.route("/expedientes/<int:expediente_id>/detalle")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def detalle_expediente(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)

        # RF-SEG-002: Segregación Interna de Expedientes
        if current_user.rol == "Asociado" and current_user not in exp.abogados:
            return jsonify({"success": False, "error": "Acceso denegado. No está asignado a este expediente."}), 403

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
                "detalles": log.detalles_tecnicos,
            }
            for log in historial_db
            if log.accion_realizada != "Visualización"
        ]

        tiempos_data = []
        if current_user.rol in ["Socio", "Asociado", "Paralegal", "Administrador"]:
            tiempos_db = (
                BitacoraTiempoTarea.query.filter_by(expediente_id=exp.id)
                .order_by(BitacoraTiempoTarea.fecha_tarea.desc())
                .all()
            )
            tiempos_data = [
                {
                    "id": t.id,
                    "fecha": t.fecha_tarea.strftime("%Y-%m-%d"),
                    "usuario": t.usuario.nombre if t.usuario else "Desconocido",
                    "horas": float(t.horas_trabajadas),
                    "descripcion": t.descripcion_gestion,
                    "estado": t.estado_cierre
                }
                for t in tiempos_db
            ]

        # 3. Serializar expediente
        item = {
            "id": exp.id,
            "tiempos": tiempos_data,
            "codigo_firma": exp.codigo_firma,
            "cliente_id": exp.cliente_id,
            "cliente_nombre": exp.cliente.nombre_completo
            if exp.cliente
            else "Desconocido",
            "abogado_responsable_id": exp.abogado_responsable_id,
            "abogado_responsable_nombre": ", ".join([a.nombre for a in exp.abogados]) if exp.abogados else "No asignado",
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
            "razon_estado": exp.razon_estado or "",
            "tipo_finalizacion": exp.tipo_finalizacion or "",
            "fase_actual": exp.fase_actual,
            "fase_nota": exp.fase_nota or "",
            "esquema_cobro": exp.esquema_cobro or "Fijo",
            "tarifa_monto": float(exp.tarifa_monto or 0.00),
            "porcentaje_exito": float(exp.porcentaje_exito or 0.00),
            "auditorias": auditorias_data,
            "historial": historial_data,
            "materia_id": exp.materia_id,
            "procedimiento_id": exp.procedimiento_id,
            "materia_nombre": exp.materia.nombre if exp.materia else "",
            "procedimiento_nombre": exp.procedimiento.nombre if exp.procedimiento else "",
            "prioridad": exp.prioridad or "",
            "nivel_riesgo": exp.nivel_riesgo or "",
            "probabilidad_exito": exp.probabilidad_exito or "",
            "origen_cliente": exp.origen_cliente or "",
            "fecha_contratacion": exp.fecha_contratacion.strftime("%Y-%m-%d") if exp.fecha_contratacion else None,
            "valor_estimado_caso": float(exp.valor_estimado_caso) if exp.valor_estimado_caso is not None else None,
            "datos_dinamicos": exp.datos_dinamicos or {},
        }

        if exp.tipo_tramite == "Judicial":
            next_hearing = (
                AlertaPlazoAudiencia.query.filter_by(
                    expediente_id=exp.id, es_audiencia=True, estado_alerta="Pendiente"
                )
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
                    "contacto_abogado_contraparte": exp.contacto_abogado_contraparte
                    or "",
                    "monto_demanda": float(exp.monto_demanda)
                    if exp.monto_demanda is not None
                    else None,
                    "fecha_audiencia": next_hearing.fecha_vencimiento.strftime(
                        "%Y-%m-%d"
                    )
                    if next_hearing
                    else None,
                    "hora_audiencia": next_hearing.fecha_vencimiento.strftime("%H:%M")
                    if next_hearing
                    else None,
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
                    "monto_tasas_impuestos": float(exp.monto_tasas_impuestos)
                    if exp.monto_tasas_impuestos is not None
                    else None,
                }
            )
        return jsonify(item)

    @app.route("/expedientes/<int:expediente_id>/tiempos/agregar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agregar_tiempo_expediente(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)
        
        # RF-SEG-002: Segregación Interna de Expedientes
        if current_user.rol == "Asociado" and current_user not in exp.abogados:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("expedientes"))
            
        try:
            horas_str = request.form.get("horas", "0")
            descripcion = request.form.get("descripcion", "").strip()
            fecha_str = request.form.get("fecha", "")
            
            try:
                horas = float(horas_str)
            except ValueError:
                flash("El número de horas es inválido.", "danger")
                return redirect(url_for("expedientes"))
                
            if horas <= 0:
                flash("Las horas trabajadas deben ser mayores a cero.", "danger")
                return redirect(url_for("expedientes"))
            if not descripcion:
                flash("La descripción de la gestión es obligatoria.", "danger")
                return redirect(url_for("expedientes"))
            if not fecha_str:
                flash("La fecha es obligatoria.", "danger")
                return redirect(url_for("expedientes"))
                
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            
            nuevo_tiempo = BitacoraTiempoTarea(
                expediente_id=exp.id,
                usuario_id=current_user.id,
                fecha_tarea=fecha,
                horas_trabajadas=horas,
                descripcion_gestion=descripcion,
                estado_cierre="Abierto"
            )
            db.session.add(nuevo_tiempo)
            
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="REGISTRO_TIEMPO",
                detalles=f"Registró {horas} horas de trabajo en el expediente '{exp.nombre_caso}'.",
                expediente_id=exp.id,
                cliente_id=exp.cliente_id
            )
            db.session.commit()
            flash("Horas registradas correctamente en la bitácora.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al registrar horas: {str(e)}", "danger")
            
        return redirect(url_for("expedientes"))

    @app.route("/expedientes/<int:expediente_id>/bitacora")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def bitacora_expediente(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)

        # RF-SEG-002: Segregación Interna de Expedientes
        if current_user.rol == "Asociado" and current_user not in exp.abogados:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("expedientes"))

        # Obtener historial de proceso (bitácora) desde BitacoraAuditoria
        historial_raw = (
            BitacoraAuditoria.query.filter_by(expediente_id=exp.id)
            .order_by(BitacoraAuditoria.fecha_hora.desc())
            .all()
        )
        # Filtrar solo acciones relevantes de cambio de estado, fase o carga de documentos
        historial_db = [
            log
            for log in historial_raw
            if "Visualización" not in log.accion_realizada
            and "Descarga" not in log.accion_realizada
        ]

        # Registrar auditoría de visualización de bitácora
        registrar_auditoria(
            usuario_id=current_user.id,
            accion="Visualización Bitácora",
            detalles=f"Consultó la bitácora completa del expediente '{exp.nombre_caso}'.",
            expediente_id=exp.id,
        )

        return render_template(
            "expedientes/bitacora.html",
            expediente=exp,
            historial=historial_db,
            usuario=current_user,
        )

    # --- APIS PARA CATÁLOGOS Y FORMULARIOS DINÁMICOS ---
    @app.route("/api/materias")
    @login_required
    def api_get_materias():
        tipo = request.args.get("tipo", "").strip()  # 'Judicial' o 'Administrativo'
        if not tipo:
            return jsonify([])
        materias = MateriaLegal.query.filter_by(tipo_expediente=tipo, activo=True).order_by(MateriaLegal.nombre.asc()).all()
        return jsonify([{"id": m.id, "nombre": m.nombre, "descripcion": m.descripcion, "requiere_procedimiento": m.requiere_procedimiento} for m in materias])

    @app.route("/api/procedimientos")
    @login_required
    def api_get_procedimientos():
        materia_id = request.args.get("materia_id", type=int)
        if not materia_id:
            return jsonify([])
        procedimientos = ProcedimientoLegal.query.filter_by(materia_id=materia_id, activo=True).order_by(ProcedimientoLegal.orden.asc(), ProcedimientoLegal.nombre.asc()).all()
        return jsonify([{"id": p.id, "nombre": p.nombre, "descripcion": p.descripcion} for p in procedimientos])

    @app.route("/api/procedimientos/<int:procedimiento_id>/campos")
    @login_required
    def api_get_campos_dinamicos(procedimiento_id):
        proc = ProcedimientoLegal.query.get_or_404(procedimiento_id)
        campos = DYNAMIC_FIELDS_BY_PROCEDURE.get(proc.nombre, [])
        return jsonify({"campos": campos})

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

        # Asignamos las opciones
        form_judicial.cliente_id.choices = [
            (0, "Seleccione un cliente...")
        ] + opciones_clientes
        form_judicial.abogados_ids.choices = opciones_abogados

        form_admin.cliente_id.choices = [
            (0, "Seleccione un cliente...")
        ] + opciones_clientes
        form_admin.abogados_ids.choices = opciones_abogados

        # Cargar materias del catálogo para el selector
        materias_jud = MateriaLegal.query.filter_by(tipo_expediente='Judicial', activo=True).order_by(MateriaLegal.nombre.asc()).all()
        form_judicial.materia_id.choices = [(0, "Seleccione materia...")] + [(m.id, m.nombre) for m in materias_jud]
        
        materias_adm = MateriaLegal.query.filter_by(tipo_expediente='Administrativo', activo=True).order_by(MateriaLegal.nombre.asc()).all()
        form_admin.materia_id.choices = [(0, "Seleccione materia...")] + [(m.id, m.nombre) for m in materias_adm]

        # Cargar procedimientos para validar el POST si se envía
        selected_materia_jud = request.form.get("materia_id", type=int) if form_judicial.submit_judicial.name in request.form else 0
        if selected_materia_jud:
            procs = ProcedimientoLegal.query.filter_by(materia_id=selected_materia_jud, activo=True).order_by(ProcedimientoLegal.nombre.asc()).all()
            form_judicial.procedimiento_id.choices = [(0, "Seleccione procedimiento...")] + [(p.id, p.nombre) for p in procs]
        else:
            form_judicial.procedimiento_id.choices = [(0, "Seleccione procedimiento...")]

        selected_materia_adm = request.form.get("materia_id", type=int) if form_admin.submit_admin.name in request.form else 0
        if selected_materia_adm:
            procs = ProcedimientoLegal.query.filter_by(materia_id=selected_materia_adm, activo=True).order_by(ProcedimientoLegal.nombre.asc()).all()
            form_admin.procedimiento_id.choices = [(0, "Seleccione procedimiento...")] + [(p.id, p.nombre) for p in procs]
        else:
            form_admin.procedimiento_id.choices = [(0, "Seleccione procedimiento...")]

        # Si es un GET y se reciben parámetros para pre-llenar (ej: desde aceptar presupuesto)
        if request.method == "GET":
            cliente_pre = request.args.get("cliente_id", type=int)
            if cliente_pre:
                form_judicial.cliente_id.data = cliente_pre
                form_admin.cliente_id.data = cliente_pre
            
            nombre_caso_pre = request.args.get("nombre_caso")
            if nombre_caso_pre:
                form_judicial.nombre_caso.data = nombre_caso_pre
                form_admin.nombre_caso.data = nombre_caso_pre
                
            materia_pre = request.args.get("materia")
            if materia_pre:
                materia_obj = MateriaLegal.query.filter(MateriaLegal.nombre.ilike(materia_pre)).first()
                if materia_obj:
                    form_judicial.materia_id.data = materia_obj.id
                    form_admin.materia_id.data = materia_obj.id
                    
                    # Cargar procedimientos para esa materia de forma preventiva
                    procs_jud = ProcedimientoLegal.query.filter_by(materia_id=materia_obj.id, activo=True).order_by(ProcedimientoLegal.nombre.asc()).all()
                    form_judicial.procedimiento_id.choices = [(0, "Seleccione procedimiento...")] + [(p.id, p.nombre) for p in procs_jud]
                    
                    procs_adm = ProcedimientoLegal.query.filter_by(materia_id=materia_obj.id, activo=True).order_by(ProcedimientoLegal.nombre.asc()).all()
                    form_admin.procedimiento_id.choices = [(0, "Seleccione procedimiento...")] + [(p.id, p.nombre) for p in procs_adm]
                    
            monto_pre = request.args.get("monto", type=float)
            if monto_pre:
                form_judicial.valor_estimado_caso.data = monto_pre
                form_admin.valor_estimado_caso.data = monto_pre
                form_judicial.tarifa_monto.data = monto_pre
                form_admin.tarifa_monto.data = monto_pre

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

                # Validar abogados asignados
                if not form_judicial.abogados_ids.data:
                    flash("Debe seleccionar al menos un abogado para el expediente.", "danger")
                    return render_template(
                        "expedientes/nuevo.html",
                        form_judicial=form_judicial,
                        form_admin=form_admin,
                    )

                abogados_seleccionados = Usuario.query.filter(Usuario.id.in_(form_judicial.abogados_ids.data)).all()

                materia_obj = MateriaLegal.query.get(form_judicial.materia_id.data)
                
                # Validar procedimiento condicionalmente
                proc_id = form_judicial.procedimiento_id.data
                proc_obj = None
                if materia_obj and materia_obj.requiere_procedimiento:
                    if not proc_id or proc_id == 0:
                        flash("Debe seleccionar un procedimiento para esta materia.", "danger")
                        return render_template(
                            "expedientes/nuevo.html",
                            form_judicial=form_judicial,
                            form_admin=form_admin,
                        )
                    proc_obj = ProcedimientoLegal.query.get(proc_id)
                    actual_procedimiento_id = proc_id
                else:
                    actual_procedimiento_id = None

                # Extraer campos dinámicos
                datos_dinamicos_json = {}
                if proc_obj:
                    campos_definidos = DYNAMIC_FIELDS_BY_PROCEDURE.get(proc_obj.nombre, [])
                    for campo in campos_definidos:
                        field_name = campo["name"]
                        val = request.form.get(field_name)
                        if val is not None:
                            datos_dinamicos_json[field_name] = val

                nuevo_caso = ExpedienteJudicial(
                    codigo_firma=codigo_generado,
                    cliente_id=form_judicial.cliente_id.data,
                    abogado_responsable_id=form_judicial.abogados_ids.data[0] if form_judicial.abogados_ids.data else None,
                    nombre_caso=form_judicial.nombre_caso.data,
                    rol_firma=form_judicial.rol_firma.data,
                    
                    # Catálogos y campos dinámicos
                    materia_id=form_judicial.materia_id.data,
                    procedimiento_id=actual_procedimiento_id,
                    prioridad=form_judicial.prioridad.data,
                    nivel_riesgo=form_judicial.nivel_riesgo.data,
                    probabilidad_exito=form_judicial.probabilidad_exito.data,
                    origen_cliente=form_judicial.origen_cliente.data,
                    fecha_contratacion=form_judicial.fecha_contratacion.data,
                    valor_estimado_caso=form_judicial.valor_estimado_caso.data,
                    datos_dinamicos=datos_dinamicos_json,

                    # Compatibilidad antigua (mapeo automático)
                    rama_derecho=materia_obj.nombre if materia_obj else "",
                    sub_categoria=proc_obj.nombre if proc_obj else "",
                    tipo_accion=proc_obj.nombre if proc_obj else "",

                    # Campos específicos judiciales
                    jurisdiccion_actual=form_judicial.jurisdiccion_actual.data,
                    tribunal_asignado=form_judicial.tribunal_asignado.data,
                    numero_expediente_tribunal=form_judicial.numero_expediente_tribunal.data,
                    juez_asignado=form_judicial.juez_asignado.data,
                    nombre_contraparte=form_judicial.nombre_contraparte.data,
                    contacto_contraparte=form_judicial.contacto_contraparte.data,
                    abogado_contraparte=form_judicial.abogado_contraparte.data,
                    contacto_abogado_contraparte=form_judicial.contacto_abogado_contraparte.data,
                    monto_demanda=form_judicial.monto_demanda.data,
                    esquema_cobro=form_judicial.esquema_cobro.data,
                    tarifa_monto=form_judicial.tarifa_monto.data,
                    porcentaje_exito=form_judicial.porcentaje_exito.data,
                    tipo_tramite="Judicial",
                )
                nuevo_caso.abogados = abogados_seleccionados

                try:
                    db.session.add(nuevo_caso)
                    db.session.commit()
                    
                    # Vincular contrato si viene de un presupuesto aceptado
                    contrato_id = request.args.get("contrato_id", type=int)
                    if contrato_id:
                        contrato = ContratoHonorarios.query.get(contrato_id)
                        if contrato:
                            contrato.expediente_id = nuevo_caso.id
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

                # Validar abogados asignados
                if not form_admin.abogados_ids.data:
                    flash("Debe seleccionar al menos un abogado para el trámite.", "danger")
                    return render_template(
                        "expedientes/nuevo.html",
                        form_judicial=form_judicial,
                        form_admin=form_admin,
                    )

                abogados_seleccionados = Usuario.query.filter(Usuario.id.in_(form_admin.abogados_ids.data)).all()

                materia_obj = MateriaLegal.query.get(form_admin.materia_id.data)
                
                # Validar procedimiento condicionalmente
                proc_id = form_admin.procedimiento_id.data
                proc_obj = None
                if materia_obj and materia_obj.requiere_procedimiento:
                    if not proc_id or proc_id == 0:
                        flash("Debe seleccionar un procedimiento para esta materia.", "danger")
                        return render_template(
                            "expedientes/nuevo.html",
                            form_judicial=form_judicial,
                            form_admin=form_admin,
                        )
                    proc_obj = ProcedimientoLegal.query.get(proc_id)
                    actual_procedimiento_id = proc_id
                else:
                    actual_procedimiento_id = None

                # Extraer campos dinámicos
                datos_dinamicos_json = {}
                if proc_obj:
                    campos_definidos = DYNAMIC_FIELDS_BY_PROCEDURE.get(proc_obj.nombre, [])
                    for campo in campos_definidos:
                        field_name = campo["name"]
                        val = request.form.get(field_name)
                        if val is not None:
                            datos_dinamicos_json[field_name] = val

                nuevo_tramite = ExpedienteAdministrativo(
                    codigo_firma=codigo_generado,
                    cliente_id=form_admin.cliente_id.data,
                    abogado_responsable_id=form_admin.abogados_ids.data[0] if form_admin.abogados_ids.data else None,
                    nombre_caso=form_admin.nombre_caso.data,
                    rol_firma=form_admin.rol_firma.data,
                    
                    # Catálogos y campos dinámicos
                    materia_id=form_admin.materia_id.data,
                    procedimiento_id=actual_procedimiento_id,
                    prioridad=form_admin.prioridad.data,
                    nivel_riesgo=form_admin.nivel_riesgo.data,
                    probabilidad_exito=form_admin.probabilidad_exito.data,
                    origen_cliente=form_admin.origen_cliente.data,
                    fecha_contratacion=form_admin.fecha_contratacion.data,
                    valor_estimado_caso=form_admin.valor_estimado_caso.data,
                    datos_dinamicos=datos_dinamicos_json,

                    # Compatibilidad antigua (mapeo automático)
                    tipo_proceso=materia_obj.nombre if materia_obj else "",
                    sub_proceso=proc_obj.nombre if proc_obj else "",

                    # Campos específicos administrativos
                    institucion_encargada=form_admin.institucion_encargada.data,
                    numero_solicitud_oficial=form_admin.numero_solicitud_oficial.data,
                    descripcion_tramite=form_admin.descripcion_tramite.data,
                    monto_tasas_impuestos=form_admin.monto_tasas_impuestos.data,
                    esquema_cobro=form_admin.esquema_cobro.data,
                    tarifa_monto=form_admin.tarifa_monto.data,
                    porcentaje_exito=form_admin.porcentaje_exito.data,
                    tipo_tramite="Administrativo",
                )
                nuevo_tramite.abogados = abogados_seleccionados

                try:
                    db.session.add(nuevo_tramite)
                    db.session.commit()
                    
                    # Vincular contrato si viene de un presupuesto aceptado
                    contrato_id = request.args.get("contrato_id", type=int)
                    if contrato_id:
                        contrato = ContratoHonorarios.query.get(contrato_id)
                        if contrato:
                            contrato.expediente_id = nuevo_tramite.id
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

        # RF-SEG-002: Segregación Interna de Expedientes
        if current_user.rol == "Asociado" and current_user not in exp.abogados:
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("expedientes"))

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
        form.abogados_ids.choices = opciones_abogados

        # Cargar materias del catálogo para el selector según el tipo de expediente
        materias = MateriaLegal.query.filter_by(tipo_expediente=exp.tipo_tramite, activo=True).order_by(MateriaLegal.nombre.asc()).all()
        form.materia_id.choices = [(0, "Seleccione materia...")] + [(m.id, m.nombre) for m in materias]

        # Cargar procedimientos para el selector
        # Si es POST, usar la materia enviada, de lo contrario la guardada en el expediente
        materia_id_seleccionada = request.form.get("materia_id", type=int) if request.method == "POST" else exp.materia_id
        if materia_id_seleccionada:
            procs = ProcedimientoLegal.query.filter_by(materia_id=materia_id_seleccionada, activo=True).order_by(ProcedimientoLegal.nombre.asc()).all()
            form.procedimiento_id.choices = [(0, "Seleccione procedimiento...")] + [(p.id, p.nombre) for p in procs]
        else:
            form.procedimiento_id.choices = [(0, "Seleccione procedimiento...")]

        if request.method == "GET":
            # Pre-poblar los campos
            form.cliente_id.data = exp.cliente_id
            form.abogados_ids.data = [a.id for a in exp.abogados]
            form.nombre_caso.data = exp.nombre_caso
            form.rol_firma.data = exp.rol_firma
            
            # Nuevos Catálogos y generales
            form.materia_id.data = exp.materia_id or 0
            form.procedimiento_id.data = exp.procedimiento_id or 0
            form.prioridad.data = exp.prioridad or 'Media'
            form.nivel_riesgo.data = exp.nivel_riesgo or 'Medio'
            form.probabilidad_exito.data = exp.probabilidad_exito or 'Media'
            form.origen_cliente.data = exp.origen_cliente or 'Cliente Nuevo'
            form.fecha_contratacion.data = exp.fecha_contratacion
            form.valor_estimado_caso.data = exp.valor_estimado_caso or 0.00

            form.esquema_cobro.data = exp.esquema_cobro or "Fijo"
            form.tarifa_monto.data = exp.tarifa_monto or 0.00
            form.porcentaje_exito.data = exp.porcentaje_exito or 0.00

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
            abogados_seleccionados = Usuario.query.filter(Usuario.id.in_(form.abogados_ids.data)).all()
            exp.abogados = abogados_seleccionados
            exp.abogado_responsable_id = form.abogados_ids.data[0] if form.abogados_ids.data else None
            exp.nombre_caso = form.nombre_caso.data.strip()
            exp.rol_firma = form.rol_firma.data
            exp.esquema_cobro = form.esquema_cobro.data
            exp.tarifa_monto = form.tarifa_monto.data
            exp.porcentaje_exito = form.porcentaje_exito.data

            # Actualizar nuevos campos de catálogos y generales
            exp.materia_id = form.materia_id.data
            exp.procedimiento_id = form.procedimiento_id.data
            exp.prioridad = form.prioridad.data
            exp.nivel_riesgo = form.nivel_riesgo.data
            exp.probabilidad_exito = form.probabilidad_exito.data
            exp.origen_cliente = form.origen_cliente.data
            exp.fecha_contratacion = form.fecha_contratacion.data
            exp.valor_estimado_caso = form.valor_estimado_caso.data

            materia_obj = MateriaLegal.query.get(form.materia_id.data)
            
            # Validar procedimiento condicionalmente
            proc_id = form.procedimiento_id.data
            proc_obj = None
            if materia_obj and materia_obj.requiere_procedimiento:
                if not proc_id or proc_id == 0:
                    flash("Debe seleccionar un procedimiento para esta materia.", "danger")
                    return render_template(
                        "expedientes/editar.html",
                        form=form,
                        exp=exp,
                    )
                proc_obj = ProcedimientoLegal.query.get(proc_id)
                exp.procedimiento_id = proc_id
            else:
                exp.procedimiento_id = None

            # Extraer campos dinámicos
            datos_dinamicos_json = {}
            if proc_obj:
                campos_definidos = DYNAMIC_FIELDS_BY_PROCEDURE.get(proc_obj.nombre, [])
                for campo in campos_definidos:
                    field_name = campo["name"]
                    val = request.form.get(field_name)
                    if val is not None:
                        datos_dinamicos_json[field_name] = val
            exp.datos_dinamicos = datos_dinamicos_json

            if exp.tipo_tramite == "Judicial":
                # Compatibilidad antigua (mapeo automático)
                exp.rama_derecho = materia_obj.nombre if materia_obj else ""
                exp.sub_categoria = proc_obj.nombre if proc_obj else ""
                exp.tipo_accion = proc_obj.nombre if proc_obj else ""

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
                # Compatibilidad antigua (mapeo automático)
                exp.tipo_proceso = materia_obj.nombre if materia_obj else ""
                exp.sub_proceso = proc_obj.nombre if proc_obj else ""

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
            flash(
                "Debe especificar una razón para cambiar el estado del expediente.",
                "danger",
            )
            return redirect(url_for("expedientes", id=exp.id))

        tipo_finalizacion = None
        if nuevo_estado == "Finalizado":
            tipo_finalizacion = request.form.get("tipo_finalizacion", "").strip()
            if not tipo_finalizacion:
                flash(
                    "Debe especificar el tipo de finalización del expediente.", "danger"
                )
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
            if nuevo_estado == "Abierto" and estado_anterior in [
                "Finalizado",
                "Archivado",
            ]:
                exp.tipo_finalizacion = None

        try:
            # Notificar al cliente del expediente si tiene usuario vinculado
            if exp.cliente and exp.cliente.usuario_id:
                notif = NotificacionInterna(
                    usuario_id=exp.cliente.usuario_id,
                    mensaje=f"El estado de tu caso '{exp.nombre_caso}' ha cambiado a '{nuevo_estado}'. Razón: {razon}.",
                    leida=False,
                    expediente_id=exp.id,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif)

                # Enviar notificación por correo electrónico
                if exp.cliente.usuario:
                    try:
                        from app.utils import enviar_email_notificacion_cliente

                        enviar_email_notificacion_cliente(
                            usuario=exp.cliente.usuario,
                            subject="Actualización de tu caso - SIGEX",
                            mensaje=f"El estado de tu caso '{exp.nombre_caso}' ha cambiado a '{nuevo_estado}'. Razón: {razon}.",
                        )
                    except Exception as e_mail:
                        print(f"Error al enviar email por cambio de estado: {e_mail}")

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
        if (
            current_user.rol == "Asociado"
            and current_user not in exp.abogados
        ):
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("expedientes", id=exp.id))

        fase = request.form.get("fase_actual", type=int)
        nota = request.form.get("fase_nota", "").strip()

        if fase is not None and (fase < 1 or fase > 5):
            flash("Fase de progreso inválida.", "danger")
            return redirect(url_for("expedientes", id=exp.id))

        fase_anterior = exp.fase_actual or 1

        # Si hay cambio de fase, aplicar validaciones estrictas
        if fase is not None and fase != fase_anterior:
            # 1. Justificación obligatoria
            if not nota:
                flash(
                    "Para cambiar la fase del expediente es obligatorio ingresar una nota de justificación.",
                    "danger",
                )
                return redirect(url_for("expedientes", id=exp.id))

            # 2. Permisos de retroceso (Socio / Administrador)
            if fase < fase_anterior:
                if current_user.rol not in ["Socio", "Administrador"]:
                    flash(
                        "Acceso denegado. Solo un Socio o Administrador puede retroceder un expediente a una fase anterior.",
                        "danger",
                    )
                    return redirect(url_for("expedientes", id=exp.id))

            # 3. Secuencialidad y Tareas pendientes al avanzar
            if fase > fase_anterior:
                if fase != fase_anterior + 1:
                    flash(
                        f"Avance no permitido. Debe cambiar las fases de forma secuencial (siguiente fase: {fase_anterior + 1}).",
                        "danger",
                    )
                    return redirect(url_for("expedientes", id=exp.id))

                # Validar tareas pendientes
                tareas_pendientes = Tarea.query.filter(
                    Tarea.expediente_id == exp.id, Tarea.estado != "Completada"
                ).count()
                if tareas_pendientes > 0:
                    flash(
                        f"No se puede avanzar a la siguiente fase porque el expediente tiene {tareas_pendientes} tareas pendientes de completar.",
                        "danger",
                    )
                    return redirect(url_for("expedientes", id=exp.id))

        if fase is not None:
            exp.fase_actual = fase

        exp.fase_nota = nota if nota else None

        try:
            # Notificar al cliente si tiene usuario vinculado
            if exp.cliente and exp.cliente.usuario_id:
                notif = NotificacionInterna(
                    usuario_id=exp.cliente.usuario_id,
                    mensaje=f"Se ha actualizado el progreso de tu caso '{exp.nombre_caso}' a la fase {fase}. Nota: {nota or 'Sin nota'}.",
                    leida=False,
                    expediente_id=exp.id,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif)

                # Enviar notificación por correo electrónico
                if exp.cliente.usuario:
                    try:
                        from app.utils import enviar_email_notificacion_cliente

                        enviar_email_notificacion_cliente(
                            usuario=exp.cliente.usuario,
                            subject="Actualización de progreso de tu caso - SIGEX",
                            mensaje=f"Se ha actualizado el progreso de tu caso '{exp.nombre_caso}' a la fase {fase}. Nota: {nota or 'Sin nota'}.",
                        )
                    except Exception as e_mail:
                        print(f"Error al enviar email por cambio de fase: {e_mail}")

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
    @roles_permitidos("Administrador", "Socio")
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
            flash(
                "Acceso denegado. No tiene permisos para acceder al gestor documental.",
                "danger",
            )
            return redirect(url_for("dashboard"))

        # Cargar lista de expedientes para el selector
        expedientes_select = []
        if rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if cliente_db:
                expedientes_select = [
                    e for e in cliente_db.expedientes if e.estado != "Archivado"
                ]
        elif rol == "Asociado":
            expedientes_select = (
                Expediente.query.filter(
                    Expediente.estado != "Archivado",
                    Expediente.abogados.any(Usuario.id == current_user.id),
                )
                .order_by(Expediente.nombre_caso.asc())
                .all()
            )
        else:
            expedientes_select = (
                Expediente.query.filter(Expediente.estado != "Archivado")
                .order_by(Expediente.nombre_caso.asc())
                .all()
            )

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
            if (
                expediente_preseleccionado
                and rol == "Asociado"
                and current_user not in expediente_preseleccionado.abogados
            ):
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
            carpetas = (
                Carpeta.query.filter_by(expediente_id=expediente_id)
                .order_by(Carpeta.nombre.asc())
                .all()
            )
            query = Documento.query.filter_by(expediente_id=expediente_id)

            # Filtro por carpeta
            if carpeta_filtro != "" and carpeta_filtro is not None:
                if carpeta_filtro == "0":
                    query = query.filter(Documento.carpeta_id.is_(None))
                else:
                    try:
                        c_id = int(carpeta_filtro)
                        query = query.filter(Documento.carpeta_id == c_id)
                    except ValueError:
                        pass

            if rol == "Cliente":
                cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
                if cliente_db:
                    query = query.filter(Documento.visibilidad == "Compartido").filter(
                        db.or_(
                            Documento.cliente_id.is_(None),
                            Documento.cliente_id == cliente_db.id,
                        )
                    )
                else:
                    query = query.filter(False)

            if q:
                search_pattern = f"%{q}%"
                query = query.join(VersionDocumento).filter(
                    db.or_(
                        VersionDocumento.descripcion.ilike(search_pattern),
                        VersionDocumento.ruta_almacenamiento.ilike(search_pattern),
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
                audit_query = BitacoraAuditoria.query.filter_by(
                    expediente_id=expediente_id
                )

                # Filtros de bitácora
                audit_doc = request.args.get("audit_doc", "").strip()
                audit_action = request.args.get("audit_action", "Todos").strip()
                audit_user = request.args.get("audit_user", "Todos").strip()
                audit_desde = request.args.get("audit_desde", "").strip()
                audit_hasta = request.args.get("audit_hasta", "").strip()

                if audit_doc:
                    audit_query = audit_query.filter(
                        BitacoraAuditoria.detalles_tecnicos.ilike(f"%{audit_doc}%")
                    )
                if audit_action != "Todos":
                    audit_query = audit_query.filter(
                        BitacoraAuditoria.accion_realizada == audit_action
                    )
                if audit_user != "Todos":
                    try:
                        u_id = int(audit_user)
                        audit_query = audit_query.filter(
                            BitacoraAuditoria.usuario_id == u_id
                        )
                    except ValueError:
                        pass
                if audit_desde:
                    try:
                        desde_dt = datetime.strptime(audit_desde, "%Y-%m-%d")
                        audit_query = audit_query.filter(
                            BitacoraAuditoria.fecha_hora >= desde_dt
                        )
                    except ValueError:
                        pass
                if audit_hasta:
                    try:
                        hasta_dt = datetime.strptime(audit_hasta, "%Y-%m-%d")
                        from datetime import timedelta

                        audit_query = audit_query.filter(
                            BitacoraAuditoria.fecha_hora < hasta_dt + timedelta(days=1)
                        )
                    except ValueError:
                        pass

                audit_logs = audit_query.order_by(
                    BitacoraAuditoria.fecha_hora.desc()
                ).all()
                usuarios_audit_select = Usuario.query.order_by(
                    Usuario.nombre.asc()
                ).all()

        # Datos para los selectores del modal de subida (solo para internos)
        clientes_select = []
        tipos_documentos = []

        if rol != "Cliente":
            clientes_select = Cliente.query.order_by(Cliente.nombres.asc()).all()
            tipos_documentos = TipoDocumento.query.order_by(
                TipoDocumento.nombre_tipo.asc()
            ).all()

        # Estadísticas rápidas
        total_docs = len(documentos_lista)
        compartidos_docs = sum(
            1 for d in documentos_lista if d.visibilidad == "Compartido"
        )
        internos_docs = sum(1 for d in documentos_lista if d.visibilidad == "Interno")

        # Conteos no filtrados para el listado de carpetas
        unfiltered_total_docs = 0
        unfiltered_raiz_docs = 0
        if expediente_preseleccionado:
            base_q = Documento.query.filter_by(expediente_id=expediente_id)
            if rol == "Cliente":
                base_q = base_q.filter_by(visibilidad="Compartido")
            unfiltered_total_docs = base_q.count()
            unfiltered_raiz_docs = base_q.filter(Documento.carpeta_id.is_(None)).count()

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
            current_date=datetime.now(),
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
            flash(
                "Extensión de archivo no permitida. Solo se admiten documentos estándar, imágenes y comprimidos.",
                "danger",
            )
            return redirect(url_for("documentos", expediente_id=expediente_id))

        # Validaciones de relaciones
        exp = Expediente.query.get(expediente_id)
        if not exp:
            flash("El expediente seleccionado no existe.", "danger")
            return redirect(url_for("documentos"))

        if (
            current_user.rol == "Asociado"
            and current_user not in exp.abogados
        ):
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
            filepath = os.path.join(
                current_app.config["UPLOAD_FOLDER"], unique_filename
            )

            # Guardar archivo físico
            archivo.save(filepath)
            tamano = os.path.getsize(filepath)

            # Validar carpeta si se seleccionó una
            if carpeta_id:
                carpeta = Carpeta.query.get(carpeta_id)
                if not carpeta or carpeta.expediente_id != expediente_id:
                    flash(
                        "La carpeta seleccionada no es válida para este expediente.",
                        "danger",
                    )
                    return redirect(url_for("documentos", expediente_id=expediente_id))

            # Crear Documento lógico
            nuevo_doc = Documento(
                expediente_id=expediente_id,
                tipo_documento_id=tipo_documento_id,
                visibilidad=visibilidad,
                carpeta_id=carpeta_id if carpeta_id else None,
                cliente_id=compartir_cliente_id
                if (visibilidad == "Compartido" and compartir_cliente_id)
                else None,
            )
            db.session.add(nuevo_doc)
            db.session.flush()  # Para obtener el ID del documento lógico

            # Crear primera VersionDocumento
            nueva_version = VersionDocumento(
                documento_id=nuevo_doc.id,
                usuario_id=current_user.id,
                version_numero="1.0",
                descripcion=descripcion or f"Carga inicial de {sec_filename}",
                tamano_bytes=tamano,
                ruta_almacenamiento=unique_filename,
                es_firmado=False,
            )
            db.session.add(nueva_version)

            # Notificar al cliente si el documento es compartido
            if visibilidad == "Compartido" and exp.cliente and exp.cliente.usuario_id:
                notif = NotificacionInterna(
                    usuario_id=exp.cliente.usuario_id,
                    mensaje=f"Se ha compartido un nuevo documento contigo: '{sec_filename}' en tu expediente '{exp.nombre_caso}'.",
                    leida=False,
                    expediente_id=exp.id,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif)

                # Enviar notificación por correo electrónico
                if exp.cliente.usuario:
                    try:
                        from app.utils import enviar_email_notificacion_cliente

                        enviar_email_notificacion_cliente(
                            usuario=exp.cliente.usuario,
                            subject="Nuevo documento compartido - SIGEX",
                            mensaje=f"Se ha compartido un nuevo documento contigo: '{sec_filename}' en tu expediente '{exp.nombre_caso}'.",
                        )
                    except Exception as e_mail:
                        print(
                            f"Error al enviar email por documento compartido: {e_mail}"
                        )

            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Carga Documento",
                detalles=f"Subió el documento '{sec_filename}' para el expediente '{exp.nombre_caso}'. Visibilidad: {visibilidad}.",
                expediente_id=exp.id,
                cliente_id=exp.cliente_id,
            )

            flash(
                f"Documento '{sec_filename}' subido exitosamente como versión 1.0.",
                "success",
            )
        except Exception as e:
            db.session.rollback()
            flash(f"Error al subir el archivo: {str(e)}", "danger")

        # Mantener los filtros de contexto si existían
        return redirect(url_for("documentos", expediente_id=expediente_id))

    @app.route("/portal/documentos/subir", methods=["POST"])
    @login_required
    @roles_permitidos("Cliente")
    def subir_documento_cliente():
        cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
        if not cliente_db:
            flash("No tienes un perfil de cliente asociado.", "danger")
            return redirect(url_for("dashboard"))

        expediente_id = request.form.get("expediente_id", type=int)
        tipo_documento_id = request.form.get("tipo_documento_id", type=int)
        descripcion = request.form.get("descripcion", "").strip()

        # Validaciones de archivos
        if "archivo" not in request.files:
            flash("No se seleccionó ningún archivo.", "danger")
            return redirect(url_for("dashboard"))

        archivo = request.files["archivo"]
        if archivo.filename == "":
            flash("El nombre de archivo está vacío.", "danger")
            return redirect(url_for("dashboard"))

        if not allowed_file(archivo.filename):
            flash("Extensión de archivo no permitida.", "danger")
            return redirect(url_for("dashboard"))

        # Validar que el expediente pertenezca al cliente y esté activo
        exp = Expediente.query.filter_by(
            id=expediente_id, cliente_id=cliente_db.id
        ).first()
        if not exp:
            flash("Expediente no válido o no asignado a tu usuario.", "danger")
            return redirect(url_for("dashboard"))

        # Validar tipo de documento
        tipo = TipoDocumento.query.get(tipo_documento_id)
        if not tipo:
            flash("El tipo de documento seleccionado no existe.", "danger")
            return redirect(url_for("dashboard"))

        try:
            # Guardar archivo físico
            sec_filename = secure_filename(archivo.filename)
            unique_filename = f"{uuid.uuid4().hex}_{sec_filename}"
            filepath = os.path.join(
                current_app.config["UPLOAD_FOLDER"], unique_filename
            )
            archivo.save(filepath)
            tamano = os.path.getsize(filepath)

            # Crear Documento lógico
            nuevo_doc = Documento(
                expediente_id=expediente_id,
                tipo_documento_id=tipo_documento_id,
                visibilidad="Compartido",
                cliente_id=cliente_db.id,
            )
            db.session.add(nuevo_doc)
            db.session.flush()

            # Crear primera versión
            nueva_version = VersionDocumento(
                documento_id=nuevo_doc.id,
                usuario_id=current_user.id,
                version_numero="1.0",
                descripcion=descripcion
                or f"Cargado por el cliente {cliente_db.nombre_completo}",
                tamano_bytes=tamano,
                ruta_almacenamiento=unique_filename,
                es_firmado=False,
            )
            db.session.add(nueva_version)

            # Notificar a los abogados del caso si están asignados
            for abogado_c in exp.abogados:
                notif = NotificacionInterna(
                    usuario_id=abogado_c.id,
                    mensaje=f"Tu cliente '{cliente_db.nombre_completo}' ha subido un nuevo documento: '{sec_filename}' en el expediente '{exp.nombre_caso}'.",
                    leida=False,
                    expediente_id=exp.id,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif)

                try:
                    from app.utils import enviar_email_notificacion_cliente

                    enviar_email_notificacion_cliente(
                        usuario=abogado_c,
                        subject="Cliente subió documento - SIGEX",
                        mensaje=f"Tu cliente '{cliente_db.nombre_completo}' ha subido un nuevo documento compartido: '{sec_filename}' en el expediente '{exp.nombre_caso}'.",
                    )
                except Exception as e_mail:
                    print(
                        f"Error al notificar al abogado del documento subido: {e_mail}"
                    )

            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Cliente Carga Documento",
                detalles=f"El cliente subió el documento '{sec_filename}' para el expediente '{exp.nombre_caso}'.",
                expediente_id=exp.id,
                cliente_id=cliente_db.id,
            )

            flash(
                f"Documento '{sec_filename}' subido y compartido exitosamente.",
                "success",
            )
        except Exception as e:
            db.session.rollback()
            flash(f"Error al subir el archivo: {str(e)}", "danger")

        return redirect(url_for("dashboard"))

    @app.route("/documentos/<int:documento_id>/nueva_version", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def nueva_version_documento(documento_id):
        doc = Documento.query.get_or_404(documento_id)
        if (
            current_user.rol == "Asociado"
            and current_user not in doc.expediente.abogados
        ):
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
            flash(
                "Extensión de archivo no permitida. Solo se admiten documentos estándar, imágenes y comprimidos.",
                "danger",
            )
            return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        try:
            # Obtener última versión para auto-calcular si no se provee
            ult_version = (
                VersionDocumento.query.filter_by(documento_id=doc.id)
                .order_by(VersionDocumento.fecha_carga.desc())
                .first()
            )
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
            filepath = os.path.join(
                current_app.config["UPLOAD_FOLDER"], unique_filename
            )

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
                es_firmado=False,
            )
            db.session.add(nueva_version)

            # Notificar al cliente si el documento es compartido
            if (
                doc.visibilidad == "Compartido"
                and doc.expediente
                and doc.expediente.cliente
                and doc.expediente.cliente.usuario_id
            ):
                notif = NotificacionInterna(
                    usuario_id=doc.expediente.cliente.usuario_id,
                    mensaje=f"Se ha subido una nueva versión ({version_input}) del documento compartido: '{sec_filename}' en tu expediente '{doc.expediente.nombre_caso}'.",
                    leida=False,
                    expediente_id=doc.expediente_id,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif)

                # Enviar notificación por correo electrónico
                if doc.expediente.cliente.usuario:
                    try:
                        from app.utils import enviar_email_notificacion_cliente

                        enviar_email_notificacion_cliente(
                            usuario=doc.expediente.cliente.usuario,
                            subject="Nueva versión de documento - SIGEX",
                            mensaje=f"Se ha subido una nueva versión ({version_input}) del documento compartido: '{sec_filename}' en tu expediente '{doc.expediente.nombre_caso}'.",
                        )
                    except Exception as e_mail:
                        print(
                            f"Error al enviar email por nueva versión de documento: {e_mail}"
                        )

            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Nueva Versión",
                detalles=f"Subió la versión {version_input} del documento ID {doc.id} ({sec_filename}).",
                expediente_id=doc.expediente_id,
                cliente_id=doc.expediente.cliente_id,
            )

            flash(
                f"Nueva versión {version_input} del documento cargada con éxito.",
                "success",
            )
        except Exception as e:
            db.session.rollback()
            flash(f"Error al subir la versión: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=doc.expediente_id))

    @app.route("/documentos/descargar/<int:version_id>")
    @login_required
    def descargar_documento(version_id):
        version = VersionDocumento.query.get_or_404(version_id)
        doc = version.documento_maestro

        if (
            current_user.rol == "Asociado"
            and current_user not in doc.expediente.abogados
        ):
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))

        # Permisos
        if current_user.rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if not cliente_db or doc.visibilidad != "Compartido":
                flash("No tiene permisos para descargar este documento.", "danger")
                return redirect(url_for("dashboard"))

            tiene_acceso = (doc.expediente.cliente_id == cliente_db.id) or (
                doc.cliente_id == cliente_db.id
            )
            if not tiene_acceso:
                flash("No tiene permisos para descargar este documento.", "danger")
                return redirect(url_for("dashboard"))

        # Verificar si el archivo existe físicamente
        filepath = os.path.join(
            current_app.config["UPLOAD_FOLDER"], version.ruta_almacenamiento
        )
        if not os.path.exists(filepath):
            flash(
                "El archivo físico no se encuentra en el servidor. Puede que haya sido eliminado del almacenamiento local.",
                "danger",
            )
            return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        # Reconstruir nombre de descarga original quitando el UUID prefijo
        orig_filename = (
            version.ruta_almacenamiento.split("_", 1)[-1]
            if "_" in version.ruta_almacenamiento
            else version.ruta_almacenamiento
        )

        # Auditoría
        registrar_auditoria(
            usuario_id=current_user.id,
            accion="Descarga",
            detalles=f"Descargó el documento '{orig_filename}' (versión {version.version_numero}).",
            expediente_id=doc.expediente_id,
            cliente_id=doc.expediente.cliente_id,
        )

        return send_from_directory(
            current_app.config["UPLOAD_FOLDER"],
            version.ruta_almacenamiento,
            as_attachment=True,
            download_name=orig_filename,
        )

    @app.route("/documentos/ver/<int:version_id>")
    @login_required
    def ver_documento(version_id):
        version = VersionDocumento.query.get_or_404(version_id)
        doc = version.documento_maestro

        if (
            current_user.rol == "Asociado"
            and current_user not in doc.expediente.abogados
        ):
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))

        # Permisos
        if current_user.rol == "Cliente":
            cliente_db = Cliente.query.filter_by(usuario_id=current_user.id).first()
            if not cliente_db or doc.visibilidad != "Compartido":
                flash("No tiene permisos para ver este documento.", "danger")
                return redirect(url_for("dashboard"))

            tiene_acceso = (doc.expediente.cliente_id == cliente_db.id) or (
                doc.cliente_id == cliente_db.id
            )
            if not tiene_acceso:
                flash("No tiene permisos para ver este documento.", "danger")
                return redirect(url_for("dashboard"))

        # Verificar si el archivo existe físicamente (vista previa cargada en iframe)
        filepath = os.path.join(
            current_app.config["UPLOAD_FOLDER"], version.ruta_almacenamiento
        )
        if not os.path.exists(filepath):
            return (
                """
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
            """,
                404,
            )

        # Reconstruir nombre de descarga original quitando el UUID prefijo
        orig_filename = (
            version.ruta_almacenamiento.split("_", 1)[-1]
            if "_" in version.ruta_almacenamiento
            else version.ruta_almacenamiento
        )

        # Auditoría
        registrar_auditoria(
            usuario_id=current_user.id,
            accion="Visualización",
            detalles=f"Visualizó el documento '{orig_filename}' (versión {version.version_numero}).",
            expediente_id=doc.expediente_id,
            cliente_id=doc.expediente.cliente_id,
        )

        return send_from_directory(
            current_app.config["UPLOAD_FOLDER"],
            version.ruta_almacenamiento,
            as_attachment=False,
        )

    @app.route("/documentos/<int:documento_id>/cambiar_visibilidad", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def cambiar_visibilidad_documento(documento_id):
        doc = Documento.query.get_or_404(documento_id)
        if (
            current_user.rol == "Asociado"
            and current_user not in doc.expediente.abogados
        ):
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
        doc.cliente_id = (
            compartir_cliente_id
            if (nueva_vis == "Compartido" and compartir_cliente_id)
            else None
        )

        # Notificar al cliente si se cambia a compartido
        if nueva_vis == "Compartido":
            target_cli = None
            if compartir_cliente_id:
                target_cli = Cliente.query.get(compartir_cliente_id)
            elif doc.expediente:
                target_cli = doc.expediente.cliente

            # Obtener nombre original del archivo
            ult_ver = (
                VersionDocumento.query.filter_by(documento_id=doc.id)
                .order_by(VersionDocumento.fecha_carga.desc())
                .first()
            )
            filename = (
                ult_ver.ruta_almacenamiento.split("_", 1)[1]
                if (ult_ver and "_" in ult_ver.ruta_almacenamiento)
                else "documento"
            )

            if target_cli and target_cli.usuario_id:
                notif = NotificacionInterna(
                    usuario_id=target_cli.usuario_id,
                    mensaje=f"Se ha compartido el documento '{filename}' contigo en tu expediente '{doc.expediente.nombre_caso if doc.expediente else 'N/A'}'.",
                    leida=False,
                    expediente_id=doc.expediente_id,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif)

                # Enviar notificación por correo electrónico
                if target_cli.usuario:
                    try:
                        from app.utils import enviar_email_notificacion_cliente

                        enviar_email_notificacion_cliente(
                            usuario=target_cli.usuario,
                            subject="Documento compartido - SIGEX",
                            mensaje=f"Se ha compartido el documento '{filename}' contigo en tu expediente '{doc.expediente.nombre_caso if doc.expediente else 'N/A'}'.",
                        )
                    except Exception as e_mail:
                        print(
                            f"Error al enviar email por cambio de visibilidad a compartido: {e_mail}"
                        )

        try:
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Editar Visibilidad",
                detalles=f"Cambió la visibilidad del documento ID {doc.id} de '{vis_anterior}' a '{nueva_vis}'.",
                expediente_id=doc.expediente_id,
                cliente_id=doc.expediente.cliente_id,
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
        if (
            current_user.rol == "Asociado"
            and current_user not in doc.expediente.abogados
        ):
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
                filepath = os.path.join(
                    current_app.config["UPLOAD_FOLDER"], version.ruta_almacenamiento
                )
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                # Loggear y continuar para evitar atascar la base de datos
                print(
                    f"Error al eliminar archivo físico {version.ruta_almacenamiento}: {str(e)}"
                )

        try:
            db.session.delete(doc)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Eliminar Documento",
                detalles=f"Eliminó permanentemente el documento ID {documento_id}. Razón: {razon}",
                expediente_id=exp_id,
                cliente_id=cli_id,
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
            "documentos/tipologias.html", tipologias=tipologias, usuario=current_user
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
        existente = TipoDocumento.query.filter(
            TipoDocumento.nombre_tipo.ilike(nombre_tipo)
        ).first()
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
                detalles=f"Creó la tipología de documento '{nombre_tipo}'.",
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
            TipoDocumento.nombre_tipo.ilike(nombre_tipo), TipoDocumento.id != tipo_id
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
                detalles=f"Modificó la tipología ID {tipo_id} de '{nombre_anterior}' a '{nombre_tipo}'.",
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
        documentos_asociados = Documento.query.filter_by(
            tipo_documento_id=tipo_id
        ).count()
        if documentos_asociados > 0:
            flash(
                f"No se puede eliminar la tipología '{tipologia.nombre_tipo}' porque tiene {documentos_asociados} documentos asociados.",
                "danger",
            )
            return redirect(url_for("listar_tipologias"))

        nombre_tipo = tipologia.nombre_tipo
        try:
            db.session.delete(tipologia)
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Eliminar Tipología",
                detalles=f"Eliminó la tipología de documento '{nombre_tipo}' (ID {tipo_id}).",
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
        total_docs_en_carpetas = Documento.query.filter(
            Documento.carpeta_id.is_not(None)
        ).count()
        total_docs_sin_carpeta = Documento.query.filter(
            Documento.carpeta_id.is_(None)
        ).count()
        expedientes_con_carpetas = db.session.query(
            db.func.count(db.distinct(Carpeta.expediente_id))
        ).scalar()

        # Expedientes para el selector de filtro
        expedientes_select = (
            Expediente.query.filter(Expediente.estado != "Archivado")
            .order_by(Expediente.nombre_caso.asc())
            .all()
        )

        # Auditorías recientes relacionadas con carpetas
        auditorias_carpetas = (
            BitacoraAuditoria.query.filter(
                db.or_(
                    BitacoraAuditoria.accion_realizada.ilike("%Carpeta%"),
                    BitacoraAuditoria.detalles_tecnicos.ilike("%carpeta%"),
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
            current_date=datetime.now(),
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
        if (
            current_user.rol == "Asociado"
            and current_user not in exp.abogados
        ):
            flash("Acceso denegado. No está asignado a este expediente.", "danger")
            return redirect(url_for("documentos"))

        # Validar duplicados
        existente = Carpeta.query.filter(
            Carpeta.expediente_id == expediente_id, Carpeta.nombre.ilike(nombre)
        ).first()

        if existente:
            flash(
                f"Ya existe una carpeta con el nombre '{nombre}' en este expediente.",
                "danger",
            )
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
                cliente_id=exp.cliente_id,
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
        if (
            current_user.rol == "Asociado"
            and current_user not in carpeta.expediente.abogados
        ):
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
            Carpeta.id != carpeta_id,
        ).first()

        if existente:
            flash(
                f"Ya existe otra carpeta con el nombre '{nombre}' en este expediente.",
                "danger",
            )
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
                cliente_id=carpeta.expediente.cliente_id,
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
                cliente_id=carpeta.expediente.cliente_id,
            )
            flash(
                f"Carpeta '{nombre}' eliminada con éxito. Los documentos contenidos fueron movidos a la raíz.",
                "success",
            )
        except Exception as e:
            db.session.rollback()
            flash(f"Error al eliminar la carpeta: {str(e)}", "danger")

        return redirect(url_for("documentos", expediente_id=expediente_id))

    @app.route("/documentos/<int:documento_id>/mover", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def mover_documento(documento_id):
        doc = Documento.query.get_or_404(documento_id)
        if (
            current_user.rol == "Asociado"
            and current_user not in doc.expediente.abogados
        ):
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
                    flash(
                        "La carpeta seleccionada no pertenece al expediente de este documento.",
                        "danger",
                    )
                    return redirect(
                        url_for("documentos", expediente_id=doc.expediente_id)
                    )
                dest_nombre = carpeta.nombre
            except ValueError:
                flash("Carpeta de destino no válida.", "danger")
                return redirect(url_for("documentos", expediente_id=doc.expediente_id))

        try:
            doc.carpeta_id = c_id
            db.session.commit()

            # Obtener nombre original
            ult_version = doc.versiones[0] if doc.versiones else None
            orig_filename = (
                ult_version.ruta_almacenamiento.split("_", 1)[-1]
                if ult_version and "_" in ult_version.ruta_almacenamiento
                else (ult_version.ruta_almacenamiento if ult_version else "Documento")
            )

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Mover Documento",
                detalles=f"Movió el documento '{orig_filename}' a la carpeta '{dest_nombre}'.",
                expediente_id=doc.expediente_id,
                cliente_id=doc.expediente.cliente_id,
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
            query = query.filter(
                db.or_(
                    Tarea.asignados.any(Usuario.id == current_user.id),
                    ~Tarea.asignados.any(),
                )
            )
        elif filtro_asignado != "Todos":
            if filtro_asignado == "General":
                query = query.filter(~Tarea.asignados.any())
            else:
                try:
                    a_id = int(filtro_asignado)
                    query = query.filter(Tarea.asignados.any(Usuario.id == a_id))
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
            query = query.filter(
                db.or_(
                    Tarea.titulo.ilike(f"%{filtro_q}%"),
                    Tarea.descripcion.ilike(f"%{filtro_q}%"),
                )
            )

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

        tareas = query.order_by(
            Tarea.estado.desc(), Tarea.fecha_limite.asc(), Tarea.prioridad.asc()
        ).all()

        # Datos para los selectores del formulario de creación/edición
        expedientes_list = (
            Expediente.query.filter(Expediente.estado != "Archivado")
            .order_by(Expediente.nombre_caso.asc())
            .all()
        )
        usuarios_list = (
            Usuario.query.filter(Usuario.activo, Usuario.rol != 'Cliente')
            .order_by(Usuario.nombre.asc())
            .all()
        )

        # Instanciar el formulario
        form = TareaForm()
        # Cargar opciones dinámicas (0 representa "Todo el equipo")
        form.expediente_id.choices = [(0, "-- Seleccione un expediente --")] + [
            (e.id, f"{e.nombre_caso} ({e.codigo_firma})") for e in expedientes_list
        ]
        form.asignados_ids.choices = [
            (u.id, u.nombre) for u in usuarios_list
        ]

        # Calcular estadísticas rápidas
        stat_query = Tarea.query
        if current_user.rol in ["Asociado", "Paralegal"]:
            stat_query = stat_query.filter(
                db.or_(
                    Tarea.asignados.any(Usuario.id == current_user.id),
                    ~Tarea.asignados.any(),
                )
            )

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
        stat_vencidas = stat_query.filter(
            Tarea.estado != "Completada", Tarea.fecha_limite < hoy
        ).count()

        # Obtener auditorías relacionadas con movimientos en tareas
        auditorias_tareas = (
            BitacoraAuditoria.query.filter(
                db.or_(
                    BitacoraAuditoria.accion_realizada.ilike("%tarea%"),
                    BitacoraAuditoria.detalles_tecnicos.ilike("%tarea%"),
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
            usuario=current_user,
        )

    @app.route("/tareas/crear", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def crear_tarea():
        form = TareaForm()
        # Cargar opciones para pasar validaciones
        expedientes_list = Expediente.query.filter(
            Expediente.estado != "Archivado"
        ).all()
        usuarios_list = (
            Usuario.query.filter(Usuario.activo, Usuario.rol != 'Cliente')
            .order_by(Usuario.nombre.asc())
            .all()
        )
        form.expediente_id.choices = [(0, "-- Seleccione un expediente --")] + [
            (e.id, e.nombre_caso) for e in expedientes_list
        ]
        form.asignados_ids.choices = [
            (u.id, u.nombre) for u in usuarios_list
        ]

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if form.validate_on_submit():
            exp_id = form.expediente_id.data
            
            abogados_seleccionados = Usuario.query.filter(Usuario.id.in_(form.asignados_ids.data)).all()
            asignado_id = form.asignados_ids.data[0] if form.asignados_ids.data else None

            nueva_tarea = Tarea(
                titulo=form.titulo.data.strip(),
                descripcion=form.descripcion.data.strip()
                if form.descripcion.data
                else None,
                fecha_limite=form.fecha_limite.data,
                prioridad=form.prioridad.data,
                estado=form.estado.data,
                expediente_id=exp_id,
                asignado_a_id=asignado_id,
                creado_por_id=current_user.id,
            )
            nueva_tarea.asignados = abogados_seleccionados
            try:
                db.session.add(nueva_tarea)
                db.session.commit()

                # Auditoría
                nombre_asignado = (
                    ", ".join([u.nombre for u in nueva_tarea.asignados])
                    if nueva_tarea.asignados
                    else "Todo el equipo"
                )
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Creación Tarea",
                    detalles=f"Creó la tarea '{form.titulo.data}' asignada a: {nombre_asignado}.",
                    expediente_id=exp_id,
                    cliente_id=nueva_tarea.expediente.cliente_id,
                )
                msg = f"Tarea '{form.titulo.data}' creada exitosamente."
                if is_ajax:
                    return jsonify({"success": True, "message": msg})
                flash(msg, "success")
            except Exception as e:
                db.session.rollback()
                err_msg = f"Error al guardar la tarea: {str(e)}"
                if is_ajax:
                    return jsonify({"success": False, "errors": [err_msg]})
                flash(err_msg, "danger")
        else:
            errors_list = []
            for field, errors in form.errors.items():
                for error in errors:
                    label = getattr(form, field).label.text
                    errors_list.append(f"Error en {label}: {error}")
            
            if is_ajax:
                return jsonify({"success": False, "errors": errors_list})
            
            for err in errors_list:
                flash(err, "danger")

        return redirect(url_for("listar_tareas"))

    @app.route("/tareas/<int:tarea_id>/editar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def editar_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)

        # Validar permisos
        if (
            current_user.rol in ["Asociado", "Paralegal"]
            and tarea.asignados
            and current_user not in tarea.asignados
        ):
            flash("No tiene permisos para modificar esta tarea.", "danger")
            return redirect(url_for("listar_tareas"))

        form = TareaForm()
        # Cargar opciones para pasar validaciones
        expedientes_list = Expediente.query.filter(
            Expediente.estado != "Archivado"
        ).all()
        usuarios_list = (
            Usuario.query.filter(Usuario.activo, Usuario.rol != 'Cliente')
            .order_by(Usuario.nombre.asc())
            .all()
        )
        form.expediente_id.choices = [(0, "-- Seleccione un expediente --")] + [
            (e.id, e.nombre_caso) for e in expedientes_list
        ]
        form.asignados_ids.choices = [
            (u.id, u.nombre) for u in usuarios_list
        ]

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if form.validate_on_submit():
            exp_id = form.expediente_id.data

            if current_user.rol in ["Asociado", "Paralegal"]:
                # Asociado/Paralegal no pueden reasignar
                abogados_seleccionados = tarea.asignados
                asignado_id = tarea.asignado_a_id
            else:
                abogados_seleccionados = Usuario.query.filter(Usuario.id.in_(form.asignados_ids.data)).all()
                asignado_id = form.asignados_ids.data[0] if form.asignados_ids.data else None

            tarea.titulo = form.titulo.data.strip()
            tarea.descripcion = (
                form.descripcion.data.strip() if form.descripcion.data else None
            )
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
            tarea.asignados = abogados_seleccionados

            try:
                db.session.commit()

                # Auditoría
                nombre_asignado = (
                    ", ".join([u.nombre for u in tarea.asignados])
                    if tarea.asignados
                    else "Todo el equipo"
                )
                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Editar Tarea",
                    detalles=f"Modificó la tarea ID {tarea_id} ('{tarea.titulo}'). Asignado: {nombre_asignado}.",
                    expediente_id=exp_id,
                    cliente_id=tarea.expediente.cliente_id,
                )
                msg = f"Tarea '{tarea.titulo}' modificada con éxito."
                if is_ajax:
                    return jsonify({"success": True, "message": msg})
                flash(msg, "success")
            except Exception as e:
                db.session.rollback()
                err_msg = f"Error al actualizar la tarea: {str(e)}"
                if is_ajax:
                    return jsonify({"success": False, "errors": [err_msg]})
                flash(err_msg, "danger")
        else:
            errors_list = []
            for field, errors in form.errors.items():
                for error in errors:
                    label = getattr(form, field).label.text
                    errors_list.append(f"Error en {label}: {error}")
            
            if is_ajax:
                return jsonify({"success": False, "errors": errors_list})
            
            for err in errors_list:
                flash(err, "danger")

        return redirect(url_for("listar_tareas"))

    @app.route("/tareas/<int:tarea_id>/completar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def completar_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)

        # Validar permisos
        if (
            current_user.rol in ["Asociado", "Paralegal"]
            and tarea.asignados
            and current_user not in tarea.asignados
        ):
            flash("No tiene permisos para modificar esta tarea.", "danger")
            return redirect(url_for("listar_tareas"))

        # Alternar estado
        if tarea.estado == "Completada":
            tarea.estado = "Pendiente"
            tarea.fecha_completada = None
            accion_aud = "Reabrir Tarea"
            detalles_aud = (
                f"Marcó la tarea ID {tarea_id} ('{tarea.titulo}') como Pendiente."
            )
            msg = f"Tarea '{tarea.titulo}' reabierta."
        else:
            tarea.estado = "Completada"
            tarea.fecha_completada = rd_now()
            accion_aud = "Completar Tarea"
            detalles_aud = (
                f"Marcó la tarea ID {tarea_id} ('{tarea.titulo}') como Completada."
            )
            msg = f"Tarea '{tarea.titulo}' completada exitosamente."

        try:
            db.session.commit()

            # Auditoría
            registrar_auditoria(
                usuario_id=current_user.id,
                accion=accion_aud,
                detalles=detalles_aud,
                expediente_id=tarea.expediente_id,
                cliente_id=tarea.expediente.cliente_id if tarea.expediente_id else None,
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
        puede_eliminar = (current_user.rol in ["Socio", "Administrador"]) or (
            tarea.creado_por_id == current_user.id
        )
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
                cliente_id=cli_id,
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
        if (
            current_user.rol in ["Asociado", "Paralegal"]
            and tarea.asignados
            and current_user not in tarea.asignados
        ):
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
                cliente_id=tarea.expediente.cliente_id if tarea.expediente_id else None,
            )
            flash(
                f"Estado de '{tarea.titulo}' cambiado a <strong>{nuevo_estado}</strong>.",
                "success",
            )
        except Exception as e:
            db.session.rollback()
            flash(f"Error al cambiar el estado: {str(e)}", "danger")

        return redirect(url_for("listar_tareas"))

    # === RUTAS DE LA AGENDA ===
    @app.route("/agenda")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda():
        expedientes_select = Expediente.query.filter(
            Expediente.estado == "Abierto"
        ).all()
        usuarios_select = Usuario.query.filter(Usuario.activo, Usuario.rol != "Cliente").order_by(Usuario.nombre.asc()).all()
        return render_template(
            "agenda/index.html",
            expedientes_select=expedientes_select,
            usuarios_select=usuarios_select,
        )

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
                tareas_query = tareas_query.filter(
                    Tarea.fecha_limite >= start_date.date()
                )
            if end_date:
                tareas_query = tareas_query.filter(
                    Tarea.fecha_limite <= end_date.date()
                )

            for t in tareas_query.all():
                is_completed = t.estado == "Completada"
                cat = "tarea-completada" if is_completed else "tarea-pendiente"
                if cat not in categories:
                    continue

                if (
                    current_user.rol == "Asociado"
                    and current_user not in t.expediente.abogados
                ):
                    continue

                events.append(
                    {
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
                            "cliente_id": t.expediente.cliente_id if t.expediente else None,
                            "cliente_nombre": (t.expediente.cliente.nombres + " " + t.expediente.cliente.apellidos) if (t.expediente and t.expediente.cliente) else "",
                            "cliente_cedula": t.expediente.cliente.rnc_cedula if (t.expediente and t.expediente.cliente) else "",
                            "asignado_nombre": ", ".join([u.nombre for u in t.asignados]) if t.asignados else "Todo el equipo",
                            "asignado_id": t.asignado_a_id or 0,
                            "asignados_ids": [u.id for u in t.asignados],
                            "prioridad": t.prioridad,
                            "descripcion": t.descripcion or "",
                            "start": t.fecha_limite.isoformat()
                            if t.fecha_limite
                            else "",
                        },
                    }
                )

        # Audiencias
        if "audiencia" in categories:
            aud_query = AlertaPlazoAudiencia.query.filter_by(es_audiencia=True)
            if start_date:
                aud_query = aud_query.filter(
                    AlertaPlazoAudiencia.fecha_vencimiento >= start_date
                )
            if end_date:
                aud_query = aud_query.filter(
                    AlertaPlazoAudiencia.fecha_vencimiento <= end_date
                )

            for a in aud_query.all():
                if (
                    current_user.rol == "Asociado"
                    and current_user not in a.expediente.abogados
                ):
                    continue

                events.append(
                    {
                        "id": f"audiencia_{a.id}",
                        "title": f"[Audiencia] {a.titulo_hito}",
                        "start": a.fecha_vencimiento.isoformat()
                        if a.fecha_vencimiento
                        else "",
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
                            "cliente_id": a.expediente.cliente_id if a.expediente else None,
                            "cliente_nombre": (a.expediente.cliente.nombres + " " + a.expediente.cliente.apellidos) if (a.expediente and a.expediente.cliente) else "",
                            "cliente_cedula": a.expediente.cliente.rnc_cedula if (a.expediente and a.expediente.cliente) else "",
                            "hora": a.fecha_vencimiento.strftime("%H:%M")
                            if a.fecha_vencimiento
                            else "",
                            "fecha_vencimiento": a.fecha_vencimiento.isoformat()
                            if a.fecha_vencimiento
                            else "",
                        },
                    }
                )

        # Plazos
        if "plazo" in categories:
            plazo_query = AlertaPlazoAudiencia.query.filter_by(es_audiencia=False)
            if start_date:
                plazo_query = plazo_query.filter(
                    AlertaPlazoAudiencia.fecha_vencimiento >= start_date
                )
            if end_date:
                plazo_query = plazo_query.filter(
                    AlertaPlazoAudiencia.fecha_vencimiento <= end_date
                )

            for p in plazo_query.all():
                if (
                    current_user.rol == "Asociado"
                    and current_user not in p.expediente.abogados
                ):
                    continue

                events.append(
                    {
                        "id": f"plazo_{p.id}",
                        "title": f"[Plazo] {p.titulo_hito}",
                        "start": p.fecha_vencimiento.date().isoformat()
                        if p.fecha_vencimiento
                        else "",
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
                            "cliente_id": p.expediente.cliente_id if p.expediente else None,
                            "cliente_nombre": (p.expediente.cliente.nombres + " " + p.expediente.cliente.apellidos) if (p.expediente and p.expediente.cliente) else "",
                            "cliente_cedula": p.expediente.cliente.rnc_cedula if (p.expediente and p.expediente.cliente) else "",
                            "fecha_vencimiento": p.fecha_vencimiento.date().isoformat()
                            if p.fecha_vencimiento
                            else "",
                        },
                    }
                )

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
        asignados_ids = data.get("asignados_ids", [])
        prioridad = data.get("prioridad", "Media")

        if not tipo or not expediente_id or not fecha_str:
            return jsonify({"success": False, "error": "Faltan campos requeridos."})

        expediente = Expediente.query.get_or_404(expediente_id)
        if (
            current_user.rol == "Asociado"
            and current_user not in expediente.abogados
        ):
            return jsonify(
                {
                    "success": False,
                    "error": "Acceso denegado. No está asignado a este expediente.",
                }
            )

        try:
            if tipo == "tarea":
                if not titulo:
                    return jsonify(
                        {
                            "success": False,
                            "error": "El título de la tarea es obligatorio.",
                        }
                    )
                fecha_limite = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                if fecha_limite < rd_now().date():
                    return jsonify({"success": False, "error": "No se pueden programar tareas con fecha anterior al día en curso."})
                abogados_seleccionados = Usuario.query.filter(Usuario.id.in_(asignados_ids)).all()
                asignado_id = asignados_ids[0] if asignados_ids else None

                tarea = Tarea(
                    expediente_id=expediente_id,
                    titulo=titulo,
                    descripcion=descripcion if descripcion else None,
                    fecha_limite=fecha_limite,
                    prioridad=prioridad,
                    estado="Pendiente",
                    asignado_a_id=asignado_id,
                    creado_por_id=current_user.id,
                )
                tarea.asignados = abogados_seleccionados
                db.session.add(tarea)
                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Crear Tarea desde Agenda",
                    detalles=f"Creó la tarea '{titulo}' (ID {tarea.id}) para el expediente '{expediente.nombre_caso}'.",
                    expediente_id=expediente_id,
                    cliente_id=expediente.cliente_id,
                )
                return jsonify(
                    {"success": True, "message": "Tarea creada con éxito en la agenda."}
                )

            elif tipo == "audiencia":
                if not hora_str:
                    return jsonify(
                        {
                            "success": False,
                            "error": "La hora de la audiencia es obligatoria.",
                        }
                    )

                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                if fecha < rd_now().date():
                    return jsonify({"success": False, "error": "No se pueden programar audiencias con fecha anterior al día en curso."})
                hora = datetime.strptime(hora_str, "%H:%M").time()
                fecha_vencimiento = datetime.combine(fecha, hora)

                alerta = AlertaPlazoAudiencia(
                    expediente_id=expediente_id,
                    titulo_hito=f"Audiencia de {expediente.nombre_caso}",
                    fecha_vencimiento=fecha_vencimiento,
                    estado_alerta="Pending",
                    fuente_origen="Firma",
                    es_audiencia=True,
                )
                db.session.add(alerta)

                # Notificar al cliente
                if expediente.cliente and expediente.cliente.usuario_id:
                    notif = NotificacionInterna(
                        usuario_id=expediente.cliente.usuario_id,
                        mensaje=f"Se ha programado una nueva audiencia para tu caso '{expediente.nombre_caso}' el {fecha_vencimiento.strftime('%d/%m/%Y %I:%M %p')}.",
                        leida=False,
                        expediente_id=expediente.id,
                        fecha_creacion=rd_now(),
                    )
                    db.session.add(notif)

                    # Enviar notificación por correo electrónico
                    if expediente.cliente.usuario:
                        try:
                            from app.utils import enviar_email_notificacion_cliente

                            enviar_email_notificacion_cliente(
                                usuario=expediente.cliente.usuario,
                                subject="Nueva audiencia programada - SIGEX",
                                mensaje=f"Se ha programado una nueva audiencia para tu caso '{expediente.nombre_caso}' el {fecha_vencimiento.strftime('%d/%m/%Y %I:%M %p')}.",
                            )
                        except Exception as e_mail:
                            print(
                                f"Error al enviar email por nueva audiencia: {e_mail}"
                            )

                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Crear Audiencia desde Agenda",
                    detalles=f"Creó la audiencia ID {alerta.id} para el expediente '{expediente.nombre_caso}' programada para el {fecha_vencimiento.strftime('%d/%m/%Y %H:%M')}.",
                    expediente_id=expediente_id,
                    cliente_id=expediente.cliente_id,
                )
                return jsonify(
                    {
                        "success": True,
                        "message": "Audiencia programada con éxito en la agenda.",
                    }
                )

            elif tipo == "plazo":
                if not titulo:
                    return jsonify(
                        {
                            "success": False,
                            "error": "El título del plazo es obligatorio.",
                        }
                    )

                fecha_venc = datetime.strptime(fecha_str, "%Y-%m-%d")
                if fecha_venc.date() < rd_now().date():
                    return jsonify({"success": False, "error": "No se pueden programar plazos con fecha anterior al día en curso."})

                alerta = AlertaPlazoAudiencia(
                    expediente_id=expediente_id,
                    titulo_hito=titulo,
                    fecha_vencimiento=fecha_venc,
                    estado_alerta="Pending",
                    fuente_origen="Firma",
                    es_audiencia=False,
                )
                db.session.add(alerta)

                # Notificar al cliente
                if expediente.cliente and expediente.cliente.usuario_id:
                    notif = NotificacionInterna(
                        usuario_id=expediente.cliente.usuario_id,
                        mensaje=f"Se ha registrado una nueva actividad/plazo para tu caso '{expediente.nombre_caso}' con vencimiento el {fecha_venc.strftime('%d/%m/%Y')}.",
                        leida=False,
                        expediente_id=expediente.id,
                        fecha_creacion=rd_now(),
                    )
                    db.session.add(notif)

                    # Enviar notificación por correo electrónico
                    if expediente.cliente.usuario:
                        try:
                            from app.utils import enviar_email_notificacion_cliente

                            enviar_email_notificacion_cliente(
                                usuario=expediente.cliente.usuario,
                                subject="Nueva actividad/plazo registrado - SIGEX",
                                mensaje=f"Se ha registrado una nueva actividad/plazo para tu caso '{expediente.nombre_caso}' con vencimiento el {fecha_venc.strftime('%d/%m/%Y')}.",
                            )
                        except Exception as e_mail:
                            print(f"Error al enviar email por nuevo plazo: {e_mail}")

                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Crear Plazo desde Agenda",
                    detalles=f"Creó el plazo '{titulo}' (ID {alerta.id}) para el expediente '{expediente.nombre_caso}' con vencimiento el {fecha_venc.strftime('%d/%m/%Y')}.",
                    expediente_id=expediente_id,
                    cliente_id=expediente.cliente_id,
                )
                return jsonify(
                    {
                        "success": True,
                        "message": "Plazo registrado con éxito en la agenda.",
                    }
                )

            else:
                return jsonify({"success": False, "error": "Tipo de evento inválido."})

        except Exception as e:
            db.session.rollback()
            return jsonify(
                {"success": False, "error": f"Error de base de datos: {str(e)}"}
            )

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
        asignados_ids = data.get("asignados_ids", [])
        prioridad = data.get("prioridad", "Media")

        if not fecha_str:
            return jsonify({"success": False, "error": "La fecha es obligatoria."})

        try:
            if tipo == "tarea-pendiente" or tipo == "tarea-completada":
                tarea = Tarea.query.get_or_404(evento_id)
                if (
                    current_user.rol == "Asociado"
                    and current_user not in tarea.expediente.abogados
                ):
                    return jsonify(
                        {
                            "success": False,
                            "error": "Acceso denegado. No está asignado a este expediente.",
                        }
                    )

                if not titulo:
                    return jsonify(
                        {
                            "success": False,
                            "error": "El título de la tarea es obligatorio.",
                        }
                    )

                fecha_limite = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                if fecha_limite < rd_now().date():
                    return jsonify({"success": False, "error": "No se pueden programar tareas con fecha anterior al día en curso."})
                abogados_seleccionados = Usuario.query.filter(Usuario.id.in_(asignados_ids)).all()
                asignado_id = asignados_ids[0] if asignados_ids else None

                cambios = []
                if tarea.titulo != titulo:
                    cambios.append(f"título: '{tarea.titulo}' -> '{titulo}'")
                    tarea.titulo = titulo
                if (tarea.descripcion or "") != descripcion:
                    cambios.append(
                        f"descripción: '{tarea.descripcion}' -> '{descripcion}'"
                    )
                    tarea.descripcion = descripcion if descripcion else None
                if tarea.fecha_limite != fecha_limite:
                    cambios.append(
                        f"fecha límite: '{tarea.fecha_limite}' -> '{fecha_limite}'"
                    )
                    tarea.fecha_limite = fecha_limite
                if tarea.prioridad != prioridad:
                    cambios.append(f"prioridad: '{tarea.prioridad}' -> '{prioridad}'")
                    tarea.prioridad = prioridad

                set_actual = {u.id for u in tarea.asignados}
                set_nuevo = set(asignados_ids)
                if set_actual != set_nuevo:
                    anterior_nom = ", ".join([u.nombre for u in tarea.asignados]) if tarea.asignados else "Todo el equipo"
                    tarea.asignados = abogados_seleccionados
                    tarea.asignado_a_id = asignado_id
                    db.session.flush()
                    nuevo_nom = ", ".join([u.nombre for u in tarea.asignados]) if tarea.asignados else "Todo el equipo"
                    cambios.append(f"asignados: '{anterior_nom}' -> '{nuevo_nom}'")

                if cambios:
                    db.session.commit()
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Editar Tarea desde Agenda",
                        detalles=f"Editó la tarea ID {evento_id} ('{tarea.titulo}'). Cambios: {', '.join(cambios)}.",
                        expediente_id=tarea.expediente_id,
                        cliente_id=tarea.expediente.cliente_id,
                    )
                return jsonify(
                    {"success": True, "message": "Tarea modificada con éxito."}
                )

            elif tipo == "audiencia":
                audiencia = AlertaPlazoAudiencia.query.get_or_404(evento_id)
                if (
                    current_user.rol == "Asociado"
                    and current_user not in audiencia.expediente.abogados
                ):
                    return jsonify(
                        {
                            "success": False,
                            "error": "Acceso denegado. No está asignado a este expediente.",
                        }
                    )

                if not hora_str:
                    return jsonify(
                        {
                            "success": False,
                            "error": "La hora de la audiencia es obligatoria.",
                        }
                    )

                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                if fecha < rd_now().date():
                    return jsonify({"success": False, "error": "No se pueden programar audiencias con fecha anterior al día en curso."})
                hora = datetime.strptime(hora_str, "%H:%M").time()
                fecha_vencimiento = datetime.combine(fecha, hora)

                cambios = []
                if audiencia.fecha_vencimiento != fecha_vencimiento:
                    cambios.append(
                        f"fecha/hora: '{audiencia.fecha_vencimiento}' -> '{fecha_vencimiento}'"
                    )
                    audiencia.fecha_vencimiento = fecha_vencimiento

                if cambios:
                    db.session.commit()
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Editar Audiencia desde Agenda",
                        detalles=f"Modificó la fecha/hora de la audiencia ID {evento_id} para el caso '{audiencia.expediente.nombre_caso}'. Cambios: {', '.join(cambios)}.",
                        expediente_id=audiencia.expediente_id,
                        cliente_id=audiencia.expediente.cliente_id,
                    )
                return jsonify(
                    {
                        "success": True,
                        "message": "Audiencia judicial modificada con éxito.",
                    }
                )

            elif tipo == "plazo":
                plazo = AlertaPlazoAudiencia.query.get_or_404(evento_id)
                if (
                    current_user.rol == "Asociado"
                    and current_user not in plazo.expediente.abogados
                ):
                    return jsonify(
                        {
                            "success": False,
                            "error": "Acceso denegado. No está asignado a este expediente.",
                        }
                    )

                if not titulo:
                    return jsonify(
                        {
                            "success": False,
                            "error": "El título del plazo es obligatorio.",
                        }
                    )

                fecha_venc = datetime.strptime(fecha_str, "%Y-%m-%d")
                if fecha_venc.date() < rd_now().date():
                    return jsonify({"success": False, "error": "No se pueden programar plazos con fecha anterior al día en curso."})

                cambios = []
                if plazo.titulo_hito != titulo:
                    cambios.append(f"título: '{plazo.titulo_hito}' -> '{titulo}'")
                    plazo.titulo_hito = titulo
                if plazo.fecha_vencimiento != fecha_venc:
                    cambios.append(
                        f"vencimiento: '{plazo.fecha_vencimiento}' -> '{fecha_venc}'"
                    )
                    plazo.fecha_vencimiento = fecha_venc

                if cambios:
                    db.session.commit()
                    registrar_auditoria(
                        usuario_id=current_user.id,
                        accion="Editar Plazo desde Agenda",
                        detalles=f"Modificó el plazo administrativo ID {evento_id} ('{plazo.titulo_hito}'). Cambios: {', '.join(cambios)}.",
                        expediente_id=plazo.expediente_id,
                        cliente_id=plazo.expediente.cliente_id,
                    )
                return jsonify(
                    {
                        "success": True,
                        "message": "Plazo administrativo modificado con éxito.",
                    }
                )

            else:
                return jsonify({"success": False, "error": "Tipo de evento inválido."})

        except Exception as e:
            db.session.rollback()
            return jsonify(
                {"success": False, "error": f"Error al modificar el evento: {str(e)}"}
            )

    @app.route(
        "/agenda/evento/<string:tipo>/<int:evento_id>/eliminar", methods=["POST"]
    )
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda_eliminar_evento(tipo, evento_id):
        data = request.get_json() or {}
        justificacion = data.get("justificacion", "").strip()

        if not justificacion:
            return jsonify(
                {
                    "success": False,
                    "error": "La justificación de la eliminación es obligatoria.",
                }
            )

        try:
            if tipo == "tarea-pendiente" or tipo == "tarea-completada":
                tarea = Tarea.query.get_or_404(evento_id)
                if (
                    current_user.rol == "Asociado"
                    and current_user not in tarea.expediente.abogados
                ):
                    return jsonify(
                        {
                            "success": False,
                            "error": "Acceso denegado. No está asignado a este expediente.",
                        }
                    )

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
                    cliente_id=cliente_id,
                )
                return jsonify(
                    {
                        "success": True,
                        "message": "Tarea eliminada con éxito de la agenda.",
                    }
                )

            elif tipo == "audiencia" or tipo == "plazo":
                alerta = AlertaPlazoAudiencia.query.get_or_404(evento_id)
                if (
                    current_user.rol == "Asociado"
                    and current_user not in alerta.expediente.abogados
                ):
                    return jsonify(
                        {
                            "success": False,
                            "error": "Acceso denegado. No está asignado a este expediente.",
                        }
                    )

                titulo = alerta.titulo_hito
                exp_id = alerta.expediente_id
                cliente_id = alerta.expediente.cliente_id if alerta.expediente else None
                es_aud = alerta.es_audiencia

                db.session.delete(alerta)
                db.session.commit()

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="Eliminar Audiencia desde Agenda"
                    if es_aud
                    else "Eliminar Plazo desde Agenda",
                    detalles=f"Eliminó la {'audiencia' if es_aud else 'alerta de plazo'} ID {evento_id} ('{titulo}'). Justificación: {justificacion}",
                    expediente_id=exp_id,
                    cliente_id=cliente_id,
                )
                return jsonify(
                    {
                        "success": True,
                        "message": f"{'Audiencia' if es_aud else 'Plazo'} eliminado con éxito de la agenda.",
                    }
                )

            else:
                return jsonify({"success": False, "error": "Tipo de evento inválido."})

        except Exception as e:
            db.session.rollback()
            return jsonify(
                {"success": False, "error": f"Error al eliminar el evento: {str(e)}"}
            )

    @app.route("/agenda/evento/tarea/<int:tarea_id>/completar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def agenda_completar_tarea(tarea_id):
        tarea = Tarea.query.get_or_404(tarea_id)
        if (
            current_user.rol == "Asociado"
            and current_user not in tarea.expediente.abogados
        ):
            return jsonify(
                {
                    "success": False,
                    "error": "Acceso denegado. No está asignado a este expediente.",
                }
            )

        tarea.estado = "Completada"
        tarea.fecha_completada = datetime.now()
        try:
            db.session.commit()
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="Completar Tarea desde Agenda",
                detalles=f"Marcó como completada la tarea '{tarea.titulo}' (ID {tarea_id}).",
                expediente_id=tarea.expediente_id,
                cliente_id=tarea.expediente.cliente_id if tarea.expediente else None,
            )
            return jsonify(
                {
                    "success": True,
                    "message": f"Tarea '{tarea.titulo}' marcada como completada.",
                }
            )
        except Exception as e:
            db.session.rollback()
            return jsonify(
                {"success": False, "error": f"Error al actualizar la tarea: {str(e)}"}
            )

    # === RUTAS DE NOTIFICACIONES ===
    @app.context_processor
    def inject_notificaciones():
        if current_user.is_authenticated:
            try:
                from app.models import NotificacionInterna

                unreads_count = NotificacionInterna.query.filter_by(
                    usuario_id=current_user.id, leida=False
                ).count()
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
            return jsonify(
                {
                    "success": True,
                    "message": "Procesamiento de alertas ejecutado con éxito.",
                }
            )
        except Exception as e:
            return jsonify(
                {"success": False, "error": f"Error al procesar alertas: {str(e)}"}
            )

    @app.route("/notificaciones")
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador", "Cliente")
    def ver_notificaciones():
        notificaciones = (
            NotificacionInterna.query.filter_by(usuario_id=current_user.id)
            .order_by(NotificacionInterna.fecha_creacion.desc())
            .all()
        )
        return render_template(
            "notificaciones/index.html",
            notificaciones=notificaciones,
            current_date=rd_now(),
        )

    @app.route("/notificaciones/<int:notificacion_id>/leer", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador", "Cliente")
    def marcar_notificacion_leida(notificacion_id):
        notif = NotificacionInterna.query.filter_by(
            id=notificacion_id, usuario_id=current_user.id
        ).first_or_404()
        notif.leida = True
        try:
            db.session.commit()
            return jsonify(
                {"success": True, "message": "Notificación marcada como leída."}
            )
        except Exception as e:
            db.session.rollback()
            return jsonify(
                {"success": False, "error": f"Error al marcar como leída: {str(e)}"}
            )

    @app.route("/notificaciones/leer_todas", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador", "Cliente")
    def marcar_todas_notificaciones_leidas():
        notifs = NotificacionInterna.query.filter_by(
            usuario_id=current_user.id, leida=False
        ).all()
        for notif in notifs:
            notif.leida = True
        try:
            db.session.commit()
            return jsonify(
                {
                    "success": True,
                    "message": "Todas las notificaciones marcadas como leídas.",
                }
            )
        except Exception as e:
            db.session.rollback()
            return jsonify(
                {
                    "success": False,
                    "error": f"Error al actualizar notificaciones: {str(e)}",
                }
            )

    @app.route("/facturas/nueva", methods=["GET", "POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador", "Asociado")
    def crear_factura():
        if request.method == "POST":
            cliente_id = request.form.get("cliente_id")
            expediente_id = request.form.get("expediente_id") or None
            ncf = request.form.get("ncf") or None
            tipo_comprobante = request.form.get("tipo_comprobante")
            fecha_emision_str = request.form.get("fecha_emision")
            plazo_pago_dias_str = request.form.get("plazo_pago_dias")
            tasa_mora_mensual_str = request.form.get("tasa_mora_mensual")

            servicios_desc = request.form.getlist("servicio_descripcion[]")
            servicios_cant = request.form.getlist("servicio_cantidad[]")
            servicios_precio = request.form.getlist("servicio_precio[]")

            partidas_desc = request.form.getlist("partida_descripcion[]")
            partidas_monto = request.form.getlist("partida_monto[]")
            partidas_fecha = request.form.getlist("partida_fecha[]")

            if not cliente_id or not tipo_comprobante or not fecha_emision_str:
                flash("Por favor complete los campos obligatorios.", "danger")
                return redirect(url_for("crear_factura"))

            # Validar que el cliente tenga expedientes y que el expediente seleccionado sea válido y le pertenezca
            expedientes_count = Expediente.query.filter_by(cliente_id=int(cliente_id)).count()
            if expedientes_count == 0:
                flash("No se puede emitir una factura para un cliente que no tiene expedientes asociados.", "danger")
                return redirect(url_for("crear_factura"))

            if not expediente_id:
                flash("Debe seleccionar un expediente asociado para emitir la factura.", "danger")
                return redirect(url_for("crear_factura"))

            expediente_valido = Expediente.query.filter_by(id=int(expediente_id), cliente_id=int(cliente_id)).first()
            if not expediente_valido:
                flash("El expediente seleccionado no es válido o no pertenece al cliente.", "danger")
                return redirect(url_for("crear_factura"))

            # Evitar facturar el mismo expediente más de una vez
            factura_existente = FacturaHonorario.query.filter_by(
                expediente_id=int(expediente_id)
            ).filter(FacturaHonorario.estado_pago != 'Anulado').first()
            if factura_existente:
                flash(f"El expediente seleccionado ya tiene una factura activa registrada (Factura #{factura_existente.id}). No se puede facturar más de una vez.", "danger")
                return redirect(url_for("crear_factura"))

            try:
                fecha_emision = datetime.strptime(fecha_emision_str, "%Y-%m-%d")
            except ValueError:
                fecha_emision = rd_now()

            if not ncf or not ncf.strip():
                # Auto-generar NCF según tipo_comprobante
                last_invoice = FacturaHonorario.query.filter(
                    FacturaHonorario.tipo_comprobante == tipo_comprobante,
                    FacturaHonorario.ncf.like(f"B{tipo_comprobante}%")
                ).order_by(FacturaHonorario.id.desc()).first()
                
                if last_invoice and last_invoice.ncf and len(last_invoice.ncf) > 3:
                    try:
                        suffix = last_invoice.ncf[3:]
                        next_num = int(suffix) + 1
                        pad_len = len(suffix)
                        ncf = f"B{tipo_comprobante}{next_num:0{pad_len}d}"
                    except ValueError:
                        ncf = f"B{tipo_comprobante}00000001"
                else:
                    ncf = f"B{tipo_comprobante}00000001"
            else:
                ncf = ncf.strip().upper()
                existing_invoice = FacturaHonorario.query.filter_by(ncf=ncf).first()
                if existing_invoice:
                    flash(f"El NCF '{ncf}' ya está registrado en la factura #{existing_invoice.id}. Por favor, verifique o ingrese uno nuevo.", "danger")
                    return redirect(url_for("crear_factura"))

            try:
                plazo_pago_dias = int(plazo_pago_dias_str)
            except (ValueError, TypeError):
                plazo_pago_dias = 30

            try:
                tasa_mora_mensual = float(tasa_mora_mensual_str)
            except (ValueError, TypeError):
                tasa_mora_mensual = 0.00

            subtotal_calculado = 0
            detalles_to_save = []

            for i in range(len(servicios_desc)):
                desc = servicios_desc[i].strip()
                if not desc:
                    continue
                try:
                    cant = int(servicios_cant[i])
                    precio = float(servicios_precio[i])
                    # RF-INT-001: Validación de Datos Monetarios
                    if cant <= 0 or precio < 0:
                        flash("Las cantidades de servicios deben ser mayores a cero y los precios no pueden ser negativos.", "danger")
                        return redirect(url_for("crear_factura"))
                    if round(precio, 2) != precio:
                        flash("El precio unitario no puede tener más de dos decimales.", "danger")
                        return redirect(url_for("crear_factura"))
                except (ValueError, TypeError):
                    continue
                sub_item = cant * precio
                subtotal_calculado += sub_item
                detalles_to_save.append({
                    "descripcion": desc,
                    "cantidad": cant,
                    "precio_unitario": precio,
                    "subtotal": sub_item
                })

            itbis_calculado = subtotal_calculado * 0.18
            total_calculado = subtotal_calculado + itbis_calculado

            partidas_to_save = []
            suma_partidas = 0
            for i in range(len(partidas_desc)):
                p_desc = partidas_desc[i].strip()
                if not p_desc:
                    continue
                try:
                    p_monto = float(partidas_monto[i])
                    p_fecha = datetime.strptime(partidas_fecha[i], "%Y-%m-%d").date()
                    # RF-INT-001: Validación de Datos Monetarios
                    if p_monto <= 0:
                        flash("El monto de cada cuota debe ser mayor a cero.", "danger")
                        return redirect(url_for("crear_factura"))
                    if round(p_monto, 2) != p_monto:
                        flash("El monto de la cuota no puede tener más de dos decimales.", "danger")
                        return redirect(url_for("crear_factura"))
                except (ValueError, TypeError):
                    continue

                suma_partidas += p_monto
                partidas_to_save.append({
                    "descripcion_partida": p_desc,
                    "monto": p_monto,
                    "fecha_vencimiento": p_fecha
                })

            if abs(suma_partidas - total_calculado) > 0.05:
                flash(f"La suma de las partidas (RD$ {suma_partidas:,.2f}) debe ser exactamente igual al total de la factura (RD$ {total_calculado:,.2f}).", "danger")
                return redirect(url_for("crear_factura"))

            try:
                factura = FacturaHonorario(
                    cliente_id=int(cliente_id),
                    expediente_id=int(expediente_id) if expediente_id else None,
                    ncf=ncf,
                    tipo_comprobante=tipo_comprobante,
                    monto_subtotal=subtotal_calculado,
                    monto_itbis=itbis_calculado,
                    monto_total=total_calculado,
                    fecha_emision=fecha_emision,
                    estado_pago="Pendiente",
                    plazo_pago_dias=plazo_pago_dias,
                    tasa_mora_mensual=tasa_mora_mensual
                )
                db.session.add(factura)
                db.session.flush()

                for d in detalles_to_save:
                    detalle = DetalleFactura(
                        factura_id=factura.id,
                        descripcion=d["descripcion"],
                        cantidad=d["cantidad"],
                        precio_unitario=d["precio_unitario"],
                        subtotal=d["subtotal"]
                    )
                    db.session.add(detalle)

                for p in partidas_to_save:
                    partida = PartidaPagoFactura(
                        factura_id=factura.id,
                        descripcion_partida=p["descripcion_partida"],
                        monto=p["monto"],
                        fecha_vencimiento=p["fecha_vencimiento"],
                        estado_pago="Pendiente"
                    )
                    db.session.add(partida)

                # Si viene de facturación por lotes, marcar tiempos como Facturado
                time_ids_str = request.form.get("prefilled_time_ids", "")
                if time_ids_str:
                    time_ids = [int(x) for x in time_ids_str.split(",") if x.isdigit()]
                    tiempos_facturados = BitacoraTiempoTarea.query.filter(
                        BitacoraTiempoTarea.id.in_(time_ids)
                    ).all()
                    for t in tiempos_facturados:
                        t.estado_cierre = 'Facturado'

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="CREACION_FACTURA",
                    detalles=f"Se creó la factura NCF {ncf or 'N/A'} por un total de RD$ {total_calculado:,.2f} con {len(partidas_to_save)} cuotas.",
                    cliente_id=int(cliente_id),
                    expediente_id=int(expediente_id) if expediente_id else None
                )

                db.session.commit()
                
                from markupsafe import Markup
                pdf_url = url_for("descargar_factura_pdf", factura_id=factura.id)
                flash(Markup(f"Factura e Hitos de Pago guardados correctamente. <a href='{pdf_url}' target='_blank' class='alert-link fw-bold'><i class='bi bi-file-pdf'></i> Descargar PDF Factura</a>"), "success")
                return redirect(url_for("listar_facturas"))
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar la factura: {str(e)}", "danger")
                return redirect(url_for("crear_factura"))

        # Prefilling logic for Lotes in GET request
        clientes = Cliente.query.all()
        lote_cliente_id = request.args.get("lote_cliente_id", type=int)
        expediente_id_arg = request.args.get("expediente_id", type=int)
        prefilled_services = []
        prefilled_time_ids = ""
        prefilled_expediente_id = None
        
        if expediente_id_arg:
            exp = Expediente.query.get(expediente_id_arg)
            if exp:
                prefilled_expediente_id = exp.id
                lote_cliente_id = exp.cliente_id
                
                # Check billing scheme
                if exp.esquema_cobro == 'Fijo':
                    prefilled_services.append({
                        "descripcion": f"Honorarios profesionales cerrados - Expediente {exp.nombre_caso} (Ref: {exp.codigo_firma})",
                        "cantidad": 1,
                        "precio": float(exp.tarifa_monto or 0.00)
                    })
                elif exp.esquema_cobro == 'Iguala':
                    prefilled_services.append({
                        "descripcion": f"Iguala mensual de asesoría jurídica - Expediente {exp.nombre_caso} (Ref: {exp.codigo_firma})",
                        "cantidad": 1,
                        "precio": float(exp.tarifa_monto or 0.00)
                    })
                elif exp.esquema_cobro == 'Contingencia':
                    prefilled_services.append({
                        "descripcion": f"Honorarios de éxito / Contingencia ({exp.porcentaje_exito or 0}%) - Expediente {exp.nombre_caso} (Ref: {exp.codigo_firma})",
                        "cantidad": 1,
                        "precio": float(exp.tarifa_monto or 0.00)
                    })
                elif exp.esquema_cobro == 'Por Hora':
                    # Load approved times for this case
                    tiempos = BitacoraTiempoTarea.query.filter_by(
                        expediente_id=exp.id,
                        estado_cierre='Aprobado'
                    ).all()
                    for t in tiempos:
                        prefilled_services.append({
                            "descripcion": f"{t.descripcion_gestion} (Horas: {t.horas_trabajadas}) (Ref: {exp.codigo_firma})",
                            "cantidad": 1,
                            "precio": float(t.horas_trabajadas) * float(exp.tarifa_monto or 5000.00)
                        })
                    prefilled_time_ids = ",".join(str(t.id) for t in tiempos)
        elif lote_cliente_id:
            time_ids_str = request.args.get("t_ids", "")
            if time_ids_str:
                time_ids = [int(x) for x in time_ids_str.split(",") if x.isdigit()]
                tiempos = BitacoraTiempoTarea.query.filter(
                    BitacoraTiempoTarea.id.in_(time_ids),
                    BitacoraTiempoTarea.estado_cierre == 'Aprobado'
                ).all()
                
                if tiempos:
                    prefilled_expediente_id = tiempos[0].expediente_id
                    
                for t in tiempos:
                    prefilled_services.append({
                        "descripcion": f"{t.descripcion_gestion} (Horas: {t.horas_trabajadas}) (Ref: {t.expediente.codigo_firma})",
                        "cantidad": 1,
                        "precio": float(t.horas_trabajadas) * (float(t.expediente.tarifa_monto) if t.expediente.esquema_cobro == 'Por Hora' and t.expediente.tarifa_monto else 5000.00)
                    })
                prefilled_time_ids = ",".join(str(t.id) for t in tiempos)
                
        return render_template(
            "facturas/crear_factura.html",
            clientes=clientes,
            current_date=rd_now().strftime("%Y-%m-%d"),
            lote_cliente_id=lote_cliente_id,
            prefilled_services=prefilled_services,
            prefilled_time_ids=prefilled_time_ids,
            prefilled_expediente_id=prefilled_expediente_id
        )

    @app.route("/tiempos/<int:tiempo_id>/aprobar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def aprobar_tiempo_tarea(tiempo_id):
        tiempo = BitacoraTiempoTarea.query.get_or_404(tiempo_id)
        if tiempo.estado_cierre != 'Abierto':
            return jsonify({"success": False, "error": "Este registro de tiempo no está pendiente de aprobación."})
        
        try:
            tiempo.estado_cierre = 'Aprobado'
            registrar_auditoria(
                usuario_id=current_user.id,
                accion="APROBACION_TIEMPO",
                detalles=f"Aprobó el registro de tiempo ID {tiempo.id} ({tiempo.horas_trabajadas} horas) para el expediente '{tiempo.expediente.nombre_caso}'.",
                cliente_id=tiempo.expediente.cliente_id,
                expediente_id=tiempo.expediente_id
            )
            db.session.commit()
            return jsonify({"success": True, "message": "Registro de tiempo aprobado con éxito."})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)})

    @app.route("/facturas/lotes", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def facturacion_lotes():
        # Find all BitacoraTiempoTarea with estado_cierre == 'Aprobado'
        tiempos = BitacoraTiempoTarea.query.filter_by(estado_cierre='Aprobado').all()
        
        # Group by client
        grouped_data = {}
        for t in tiempos:
            cliente = t.expediente.cliente
            if not cliente:
                continue
            if cliente.id not in grouped_data:
                grouped_data[cliente.id] = {
                    "cliente": cliente,
                    "horas_totales": 0,
                    "registros": []
                }
            grouped_data[cliente.id]["horas_totales"] += float(t.horas_trabajadas)
            grouped_data[cliente.id]["registros"].append(t)
            
        return render_template("facturas/lotes.html", lotes=grouped_data.values())

    @app.route("/facturas/<int:factura_id>/editar", methods=["GET", "POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def editar_factura(factura_id):
        factura = FacturaHonorario.query.get_or_404(factura_id)
        if request.method == "POST":
            cliente_id = request.form.get("cliente_id")
            expediente_id = request.form.get("expediente_id") or None
            tipo_comprobante = request.form.get("tipo_comprobante")
            fecha_emision_str = request.form.get("fecha_emision")
            plazo_pago_dias_str = request.form.get("plazo_pago_dias")
            tasa_mora_mensual_str = request.form.get("tasa_mora_mensual")
            justificacion = request.form.get("justificacion_edicion")

            servicios_desc = request.form.getlist("servicio_descripcion[]")
            servicios_cant = request.form.getlist("servicio_cantidad[]")
            servicios_precio = request.form.getlist("servicio_precio[]")

            partidas_desc = request.form.getlist("partida_descripcion[]")
            partidas_monto = request.form.getlist("partida_monto[]")
            partidas_fecha = request.form.getlist("partida_fecha[]")

            if not justificacion or not justificacion.strip():
                flash("Debe proporcionar una justificación válida para la edición.", "danger")
                return redirect(url_for("editar_factura", factura_id=factura.id))

            if not cliente_id or not tipo_comprobante or not fecha_emision_str:
                flash("Por favor complete los campos obligatorios.", "danger")
                return redirect(url_for("editar_factura", factura_id=factura.id))

            # Validar que el cliente tenga expedientes y que el expediente seleccionado sea válido
            expediente_valido = Expediente.query.filter_by(id=int(expediente_id), cliente_id=int(cliente_id)).first()
            if not expediente_valido:
                flash("El expediente seleccionado no es válido o no pertenece al cliente.", "danger")
                return redirect(url_for("editar_factura", factura_id=factura.id))

            # Evitar facturar el mismo expediente más de una vez
            factura_existente = FacturaHonorario.query.filter_by(
                expediente_id=int(expediente_id)
            ).filter(
                FacturaHonorario.id != factura.id,
                FacturaHonorario.estado_pago != 'Anulado'
            ).first()
            if factura_existente:
                flash(f"El expediente seleccionado ya tiene una factura activa registrada (Factura #{factura_existente.id}). No se puede asociar a esta factura.", "danger")
                return redirect(url_for("editar_factura", factura_id=factura.id))

            try:
                fecha_emision = datetime.strptime(fecha_emision_str, "%Y-%m-%d")
            except ValueError:
                fecha_emision = rd_now()

            try:
                plazo_pago_dias = int(plazo_pago_dias_str)
            except (ValueError, TypeError):
                plazo_pago_dias = 30

            try:
                tasa_mora_mensual = float(tasa_mora_mensual_str)
            except (ValueError, TypeError):
                tasa_mora_mensual = 0.00

            subtotal_calculado = 0
            detalles_to_save = []

            for i in range(len(servicios_desc)):
                desc = servicios_desc[i].strip()
                if not desc:
                    continue
                try:
                    cant = int(servicios_cant[i])
                    precio = float(servicios_precio[i])
                    # RF-INT-001: Validación de Datos Monetarios
                    if cant <= 0 or precio < 0:
                        flash("Las cantidades de servicios deben ser mayores a cero y los precios no pueden ser negativos.", "danger")
                        return redirect(url_for("editar_factura", factura_id=factura.id))
                    if round(precio, 2) != precio:
                        flash("El precio unitario no puede tener más de dos decimales.", "danger")
                        return redirect(url_for("editar_factura", factura_id=factura.id))
                except (ValueError, TypeError):
                    continue
                sub_item = cant * precio
                subtotal_calculado += sub_item
                detalles_to_save.append({
                    "descripcion": desc,
                    "cantidad": cant,
                    "precio_unitario": precio,
                    "subtotal": sub_item
                })

            itbis_calculado = subtotal_calculado * 0.18
            total_calculado = subtotal_calculado + itbis_calculado

            partidas_to_save = []
            suma_partidas = 0
            for i in range(len(partidas_desc)):
                p_desc = partidas_desc[i].strip()
                if not p_desc:
                    continue
                try:
                    p_monto = float(partidas_monto[i])
                    p_fecha = datetime.strptime(partidas_fecha[i], "%Y-%m-%d").date()
                    # RF-INT-001: Validación de Datos Monetarios
                    if p_monto <= 0:
                        flash("El monto de cada cuota debe ser mayor a cero.", "danger")
                        return redirect(url_for("editar_factura", factura_id=factura.id))
                    if round(p_monto, 2) != p_monto:
                        flash("El monto de la cuota no puede tener más de dos decimales.", "danger")
                        return redirect(url_for("editar_factura", factura_id=factura.id))
                except (ValueError, TypeError):
                    continue

                suma_partidas += p_monto
                partidas_to_save.append({
                    "descripcion_partida": p_desc,
                    "monto": p_monto,
                    "fecha_vencimiento": p_fecha
                })

            if abs(suma_partidas - total_calculado) > 0.05:
                flash(f"La suma de las partidas (RD$ {suma_partidas:,.2f}) debe ser exactamente igual al total de la factura (RD$ {total_calculado:,.2f}).", "danger")
                return redirect(url_for("editar_factura", factura_id=factura.id))

            try:
                factura.cliente_id = int(cliente_id)
                factura.expediente_id = int(expediente_id) if expediente_id else None
                factura.tipo_comprobante = tipo_comprobante
                factura.monto_subtotal = subtotal_calculado
                factura.monto_itbis = itbis_calculado
                factura.monto_total = total_calculado
                factura.fecha_emision = fecha_emision
                factura.plazo_pago_dias = plazo_pago_dias
                factura.tasa_mora_mensual = tasa_mora_mensual

                for d in factura.detalles:
                    db.session.delete(d)
                
                for p in factura.partidas:
                    db.session.delete(p)

                db.session.flush()

                for d in detalles_to_save:
                    detalle = DetalleFactura(
                        factura_id=factura.id,
                        descripcion=d["descripcion"],
                        cantidad=d["cantidad"],
                        precio_unitario=d["precio_unitario"],
                        subtotal=d["subtotal"]
                    )
                    db.session.add(detalle)

                for p in partidas_to_save:
                    partida = PartidaPagoFactura(
                        factura_id=factura.id,
                        descripcion_partida=p["descripcion_partida"],
                        monto=p["monto"],
                        fecha_vencimiento=p["fecha_vencimiento"],
                        estado_pago="Pendiente"
                    )
                    db.session.add(partida)

                registrar_auditoria(
                    usuario_id=current_user.id,
                    accion="EDICION_FACTURA",
                    detalles=f"Se editó la factura ID {factura.id} (NCF: {factura.ncf or 'N/A'}) por un total de RD$ {total_calculado:,.2f}. Justificación: {justificacion}",
                    cliente_id=int(cliente_id),
                    expediente_id=int(expediente_id) if expediente_id else None
                )

                db.session.commit()
                flash("Factura editada correctamente.", "success")
                return redirect(url_for("ver_detalle_factura", factura_id=factura.id))
            except Exception as e:
                db.session.rollback()
                flash(f"Error al guardar la factura editada: {str(e)}", "danger")
                return redirect(url_for("editar_factura", factura_id=factura.id))

        clientes = Cliente.query.all()
        expedientes = Expediente.query.filter_by(cliente_id=factura.cliente_id).all()
        return render_template("facturas/editar_factura.html", factura=factura, clientes=clientes, expedientes=expedientes)

    @app.route("/facturas", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Administrador", "Asociado")
    def listar_facturas():
        status_filter = request.args.get("status")
        cliente_search = request.args.get("cliente_search", "").strip()
        ncf_filter = request.args.get("ncf")

        query = FacturaHonorario.query

        if current_user.rol == "Cliente":
            if not current_user.cliente_profile:
                flash("Perfil de cliente no encontrado.", "danger")
                return redirect(url_for("dashboard"))
            query = query.filter_by(cliente_id=current_user.cliente_profile.id)
        else:
            if cliente_search:
                search_pattern = f"%{cliente_search}%"
                query = query.join(Cliente).filter(
                    db.or_(
                        db.func.unaccent(Cliente.nombres).ilike(db.func.unaccent(search_pattern)),
                        db.func.unaccent(Cliente.apellidos).ilike(db.func.unaccent(search_pattern)),
                        db.func.unaccent(db.func.concat(Cliente.nombres, ' ', Cliente.apellidos)).ilike(db.func.unaccent(search_pattern)),
                        Cliente.rnc_cedula.ilike(search_pattern)
                    )
                )

        if ncf_filter:
            query = query.filter(FacturaHonorario.ncf.ilike(f"%{ncf_filter.strip()}%"))

        all_invoices = query.order_by(FacturaHonorario.fecha_emision.desc(), FacturaHonorario.id.desc()).all()

        total_facturado = sum(f.monto_total for f in all_invoices if f.estado_pago != 'Anulado')
        total_cobrado = sum(f.total_pagado for f in all_invoices if f.estado_pago != 'Anulado')
        total_pendiente = sum(f.total_pendiente for f in all_invoices if f.estado_pago != 'Anulado')
        
        total_mora = 0
        now_date = rd_now().date()
        for f in all_invoices:
            if f.estado_pago != 'Anulado':
                for p in f.partidas:
                    if p.estado_pago == 'Pendiente' and p.fecha_vencimiento < now_date:
                        total_mora += p.monto

        filtered_invoices = []
        for f in all_invoices:
            dynamic_state = f.estado_pago
            if f.estado_pago != 'Anulado':
                pagadas = sum(1 for p in f.partidas if p.estado_pago == 'Pagado')
                if pagadas == len(f.partidas) and len(f.partidas) > 0:
                    dynamic_state = 'Pagada'
                elif pagadas > 0:
                    dynamic_state = 'Pagada Parcial'
                else:
                    dynamic_state = 'Pendiente'

            if status_filter:
                if status_filter == 'Mora':
                    has_mora = any(p.estado_pago == 'Pendiente' and p.fecha_vencimiento < now_date for p in f.partidas)
                    if not has_mora:
                        continue
                elif status_filter != dynamic_state:
                    continue

            filtered_invoices.append((f, dynamic_state))

        return render_template(
            "facturas/index.html",
            facturas_con_estado=filtered_invoices,
            total_facturado=total_facturado,
            total_cobrado=total_cobrado,
            total_pendiente=total_pendiente,
            total_mora=total_mora,
            status_filter=status_filter,
            cliente_search=cliente_search,
            ncf_filter=ncf_filter
        )

    @app.route("/facturas/<int:factura_id>", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Administrador", "Asociado", "Cliente")
    def ver_detalle_factura(factura_id):
        factura = FacturaHonorario.query.get_or_404(factura_id)

        if current_user.rol == "Cliente":
            if not current_user.cliente_profile or factura.cliente_id != current_user.cliente_profile.id:
                flash("No tiene permisos para ver esta factura.", "danger")
                return redirect(url_for("dashboard"))

        now_date = rd_now().date()
        cuotas_con_mora = []
        for p in factura.partidas:
            mora_calculada = 0
            dias_retraso = 0
            if p.estado_pago == 'Pendiente' and p.fecha_vencimiento < now_date:
                dias_retraso = (now_date - p.fecha_vencimiento).days
                tasa_mensual = float(factura.tasa_mora_mensual or 0)
                mora_calculada = float(p.monto) * (tasa_mensual / 100) * (dias_retraso / 30)

            cuotas_con_mora.append({
                "partida": p,
                "dias_retraso": dias_retraso,
                "mora": mora_calculada
            })

        dynamic_state = factura.estado_pago
        if factura.estado_pago != 'Anulado':
            pagadas = sum(1 for p in factura.partidas if p.estado_pago == 'Pagado')
            if pagadas == len(factura.partidas) and len(factura.partidas) > 0:
                dynamic_state = 'Pagada'
            elif pagadas > 0:
                dynamic_state = 'Pagada Parcial'
            else:
                dynamic_state = 'Pendiente'

        return render_template(
            "facturas/detalle_factura.html",
            factura=factura,
            cuotas=cuotas_con_mora,
            dynamic_state=dynamic_state,
            current_date=now_date
        )

    @app.route("/facturas/<int:factura_id>/pagar-cuota/<int:cuota_id>", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def pagar_cuota_factura(factura_id, cuota_id):
        factura = FacturaHonorario.query.get_or_404(factura_id)
        cuota = PartidaPagoFactura.query.filter_by(id=cuota_id, factura_id=factura_id).first_or_404()

        if cuota.estado_pago == 'Pagado':
            flash("Esta cuota ya ha sido cobrada anteriormente.", "warning")
            return redirect(url_for("ver_detalle_factura", factura_id=factura.id))

        try:
            cuota.estado_pago = 'Pagado'
            
            pagadas = sum(1 for p in factura.partidas if p.estado_pago == 'Pagado')
            if pagadas == len(factura.partidas):
                factura.estado_pago = 'Cobrado'
            else:
                factura.estado_pago = 'Cobrado Parcial'

            registrar_auditoria(
                usuario_id=current_user.id,
                accion="COBRO_CUOTA_FACTURA",
                detalles=f"Se registró el cobro de la cuota '{cuota.descripcion_partida}' por un monto de RD$ {cuota.monto:,.2f} de la factura ID {factura.id} (NCF: {factura.ncf or 'N/A'}).",
                cliente_id=factura.cliente_id,
                expediente_id=factura.expediente_id
            )

            db.session.commit()
            flash(f"Cobro de cuota '{cuota.descripcion_partida}' registrado exitosamente.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al registrar el cobro: {str(e)}", "danger")

        return redirect(url_for("ver_detalle_factura", factura_id=factura.id))

    @app.route("/facturas/<int:factura_id>/pdf", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Administrador", "Asociado", "Cliente")
    def descargar_factura_pdf(factura_id):
        factura = FacturaHonorario.query.get_or_404(factura_id)
        
        if current_user.rol == "Cliente":
            if not current_user.cliente_profile or factura.cliente_id != current_user.cliente_profile.id:
                flash("No tiene permisos para ver esta factura.", "danger")
                return redirect(url_for("dashboard"))
                
        from xhtml2pdf import pisa
        from io import BytesIO
        from flask import make_response
        
        html_content = render_template("facturas/factura_pdf.html", factura=factura, current_date=rd_now())
        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)
        
        if pisa_status.err:
            flash("Error al generar el PDF de la factura.", "danger")
            return redirect(url_for("ver_detalle_factura", factura_id=factura.id))
            
        pdf_data = pdf_buffer.getvalue()
        
        response = make_response(pdf_data)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"inline; filename=factura_{factura.ncf or factura.id}.pdf"
        return response

    @app.route("/api/clientes/<int:cliente_id>/expedientes", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Paralegal", "Administrador")
    def api_cliente_expedientes(cliente_id):
        exclude_factura_id = request.args.get("exclude_factura_id", type=int)
        expedientes = Expediente.query.filter_by(cliente_id=cliente_id).all()
        
        result = []
        for e in expedientes:
            query = FacturaHonorario.query.filter_by(expediente_id=e.id).filter(
                FacturaHonorario.estado_pago != "Anulado"
            )
            if exclude_factura_id:
                query = query.filter(FacturaHonorario.id != exclude_factura_id)
            
            facturado = query.first() is not None
            
            result.append({
                "id": e.id,
                "nombre_caso": f"{e.codigo_firma} - {e.nombre_caso} ({e.tipo_tramite})" + (" (YA FACTURADO)" if facturado else ""),
                "facturado": facturado,
                "tipo_tramite": e.tipo_tramite
            })
            
        return jsonify(result)

    @app.route("/nomina", methods=["GET"])
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def ver_nomina():
        # Get selected month and year
        now = rd_now()
        mes = request.args.get("mes", type=int, default=now.month)
        anio = request.args.get("anio", type=int, default=now.year)
        
        # Load all staff members (Asociado, Paralegal, Socio, Administrador)
        abogados = Usuario.query.filter(Usuario.rol.in_(["Asociado", "Paralegal", "Socio"])).all()
        
        # Query audit logs for payments in that month and year
        import calendar
        start_date = datetime(anio, mes, 1, 0, 0, 0)
        _, last_day = calendar.monthrange(anio, mes)
        end_date = datetime(anio, mes, last_day, 23, 59, 59)
        
        auditorias_cobro = BitacoraAuditoria.query.filter(
            BitacoraAuditoria.accion_realizada == "COBRO_CUOTA_FACTURA",
            BitacoraAuditoria.fecha_hora >= start_date,
            BitacoraAuditoria.fecha_hora <= end_date
        ).all()
        
        import re
        def parse_monto(detalles):
            match = re.search(r'monto de RD\$\s*([\d,]+\.?\d*)', detalles)
            if match:
                return float(match.group(1).replace(',', ''))
            return 0.0
            
        # Group commissions by user
        pagos_abogados = {}
        for abog in abogados:
            pagos_abogados[abog.id] = {
                "id": abog.id,
                "nombre": abog.nombre,
                "rol": abog.rol,
                "salario_base": float(abog.salario_base or 0.0),
                "porcentaje_comision": float(abog.porcentaje_comision or 0.0),
                "cobros_realizados": [],
                "total_comisiones": 0.0,
                "total_liquidar": float(abog.salario_base or 0.0)
            }
            
        for log in auditorias_cobro:
            if not log.expediente_id:
                continue
            exp = Expediente.query.get(log.expediente_id)
            if not exp or not exp.abogado_responsable_id:
                continue
                
            resp_id = exp.abogado_responsable_id
            if resp_id in pagos_abogados:
                monto = parse_monto(log.accion_realizada + " " + log.detalles_tecnicos)
                if monto == 0.0:
                    monto = parse_monto(log.detalles_tecnicos)
                
                comision = monto * (pagos_abogados[resp_id]["porcentaje_comision"] / 100.0)
                pagos_abogados[resp_id]["cobros_realizados"].append({
                    "caso": exp.nombre_caso,
                    "codigo": exp.codigo_firma,
                    "monto_cobrado": monto,
                    "comision": comision,
                    "fecha": log.fecha_hora.strftime("%d/%m/%Y %I:%M %p")
                })
                pagos_abogados[resp_id]["total_comisiones"] += comision
                pagos_abogados[resp_id]["total_liquidar"] += comision
                
        return render_template(
            "nomina/index.html",
            pagos_abogados=pagos_abogados.values(),
            mes=mes,
            anio=anio,
            current_date=now
        )

    # ==========================================
    # REDISEÑO DE HONORARIOS, FACTURACIÓN Y COBROS (DOC 2)
    # ==========================================

    @app.route("/presupuestos")
    @login_required
    def presupuestos_index():
        q = request.args.get("q", "").strip()
        query = Presupuesto.query
        if q:
            search_pattern = f"%{q}%"
            query = query.join(Cliente, Presupuesto.cliente_id == Cliente.id).filter(
                db.or_(
                    Presupuesto.titulo.ilike(search_pattern),
                    Cliente.nombres.ilike(search_pattern),
                    Cliente.apellidos.ilike(search_pattern),
                    db.func.concat(Cliente.nombres, ' ', Cliente.apellidos).ilike(search_pattern)
                )
            )
        presupuestos = query.order_by(Presupuesto.fecha_emision.desc()).all()
        return render_template("presupuestos/index.html", presupuestos=presupuestos, query_q=q)

    @app.route("/presupuestos/nuevo", methods=["GET", "POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Administrador")
    def presupuestos_nuevo():
        clientes = Cliente.query.all()
        if request.method == "POST":
            cliente_id = request.form.get("cliente_id")
            titulo = request.form.get("titulo")
            descripcion = request.form.get("descripcion")
            materia = request.form.get("materia")
            tipo_asunto = request.form.get("tipo_asunto")
            
            descripciones = request.form.getlist("partida_desc[]")
            cantidades = request.form.getlist("partida_cant[]")
            precios = request.form.getlist("partida_precio[]")
            
            subtotal = Decimal('0.00')
            detalles = []
            for i in range(len(descripciones)):
                if not descripciones[i]:
                     continue
                cant = int(cantidades[i]) if cantidades[i] else 1
                precio = Decimal(precios[i]) if precios[i] else Decimal('0.00')
                part_sub = (cant * precio).quantize(Decimal('0.01'))
                subtotal += part_sub
                detalles.append({
                    'descripcion': descripciones[i],
                    'cantidad': cant,
                    'precio_unitario': precio,
                    'subtotal': part_sub
                })
                 
            aplica_itbis = request.form.get("aplica_itbis") == "on"
            itbis, total = BillingService.calcular_itbis(subtotal, aplica_itbis)
            
            pres = Presupuesto(
                cliente_id=cliente_id,
                titulo=titulo,
                descripcion=descripcion,
                materia=materia,
                tipo_asunto=tipo_asunto,
                monto_subtotal=subtotal,
                monto_itbis=itbis,
                monto_total=total,
                estado='Pendiente Aceptación'
            )
            db.session.add(pres)
            db.session.flush()
            
            for det in detalles:
                p_det = PresupuestoDetalle(
                    presupuesto_id=pres.id,
                    descripcion=det['descripcion'],
                    cantidad=det['cantidad'],
                    precio_unitario=det['precio_unitario'],
                    subtotal=det['subtotal']
                )
                db.session.add(p_det)
                 
            db.session.commit()
            flash("Presupuesto creado exitosamente.", "success")
            return redirect(url_for("presupuestos_index"))
             
        return render_template("presupuestos/nuevo.html", clientes=clientes)

    @app.route("/presupuestos/<int:presupuesto_id>/aceptar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Administrador")
    def presupuestos_aceptar(presupuesto_id):
        pres = Presupuesto.query.get_or_404(presupuesto_id)
        pres.estado = 'Aceptado'
        
        # 1. Crear contrato de honorarios
        contrato = ContratoHonorarios(
            cliente_id=pres.cliente_id,
            presupuesto_id=pres.id,
            fecha_firma=rd_today(),
            fecha_inicio=rd_today(),
            estado='Vigente',
            observaciones=f"Contrato firmado a partir de Presupuesto #{pres.id}: {pres.titulo}",
            tipo_cobro='Fijo',
            moneda='DOP',
            aplica_itbis=True if pres.monto_itbis > 0 else False,
            porcentaje_itbis=BillingService.get_itbis_percentage(),
            subtotal=pres.monto_subtotal,
            itbis=pres.monto_itbis,
            total_contrato=pres.monto_total
        )
        db.session.add(contrato)
        db.session.flush()
        
        # Generar cronograma del contrato
        BillingService.generar_cronograma(contrato)
        
        # 2. Redireccionar a la pantalla de crear expediente pre-llenado
        db.session.commit()
        flash(f"Presupuesto #{pres.id} aceptado. Por favor complete los detalles para registrar el nuevo expediente.", "success")
        return redirect(url_for("nuevo_expediente",
                                cliente_id=pres.cliente_id,
                                nombre_caso=pres.titulo,
                                materia=pres.materia,
                                monto=pres.monto_total,
                                contrato_id=contrato.id,
                                presupuesto_id=pres.id))

    @app.route("/presupuestos/<int:presupuesto_id>/rechazar", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Administrador")
    def presupuestos_rechazar(presupuesto_id):
        pres = Presupuesto.query.get_or_404(presupuesto_id)
        pres.estado = 'Rechazado'
        db.session.commit()
        flash(f"El presupuesto #{pres.id} ha sido marcado como Rechazado.", "warning")
        return redirect(url_for("presupuestos_index"))

    @app.route("/contratos")
    @login_required
    def contratos_index():
        q = request.args.get("q", "").strip()
        period = request.args.get("period", "Todos").strip()
        
        query = ContratoHonorarios.query
        
        if q:
            search_pattern = f"%{q}%"
            query = query.join(Cliente, ContratoHonorarios.cliente_id == Cliente.id).outerjoin(
                Expediente, ContratoHonorarios.expediente_id == Expediente.id
            ).filter(
                db.or_(
                    Cliente.nombres.ilike(search_pattern),
                    Cliente.apellidos.ilike(search_pattern),
                    db.func.concat(Cliente.nombres, ' ', Cliente.apellidos).ilike(search_pattern),
                    Expediente.nombre_caso.ilike(search_pattern),
                    Expediente.codigo_firma.ilike(search_pattern),
                    db.func.cast(ContratoHonorarios.id, db.String).ilike(search_pattern)
                )
            )
            
        if period == "semana":
            start_date = rd_today() - timedelta(days=rd_today().weekday())
            query = query.filter(ContratoHonorarios.fecha_firma >= start_date)
        elif period == "mes":
            start_date = rd_today().replace(day=1)
            query = query.filter(ContratoHonorarios.fecha_firma >= start_date)
        elif period == "anio":
            start_date = rd_today().replace(month=1, day=1)
            query = query.filter(ContratoHonorarios.fecha_firma >= start_date)
            
        contratos = query.order_by(ContratoHonorarios.fecha_firma.desc(), ContratoHonorarios.id.desc()).all()
        return render_template("contratos/index.html", contratos=contratos, query_q=q, selected_period=period)

    @app.route("/contratos/nuevo", methods=["GET", "POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Administrador")
    def contratos_nuevo():
        clientes = Cliente.query.all()
        expedientes = Expediente.query.all()
        if request.method == "POST":
            cliente_id = request.form.get("cliente_id")
            expediente_id = request.form.get("expediente_id") or None
            if expediente_id == '0' or expediente_id == '':
                expediente_id = None
            fecha_firma_str = request.form.get("fecha_firma")
            fecha_inicio_str = request.form.get("fecha_inicio")
            tipo_cobro = request.form.get("tipo_cobro")
            moneda = request.form.get("moneda", "DOP")
            subtotal = Decimal(request.form.get("subtotal", 0))
            aplica_itbis = request.form.get("aplica_itbis") == "on"
            itbis, total = BillingService.calcular_itbis(subtotal, aplica_itbis)
            observaciones = request.form.get("observaciones")
            
            contrato = ContratoHonorarios(
                cliente_id=cliente_id,
                expediente_id=expediente_id,
                fecha_firma=datetime.strptime(fecha_firma_str, '%Y-%m-%d').date() if fecha_firma_str else rd_today(),
                fecha_inicio=datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date() if fecha_inicio_str else rd_today(),
                estado='Vigente',
                tipo_cobro=tipo_cobro,
                moneda=moneda,
                aplica_itbis=aplica_itbis,
                porcentaje_itbis=BillingService.get_itbis_percentage(),
                subtotal=subtotal,
                itbis=itbis,
                total_contrato=total,
                observaciones=observaciones
            )
            db.session.add(contrato)
            db.session.flush()
            
            c_desc = request.form.getlist("cuota_desc[]")
            c_monto = request.form.getlist("cuota_monto[]")
            c_venc = request.form.getlist("cuota_venc[]")
            
            cuotas_data = []
            for i in range(len(c_desc)):
                if not c_desc[i]:
                    continue
                cuotas_data.append({
                    'descripcion': c_desc[i],
                    'monto': Decimal(c_monto[i]) if c_monto[i] else Decimal('0.00'),
                    'fecha_vencimiento': c_venc[i]
                })
                 
            BillingService.generar_cronograma(contrato, cuotas_data)
            flash("Contrato creado exitosamente con su cronograma de cobro.", "success")
            return redirect(url_for("contratos_index"))
             
        return render_template("contratos/nuevo.html", clientes=clientes, expedientes=expedientes)

    @app.route("/contratos/<int:contrato_id>")
    @login_required
    def contratos_detalle(contrato_id):
        contrato = ContratoHonorarios.query.get_or_404(contrato_id)
        return render_template("contratos/detalle.html", contrato=contrato)

    @app.route("/contratos/<int:contrato_id>/facturar-cuota/<int:cuota_id>", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Administrador")
    def facturar_cuota(contrato_id, cuota_id):
        contrato = ContratoHonorarios.query.get_or_404(contrato_id)
        cuota = CronogramaCobro.query.get_or_404(cuota_id)
        
        if cuota.estado != 'Pendiente':
            flash("Esta cuota ya ha sido facturada o cancelada.", "warning")
            return redirect(url_for("contratos_detalle", contrato_id=contrato.id))
             
        # Crear FacturaHonorario
        subtotal = cuota.monto
        aplica_itbis = contrato.aplica_itbis
        itbis, total = BillingService.calcular_itbis(subtotal, aplica_itbis)
        
        # Generar NCF Consumidor Final B02
        last_f = FacturaHonorario.query.filter(FacturaHonorario.ncf.like('B02%')).order_by(FacturaHonorario.id.desc()).first()
        correlativo = 1
        if last_f and last_f.ncf:
            try:
                correlativo = int(last_f.ncf[3:]) + 1
            except ValueError:
                pass
        ncf = f"B02{correlativo:010d}"
        
        factura = FacturaHonorario(
            cliente_id=contrato.cliente_id,
            expediente_id=contrato.expediente_id,
            contrato_id=contrato.id,
            cuota_id=cuota.id,
            ncf=ncf,
            tipo_comprobante='02',
            monto_subtotal=subtotal,
            monto_itbis=itbis,
            monto_total=total,
            estado_pago='Pendiente',
            plazo_pago_dias=30
        )
        db.session.add(factura)
        db.session.flush()
         
        # Crear DetalleFactura
        detalle = DetalleFactura(
            factura_id=factura.id,
            descripcion=f"Cobro de Honorarios - {cuota.descripcion}",
            cantidad=1,
            precio_unitario=subtotal,
            subtotal=subtotal
        )
        db.session.add(detalle)
         
        # Marcar cuota como Facturada
        cuota.estado = 'Facturado'
         
        db.session.commit()
        flash(f"Factura NCF {ncf} generada exitosamente para la cuota '{cuota.descripcion}'", "success")
        return redirect(url_for("contratos_detalle", contrato_id=contrato.id))

    @app.route("/facturas/<int:factura_id>/pagar-parcial", methods=["POST"])
    @login_required
    @roles_permitidos("Socio", "Asociado", "Administrador")
    def pagar_parcial(factura_id):
        monto = request.form.get("monto")
        metodo_pago = request.form.get("metodo_pago")
        referencia = request.form.get("referencia")
        
        recibo, err = BillingService.registrar_pago(factura_id, monto, metodo_pago, referencia)
        if err:
            flash(err, "danger")
        else:
            flash(f"Pago registrado exitosamente. Se emitió el Recibo de Caja {recibo.numero_recibo}", "success")
             
        return redirect(url_for("ver_detalle_factura", factura_id=factura_id))

    @app.route("/recibos")
    @login_required
    def recibos_index():
        recibos = ReciboInterno.query.order_by(ReciboInterno.fecha_emision.desc()).all()
        return render_template("facturas/recibos.html", recibos=recibos)

    @app.route("/expedientes/<int:expediente_id>/gastos", methods=["GET", "POST"])
    @login_required
    def gastos_reembolsables(expediente_id):
        exp = Expediente.query.get_or_404(expediente_id)
        if request.method == "POST":
            tipo_gasto = request.form.get("tipo_gasto")
            descripcion = request.form.get("descripcion")
            monto = Decimal(request.form.get("monto", 0))
            fecha_str = request.form.get("fecha")
            estado = request.form.get("estado", "Pendiente")
             
            gasto = GastoReembolsable(
                expediente_id=exp.id,
                tipo_gasto=tipo_gasto,
                descripcion=descripcion,
                monto=monto,
                fecha=datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else rd_today(),
                estado=estado
            )
            db.session.add(gasto)
            db.session.commit()
            flash("Gasto reembolsable registrado exitosamente.", "success")
            return redirect(url_for("gastos_reembolsables", expediente_id=exp.id))
             
        gastos = GastoReembolsable.query.filter_by(expediente_id=exp.id).order_by(GastoReembolsable.fecha.desc()).all()
        return render_template("expedientes/gastos.html", exp=exp, gastos=gastos)

    @app.route("/facturas/reportes")
    @login_required
    @roles_permitidos("Socio", "Administrador")
    def reportes_financieros():
        # Métricas principales
        total_facturado = db.session.query(db.func.sum(FacturaHonorario.monto_total)).filter(FacturaHonorario.estado_pago != 'Anulado').scalar() or 0
        total_cobrado = db.session.query(db.func.sum(TransaccionPago.monto)).scalar() or 0
        total_pendiente = total_facturado - total_cobrado
        
        # Cobros por método
        cobros_por_metodo = db.session.query(
            TransaccionPago.metodo_pago, db.func.sum(TransaccionPago.monto)
        ).group_by(TransaccionPago.metodo_pago).all()

        # Gastos reembolsables por estado
        gastos_por_estado = db.session.query(
            GastoReembolsable.estado, db.func.sum(GastoReembolsable.monto)
        ).group_by(GastoReembolsable.estado).all()
        
        return render_template("facturas/reportes.html",
                               total_facturado=total_facturado,
                               total_cobrado=total_cobrado,
                               total_pendiente=total_pendiente,
                               cobros_por_metodo=cobros_por_metodo,
                               gastos_por_estado=gastos_por_estado)

def procesar_alertas_preventivas():
    """
    Calcula y despacha alertas internas y notificaciones por correo para
    plazos procesales, trámites administrativos, audiencias y tareas pendientes con 30, 15 y 3 días de anticipación.
    """
    from datetime import datetime

    import pytz

    from app import db
    from app.models import AlertaPlazoAudiencia, NotificacionInterna, Tarea, Usuario, PartidaPagoFactura

    print("[PLANIFICADOR] Iniciando procesamiento de alertas preventivas...")
    tz_rd = pytz.timezone("America/Santo_Domingo")
    now_local = datetime.now(tz_rd).date()

    # === 1. PROCESAR ALERTAS, PLAZOS Y AUDIENCIAS ===
    plazos = AlertaPlazoAudiencia.query.filter_by(estado_alerta="Pending").all()
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
            alerta_id=plazo.id, dias_anticipacion=anticipacion
        ).first()

        if envio_previo:
            continue

        # Determinar destinatarios
        exp = plazo.expediente
        abogados = []
        if exp and exp.abogado_responsable:
            abogados.append(exp.abogado_responsable)
        else:
            abogados = Usuario.query.filter_by(rol="Socio", activo=True).all()

        if not abogados:
            print(
                f"[PLANIFICADOR] Sin destinatarios válidos para el hito ID {plazo.id}"
            )
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
                    expediente_id=exp.id if exp else None,
                )
                db.session.add(notif)
            except Exception as e:
                print(
                    f"[PLANIFICADOR] Error al despachar alerta al usuario {abogado.id}: {e}"
                )

        # También notificar al cliente del expediente si tiene portal de acceso
        if exp and exp.cliente and exp.cliente.usuario_id:
            try:
                enviar_email_alerta_preventiva(exp.cliente.usuario, plazo, anticipacion)
                msj_cliente = f"[Recordatorio {anticipacion} días] La {tipo_nombre} '{plazo.titulo_hito}' programada para el caso '{exp.nombre_caso}' ocurre el {venc_local.strftime('%d/%m/%Y')}."
                notif_cliente = NotificacionInterna(
                    usuario_id=exp.cliente.usuario_id,
                    mensaje=msj_cliente,
                    leida=False,
                    expediente_id=exp.id,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif_cliente)
            except Exception as e:
                print(
                    f"[PLANIFICADOR] Error al despachar alerta al cliente {exp.cliente.id}: {e}"
                )

        try:
            registro = RegistroEnvioAlerta(
                alerta_id=plazo.id, dias_anticipacion=anticipacion
            )
            db.session.add(registro)
            db.session.commit()
            print(
                f"[PLANIFICADOR] Alerta de {anticipacion} días enviada para hito ID {plazo.id} ({plazo.titulo_hito})"
            )
        except Exception as e:
            db.session.rollback()
            print(
                f"[PLANIFICADOR] Error al guardar registro de envío para hito ID {plazo.id}: {e}"
            )

    # === 2. PROCESAR TAREAS PENDIENTES ===
    tareas = Tarea.query.filter(
        Tarea.estado != "Completada", Tarea.fecha_limite.is_not(None)
    ).all()
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
            tarea_id=tarea.id, dias_anticipacion=anticipacion
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
            abogados = Usuario.query.filter_by(rol="Socio", activo=True).all()

        if not abogados:
            print(
                f"[PLANIFICADOR] Sin destinatarios válidos para la tarea ID {tarea.id}"
            )
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
                    expediente_id=exp.id if exp else None,
                )
                db.session.add(notif)
            except Exception as e:
                print(
                    f"[PLANIFICADOR] Error al despachar alerta de tarea al usuario {abogado.id}: {e}"
                )

        try:
            registro = RegistroEnvioAlerta(
                tarea_id=tarea.id, dias_anticipacion=anticipacion
            )
            db.session.add(registro)
            db.session.commit()
            print(
                f"[PLANIFICADOR] Alerta de {anticipacion} días enviada para tarea ID {tarea.id} ({tarea.titulo})"
            )
        except Exception as e:
            db.session.rollback()
            print(
                f"[PLANIFICADOR] Error al guardar registro de envío para tarea ID {tarea.id}: {e}"
            )

    # === 3. PROCESAR CUOTAS/PARTIDAS DE PAGO PENDIENTES ===
    partidas = PartidaPagoFactura.query.filter_by(estado_pago='Pendiente').all()
    for partida in partidas:
        if not partida.fecha_vencimiento:
            continue
        venc_local = partida.fecha_vencimiento
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

        envio_previo = RegistroEnvioAlerta.query.filter_by(
            partida_factura_id=partida.id, dias_anticipacion=anticipacion
        ).first()

        if envio_previo:
            continue

        abogados = []
        fact = partida.factura
        exp = fact.expediente if fact else None
        if exp and exp.abogado_responsable:
            abogados.append(exp.abogado_responsable)
        else:
            abogados = Usuario.query.filter_by(rol='Socio', activo=True).all()

        if not abogados:
            print(f"[PLANIFICADOR] Sin destinatarios válidos para la partida de pago ID {partida.id}")
            continue

        for abogado in abogados:
            try:
                enviar_email_alerta_preventiva(abogado, partida, anticipacion)

                msj = f"[Alerta Pago {anticipacion} días] La cuota '{partida.descripcion_partida}' de la factura NCF {fact.ncf or 'N/A'} (monto RD$ {partida.monto:,.2f}) vence el {venc_local.strftime('%d/%m/%Y')}."
                notif = NotificacionInterna(
                    usuario_id=abogado.id,
                    mensaje=msj,
                    leida=False,
                    expediente_id=exp.id if exp else None,
                )
                db.session.add(notif)
            except Exception as e:
                print(f"[PLANIFICADOR] Error al despachar alerta de cuota al abogado {abogado.id}: {e}")

        if fact and fact.cliente and fact.cliente.usuario_id:
            try:
                enviar_email_alerta_preventiva(fact.cliente.usuario, partida, anticipacion)
                msj_cliente = f"[Recordatorio Pago {anticipacion} días] Su cuota '{partida.descripcion_partida}' por RD$ {partida.monto:,.2f} vence el {venc_local.strftime('%d/%m/%Y')}."
                notif_cliente = NotificacionInterna(
                    usuario_id=fact.cliente.usuario_id,
                    mensaje=msj_cliente,
                    leida=False,
                    expediente_id=exp.id if exp else None,
                    fecha_creacion=rd_now(),
                )
                db.session.add(notif_cliente)
            except Exception as e:
                print(f"[PLANIFICADOR] Error al despachar alerta de cuota al cliente {fact.cliente.id}: {e}")

        try:
            registro = RegistroEnvioAlerta(
                partida_factura_id=partida.id, dias_anticipacion=anticipacion
            )
            db.session.add(registro)
            db.session.commit()
            print(f"[PLANIFICADOR] Alerta de {anticipacion} días enviada para cuota ID {partida.id} ({partida.descripcion_partida})")
        except Exception as e:
            db.session.rollback()
            print(f"[PLANIFICADOR] Error al guardar registro de envío para cuota ID {partida.id}: {e}")

    print("[PLANIFICADOR] Fin del procesamiento de alertas preventivas.")
