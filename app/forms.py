from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, Optional, Length
from wtforms import DateField, TextAreaField

# FORMULARIO DE SEGURIDAD PARA EL LOGIN
class LoginForm(FlaskForm):
    email = StringField('Correo Institucional', validators=[
        DataRequired(message="El correo es obligatorio."), 
        Email(message="Ingrese un formato de correo válido.")
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message="La contraseña es obligatoria.")
    ])
    recordarme = BooleanField('Recordarme')
    submit = SubmitField('Iniciar')


# FORMULARIO DE SEGURIDAD PARA CLIENTES
class ClienteForm(FlaskForm):
    tipo_cliente = SelectField('Tipo de Cliente', choices=[
        ('Persona física', 'Persona física'), 
        ('Persona jurídica', 'Persona jurídica')
    ])
    nombre = StringField('Nombre(s)', validators=[
        DataRequired(message="El nombre es obligatorio.")
    ])
    apellido = StringField('Apellido(s)', validators=[
        DataRequired(message="El apellido es obligatorio.")
    ])
    rnc_cedula = StringField('Cédula / RNC', validators=[
        DataRequired(message="La cédula o RNC es obligatoria."),
        Length(min=9, max=13, message="La cédula o RNC debe tener entre 9 y 13 caracteres.")
    ])
    telefono = StringField('Teléfono', validators=[Optional()])
    email_contacto = StringField('Correo Electrónico', validators=[
        DataRequired(message="El correo de contacto es obligatorio."),
        Email(message="Ingrese un formato de correo válido.")
    ])
    fecha_nacimiento = DateField('Fecha de Nacimiento', format='%Y-%m-%d', validators=[Optional()])
    direccion = TextAreaField('Dirección Física', validators=[Optional(), Length(max=500)])
    consentimiento = BooleanField('Autorización Ley 172-13')
    submit = SubmitField('Guardar Cliente')


# --- FORMULARIO DE SEGURIDAD PARA USUARIOS ---
class UsuarioForm(FlaskForm):
    nombre = StringField('Nombre Completo', validators=[
        DataRequired(message="El nombre es obligatorio.")
    ])
    email = StringField('Correo Electrónico', validators=[
        DataRequired(message="El correo es obligatorio."),
        Email(message="Ingrese un formato de correo válido.")
    ])
    rol = SelectField('Rol en el Sistema', choices=[
        ('Administrador', 'Administrador'),
        ('Socio', 'Socio'),
        ('Asociado', 'Asociado'),
        ('Paralegal', 'Paralegal'),
        ('Cliente', 'Cliente')
    ])
    # Opcional en el form. La ruta de "agregar" validará si está vacío.
    password = PasswordField('Contraseña', validators=[Optional(), Length(min=6, message="La clave debe tener al menos 6 caracteres.")])
    submit = SubmitField('Guardar Usuario')