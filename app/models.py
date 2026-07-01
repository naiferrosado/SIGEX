from app import db
from flask_login import UserMixin
from datetime import datetime
import pytz

# Configurar la zona horaria de República Dominicana según el RF-PRO-001 [cite: 54, 84]
tz_rd = pytz.timezone('America/Santo_Domingo')

def rd_now():
    return datetime.now(tz_rd)

# 1. SEGURIDAD Y AUTENTICACIÓN

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    

    rol = db.Column(db.String(50), nullable=False) # 'Socio', 'Asociado', 'Paralegal', 'Administrador', 'Cliente'
    activo = db.Column(db.Boolean, nullable=False, default=True)
    requiere_cambio_password = db.Column(db.Boolean, nullable=False, default=True)

    # Propiedades helper
    @property
    def is_personal(self):
        return self.rol in ['Socio', 'Asociado', 'Paralegal', 'Administrador']

    @property
    def is_cliente(self):
        return self.rol == 'Cliente'


class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    rnc_cedula = db.Column(db.String(11), unique=True, nullable=False)
    nombres = db.Column(db.String(150),  nullable=False) 
    apellidos = db.Column(db.String(150),  nullable=False) 
    
    # --- NUEVOS CAMPOS ---
    tipo_cliente = db.Column(db.String(50), nullable=False, default='Persona física')
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    direccion = db.Column(db.Text, nullable=True)
    # ---------------------
    
    telefono = db.Column(db.String(20), nullable=True)
    email_contacto = db.Column(db.String(150), nullable=False)
    consentimiento_datos = db.Column(db.Boolean, nullable=False, default=False)
    fecha_consentimiento = db.Column(db.DateTime(timezone=True), nullable=True)
    
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)

    expedientes = db.relationship(
    'Expediente',
    backref='cliente',
    lazy=True)
    facturas = db.relationship('FacturaHonorario', backref='cliente', lazy=True)
    
    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}"

# TABLA PADRE (Datos comunes a todos los expedientes)
class Expediente(db.Model):
    __tablename__ = 'expedientes'

    id = db.Column(db.Integer, primary_key=True)
    codigo_firma = db.Column(db.String(50), unique=True, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False)
    
    # NUEVO: ¿Qué abogado de la firma lleva el caso? (Asignación interna)
    abogado_responsable_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True)
    
    nombre_caso = db.Column(db.String(255), nullable=False)
    
    # NUEVO: ¿A quién representamos? (Demandante, Demandado, Querellante, Imputado, Solicitante)
    rol_firma = db.Column(db.String(50), nullable=False) 
    
    tipo_tramite = db.Column(db.String(50), nullable=False) 
    estado = db.Column(db.String(20), nullable=False, default='Abierto')
    fecha_apertura = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    fecha_cierre = db.Column(db.DateTime(timezone=True), nullable=True) # Para auditoría

    # Relaciones base
    documentos = db.relationship('Documento', backref='expediente', lazy=True, cascade="all, delete-orphan")
    tiempos = db.relationship('BitacoraTiempoTarea', backref='expediente', lazy=True)
    auditorias = db.relationship('BitacoraAuditoria', backref='expediente_afectado', lazy=True)
    abogado_responsable = db.relationship(
    'Usuario',
    foreign_keys=[abogado_responsable_id])

    __mapper_args__ = {
        'polymorphic_on': tipo_tramite,
        'polymorphic_identity': 'Base'
    }


