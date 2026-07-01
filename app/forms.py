from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, DateField, TimeField, PasswordField, BooleanField, SubmitField, SelectField
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


# FORMULARIO PADRE (Campos comunes)
class ExpedienteBaseForm(FlaskForm):
    # Usamos coerce=int porque los IDs de la base de datos son números enteros
    cliente_id = SelectField('Cliente', coerce=int, validators=[DataRequired(message="Debe seleccionar un cliente.")])
    abogado_responsable_id = SelectField('Abogado Responsable', coerce=int, validators=[Optional()])
    
    nombre_caso = StringField('Nombre del Caso / Expediente', validators=[
        DataRequired(message="El nombre del caso es obligatorio."),
        Length(max=255)
    ])
    
    rol_firma = SelectField('Rol de la Firma', choices=[
        ('', 'Seleccione un rol...'),
        ('Demandante', 'Demandante / Querellante / Actor Civil'),
        ('Demandado', 'Demandado / Imputado / Civilmente Responsable'),
        ('Solicitante', 'Solicitante / Peticionario'),
        ('Tercero', 'Tercero Interviniente')
    ], validators=[DataRequired(message="Especifique el rol de la firma.")])


# FORMULARIO HIJO: LITIGIO
class ExpedienteJudicialForm(ExpedienteBaseForm):
    cliente_id = SelectField(
        'Cliente',
        coerce=int,
        validators=[DataRequired(message='Debe seleccionar un cliente.')]
    )
    abogado_responsable_id = SelectField(
        'Abogado responsable',
        coerce=int,
        validators=[Optional()]
    )
    rama_derecho = SelectField('Rama del Derecho', choices=[
        ('Civil', 'Civil'),
        ('Penal', 'Penal'),
        ('Laboral', 'Laboral'),
        ('Inmobiliario', 'Inmobiliario'),
        ('Familia', 'Familia')
    ], validators=[Optional()])
    
    sub_categoria = StringField('Sub-categoría (Ej. Delitos contra la propiedad)', validators=[Optional(), Length(max=100)])
    tipo_accion = StringField('Tipo de Acción (Ej. Robo, Divorcio)', validators=[Optional(), Length(max=100)])
    
    jurisdiccion_actual = SelectField('Instancia Actual', choices=[
        ('Juzgado de Paz', 'Juzgado de Paz'),
        ('Primera Instancia', 'Primera Instancia'),
        ('Corte de Apelacion', 'Corte de Apelación'),
        ('Suprema Corte', 'Suprema Corte de Justicia'),
        ('Tribunal Constitucional', 'Tribunal Constitucional')
    ], validators=[Optional()])
    
    tribunal_asignado = StringField('Tribunal (Ej. 1ra Sala Cámara Civil)', validators=[Optional(), Length(max=150)])
    numero_expediente_tribunal = StringField('Número de Expediente (Tribunal)', validators=[Optional(), Length(max=100)])
    juez_asignado = StringField('Juez Asignado', validators=[Optional(), Length(max=150)])
    
    # Datos de la Contraparte
    nombre_contraparte = StringField('Nombre Contraparte', validators=[Optional(), Length(max=200)])
    contacto_contraparte = StringField('Contacto Contraparte (Para Alguacil)', validators=[Optional(), Length(max=150)])
    abogado_contraparte = StringField('Abogado Contraparte', validators=[Optional(), Length(max=200)])
    contacto_abogado_contraparte = StringField('Contacto Abogado Contraparte', validators=[Optional(), Length(max=150)])
    
    monto_demanda = DecimalField('Monto Involucrado (RD$)', places=2, validators=[Optional()])
    
    fecha_audiencia = DateField('Fecha de Próxima Audiencia', format='%Y-%m-%d', validators=[Optional()])
    hora_audiencia = TimeField('Hora', format='%H:%M', validators=[Optional()])

    submit_judicial = SubmitField('Crear Expediente Judicial')


# FORMULARIO HIJO: ADMINISTRATIVO
class ExpedienteAdministrativoForm(ExpedienteBaseForm):
    tipo_proceso = SelectField('Tipo de Trámite', choices=[
        ('Migratorio', 'Migratorio'),
        ('Impuestos', 'Impuestos / DGII'),
        ('Corporativo', 'Corporativo / Mercantil'),
        ('Propiedad Intelectual', 'Propiedad Intelectual (ONAPI)')
    ], validators=[Optional()])
    
    sub_proceso = StringField('Sub-proceso (Ej. Residencia Temporal)', validators=[Optional(), Length(max=100)])
    institucion_encargada = StringField('Institución (Ej. DGM, DGII, ONAPI)', validators=[Optional(), Length(max=150)])
    numero_solicitud_oficial = StringField('Número de Solicitud (Ticket)', validators=[Optional(), Length(max=100)])
    
    descripcion_tramite = TextAreaField('Descripción del Trámite', validators=[Optional()])
    monto_tasas_impuestos = DecimalField('Total Tasas/Impuestos (RD$)', places=2, validators=[Optional()])

    submit_admin = SubmitField('Crear Expediente Administrativo')