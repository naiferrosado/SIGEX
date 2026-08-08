import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash

# Asegurar que el path del proyecto esté en python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import (
    Usuario, Cliente, Expediente, ExpedienteJudicial, ExpedienteAdministrativo,
    MateriaLegal, ProcedimientoLegal, AlertaPlazoAudiencia, RequisitoAdministrativo,
    Documento, VersionDocumento, Carpeta, Tarea, NotificacionInterna,
    RegistroEnvioAlerta, Presupuesto, PresupuestoDetalle, ContratoHonorarios,
    CronogramaCobro, FacturaHonorario, DetalleFactura, TransaccionPago,
    ReciboInterno, GastoReembolsable, BitacoraTiempoTarea, BitacoraAuditoria,
    TipoDocumento, expediente_abogados, tarea_asignados
)

app = create_app()

with app.app_context():
    print("Iniciando limpieza de la base de datos de manera ordenada...")

    # 1. ELIMINACIÓN DE REGISTROS EXISTENTES (EVITA CONFLICTOS DE CLAVES ÚNICAS O REFERENCIAS)
    db.session.query(BitacoraAuditoria).delete()
    db.session.query(BitacoraTiempoTarea).delete()
    db.session.query(TransaccionPago).delete()
    db.session.query(ReciboInterno).delete()
    db.session.query(GastoReembolsable).delete()
    db.session.query(CronogramaCobro).delete()
    db.session.query(DetalleFactura).delete()
    db.session.query(FacturaHonorario).delete()
    db.session.query(ContratoHonorarios).delete()
    db.session.query(PresupuestoDetalle).delete()
    db.session.query(Presupuesto).delete()
    db.session.query(NotificacionInterna).delete()
    db.session.query(RegistroEnvioAlerta).delete()

    db.session.execute(tarea_asignados.delete())
    db.session.query(Tarea).delete()
    db.session.query(AlertaPlazoAudiencia).delete()
    db.session.query(RequisitoAdministrativo).delete()

    db.session.query(VersionDocumento).delete()
    db.session.query(Documento).delete()
    db.session.query(Carpeta).delete()

    db.session.execute(expediente_abogados.delete())
    db.session.query(ExpedienteJudicial).delete()
    db.session.query(ExpedienteAdministrativo).delete()
    db.session.query(Expediente).delete()

    # Desvincular perfiles de usuario antes de borrar clientes
    for c in Cliente.query.all():
        c.usuario_id = None
    db.session.commit()

    db.session.query(Cliente).delete()
    db.session.query(Usuario).filter(Usuario.email != 'naiferrosado@rosadomendez.com').delete()
    db.session.commit()

    print("Limpieza de base de datos terminada.")

    # 2. ASEGURAR ADMINISTRADOR PRINCIPAL
    admin = Usuario.query.filter_by(email='naiferrosado@rosadomendez.com').first()
    if not admin:
        admin = Usuario(
            nombre='Naifer Rosado',
            email='naiferrosado@rosadomendez.com',
            password_hash=generate_password_hash('naiferrosado123'),
            rol='Administrador',
            activo=True,
            requiere_cambio_password=False
        )
        db.session.add(admin)
        db.session.commit()
        print("Administrador principal 'Naifer Rosado' creado exitosamente.")
    else:
        print("Administrador principal existente conservado.")

    users_db = {}
    users_db['naiferrosado@rosadomendez.com'] = admin

    # 3. SEED USARIOS DE STAFF (Socio, Asociado, Paralegal, Administrador)
    usuarios_staff = [
        {"nombre": "Lic. Carlos Mendoza", "email": "carlos.mendoza@rosadomendez.com", "rol": "Socio", "salario_base": 120000.00, "porcentaje_comision": 15.00},
        {"nombre": "Dra. Laura Vásquez", "email": "laura.vasquez@rosadomendez.com", "rol": "Asociado", "salario_base": 85000.00, "porcentaje_comision": 10.00},
        {"nombre": "Dr. Alejandro Ruiz", "email": "alejandro.ruiz@rosadomendez.com", "rol": "Asociado", "salario_base": 80000.00, "porcentaje_comision": 8.00},
        {"nombre": "Julio Peralta", "email": "julio.peralta@rosadomendez.com", "rol": "Paralegal", "salario_base": 45000.00, "porcentaje_comision": 0.00},
        {"nombre": "Sofía Castro", "email": "sofia.castro@rosadomendez.com", "rol": "Paralegal", "salario_base": 40000.00, "porcentaje_comision": 0.00},
        {"nombre": "Clara Guzmán", "email": "clara.guzman@rosadomendez.com", "rol": "Administrador", "salario_base": 60000.00, "porcentaje_comision": 0.00}
    ]

    for u in usuarios_staff:
        nuevo_u = Usuario(
            nombre=u["nombre"],
            email=u["email"],
            password_hash=generate_password_hash('password123'),
            rol=u["rol"],
            activo=True,
            requiere_cambio_password=False,
            salario_base=Decimal(str(u["salario_base"])),
            porcentaje_comision=Decimal(str(u["porcentaje_comision"]))
        )
        db.session.add(nuevo_u)
        db.session.commit()
        users_db[u["email"]] = nuevo_u
        print(f"Usuario Staff {u['nombre']} ({u['rol']}) creado.")

    # 4. SEED USUARIOS CLIENTES (Para que los clientes puedan ingresar)
    client_emails = [
        "ricardo.almonte@metropolis.com.do",
        "egomez@inmobiliariasd.com",
        "fespinal@agrocibao.com.do",
        "rtejada@gmail.com",
        "anapatricia@hotmail.com"
    ]

    client_users_db = {}
    for email in client_emails:
        nombre_sug = email.split('@')[0].replace('.', ' ').title()
        c_user = Usuario(
            nombre=nombre_sug,
            email=email,
            password_hash=generate_password_hash('cliente123'),
            rol='Cliente',
            activo=True,
            requiere_cambio_password=False
        )
        db.session.add(c_user)
        db.session.commit()
        client_users_db[email] = c_user
        print(f"Usuario Cliente {c_user.nombre} ({c_user.email}) creado.")

    # 5. SEED CLIENTES (Empresas y Personas Físicas)
    clientes_datos = [
        {
            "rnc_cedula": "131985472",
            "nombres": "Constructora Metrópolis",
            "apellidos": "S.R.L.",
            "tipo_cliente": "Persona jurídica",
            "direccion": "Av. Gustavo Mejía Ricart #83, Ensanche Naco, Santo Domingo",
            "telefono": "809-540-1234",
            "email_contacto": "ricardo.almonte@metropolis.com.do",
            "consentimiento_datos": True,
            "usuario_id": client_users_db["ricardo.almonte@metropolis.com.do"].id
        },
        {
            "rnc_cedula": "101029384",
            "nombres": "Inmobiliaria Santo Domingo",
            "apellidos": "S.A.",
            "tipo_cliente": "Persona jurídica",
            "direccion": "Av. Abraham Lincoln #1012, Piantini, Santo Domingo",
            "telefono": "809-565-9876",
            "email_contacto": "egomez@inmobiliariasd.com",
            "consentimiento_datos": True,
            "usuario_id": client_users_db["egomez@inmobiliariasd.com"].id
        },
        {
            "rnc_cedula": "130987654",
            "nombres": "Agropecuaria del Cibao",
            "apellidos": "S.R.L.",
            "tipo_cliente": "Persona jurídica",
            "direccion": "Autopista Duarte Km 5, Santiago de los Caballeros",
            "telefono": "809-582-4567",
            "email_contacto": "fespinal@agrocibao.com.do",
            "consentimiento_datos": True,
            "usuario_id": client_users_db["fespinal@agrocibao.com.do"].id
        },
        {
            "rnc_cedula": "00112345678",
            "nombres": "Roberto",
            "apellidos": "Tejada Núñez",
            "tipo_cliente": "Persona física",
            "direccion": "Calle Rafael Augusto Sánchez #22, Evaristo Morales, Santo Domingo",
            "telefono": "829-450-9823",
            "email_contacto": "rtejada@gmail.com",
            "consentimiento_datos": True,
            "usuario_id": client_users_db["rtejada@gmail.com"].id
        },
        {
            "rnc_cedula": "00298765432",
            "nombres": "Ana Patricia",
            "apellidos": "Medina Rivas",
            "tipo_cliente": "Persona física",
            "direccion": "Calle El Sol #150, Santiago de los Caballeros",
            "telefono": "809-583-1122",
            "email_contacto": "anapatricia@hotmail.com",
            "consentimiento_datos": True,
            "usuario_id": client_users_db["anapatricia@hotmail.com"].id
        },
        {
            "rnc_cedula": "03100234561",
            "nombres": "Sonia Altagracia",
            "apellidos": "Guerrero Bello",
            "tipo_cliente": "Persona física",
            "direccion": "Av. Estrella Sadhalá #45, Santiago",
            "telefono": "849-200-3456",
            "email_contacto": "s.guerrero@gmail.com",
            "consentimiento_datos": True,
            "usuario_id": None
        },
        {
            "rnc_cedula": "132543210",
            "nombres": "Inversiones Turísticas Las Terrenas",
            "apellidos": "S.A.S.",
            "tipo_cliente": "Persona jurídica",
            "direccion": "Calle Principal, Las Terrenas, Samaná",
            "telefono": "809-240-6789",
            "email_contacto": "jp.dupont@lasterrenastur.com",
            "consentimiento_datos": True,
            "usuario_id": None
        },
        {
            "rnc_cedula": "40212345678",
            "nombres": "Marcos Antonio",
            "apellidos": "Rosario Cruz",
            "tipo_cliente": "Persona física",
            "direccion": "Av. República de Colombia #45, Altos de Arroyo Hondo, Santo Domingo",
            "telefono": "829-995-1234",
            "email_contacto": "marcos.rosario@gmail.com",
            "consentimiento_datos": True,
            "usuario_id": None
        },
        {
            "rnc_cedula": "102876543",
            "nombres": "Tecnología Médica Dominicana",
            "apellidos": "S.R.L.",
            "tipo_cliente": "Persona jurídica",
            "direccion": "Av. Rómulo Betancourt #1450, Bella Vista, Santo Domingo",
            "telefono": "809-482-3000",
            "email_contacto": "cpou@tecmed.com.do",
            "consentimiento_datos": True,
            "usuario_id": None
        },
        {
            "rnc_cedula": "00118273645",
            "nombres": "Lucía María",
            "apellidos": "Santos Ventura",
            "tipo_cliente": "Persona física",
            "direccion": "Calle Palo Hincado #405, Zona Colonial, Santo Domingo",
            "telefono": "829-333-4455",
            "email_contacto": "lucia.santos@gmail.com",
            "consentimiento_datos": True,
            "usuario_id": None
        }
    ]

    clients_db = []
    for c in clientes_datos:
        nuevo_c = Cliente(
            rnc_cedula=c["rnc_cedula"],
            nombres=c["nombres"],
            apellidos=c["apellidos"],
            tipo_cliente=c["tipo_cliente"],
            fecha_nacimiento=date(1985, 6, 15) if c["tipo_cliente"] == "Persona física" else None,
            direccion=c["direccion"],
            telefono=c["telefono"],
            email_contacto=c["email_contacto"],
            consentimiento_datos=c["consentimiento_datos"],
            fecha_consentimiento=datetime.utcnow(),
            usuario_id=c["usuario_id"]
        )
        db.session.add(nuevo_c)
        db.session.commit()
        clients_db.append(nuevo_c)
        print(f"Cliente '{nuevo_c.nombre_completo}' creado.")

    # 6. OBTENER MATERIAS Y PROCEDIMIENTOS MIGRATORIOS / CIVILES / PENALES
    civil_materia = MateriaLegal.query.filter_by(nombre="Civil").first()
    familia_materia = MateriaLegal.query.filter_by(nombre="Familia").first()
    penal_materia = MateriaLegal.query.filter_by(nombre="Penal").first()
    laboral_materia = MateriaLegal.query.filter_by(nombre="Laboral").first()
    comercial_materia = MateriaLegal.query.filter_by(nombre="Comercial").first()
    
    migratorio_materia = MateriaLegal.query.filter_by(nombre="Migratorio").first()
    onapi_materia = MateriaLegal.query.filter_by(nombre="ONAPI").first()
    rm_materia = MateriaLegal.query.filter_by(nombre="Registro Mercantil").first()
    dgii_materia = MateriaLegal.query.filter_by(nombre="DGII").first()
    
    civil_proc = ProcedimientoLegal.query.filter_by(materia_id=civil_materia.id).first() if civil_materia else None
    familia_proc = ProcedimientoLegal.query.filter_by(materia_id=familia_materia.id).first() if familia_materia else None
    penal_proc = ProcedimientoLegal.query.filter_by(materia_id=penal_materia.id).first() if penal_materia else None
    laboral_proc = ProcedimientoLegal.query.filter_by(materia_id=laboral_materia.id).first() if laboral_materia else None
    
    migratorio_proc = ProcedimientoLegal.query.filter_by(materia_id=migratorio_materia.id).first() if migratorio_materia else None
    onapi_proc = ProcedimientoLegal.query.filter_by(materia_id=onapi_materia.id).first() if onapi_materia else None
    rm_proc = ProcedimientoLegal.query.filter_by(materia_id=rm_materia.id).first() if rm_materia else None
    dgii_proc = ProcedimientoLegal.query.filter_by(materia_id=dgii_materia.id).first() if dgii_materia else None

    # Abogados responsables del personal
    lawyers = [
        users_db['naiferrosado@rosadomendez.com'],
        users_db['carlos.mendoza@rosadomendez.com'],
        users_db['laura.vasquez@rosadomendez.com'],
        users_db['alejandro.ruiz@rosadomendez.com']
    ]
    paralegals = [
        users_db['julio.peralta@rosadomendez.com'],
        users_db['sofia.castro@rosadomendez.com']
    ]

    expedientes_db = []

    # 7. SEED EXPEDIENTES JUDICIALES (LITIGIOS)
    judicial_cases_data = [
        {
            "cliente_idx": 0, "nombre_caso": "Demanda Civil por Incumplimiento de Contrato - Metrópolis vs. Haché",
            "rol_firma": "Demandante", "rama_derecho": "Civil", "sub_categoria": "Incumplimiento de Contrato",
            "tipo_accion": "Demanda ordinaria bajo daños y perjuicios contractuales",
            "jurisdiccion_actual": "Cámara Civil de Primera Instancia",
            "tribunal_asignado": "Primera Sala de la Cámara Civil y Comercial del Juzgado de Primera Instancia del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-ECIV-01582", "juez_asignado": "Dra. Katherine Martínez",
            "nombre_contraparte": "Almacenes Haché & Co.", "contacto_contraparte": "Av. John F. Kennedy, Santo Domingo",
            "abogado_contraparte": "Dr. Frank Valdez", "contacto_abogado_contraparte": "809-555-4321 / fvaldez@valdezlaw.com",
            "monto_demanda": 15500000.00, "materia": civil_materia, "procedimiento": civil_proc,
            "prioridad": "Alta", "riesgo": "Medio", "exito": "Alta", "esquema_cobro": "Mixto", "tarifa_monto": 250000.00, "porcentaje_exito": 10.00
        },
        {
            "cliente_idx": 1, "nombre_caso": "Litis sobre Derechos Registrados - Inmobiliaria SD vs. Sucesión Pérez",
            "rol_firma": "Demandado", "rama_derecho": "Civil", "sub_categoria": "Litis de propiedad",
            "tipo_accion": "Litis sobre derechos registrados por presunta superposición de áreas",
            "jurisdiccion_actual": "Jurisdicción Original",
            "tribunal_asignado": "Tribunal de Jurisdicción Original de Santiago de los Caballeros",
            "numero_expediente_tribunal": "034-2026-ELIT-00892", "juez_asignado": "Lic. Marcos Antonio Cabral",
            "nombre_contraparte": "Sucesión Pérez González", "contacto_contraparte": "Av. Imbert, Santiago",
            "abogado_contraparte": "Dra. Carmen Paulino", "contacto_abogado_contraparte": "809-555-8899 / cpaulino@gmail.com",
            "monto_demanda": 8000000.00, "materia": civil_materia, "procedimiento": civil_proc,
            "prioridad": "Alta", "riesgo": "Alto", "exito": "Media", "esquema_cobro": "Fijo", "tarifa_monto": 400000.00, "porcentaje_exito": 0.00
        },
        {
            "cliente_idx": 3, "nombre_caso": "Divorcio por Incompatibilidad de Caracteres - Tejada vs. Méndez",
            "rol_firma": "Demandante", "rama_derecho": "Familia", "sub_categoria": "Divorcio",
            "tipo_accion": "Demanda en divorcio por incompatibilidad de caracteres y partición de bienes",
            "jurisdiccion_actual": "Cámara Civil (Familia)",
            "tribunal_asignado": "Quinta Sala de la Cámara Civil y Comercial del Distrito Nacional (Asuntos de Familia)",
            "numero_expediente_tribunal": "024-2026-EDIV-00452", "juez_asignado": "Dra. Altagracia Ureña",
            "nombre_contraparte": "Clarissa Méndez Guzmán", "contacto_contraparte": "Calle C, Apt 101, Bella Vista, Santo Domingo",
            "abogado_contraparte": "Lic. Pedro Julio Sánchez", "contacto_abogado_contraparte": "829-555-1212 / pjsanchez@legal.do",
            "monto_demanda": 3000000.00, "materia": familia_materia, "procedimiento": familia_proc,
            "prioridad": "Media", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 150000.00, "porcentaje_exito": 0.00
        },
        {
            "cliente_idx": 4, "nombre_caso": "Querella Penal por Abuso de Confianza contra ex-administrador",
            "rol_firma": "Querellante", "rama_derecho": "Penal", "sub_categoria": "Estafa / Abuso de confianza",
            "tipo_accion": "Querella con constitución en actor civil",
            "jurisdiccion_actual": "Fase de Instrucción",
            "tribunal_asignado": "Segundo Juzgado de la Instrucción de Santiago",
            "numero_expediente_tribunal": "082-2026-EPEN-00234", "juez_asignado": "Dr. Wilson Pichardo",
            "nombre_contraparte": "José Manuel Almonte", "contacto_contraparte": "Villa Olga, Santiago",
            "abogado_contraparte": "Dr. Héctor Gómez", "contacto_abogado_contraparte": "809-555-7654 / hgomez@gomezlaw.do",
            "monto_demanda": 5000000.00, "materia": penal_materia, "procedimiento": penal_proc,
            "prioridad": "Alta", "riesgo": "Alto", "exito": "Media", "esquema_cobro": "Mixto", "tarifa_monto": 300000.00, "porcentaje_exito": 15.00
        },
        {
            "cliente_idx": 2, "nombre_caso": "Demanda Laboral por Dimisión Justificada - Gómez contra Agropecuaria",
            "rol_firma": "Demandado", "rama_derecho": "Laboral", "sub_categoria": "Prestaciones laborales",
            "tipo_accion": "Defensa ante demanda de prestaciones laborales por dimisión justificada",
            "jurisdiccion_actual": "Juzgado de Trabajo",
            "tribunal_asignado": "Segunda Sala del Juzgado de Trabajo de Santiago",
            "numero_expediente_tribunal": "082-2026-ELAB-00561", "juez_asignado": "Dra. Juana María Santos",
            "nombre_contraparte": "Erick Manuel Gómez", "contacto_contraparte": "Licey al Medio, Santiago",
            "abogado_contraparte": "Lic. Miguel Ángel Restituyo", "contacto_abogado_contraparte": "829-555-3434 / mrestituyo@laboral.do",
            "monto_demanda": 1200000.00, "materia": laboral_materia, "procedimiento": laboral_proc,
            "prioridad": "Media", "riesgo": "Medio", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 100000.00, "porcentaje_exito": 0.00
        },
        {
            "cliente_idx": 7, "nombre_caso": "Cobro de Pesos contra Consorcio Constructor Vial",
            "rol_firma": "Demandante", "rama_derecho": "Civil", "sub_categoria": "Cobro de Pesos",
            "tipo_accion": "Demanda en cobro de pesos fundada en facturas aceptadas e impagas",
            "jurisdiccion_actual": "Cámara Civil de Primera Instancia",
            "tribunal_asignado": "Quinta Sala de la Cámara Civil y Comercial del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-ECIV-02451", "juez_asignado": "Lic. Ramón Emilio Rosario",
            "nombre_contraparte": "Consorcio Constructor Vial del Este", "contacto_contraparte": "Av. Luperón #300, Santo Domingo Oeste",
            "abogado_contraparte": "Dr. Fernando Ortiz", "contacto_abogado_contraparte": "809-555-0909 / fortiz@consorciolaw.do",
            "monto_demanda": 4350000.00, "materia": civil_materia, "procedimiento": civil_proc,
            "prioridad": "Alta", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Éxito", "tarifa_monto": 0.00, "porcentaje_exito": 20.00
        },
        {
            "cliente_idx": 9, "nombre_caso": "Acción de Desalojo por Falta de Pago contra Inquilino Moroso",
            "rol_firma": "Demandante", "rama_derecho": "Civil", "sub_categoria": "Desalojo",
            "tipo_accion": "Acción de desalojo ante el Juzgado de Paz por falta de pago y vencimiento de contrato",
            "jurisdiccion_actual": "Juzgado de Paz",
            "tribunal_asignado": "Segundo Juzgado de Paz de la Segunda Circunscripción del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-EPAZ-00120", "juez_asignado": "Dra. Minerva Polanco",
            "nombre_contraparte": "Eduardo Rafael Castro", "contacto_contraparte": "Calle Mercedes #12, Zona Colonial, Santo Domingo",
            "abogado_contraparte": "Pro-Se (Sin abogado registrado)", "contacto_abogado_contraparte": "829-555-8821 / e.castro@gmail.com",
            "monto_demanda": 450000.00, "materia": civil_materia, "procedimiento": civil_proc,
            "prioridad": "Media", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 80000.00, "porcentaje_exito": 0.00
        },
        {
            "cliente_idx": 0, "nombre_caso": "Responsabilidad Civil por Daños Colaterales en Excavación",
            "rol_firma": "Demandado", "rama_derecho": "Civil", "sub_categoria": "Daños y Perjuicios",
            "tipo_accion": "Defensa en demanda de daños y perjuicios interpuesta por vecino colindante",
            "jurisdiccion_actual": "Cámara Civil de Primera Instancia",
            "tribunal_asignado": "Tercera Sala de la Cámara Civil y Comercial del Juzgado de Primera Instancia del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-ECIV-04312", "juez_asignado": "Dr. Fernando Guzmán",
            "nombre_contraparte": "Inversiones Cuesta Hermosa", "contacto_contraparte": "Cuesta Hermosa, Isabel Villas, Santo Domingo",
            "abogado_contraparte": "Lic. Nelson Corporán", "contacto_abogado_contraparte": "809-555-3311 / ncorporan@corporanlaw.do",
            "monto_demanda": 12000000.00, "materia": civil_materia, "procedimiento": civil_proc,
            "prioridad": "Alta", "riesgo": "Alto", "exito": "Media", "esquema_cobro": "Fijo", "tarifa_monto": 250000.00, "porcentaje_exito": 0.00
        }
    ]

    for idx, ej in enumerate(judicial_cases_data):
        client = clients_db[ej["cliente_idx"]]
        lawyer = lawyers[idx % len(lawyers)]
        codigo = f"EXP-JUD-{uuid.uuid4().hex[:5].upper()}"

        nuevo_exp = ExpedienteJudicial(
            codigo_firma=codigo,
            cliente_id=client.id,
            abogado_responsable_id=lawyer.id,
            nombre_caso=ej["nombre_caso"],
            rol_firma=ej["rol_firma"],
            tipo_tramite="Judicial",
            estado="Abierto",
            fecha_apertura=datetime.utcnow() - timedelta(days=idx*15),
            fase_actual=1,
            esquema_cobro=ej["esquema_cobro"],
            tarifa_monto=Decimal(str(ej["tarifa_monto"])),
            porcentaje_exito=Decimal(str(ej["porcentaje_exito"])),
            materia_id=ej["materia"].id if ej["materia"] else None,
            procedimiento_id=ej["procedimiento"].id if ej["procedimiento"] else None,
            prioridad=ej["prioridad"],
            nivel_riesgo=ej["riesgo"],
            probabilidad_exito=ej["exito"],
            origen_cliente="Cliente Recurrente" if idx % 2 == 0 else "Referido",
            fecha_contratacion=(date.today() - timedelta(days=idx*15)),
            valor_estimado_caso=Decimal(str(ej["monto_demanda"] * 0.15)),

            rama_derecho=ej["rama_derecho"],
            sub_categoria=ej["sub_categoria"],
            tipo_accion=ej["tipo_accion"],
            jurisdiccion_actual=ej["jurisdiccion_actual"],
            tribunal_asignado=ej["tribunal_asignado"],
            numero_expediente_tribunal=ej["numero_expediente_tribunal"],
            juez_asignado=ej["juez_asignado"],
            nombre_contraparte=ej["nombre_contraparte"],
            contacto_contraparte=ej["contacto_contraparte"],
            abogado_contraparte=ej["abogado_contraparte"],
            contacto_abogado_contraparte=ej["contacto_abogado_contraparte"],
            monto_demanda=Decimal(str(ej["monto_demanda"]))
        )
        db.session.add(nuevo_exp)
        db.session.commit()
        # Vincular en relación secundaria
        nuevo_exp.abogados.append(lawyer)
        db.session.commit()
        expedientes_db.append(nuevo_exp)
        print(f"Expediente Judicial '{nuevo_exp.nombre_caso}' ({nuevo_exp.codigo_firma}) creado.")

    # 8. SEED EXPEDIENTES ADMINISTRATIVOS
    admin_cases_data = [
        {
            "cliente_idx": 6, "nombre_caso": "Solicitud de Residencia Permanente por Inversión Extranjera - Dupont",
            "rol_firma": "Solicitante", "tipo_proceso": "Derecho Migratorio", "sub_proceso": "Residencia de Inversor",
            "institucion_encargada": "Dirección General de Migración (DGM)", "numero_solicitud_oficial": "DGM-INV-2026-10492",
            "descripcion_tramite": "Obtención de la residencia permanente dominicana en virtud del decreto de fomento de inversión turística.",
            "monto_tasas_impuestos": 85000.00, "materia": migratorio_materia, "procedimiento": migratorio_proc,
            "prioridad": "Alta", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 120000.00
        },
        {
            "cliente_idx": 8, "nombre_caso": "Registro de Marca Sanitaria 'TecMed' y Patente de Utilidad",
            "rol_firma": "Solicitante", "tipo_proceso": "Propiedad Intelectual", "sub_proceso": "Registro de Marca Comercial",
            "institucion_encargada": "Oficina Nacional de la Propiedad Industrial (ONAPI)", "numero_solicitud_oficial": "ONAPI-REG-2026-90432",
            "descripcion_tramite": "Registro oficial de marca de servicios comerciales y logo mixto 'TecMed' para insumos médicos.",
            "monto_tasas_impuestos": 18500.00, "materia": onapi_materia, "procedimiento": onapi_proc,
            "prioridad": "Media", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 60000.00
        },
        {
            "cliente_idx": 0, "nombre_caso": "Renovación de Registro Mercantil e Incremento de Capital Social",
            "rol_firma": "Solicitante", "tipo_proceso": "Derecho Corporativo", "sub_proceso": "Registro Mercantil",
            "institucion_encargada": "Cámara de Comercio y Producción de Santo Domingo", "numero_solicitud_oficial": "CCPSD-SOC-2026-04981",
            "descripcion_tramite": "Tramitación del incremento de capital social autorizado a RD$ 50 millones y renovación del Registro Mercantil.",
            "monto_tasas_impuestos": 45000.00, "materia": rm_materia, "procedimiento": rm_proc,
            "prioridad": "Alta", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 95000.00
        },
        {
            "cliente_idx": 2, "nombre_caso": "Acuerdo de Exención Tributaria sobre Maquinaria Agrícola",
            "rol_firma": "Solicitante", "tipo_proceso": "Derecho Tributario", "sub_proceso": "Exención de Impuestos",
            "institucion_encargada": "Dirección General de Impuestos Internos (DGII)", "numero_solicitud_oficial": "DGII-EXEN-2026-88321",
            "descripcion_tramite": "Solicitud formal de exoneración del ITBIS y aranceles de importación para cosechadoras agrícolas.",
            "monto_tasas_impuestos": 30000.00, "materia": dgii_materia, "procedimiento": dgii_proc,
            "prioridad": "Alta", "riesgo": "Medio", "exito": "Alta", "esquema_cobro": "Mixto", "tarifa_monto": 150000.00
        },
        {
            "cliente_idx": 5, "nombre_caso": "Rectificación de Acta de Nacimiento por Error en Apellido Materno",
            "rol_firma": "Solicitante", "tipo_proceso": "Derecho Civil Administrativo", "sub_proceso": "Rectificación de Estado Civil",
            "institucion_encargada": "Junta Central Electoral (JCE)", "numero_solicitud_oficial": "JCE-RECT-2026-12093",
            "descripcion_tramite": "Procedimiento administrativo de corrección de error material en el acta de nacimiento de la requirente ante la JCE.",
            "monto_tasas_impuestos": 5500.00, "materia": rm_materia, "procedimiento": rm_proc,
            "prioridad": "Media", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 45000.00
        },
        {
            "cliente_idx": 1, "nombre_caso": "Solicitud de Certificación de No Propiedad para Proyecto Inmobiliario",
            "rol_firma": "Solicitante", "tipo_proceso": "Derecho Inmobiliario Administrativo", "sub_proceso": "Certificaciones",
            "institucion_encargada": "Dirección General de Catastro Nacional", "numero_solicitud_oficial": "CAT-CERT-2026-3021",
            "descripcion_tramite": "Obtención de certificaciones de avalúo catastral e historial del inmueble.",
            "monto_tasas_impuestos": 12000.00, "materia": rm_materia, "procedimiento": rm_proc,
            "prioridad": "Baja", "riesgo": "Bajo", "exito": "Alta", "esquema_cobro": "Fijo", "tarifa_monto": 35000.00
        },
        {
            "cliente_idx": 6, "nombre_caso": "Licencia de Operación Turística ante Ministerio de Turismo",
            "rol_firma": "Solicitante", "tipo_proceso": "Derecho Administrativo", "sub_proceso": "Licencias y Permisos",
            "institucion_encargada": "Ministerio de Turismo (MITUR)", "numero_solicitud_oficial": "MITUR-LIC-2026-0091",
            "descripcion_tramite": "Solicitud de la licencia de operación para desarrollo hotelero de villas en Las Terrenas, Samaná.",
            "monto_tasas_impuestos": 150000.00, "materia": rm_materia, "procedimiento": rm_proc,
            "prioridad": "Alta", "riesgo": "Alto", "exito": "Media", "esquema_cobro": "Fijo", "tarifa_monto": 250000.00
        }
    ]

    for idx, ea in enumerate(admin_cases_data):
        client = clients_db[ea["cliente_idx"]]
        lawyer = lawyers[idx % len(lawyers)]
        codigo = f"EXP-ADM-{uuid.uuid4().hex[:5].upper()}"

        nuevo_exp = ExpedienteAdministrativo(
            codigo_firma=codigo,
            cliente_id=client.id,
            abogado_responsable_id=lawyer.id,
            nombre_caso=ea["nombre_caso"],
            rol_firma=ea["rol_firma"],
            tipo_tramite="Administrativo",
            estado="Abierto",
            fecha_apertura=datetime.utcnow() - timedelta(days=idx*20),
            fase_actual=1,
            esquema_cobro=ea["esquema_cobro"],
            tarifa_monto=Decimal(str(ea["tarifa_monto"])),
            porcentaje_exito=Decimal("0.00"),
            materia_id=ea["materia"].id if ea["materia"] else None,
            procedimiento_id=ea["procedimiento"].id if ea["procedimiento"] else None,
            prioridad=ea["prioridad"],
            nivel_riesgo=ea["riesgo"],
            probabilidad_exito=ea["exito"],
            origen_cliente="Cliente Nuevo" if idx % 2 == 0 else "Referido",
            fecha_contratacion=(date.today() - timedelta(days=idx*20)),
            valor_estimado_caso=Decimal(str(ea["monto_tasas_impuestos"] + ea["tarifa_monto"])),

            tipo_proceso=ea["tipo_proceso"],
            sub_proceso=ea["sub_proceso"],
            institucion_encargada=ea["institucion_encargada"],
            numero_solicitud_oficial=ea["numero_solicitud_oficial"],
            descripcion_tramite=ea["descripcion_tramite"],
            monto_tasas_impuestos=Decimal(str(ea["monto_tasas_impuestos"]))
        )
        db.session.add(nuevo_exp)
        db.session.commit()
        # Vincular en relación secundaria
        nuevo_exp.abogados.append(lawyer)
        db.session.commit()
        expedientes_db.append(nuevo_exp)
        print(f"Expediente Administrativo '{nuevo_exp.nombre_caso}' ({nuevo_exp.codigo_firma}) creado.")

    # 9. SEED ALERTA PLAZO AUDIENCIA (2 por cada expediente judicial)
    print("\nInsertando alertas preventivas y plazos...")
    alert_titles = [
        "Audiencia de Conciliación", "Plazo para presentación de réplica",
        "Audiencia de Presentación de Pruebas", "Vencimiento de plazo recursivo",
        "Sometimiento de conclusiones por escrito", "Lectura de Sentencia",
        "Audiencia preliminar de conciliación", "Notificación de demanda vía Alguacil",
        "Vencimiento de fianza de arraigo", "Audiencia sobre Medidas de Coerción"
    ]
    
    judicial_expedientes = [e for e in expedientes_db if e.tipo_tramite == 'Judicial']
    for idx, e in enumerate(judicial_expedientes):
        for alert_idx in range(2):
            title = alert_titles[(idx * 2 + alert_idx) % len(alert_titles)]
            days_offset = (idx * 2 + alert_idx + 1) * 6
            due_date = datetime.utcnow() + timedelta(days=days_offset)
            is_aud = "Audiencia" in title
            
            nueva_alerta = AlertaPlazoAudiencia(
                expediente_id=e.id,
                titulo_hito=f"{title} - Ref: {e.codigo_firma}",
                fecha_vencimiento=due_date,
                estado_alerta="Pending" if days_offset > 8 else "Atendida",
                fuente_origen="Firma" if idx % 2 == 0 else "Poder Judicial",
                es_audiencia=is_aud
            )
            db.session.add(nueva_alerta)
            db.session.commit()

    # 10. SEED REQUISITOS ADMINISTRATIVOS (3 por cada expediente administrativo)
    print("\nInsertando requisitos de flujos documentales...")
    reqs_titles = [
        "Copia certificada de acta de asamblea", "Traducción legalizada por intérprete público",
        "Apostilla de acta de nacimiento extranjera", "Pago de tasa de publicación ONAPI",
        "Certificación de RNC al día", "Copia de cédula del representante legal",
        "Poder de representación debidamente notariado", "Formulario oficial firmado por solicitante"
    ]
    
    admin_expedientes = [e for e in expedientes_db if e.tipo_tramite == 'Administrativo']
    for idx, e in enumerate(admin_expedientes):
        for req_idx in range(3):
            title = reqs_titles[(idx * 3 + req_idx) % len(reqs_titles)]
            nuevo_req = RequisitoAdministrativo(
                expediente_id=e.id,
                descripcion=title,
                requiere_legalizacion=req_idx == 0,
                requiere_apostilla=req_idx == 1,
                requiere_traduccion=req_idx == 2,
                estado="Pendiente" if req_idx % 2 == 0 else "Completado",
                observaciones=f"Requisito fundamental para la radicación del trámite {e.codigo_firma}."
            )
            db.session.add(nuevo_req)
            db.session.commit()

    # 11. SEED PRESUPUESTOS & DETALLES (12 presupuestos)
    print("\nInsertando presupuestos...")
    presupuestos_db = []
    budget_titles = [
        "Presupuesto de Honorarios - Litigio de Incumplimiento Contractual",
        "Presupuesto de Honorarios - Solicitud de Residencia de Inversión",
        "Presupuesto de Honorarios - Registro de Marca Nacional",
        "Presupuesto de Honorarios - Asesoría y Litis Inmobiliaria",
        "Presupuesto de Honorarios - Defensa en Demanda Laboral",
        "Presupuesto de Honorarios - Constitución de Sociedad Comercial",
        "Presupuesto de Honorarios - Demanda de Divorcio por Mutuo Acuerdo",
        "Presupuesto de Honorarios - Gestión de Exención Tributaria",
        "Presupuesto de Honorarios - Rectificación Civil ante JCE",
        "Presupuesto de Honorarios - Licencia de Turismo en Las Terrenas",
        "Presupuesto de Honorarios - Querella Penal por Estafa",
        "Presupuesto de Honorarios - Desalojo de Local Comercial"
    ]

    for idx in range(12):
        client = clients_db[idx % len(clients_db)]
        title = budget_titles[idx]
        subtotal = Decimal(str((idx + 1) * 35000.00))
        itbis = subtotal * Decimal("0.18")
        total = subtotal + itbis
        estado = 'Aceptado' if idx < 8 else ('Borrador' if idx % 2 == 0 else 'Pendiente Aceptación')

        nuevo_pres = Presupuesto(
            cliente_id=client.id,
            titulo=title,
            descripcion=f"Presupuesto estimado de honorarios profesionales por servicios legales especializados en {title.split(' - ')[-1]}.",
            materia="Litigios" if idx % 2 == 0 else "Consultoría",
            tipo_asunto=title.split(' - ')[-1],
            monto_subtotal=subtotal,
            monto_itbis=itbis,
            monto_total=total,
            fecha_emision=datetime.utcnow() - timedelta(days=idx*10),
            estado=estado
        )
        db.session.add(nuevo_pres)
        db.session.commit()
        presupuestos_db.append(nuevo_pres)

        # 2 Partidas de presupuesto
        det1 = PresupuestoDetalle(
            presupuesto_id=nuevo_pres.id,
            descripcion="Estudio preliminar de documentación, redacción de escritos iniciales e instrumentación del caso.",
            cantidad=1,
            precio_unitario=subtotal * Decimal("0.60"),
            subtotal=subtotal * Decimal("0.60")
        )
        det2 = PresupuestoDetalle(
            presupuesto_id=nuevo_pres.id,
            descripcion="Honorarios de representación ante audiencias, trámites gubernamentales o gestiones administrativas.",
            cantidad=1,
            precio_unitario=subtotal * Decimal("0.40"),
            subtotal=subtotal * Decimal("0.40")
        )
        db.session.add_all([det1, det2])
        db.session.commit()

    # 12. SEED CONTRATOS & CRONOGRAMA DE COBRO (8 contratos basados en presupuestos aprobados)
    print("\nInsertando contratos de honorarios y cronogramas de cobro...")
    contratos_db = []
    accepted_presupuestos = [p for p in presupuestos_db if p.estado == 'Aceptado']

    for idx, pres in enumerate(accepted_presupuestos):
        exp = expedientes_db[idx % len(expedientes_db)]
        tipo_cobro = 'Fijo' if idx % 3 == 0 else ('Etapas' if idx % 3 == 1 else 'Cuotas')

        nuevo_con = ContratoHonorarios(
            expediente_id=exp.id,
            cliente_id=pres.cliente_id,
            presupuesto_id=pres.id,
            fecha_firma=date.today() - timedelta(days=idx*12),
            fecha_inicio=date.today() - timedelta(days=idx*12),
            fecha_finalizacion_estimada=date.today() + timedelta(days=180),
            estado='Vigente' if idx % 2 == 0 else 'Finalizado',
            observaciones=f"Contrato formalizado bajo la modalidad de cobro '{tipo_cobro}' para el expediente '{exp.nombre_caso}'.",
            tipo_cobro=tipo_cobro,
            moneda='DOP',
            aplica_itbis=True,
            porcentaje_itbis=Decimal("18.00"),
            subtotal=pres.monto_subtotal,
            itbis=pres.monto_itbis,
            total_contrato=pres.monto_total,
            requiere_anticipo=idx % 2 == 0,
            monto_anticipo=pres.monto_total * Decimal("0.30") if idx % 2 == 0 else Decimal("0.00")
        )
        db.session.add(nuevo_con)
        db.session.commit()
        contratos_db.append(nuevo_con)

        # Generar cronograma de 3 cuotas
        num_cuotas = 3
        monto_cuota = nuevo_con.total_contrato / Decimal(str(num_cuotas))
        for c_idx in range(num_cuotas):
            fecha_venc = date.today() - timedelta(days=30 * (1 - c_idx))
            estado_c = 'Pagado' if c_idx == 0 and nuevo_con.estado == 'Vigente' else ('Pendiente' if nuevo_con.estado == 'Vigente' else 'Pagado')
            
            cuota = CronogramaCobro(
                contrato_id=nuevo_con.id,
                descripcion=f"Pago Cuota #{c_idx + 1} de {num_cuotas} del contrato",
                fecha_vencimiento=fecha_venc,
                monto=monto_cuota,
                estado=estado_c,
                orden=c_idx + 1,
                tipo='Cuota'
            )
            db.session.add(cuota)
            db.session.commit()

    # 13. SEED FACTURAS & DETALLES (15 facturas con NCF)
    print("\nInsertando facturas de honorarios...")
    facturas_db = []

    for idx in range(15):
        client = clients_db[idx % len(clients_db)]
        exp = expedientes_db[idx % len(expedientes_db)]
        con = contratos_db[idx % len(contratos_db)]
        cuota = CronogramaCobro.query.filter_by(contrato_id=con.id).first()

        subtotal = Decimal(str((idx + 1) * 20000.00))
        itbis = subtotal * Decimal("0.18")
        total = subtotal + itbis
        
        tipo_comp = "31" if idx % 2 == 0 else "32" # 31 = Crédito Fiscal, 32 = Consumo
        ncf_str = f"B{tipo_comp}000000{str(idx+1).zfill(4)}"
        estado_pago = 'Cobrado' if idx < 10 else ('Anulado' if idx == 14 else 'Pendiente')

        nueva_fac = FacturaHonorario(
            cliente_id=client.id,
            expediente_id=exp.id,
            ncf=ncf_str,
            tipo_comprobante=tipo_comp,
            monto_subtotal=subtotal,
            monto_itbis=itbis,
            monto_total=total,
            fecha_emision=datetime.utcnow() - timedelta(days=idx*15),
            fecha_vencimiento=date.today() - timedelta(days=idx*15) + timedelta(days=30),
            estado_pago=estado_pago,
            plazo_pago_dias=30,
            tasa_mora_mensual=Decimal("1.50"),
            contrato_id=con.id,
            cuota_id=cuota.id if cuota else None
        )
        db.session.add(nueva_fac)
        db.session.commit()
        facturas_db.append(nueva_fac)

        if estado_pago == 'Cobrado' and cuota:
            cuota.estado = 'Pagado'
            db.session.commit()

        # Detalle de factura
        det_fac = DetalleFactura(
            factura_id=nueva_fac.id,
            descripcion=f"Honorarios legales por gestión de servicios asociados al expediente {exp.codigo_firma}.",
            cantidad=1,
            precio_unitario=subtotal,
            subtotal=subtotal
        )
        db.session.add(det_fac)
        db.session.commit()
        print(f"Factura {nueva_fac.ncf} ({nueva_fac.estado_pago}) creada.")

    # 14. SEED TRANSACCIONES PAGO & RECIBOS INTERNOS (Para facturas cobradas)
    print("\nInsertando transacciones de cobros y recibos de pago...")
    cobrado_facturas = [f for f in facturas_db if f.estado_pago == 'Cobrado']

    for idx, fac in enumerate(cobrado_facturas):
        rec_num = f"REC-{str(idx+1).zfill(6)}"
        nuevo_rec = ReciboInterno(
            numero_recibo=rec_num,
            cliente_id=fac.cliente_id,
            fecha_emision=fac.fecha_emision,
            monto_total=fac.monto_total,
            observaciones=f"Recibo generado de forma automática por cobro total de factura con NCF {fac.ncf}."
        )
        db.session.add(nuevo_rec)
        db.session.commit()

        metodo = 'Transferencia' if idx % 3 == 0 else ('Cheque' if idx % 3 == 1 else 'Tarjeta')
        ref = f"Transf. Popular #{100000+idx}" if metodo == 'Transferencia' else (f"Cheque BHD #{890+idx}" if metodo == 'Cheque' else "Auth 991202")

        pago = TransaccionPago(
            factura_id=fac.id,
            recibo_id=nuevo_rec.id,
            monto=fac.monto_total,
            fecha_pago=fac.fecha_emision + timedelta(days=5),
            metodo_pago=metodo,
            referencia=ref
        )
        db.session.add(pago)
        db.session.commit()
        print(f"Pago registrado para NCF {fac.ncf} por RD$ {fac.monto_total:,.2f} vía {metodo}.")

    # 15. SEED TAREAS (25 tareas asignadas)
    print("\nInsertando tareas operacionales...")
    tareas_datos = [
        "Estudiar expediente y redactar demanda inicial",
        "Depositar demanda civil ante secretaría del tribunal",
        "Notificar demanda vía Alguacil a la contraparte",
        "Redactar réplica al escrito de defensa de la contraparte",
        "Preparar inventario de documentos para audiencia de pruebas",
        "Asistir a la primera audiencia fijada",
        "Someter escrito de conclusiones al tribunal",
        "Dar seguimiento mensual al estado del expediente en secretaría",
        "Digitalizar documentos de propiedad entregados por el cliente",
        "Solicitar apostilla de poder en el exterior",
        "Realizar búsqueda de factibilidad de nombre comercial en ONAPI",
        "Someter solicitud oficial de registro de marca comercial",
        "Monitorear publicación en la revista oficial de ONAPI",
        "Redactar estatutos sociales y nómina de accionistas de la nueva SRL",
        "Depositar expediente ante Cámara de Comercio para Registro Mercantil",
        "Solicitar el RNC oficial ante la DGII",
        "Preparar documentación de exención tributaria para DGII",
        "Obtener acta de nacimiento legalizada ante JCE",
        "Depositar solicitud de rectificación de acta en JCE",
        "Notificar deslinde al propietario colindante",
        "Preparar fianza de arraigo para demandado extranjero",
        "Preparar recursos contra resolución administrativa denegatoria",
        "Realizar inventario de bienes del divorcio",
        "Redactar acuerdo de estipulaciones mutuas del divorcio",
        "Realizar pago de tasas migratorias de residencia"
    ]

    for idx, titulo in enumerate(tareas_datos):
        exp = expedientes_db[idx % len(expedientes_db)]
        lawyer = lawyers[idx % len(lawyers)]
        paralegal = paralegals[idx % len(paralegals)]
        
        prioridad = 'Alta' if idx % 5 == 0 else ('Baja' if idx % 5 == 1 else 'Media')
        estado = 'Pendiente' if idx % 3 == 0 else ('En Progreso' if idx % 3 == 1 else 'Completada')
        
        fecha_lim = date.today() + timedelta(days=(idx+1)*3)
        fecha_comp = datetime.utcnow() if estado == 'Completada' else None

        nueva_t = Tarea(
            titulo=titulo,
            descripcion=f"Actividad legal prioritaria y detallada asociada al expediente {exp.codigo_firma}. Es crucial revisar los términos procesales vigentes y coordinar con el equipo.",
            fecha_limite=fecha_lim,
            prioridad=prioridad,
            estado=estado,
            expediente_id=exp.id,
            asignado_a_id=lawyer.id if idx % 2 == 0 else paralegal.id,
            creado_por_id=admin.id,
            fecha_creacion=datetime.utcnow() - timedelta(days=10),
            fecha_completada=fecha_comp
        )
        db.session.add(nueva_t)
        db.session.commit()
        # Agregar en relación muchos a muchos
        nueva_t.asignados.append(nueva_t.asignado_a)
        db.session.commit()

    # 16. SEED BITACORA TIEMPOS (15 bitácoras)
    print("\nInsertando bitácora de horas laboradas...")
    for idx in range(15):
        exp = expedientes_db[idx % len(expedientes_db)]
        lawyer = lawyers[idx % len(lawyers)]

        nuevo_tiempo = BitacoraTiempoTarea(
            expediente_id=exp.id,
            usuario_id=lawyer.id,
            fecha_tarea=date.today() - timedelta(days=idx),
            horas_trabajadas=Decimal(str(round((idx % 5 + 1) * 1.5, 2))),
            descripcion_gestion=f"Revisión de jurisprudencia aplicable, redacción de documentos procesales y llamadas de seguimiento con el cliente para {exp.codigo_firma}.",
            estado_cierre='Facturado' if idx < 10 else 'Abierto'
        )
        db.session.add(nuevo_tiempo)
        db.session.commit()

    # 17. SEED GASTOS REEMBOLSABLES (10 gastos)
    print("\nInsertando gastos reembolsables...")
    tipos_gasto = ['Impuestos', 'Tasas', 'Legalizaciones', 'Copias certificadas', 'Mensajería', 'Viáticos', 'Alguacil', 'Notaría']
    for idx in range(10):
        exp = expedientes_db[idx % len(expedientes_db)]
        fac = facturas_db[idx % len(facturas_db)]

        gasto = GastoReembolsable(
            expediente_id=exp.id,
            tipo_gasto=tipos_gasto[idx % len(tipos_gasto)],
            descripcion=f"Gasto en {tipos_gasto[idx % len(tipos_gasto)]} incurrido para el trámite del caso {exp.codigo_firma}.",
            monto=Decimal(str((idx + 1) * 1500.00)),
            fecha=date.today() - timedelta(days=idx*3),
            estado='Reembolsado' if idx % 2 == 0 else 'Pendiente',
            factura_id=fac.id if idx % 2 == 0 else None
        )
        db.session.add(gasto)
        db.session.commit()

    # 18. SEED AUDITORIA (25 logs)
    print("\nInsertando logs de auditoría forense...")
    acciones = ['CREAR_EXPEDIENTE', 'CARGAR_DOCUMENTO', 'EDITAR_FACTURA', 'VISUALIZAR_REPORTE', 'ELIMINAR_TAREA']
    for idx in range(25):
        lawyer = lawyers[idx % len(lawyers)]
        exp = expedientes_db[idx % len(expedientes_db)]

        nueva_aud = BitacoraAuditoria(
            usuario_id=lawyer.id,
            expediente_id=exp.id,
            cliente_id=exp.cliente_id,
            accion_realizada=acciones[idx % len(acciones)],
            detalles_tecnicos=f"El usuario ejecutó la acción '{acciones[idx % len(acciones)]}' en el módulo correspondiente con éxito desde la terminal IP.",
            ip_direccion="192.168.1.50" if idx % 2 == 0 else "200.88.90.12",
            dispositivo_info="Chrome 115.0 / Windows 11"
        )
        db.session.add(nueva_aud)
        db.session.commit()

    # 19. SEED CARPETAS Y DOCUMENTOS (Archivos iniciales por expediente)
    print("\nInsertando carpetas y documentos virtuales en el motor documental...")
    # Asegurar que existan algunos Tipos de Documentos
    if TipoDocumento.query.count() == 0:
        td1 = TipoDocumento(nombre_tipo="Poder de Representación")
        td2 = TipoDocumento(nombre_tipo="Instancia de Demanda")
        td3 = TipoDocumento(nombre_tipo="Medio de Prueba")
        td4 = TipoDocumento(nombre_tipo="Sentencia")
        td5 = TipoDocumento(nombre_tipo="Identificación / Cédula")
        db.session.add_all([td1, td2, td3, td4, td5])
        db.session.commit()

    t_docs = TipoDocumento.query.all()

    for idx, exp in enumerate(expedientes_db):
        carpeta = Carpeta(
            nombre="Documentación Primaria",
            expediente_id=exp.id,
            fecha_creacion=datetime.utcnow()
        )
        db.session.add(carpeta)
        db.session.commit()

        doc = Documento(
            expediente_id=exp.id,
            tipo_documento_id=t_docs[idx % len(t_docs)].id,
            visibilidad="Compartido" if idx % 3 == 0 else "Interno",
            carpeta_id=carpeta.id,
            cliente_id=exp.cliente_id
        )
        db.session.add(doc)
        db.session.commit()

        version = VersionDocumento(
            documento_id=doc.id,
            usuario_id=exp.abogado_responsable_id,
            version_numero="1.0",
            descripcion="Documento base indexado automáticamente por el seeder del sistema.",
            fecha_carga=datetime.utcnow(),
            tamano_bytes=45230,
            ruta_almacenamiento=f"uploads/{exp.codigo_firma}/documento_inicial.pdf",
            es_firmado=False
        )
        db.session.add(version)
        db.session.commit()

    print("\n¡Sembrado de base de datos finalizado exitosamente!")