# TABLA HIJA: Vía Jurisdiccional / Litigio
class ExpedienteJudicial(Expediente):
    __tablename__ = 'expedientes_judiciales'
    id = db.Column(db.Integer, db.ForeignKey('expedientes.id', ondelete='CASCADE'), primary_key=True)

    rama_derecho = db.Column(db.String(100))
    sub_categoria = db.Column(db.String(100))
    tipo_accion = db.Column(db.String(100))
    
    # NUEVO: Instancia actual (Ej: Juzgado de Paz, Primera Instancia, Corte de Apelación, Suprema Corte)
    jurisdiccion_actual = db.Column(db.String(100))
    tribunal_asignado = db.Column(db.String(150))
    numero_expediente_tribunal = db.Column(db.String(100))
    juez_asignado = db.Column(db.String(150))
    
    # NUEVO: Datos de la contraparte
    nombre_contraparte = db.Column(db.String(200))
    contacto_contraparte = db.Column(db.String(150)) # Tel/Dirección para el alguacil inicial
    abogado_contraparte = db.Column(db.String(200))
    contacto_abogado_contraparte = db.Column(db.String(150)) # Tel/Correo para negociaciones
    
    # NUEVO: Aspecto financiero del litigio (Monto demandado)
    monto_demanda = db.Column(db.Numeric(15, 2), nullable=True) # Maneja montos exactos con decimales

    fecha_audiencia = db.Column(db.Date, nullable=True)
    hora_audiencia = db.Column(db.Time, nullable=True)

    alertas_plazos = db.relationship('AlertaPlazoAudiencia', backref='expediente_judicial', lazy=True, cascade="all, delete-orphan")

    __mapper_args__ = {
        'polymorphic_identity': 'Judicial'
    }


# TABLA HIJA: Vía Administrativa / Consultoría
class ExpedienteAdministrativo(Expediente):
    __tablename__ = 'expedientes_administrativos'
    id = db.Column(db.Integer, db.ForeignKey('expedientes.id', ondelete='CASCADE'), primary_key=True)

    tipo_proceso = db.Column(db.String(100))  
    sub_proceso = db.Column(db.String(100))   
    
    # NUEVO: Ej: DGII, ONAPI, DGM, JCE, Ayuntamientos
    institucion_encargada = db.Column(db.String(150)) 
    
    # NUEVO: Número oficial que da la institución al someter el trámite
    numero_solicitud_oficial = db.Column(db.String(100), nullable=True)
    
    descripcion_tramite = db.Column(db.Text)
    
    # NUEVO: Control de impuestos pagados para el trámite
    monto_tasas_impuestos = db.Column(db.Numeric(12, 2), nullable=True, default=0.00)

    requisitos = db.relationship('RequisitoAdministrativo', backref='expediente_admin', lazy=True, cascade="all, delete-orphan")

    __mapper_args__ = {
        'polymorphic_identity': 'Administrativo'
    }

class RequisitoAdministrativo(db.Model):
    __tablename__ = 'requisitos_administrativos'

    id = db.Column(db.Integer, primary_key=True)
    expediente_id = db.Column(db.Integer, db.ForeignKey('expedientes_administrativos.id', ondelete='CASCADE'), nullable=False)
    
    descripcion = db.Column(db.String(255), nullable=False) 
    
    # NUEVO:  para flujos de documentos legales
    requiere_legalizacion = db.Column(db.Boolean, default=False) # Ej: Procuraduría, MIREX
    requiere_apostilla = db.Column(db.Boolean, default=False)
    requiere_traduccion = db.Column(db.Boolean, default=False)
    
    estado = db.Column(db.String(50), nullable=False, default='Pendiente') 
    observaciones = db.Column(db.Text, nullable=True) 

    fecha_creacion = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    fecha_completado = db.Column(db.DateTime(timezone=True), nullable=True)

class AlertaPlazoAudiencia(db.Model):
    __tablename__ = 'alertas_plazos_audiencias'

    id = db.Column(db.Integer, primary_key=True)
    # ON DELETE CASCADE
    expediente_id = db.Column(db.Integer, db.ForeignKey('expedientes.id', ondelete='CASCADE'), nullable=False)
    titulo_hito = db.Column(db.String(255), nullable=False)
    fecha_vencimiento = db.Column(db.DateTime(timezone=True), nullable=False)
    estado_alerta = db.Column(db.String(20), nullable=False, default='Pendiente') # 'Pendiente', 'Atendida', 'Escalada'
    fuente_origen = db.Column(db.String(30), nullable=False) # 'Firma', 'Poder Judicial'

# 3. MOTOR DOCUMENTAL Y VERSIONES

class TipoDocumento(db.Model):
    __tablename__ = 'tipos_documentos'

    id = db.Column(db.Integer, primary_key=True)
    nombre_tipo = db.Column(db.String(100), unique=True, nullable=False)
    
    # Relaciones
    documentos = db.relationship('Documento', backref='categoria', lazy=True)


