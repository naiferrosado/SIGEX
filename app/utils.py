import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from itsdangerous import URLSafeTimedSerializer

def generate_reset_token(user_id):
    """
    Genera un token seguro y firmado que contiene el ID de usuario.
    Expira de acuerdo a max_age en la verificación.
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(user_id, salt='password-reset-salt')


def verify_reset_token(token, expiration=1800):
    """
    Verifica la autenticidad y vigencia de un token de restablecimiento.
    Por defecto expira en 30 minutos (1800 segundos).
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = serializer.loads(
            token,
            salt='password-reset-salt',
            max_age=expiration
        )
    except Exception:
        return None
    return user_id


def enviar_email_restablecimiento(usuario, reset_url):
    """
    Envía un correo electrónico HTML al usuario con el enlace para restablecer su clave.
    Si no hay credenciales SMTP configuradas en .env, simula el envío imprimiendo en consola.
    """
    subject = "Restablecer tu contraseña - SIGEX"
    body_html = f"""
    <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #2d3748; background-color: #f7fafc; padding: 30px;">
            <div style="max-width: 600px; margin: 0 auto; padding: 30px; border: 1.5px solid #e2e8f0; border-radius: 12px; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                <h2 style="color: #00409A; font-weight: bold; margin-bottom: 20px; font-size: 1.5rem; border-bottom: 2px solid #edf2f7; padding-bottom: 10px;">Restablecer contraseña - SIGEX</h2>
                <p>Hola, <strong>{usuario.nombre}</strong>,</p>
                <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta institucional en SIGEX.</p>
                <p>Para proceder con el restablecimiento, haz clic en el siguiente botón (este enlace expirará en 30 minutos):</p>
                <div style="margin: 30px 0; text-align: center;">
                    <a href="{reset_url}" style="background-color: #00409A; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; box-shadow: 0 4px 6px rgba(0,64,154,0.25);">Restablecer Contraseña</a>
                </div>
                <p>Si no puedes ver o hacer clic en el botón, copia y pega la siguiente dirección URL en tu navegador web:</p>
                <p style="word-break: break-all; background-color: #f7fafc; padding: 10px; border-radius: 6px; border: 1px solid #edf2f7; font-size: 0.85rem;"><a href="{reset_url}" style="color: #00409A;">{reset_url}</a></p>
                <hr style="border: 0; border-top: 1px solid #edf2f7; margin: 25px 0;">
                <p style="font-size: 0.8rem; color: #718096;">Si no realizaste esta solicitud, puedes ignorar este correo de forma segura. Tu contraseña actual no sufrirá ningún cambio.</p>
            </div>
        </body>
    </html>
    """
    
    server = current_app.config.get('MAIL_SERVER')
    port = current_app.config.get('MAIL_PORT')
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    use_tls = current_app.config.get('MAIL_USE_TLS', True)
    
    # Simulación para desarrollo si no hay credenciales configuradas
    if not username or not password:
        print("\n" + "="*80)
        print(" [SIMULACIÓN DESARROLLO] CORREO DE RECUPERACIÓN DE CONTRASEÑA")
        print(f" Para: {usuario.email}")
        print(f" Asunto: {subject}")
        print(f" Enlace de restablecimiento:")
        print(f"   {reset_url}")
        print("="*80 + "\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = usuario.email
        
        part = MIMEText(body_html, 'html')
        msg.attach(part)
        
        # Conexión SMTP
        smtp = smtplib.SMTP(server, port, timeout=10)
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.sendmail(sender, [usuario.email], msg.as_string())
        smtp.quit()
        return True
    except Exception as e:
        print(f"Error SMTP al enviar email de restablecimiento: {str(e)}")
        # Fallback a consola en caso de error SMTP
        print("\n" + "="*80)
        print(" [FALLBACK DESARROLLO - ERROR SMTP] CORREO DE RECUPERACIÓN DE CONTRASEÑA")
        print(f" Para: {usuario.email}")
        print(f" Enlace de restablecimiento:")
        print(f"   {reset_url}")
        print("="*80 + "\n")
        return False


def enviar_email_alerta_preventiva(usuario, plazo, dias_anticipacion):
    """
    Envía un correo electrónico HTML al usuario abogado responsable notificándole sobre el vencimiento
    inminente de un plazo legal, trámite administrativo, audiencia o tarea.
    Si no hay credenciales SMTP en .env, simula el envío por consola.
    """
    # Detectar el tipo de plazo (AlertaPlazoAudiencia vs Tarea)
    if hasattr(plazo, 'titulo_hito'):
        # Es AlertaPlazoAudiencia (plazo, trámite o audiencia)
        titulo_plazo = plazo.titulo_hito
        tipo_alerta = "Audiencia Judicial" if plazo.es_audiencia else "Plazo Procesal / Alerta Administrativa"
        fecha_venc = plazo.fecha_vencimiento
        exp_codigo = plazo.expediente.codigo_firma if plazo.expediente else "N/A"
        exp_nombre = plazo.expediente.nombre_caso if plazo.expediente else "N/A"
    else:
        # Es Tarea
        titulo_plazo = plazo.titulo
        tipo_alerta = f"Tarea Pendiente (Prioridad: {plazo.prioridad})"
        fecha_venc = plazo.fecha_limite
        exp_codigo = plazo.expediente.codigo_firma if plazo.expediente else "N/A"
        exp_nombre = plazo.expediente.nombre_caso if plazo.expediente else "N/A"

    subject = f"[ALERTA {dias_anticipacion} DÍAS] Vencimiento de {tipo_alerta} - SIGEX"
    
    fecha_formateada = fecha_venc.strftime('%d/%m/%Y') if fecha_venc else "Sin Fecha"
    info_venc = f"el {fecha_formateada}"
    
    body_html = f"""
    <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #2d3748; background-color: #f7fafc; padding: 30px;">
            <div style="max-width: 600px; margin: 0 auto; padding: 30px; border: 1.5px solid #e2e8f0; border-radius: 12px; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                <div style="text-align: center; margin-bottom: 25px;">
                    <span style="background-color: #fffaf0; border: 1px solid #feebc8; color: #dd6b20; padding: 8px 16px; border-radius: 20px; font-size: 0.85rem; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">
                        ⚠️ Alerta Preventiva - {dias_anticipacion} Días
                    </span>
                </div>
                <h2 style="color: #c53030; font-weight: bold; margin-top: 10px; margin-bottom: 20px; font-size: 1.4rem; border-bottom: 2px solid #edf2f7; padding-bottom: 10px;">
                    Vencimiento Próximo
                </h2>
                <p>Estimado(a) abogado(a) <strong>{usuario.nombre}</strong>,</p>
                <p>Le notificamos que el siguiente vencimiento bajo su responsabilidad vencerá en <strong>{dias_anticipacion} días</strong>:</p>
                
                <div style="background-color: #f7fafc; border-left: 4px solid #c53030; padding: 15px 20px; margin: 20px 0; border-radius: 0 8px 8px 0;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                        <tr>
                            <td style="padding: 4px 0; font-weight: bold; color: #718096; width: 120px;">Elemento:</td>
                            <td style="padding: 4px 0; font-weight: bold; color: #2d3748;">{titulo_plazo}</td>
                        </tr>
                        <tr>
                            <td style="padding: 4px 0; color: #718096;">Tipo:</td>
                            <td style="padding: 4px 0; color: #2d3748;">{tipo_alerta}</td>
                        </tr>
                        <tr>
                            <td style="padding: 4px 0; color: #718096;">Vence:</td>
                            <td style="padding: 4px 0; color: #c53030; font-weight: bold;">{info_venc}</td>
                        </tr>
                        <tr>
                            <td style="padding: 4px 0; color: #718096;">Expediente:</td>
                            <td style="padding: 4px 0; color: #2d3748;">{exp_codigo} - {exp_nombre}</td>
                        </tr>
                    </table>
                </div>
                
                <p>Por favor, tome las medidas correspondientes para dar cumplimiento a esta gestión dentro del plazo establecido.</p>
                
                <div style="margin: 30px 0; text-align: center;">
                    <a href="http://localhost:5000/agenda" style="background-color: #00409A; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; box-shadow: 0 4px 6px rgba(0,64,154,0.25);">
                        Ir a la Agenda en SIGEX
                    </a>
                </div>
                
                <hr style="border: 0; border-top: 1px solid #edf2f7; margin: 25px 0;">
                <p style="font-size: 0.8rem; color: #718096; text-align: center;">Este es un mensaje automático generado por el Sistema de Control de Expedientes y Alertas Preventivas SIGEX de Rosado Méndez.</p>
            </div>
        </body>
    </html>
    """
    
    server = current_app.config.get('MAIL_SERVER')
    port = current_app.config.get('MAIL_PORT')
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    use_tls = current_app.config.get('MAIL_USE_TLS', True)
    
    if not username or not password:
        print("\n" + "="*80)
        print(f" [SIMULACIÓN DESARROLLO] CORREO DE ALERTA PREVENTIVA - {dias_anticipacion} DÍAS")
        print(f" Para: {usuario.email}")
        print(f" Asunto: {subject}")
        print(f" Elemento: '{titulo_plazo}' | Tipo: {tipo_alerta} | Vence: {info_venc}")
        print(f" Caso: {exp_codigo} - {exp_nombre}")
        print("="*80 + "\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = usuario.email
        
        part = MIMEText(body_html, 'html')
        msg.attach(part)
        
        smtp = smtplib.SMTP(server, port, timeout=10)
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.sendmail(sender, [usuario.email], msg.as_string())
        smtp.quit()
        return True
    except Exception as e:
        print(f"Error SMTP al enviar email de alerta preventiva: {str(e)}")
        # Fallback
        print("\n" + "="*80)
        print(f" [FALLBACK DESARROLLO - ERROR SMTP] CORREO DE ALERTA PREVENTIVA - {dias_anticipacion} DÍAS")
        print(f" Para: {usuario.email}")
        print(f" Elemento: '{titulo_plazo}' | Vence: {info_venc}")
        print("="*80 + "\n")
        return False


def enviar_email_credenciales_cliente(cliente, email, clave_inicial):
    """
    Envía un correo electrónico HTML al cliente con sus credenciales de acceso (usuario y clave inicial).
    Si no hay credenciales SMTP configuradas en .env, simula el envío imprimiendo en consola.
    """
    subject = "Tus credenciales de acceso al portal de clientes - SIGEX"
    body_html = f"""
    <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #2d3748; background-color: #f7fafc; padding: 30px;">
            <div style="max-width: 600px; margin: 0 auto; padding: 30px; border: 1.5px solid #e2e8f0; border-radius: 12px; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                <h2 style="color: #00409A; font-weight: bold; margin-bottom: 20px; font-size: 1.5rem; border-bottom: 2px solid #edf2f7; padding-bottom: 10px;">Acceso al Portal de Clientes - SIGEX</h2>
                <p>Estimado/a <strong>{cliente.nombre_completo}</strong>,</p>
                <p>Nos complace informarle que se ha habilitado su acceso al portal de clientes de nuestra firma en la plataforma <strong>SIGEX</strong>.</p>
                <p>A continuación, le compartimos sus credenciales de acceso iniciales:</p>
                <div style="background-color: #f7fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Usuario (Correo):</strong> <span style="color: #00409A;">{email}</span></p>
                    <p style="margin: 5px 0;"><strong>Contraseña inicial:</strong> <code style="background-color: #edf2f7; padding: 2px 6px; border-radius: 4px; font-size: 0.95rem;">{clave_inicial}</code></p>
                </div>
                <p style="color: #e53e3e; font-weight: 500;">Nota importante: Por razones de seguridad, el sistema le solicitará cambiar esta contraseña inicial la primera vez que inicie sesión.</p>
                <hr style="border: 0; border-top: 1px solid #edf2f7; margin: 25px 0;">
                <p style="font-size: 0.8rem; color: #718096;">Este es un correo automático. Por favor, no responda a este mensaje.</p>
            </div>
        </body>
    </html>
    """
    
    server = current_app.config.get('MAIL_SERVER')
    port = current_app.config.get('MAIL_PORT')
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    use_tls = current_app.config.get('MAIL_USE_TLS', True)
    
    # Simulación para desarrollo si no hay credenciales configuradas
    if not username or not password:
        print("\n" + "="*80)
        print(" [SIMULACIÓN DESARROLLO] CORREO DE CREDENCIALES DE CLIENTE")
        print(f" Para: {email}")
        print(f" Asunto: {subject}")
        print(f" Usuario: {email}")
        print(f" Clave Inicial: {clave_inicial}")
        print("="*80 + "\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = email
        
        part = MIMEText(body_html, 'html')
        msg.attach(part)
        
        smtp = smtplib.SMTP(server, port, timeout=10)
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.sendmail(sender, [email], msg.as_string())
        smtp.quit()
        return True
    except Exception as e:
        print(f"Error SMTP al enviar email de credenciales: {str(e)}")
        # Fallback
        print("\n" + "="*80)
        print(" [FALLBACK DESARROLLO - ERROR SMTP] CORREO DE CREDENCIALES DE CLIENTE")
        print(f" Para: {email}")
        print(f" Usuario: {email}")
        print(f" Clave Inicial: {clave_inicial}")
        print("="*80 + "\n")
        return False


def enviar_email_notificacion_cliente(usuario, subject, mensaje):
    """
    Envía un correo electrónico HTML al cliente notificándole sobre una novedad en su caso
    (ej. nuevo documento compartido, cambio de fase o cambio de estado).
    Si no hay credenciales SMTP configuradas en .env, simula el envío imprimiendo en consola.
    """
    body_html = f"""
    <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #2d3748; background-color: #f7fafc; padding: 30px;">
            <div style="max-width: 600px; margin: 0 auto; padding: 30px; border: 1.5px solid #e2e8f0; border-radius: 12px; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                <h2 style="color: #00409A; font-weight: bold; margin-bottom: 20px; font-size: 1.5rem; border-bottom: 2px solid #edf2f7; padding-bottom: 10px;">Notificación de Novedad - SIGEX</h2>
                <p>Estimado/a <strong>{usuario.nombre}</strong>,</p>
                <p>Le informamos sobre la siguiente novedad en su expediente:</p>
                
                <div style="background-color: #f7fafc; border-left: 4px solid #00409A; padding: 15px 20px; margin: 20px 0; border-radius: 0 8px 8px 0; font-size: 0.95rem; color: #2d3748;">
                    {mensaje}
                </div>
                
                <p>Para ver los detalles completos, por favor ingrese a su portal de cliente en el siguiente enlace:</p>
                <div style="margin: 30px 0; text-align: center;">
                    <a href="http://localhost:5000/dashboard" style="background-color: #00409A; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; box-shadow: 0 4px 6px rgba(0,64,154,0.25);">
                        Acceder al Portal de Cliente
                    </a>
                </div>
                
                <hr style="border: 0; border-top: 1px solid #edf2f7; margin: 25px 0;">
                <p style="font-size: 0.8rem; color: #718096; text-align: center;">Este es un mensaje automático generado por el portal SIGEX de Rosado Méndez. Por favor, no responda a este correo.</p>
            </div>
        </body>
    </html>
    """
    
    server = current_app.config.get('MAIL_SERVER')
    port = current_app.config.get('MAIL_PORT')
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    use_tls = current_app.config.get('MAIL_USE_TLS', True)
    
    if not username or not password:
        print("\n" + "="*80)
        print(" [SIMULACIÓN DESARROLLO] CORREO DE NOTIFICACIÓN DE NOVEDAD")
        print(f" Para: {usuario.email}")
        print(f" Asunto: {subject}")
        print(f" Mensaje: {mensaje}")
        print("="*80 + "\n")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = usuario.email
        
        part = MIMEText(body_html, 'html')
        msg.attach(part)
        
        smtp = smtplib.SMTP(server, port, timeout=10)
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.sendmail(sender, [usuario.email], msg.as_string())
        smtp.quit()
        return True
    except Exception as e:
        print(f"Error SMTP al enviar email de notificación de novedad: {str(e)}")
        print("\n" + "="*80)
        print(" [FALLBACK DESARROLLO - ERROR SMTP] CORREO DE NOTIFICACIÓN DE NOVEDAD")
        print(f" Para: {usuario.email}")
        print(f" Asunto: {subject}")
        print(f" Mensaje: {mensaje}")
        print("="*80 + "\n")
        return False

