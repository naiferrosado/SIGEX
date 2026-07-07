import uuid
from datetime import date, datetime
from app import create_app, db
from app.models import Usuario, Cliente, ExpedienteJudicial, ExpedienteAdministrativo

app = create_app()

with app.app_context():
    # 1. Obtener un abogado responsable (cualquier usuario con rol administrativo o legal)
    abogado = Usuario.query.filter(Usuario.rol.in_(['Administrador', 'Socio', 'Asociado', 'Paralegal'])).first()
    
    if not abogado:
        print("Error: No se encontró ningún abogado/usuario administrativo en la base de datos para asignar los expedientes.")
        print("Por favor, ejecuta primero 'python crear_admin.py' para registrar al administrador.")
        exit(1)
        
    print(f"Los expedientes creados serán asignados al abogado responsable: {abogado.nombre} ({abogado.rol})")

    # 2. DEFINICIÓN DE CLIENTES FICTICIOS
    clientes_datos = [
        {
            "rnc_cedula": "00115824961",
            "nombres": "Juan Carlos",
            "apellidos": "Pérez Martínez",
            "tipo_cliente": "Persona física",
            "fecha_nacimiento": date(1985, 5, 12),
            "direccion": "Av. Winston Churchill #105, Ensanche Piantini, Santo Domingo",
            "telefono": "809-555-0192",
            "email_contacto": "juan.perez@example.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "00201948572",
            "nombres": "María Altagracia",
            "apellidos": "Rodríguez Tejeda",
            "tipo_cliente": "Persona física",
            "fecha_nacimiento": date(1990, 11, 22),
            "direccion": "Calle El Sol #45, Santiago de los Caballeros",
            "telefono": "829-555-3847",
            "email_contacto": "maria.rodriguez@example.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "131849502",
            "nombres": "Constructora del",
            "apellidos": "Caribe, S.R.L.",
            "tipo_cliente": "Persona jurídica",
            "fecha_nacimiento": None,
            "direccion": "Av. Anacaona #220, Los Cacicazgos, Santo Domingo",
            "telefono": "809-555-8822",
            "email_contacto": "contacto@constructoracaribe.com.do",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "101759283",
            "nombres": "Inversiones",
            "apellidos": "Falcon, S.A.",
            "tipo_cliente": "Persona jurídica",
            "fecha_nacimiento": None,
            "direccion": "Calle Lope de Vega #12, Naco, Santo Domingo",
            "telefono": "809-555-9000",
            "email_contacto": "legal@inversionesfalcon.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "03100984711",
            "nombres": "Pedro Luis",
            "apellidos": "Espinal Gómez",
            "tipo_cliente": "Persona física",
            "fecha_nacimiento": date(1978, 8, 30),
            "direccion": "Av. 27 de Febrero #300, Sector La Julia, Santo Domingo",
            "telefono": "849-555-4721",
            "email_contacto": "pedro.espinal@example.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "99900011122",
            "nombres": "John",
            "apellidos": "Smith",
            "tipo_cliente": "Persona física",
            "fecha_nacimiento": date(1975, 4, 15),
            "direccion": "Av. Luperón, Las Terrenas, Samaná",
            "telefono": "829-555-7766",
            "email_contacto": "john.smith@example.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        }
    ]

    # Guardar ids de clientes creados/existentes
    clientes_db = {}

    print("\nProcesando clientes...")
    for c_info in clientes_datos:
        # Verificar si ya existe el cliente por RNC/Cédula
        cliente_existente = Cliente.query.filter_by(rnc_cedula=c_info["rnc_cedula"]).first()
        if cliente_existente:
            print(f"El cliente '{cliente_existente.nombre_completo}' ya existe. (ID: {cliente_existente.id})")
            clientes_db[c_info["rnc_cedula"]] = cliente_existente
        else:
            nuevo_cliente = Cliente(
                rnc_cedula=c_info["rnc_cedula"],
                nombres=c_info["nombres"],
                apellidos=c_info["apellidos"],
                tipo_cliente=c_info["tipo_cliente"],
                fecha_nacimiento=c_info["fecha_nacimiento"],
                direccion=c_info["direccion"],
                telefono=c_info["telefono"],
                email_contacto=c_info["email_contacto"],
                consentimiento_datos=c_info["consentimiento_datos"],
                fecha_consentimiento=c_info["fecha_consentimiento"]
            )
            db.session.add(nuevo_cliente)
            db.session.commit()
            print(f"Cliente '{nuevo_cliente.nombre_completo}' creado exitosamente. (ID: {nuevo_cliente.id})")
            clientes_db[c_info["rnc_cedula"]] = nuevo_cliente

    # 3. DEFINICIÓN DE EXPEDIENTES FICTICIOS
    # Expedientes Judiciales (Litigios)
    exp_judiciales = [
        {
            "rnc_cliente": "131849502", # Constructora del Caribe, S.R.L.
            "nombre_caso": "Cobro de Pesos contra Distribuidora Norte, S.A.",
            "rol_firma": "Demandante",
            "rama_derecho": "Civil",
            "sub_categoria": "Cobro de Pesos",
            "tipo_accion": "Demanda en cobro de pesos por incumplimiento de contrato de obra",
            "jurisdiccion_actual": "Primera Instancia",
            "tribunal_asignado": "Segunda Sala de la Cámara Civil y Comercial del Juzgado de Primera Instancia del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-ECIV-00482",
            "juez_asignado": "Lic. Roberto Caba",
            "nombre_contraparte": "Distribuidora Norte, S.A.",
            "contacto_contraparte": "Av. Luperón Esq. Gustavo Mejía Ricart, Santo Domingo",
            "abogado_contraparte": "Dr. Manuel Cáceres",
            "contacto_abogado_contraparte": "809-555-2244 / m.caceres@abogadosasoc.do",
            "monto_demanda": 2500000.00,
            "fecha_audiencia": date(2026, 8, 15),
            "hora_audiencia": datetime.strptime("09:00", "%H:%M").time()
        },
        {
            "rnc_cliente": "00115824961", # Juan Carlos Pérez Martínez
            "nombre_caso": "Demanda Laboral contra Tecnologías Globales Dominicana",
            "rol_firma": "Demandante",
            "rama_derecho": "Laboral",
            "sub_categoria": "Despido Injustificado",
            "tipo_accion": "Demanda laboral por prestaciones laborales y derechos adquiridos",
            "jurisdiccion_actual": "Primera Instancia",
            "tribunal_asignado": "Tercera Sala del Juzgado de Trabajo del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-ELAB-00129",
            "juez_asignado": "Dra. Angela Rosario",
            "nombre_contraparte": "Tecnologías Globales Dominicana, S.R.L.",
            "contacto_contraparte": "Calle Jacinto Mañón #20, Ensanche Naco, Santo Domingo",
            "abogado_contraparte": "Dra. Patricia Méndez",
            "contacto_abogado_contraparte": "829-555-1177 / pmendez@globaltech.com.do",
            "monto_demanda": 450000.00,
            "fecha_audiencia": date(2026, 7, 28),
            "hora_audiencia": datetime.strptime("09:30", "%H:%M").time()
        },
        {
            "rnc_cliente": "00201948572", # María Altagracia Rodríguez Tejeda
            "nombre_caso": "Querella por Estafa contra Carlos Valenzuela",
            "rol_firma": "Querellante",
            "rama_derecho": "Penal",
            "sub_categoria": "Querella con Constitución en Actor Civil",
            "tipo_accion": "Querella por violación al Art. 405 del Código Penal (Estafa)",
            "jurisdiccion_actual": "Instrucción",
            "tribunal_asignado": "Octavo Juzgado de la Instrucción del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-EPEN-00714",
            "juez_asignado": "Dr. Alejandro Vargas",
            "nombre_contraparte": "Carlos Manuel Valenzuela",
            "contacto_contraparte": "Residencial Las Palmeras, Apto 3B, Santo Domingo Oeste",
            "abogado_contraparte": "Lic. Fernando Rojas",
            "contacto_abogado_contraparte": "809-555-6677 / frojas.abogado@gmail.com",
            "monto_demanda": 1200000.00,
            "fecha_audiencia": date(2026, 9, 10),
            "hora_audiencia": datetime.strptime("10:00", "%H:%M").time()
        }
    ]

    # Expedientes Administrativos
    exp_administrativos = [
        {
            "rnc_cliente": "131849502", # Constructora del Caribe, S.R.L.
            "nombre_caso": "Registro de Marca Caribe Built",
            "rol_firma": "Solicitante",
            "tipo_proceso": "Propiedad Intelectual",
            "sub_proceso": "Registro de Nombre Comercial y Marca",
            "institucion_encargada": "ONAPI",
            "numero_solicitud_oficial": "ONAPI-2026-004381",
            "descripcion_tramite": "Registro de marca mixta 'Caribe Built' para la Clase 37 de la Clasificación de Niza (servicios de construcción y edificación).",
            "monto_tasas_impuestos": 14500.00
        },
        {
            "rnc_cliente": "101759283", # Inversiones Falcon, S.A.
            "nombre_caso": "Constitución de Sucursal y Registro Mercantil",
            "rol_firma": "Solicitante",
            "tipo_proceso": "Derecho Corporativo",
            "sub_proceso": "Constitución de Compañía y Registro Mercantil",
            "institucion_encargada": "Cámara de Comercio y Producción de Santo Domingo",
            "numero_solicitud_oficial": "CCPSD-2026-8819",
            "descripcion_tramite": "Proceso de constitución legal de sucursal, registro de estatutos sociales y obtención del Registro Mercantil oficial.",
            "monto_tasas_impuestos": 25000.00
        },
        {
            "rnc_cliente": "99900011122", # John Smith
            "nombre_caso": "Solicitud de Residencia Permanente por Inversión",
            "rol_firma": "Solicitante",
            "tipo_proceso": "Derecho Migratorio",
            "sub_proceso": "Visa de Residencia y Residencia de Inversión",
            "institucion_encargada": "Dirección General de Migración (DGM)",
            "numero_solicitud_oficial": "DGM-2026-99218",
            "descripcion_tramite": "Obtención de la residencia permanente por inversión extranjera a partir de la adquisición inmobiliaria en Las Terrenas, Samaná.",
            "monto_tasas_impuestos": 60000.00
        }
    ]

    print("\nProcesando expedientes judiciales...")
    for ej in exp_judiciales:
        # Buscar el cliente id correspondiente
        cliente = clientes_db.get(ej["rnc_cliente"])
        if not cliente:
            print(f"Error: Cliente con RNC/Cédula {ej['rnc_cliente']} no encontrado en el diccionario.")
            continue
        
        # Validar si ya existe este expediente por número de expediente de tribunal
        exp_existente = ExpedienteJudicial.query.filter_by(numero_expediente_tribunal=ej["numero_expediente_tribunal"]).first()
        if exp_existente:
            print(f"El expediente judicial '{exp_existente.nombre_caso}' ya existe. (Código: {exp_existente.codigo_firma})")
        else:
            codigo = f"EXP-{uuid.uuid4().hex[:6].upper()}"
            nuevo_exp_j = ExpedienteJudicial(
                codigo_firma=codigo,
                cliente_id=cliente.id,
                abogado_responsable_id=abogado.id,
                nombre_caso=ej["nombre_caso"],
                rol_firma=ej["rol_firma"],
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
                monto_demanda=ej["monto_demanda"],
                fecha_audiencia=ej["fecha_audiencia"],
                hora_audiencia=ej["hora_audiencia"],
                tipo_tramite="Judicial",
                estado="Abierto"
            )
            db.session.add(nuevo_exp_j)
            db.session.commit()
            print(f"Expediente judicial '{nuevo_exp_j.nombre_caso}' creado con éxito. Código: {nuevo_exp_j.codigo_firma}")

    print("\nProcesando expedientes administrativos...")
    for ea in exp_administrativos:
        # Buscar el cliente id correspondiente
        cliente = clientes_db.get(ea["rnc_cliente"])
        if not cliente:
            print(f"Error: Cliente con RNC/Cédula {ea['rnc_cliente']} no encontrado en el diccionario.")
            continue
        
        # Validar si ya existe este expediente por número de solicitud oficial
        exp_existente = ExpedienteAdministrativo.query.filter_by(numero_solicitud_oficial=ea["numero_solicitud_oficial"]).first()
        if exp_existente:
            print(f"El expediente administrativo '{exp_existente.nombre_caso}' ya existe. (Código: {exp_existente.codigo_firma})")
        else:
            codigo = f"EXP-{uuid.uuid4().hex[:6].upper()}"
            nuevo_exp_a = ExpedienteAdministrativo(
                codigo_firma=codigo,
                cliente_id=cliente.id,
                abogado_responsable_id=abogado.id,
                nombre_caso=ea["nombre_caso"],
                rol_firma=ea["rol_firma"],
                tipo_proceso=ea["tipo_proceso"],
                sub_proceso=ea["sub_proceso"],
                institucion_encargada=ea["institucion_encargada"],
                numero_solicitud_oficial=ea["numero_solicitud_oficial"],
                descripcion_tramite=ea["descripcion_tramite"],
                monto_tasas_impuestos=ea["monto_tasas_impuestos"],
                tipo_tramite="Administrativo",
                estado="Abierto"
            )
            db.session.add(nuevo_exp_a)
            db.session.commit()
            print(f"Expediente administrativo '{nuevo_exp_a.nombre_caso}' creado con éxito. Código: {nuevo_exp_a.codigo_firma}")

    print("\n¡Proceso de inserción de datos completado exitosamente!")