class Documento(db.Model):
    __tablename__ = 'documentos'

    id = db.Column(db.Integer, primary_key=True)
    # ON DELETE CASCADE: Si se borra el expediente, se borran sus documentos
    expediente_id = db.Column(db.Integer, db.ForeignKey('expedientes.id', ondelete='CASCADE'), nullable=False)
    # ON DELETE RESTRICT: No se puede borrar un tipo si hay documentos usándolo
    tipo_documento_id = db.Column(db.Integer, db.ForeignKey('tipos_documentos.id', ondelete='RESTRICT'), nullable=False)
    visibilidad = db.Column(db.String(30), nullable=False, default='Interno') # 'Interno', 'Compartido'

    # Relaciones
    versiones = db.relationship('VersionDocumento', backref='documento_maestro', lazy=True, cascade="all, delete-orphan")


class VersionDocumento(db.Model):
    __tablename__ = 'versiones_documentos'

    id = db.Column(db.Integer, primary_key=True)
    # ON DELETE CASCADE: Si se borra el documento lógico, se borran sus versiones físicas
    documento_id = db.Column(db.Integer, db.ForeignKey('documentos.id', ondelete='CASCADE'), nullable=False)
    # ON DELETE RESTRICT: No se puede borrar un usuario si tiene versiones subidas
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    
    version_numero = db.Column(db.String(10), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    fecha_carga = db.Column(db.DateTime(timezone=True), nullable=False, default=rd_now)
    tamano_bytes = db.Column(db.BigInteger, nullable=False)
    ruta_almacenamiento = db.Column(db.String(500), nullable=False)
    es_firmado = db.Column(db.Boolean, nullable=False, default=False)
    hash_firma = db.Column(db.String(512), nullable=True)

# 4. TIEMPOS Y FACTURACIÓN (LEY 32-23)

class BitacoraTiempoTarea(db.Model):
    __tablename__ = 'bitacora_tiempos_tareas'

    id = db.Column(db.Integer, primary_key=True)
    # ON DELETE RESTRICT
    expediente_id = db.Column(db.Integer, db.ForeignKey('expedientes.id', ondelete='RESTRICT'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    fecha_tarea = db.Column(db.Date, nullable=False)
    horas_trabajadas = db.Column(db.Numeric(5, 2), nullable=False) # Evita pérdida de decimales
    descripcion_gestion = db.Column(db.Text, nullable=False)
    estado_cierre = db.Column(db.String(20), nullable=False, default='Abierto') # 'Abierto', 'Aprobado', 'Facturado'


class FacturaHonorario(db.Model):
    __tablename__ = 'facturas_honorarios'

    id = db.Column(db.Integer, primary_key=True)
    # ON DELETE RESTRICT
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False)
    ncf = db.Column(db.String(13), unique=True, nullable=True)
    tipo_comprobante = db.Column(db.String(2), nullable=False) # Ej: '31', '32'
    monto_subtotal = db.Column(db.Numeric(18, 2), nullable=False)
    monto_itbis = db.Column(db.Numeric(18, 2), nullable=False) # Cálculo exacto fiscal
    monto_total = db.Column(db.Numeric(18, 2), nullable=False)
    fecha_emision = db.Column(db.DateTime(timezone=True), nullable=False, default=rd_now)
    estado_pago = db.Column(db.String(20), nullable=False, default='Pendiente') # 'Pendiente', 'Cobrado', 'Anulado'

# 5. AUDITORÍA FORENSE

class BitacoraAuditoria(db.Model):
    __tablename__ = 'bitacora_auditoria'

    id = db.Column(db.BigInteger, primary_key=True) # BIGINT para millones de registros
    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False, default=rd_now)
    # ON DELETE RESTRICT
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    # ON DELETE CASCADE
    expediente_id = db.Column(db.Integer, db.ForeignKey('expedientes.id', ondelete='CASCADE'), nullable=True)
    accion_realizada = db.Column(db.String(50), nullable=False)
    detalles_tecnicos = db.Column(db.Text, nullable=False)
    ip_direccion = db.Column(db.String(45), nullable=False) # Soporta IPv4 e IPv6 [cite: 231, 275]
    dispositivo_info = db.Column(db.String(255), nullable=False)