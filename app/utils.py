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
