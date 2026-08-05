import uuid
from datetime import date, datetime
from app import create_app, db
from app.models import Usuario, Cliente, ExpedienteJudicial, ExpedienteAdministrativo, AlertaPlazoAudiencia

app = create_app()

with app.app_context():
    # 1. Obtener un abogado responsable (cualquier usuario legal o admin)
    abogado = Usuario.query.filter(Usuario.rol.in_(['Administrador', 'Socio', 'Asociado', 'Paralegal'])).first()
    
    if not abogado:
        print("Error: No se encontró ningún abogado responsable en la base de datos.")
        exit(1)
        
    print(f"Los nuevos expedientes serán asignados a: {abogado.nombre} ({abogado.rol})")

    # 2. DEFINICIÓN DE NUEVOS CLIENTES CON NOMBRES REALES Y REALISTAS
    nuevos_clientes = [
        {
            "rnc_cedula": "131998877",
            "nombres": "Alimentos del Cibao",
            "apellidos": "S.A.S.",
            "tipo_cliente": "Persona jurídica",
            "fecha_nacimiento": None,
            "direccion": "Autopista Duarte Km 5, Santiago",
            "telefono": "809-582-4411",
            "email_contacto": "legal@alimentosdecibao.com.do",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "00118822334",
            "nombres": "Carlos Manuel",
            "apellidos": "Guerrero Santos",
            "tipo_cliente": "Persona física",
            "fecha_nacimiento": date(1982, 3, 14),
            "direccion": "Calle Rafael Augusto Sánchez #8, Ensanche Naco, Santo Domingo",
            "telefono": "829-340-9988",
            "email_contacto": "cguerrero@gmail.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "101887766",
            "nombres": "Clínica Dental",
            "apellidos": "OdontoSalud, S.R.L.",
            "tipo_cliente": "Persona jurídica",
            "fecha_nacimiento": None,
            "direccion": "Av. Rómulo Betancourt #1412, Bella Vista, Santo Domingo",
            "telefono": "809-221-5500",
            "email_contacto": "info@odontosalud.com.do",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "03100554433",
            "nombres": "Sofía Isabel",
            "apellidos": "Peralta Almonte",
            "tipo_cliente": "Persona física",
            "fecha_nacimiento": date(1993, 7, 25),
            "direccion": "Calle del Sol #92, Santiago",
            "telefono": "809-724-1122",
            "email_contacto": "sofia.peralta@gmail.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        },
        {
            "rnc_cedula": "102334455",
            "nombres": "Inmobiliaria",
            "apellidos": "Hato Nuevo, S.A.",
            "tipo_cliente": "Persona jurídica",
            "fecha_nacimiento": None,
            "direccion": "Av. Tiradentes #55, Naco, Santo Domingo",
            "telefono": "809-567-3322",
            "email_contacto": "proyectos@inmobiliariahatonuevo.com",
            "consentimiento_datos": True,
            "fecha_consentimiento": datetime.utcnow()
        }
    ]

    clientes_db = {}

    print("\nProcesando clientes nuevos...")
    for c_info in nuevos_clientes:
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

    # 3. DEFINICIÓN DE EXPEDIENTES NUEVOS
    nuevos_exp_judiciales = [
        {
            "rnc_cliente": "131998877", # Alimentos del Cibao, S.A.S.
            "nombre_caso": "Cobro de pesos contra Supermercados Dominicanos, S.A.",
            "rol_firma": "Demandante",
            "rama_derecho": "Comercial",
            "sub_categoria": "Cobro de Pesos",
            "tipo_accion": "Demanda en cobro de pesos por facturas vencidas de suministro",
            "jurisdiccion_actual": "Primera Instancia",
            "tribunal_asignado": "Primera Sala de la Cámara Civil y Comercial del Juzgado de Primera Instancia de Santiago",
            "numero_expediente_tribunal": "031-2026-ECIV-00918",
            "juez_asignado": "Licda. Carmen Almonte",
            "nombre_contraparte": "Supermercados Dominicanos, S.A.",
            "contacto_contraparte": "Av. John F. Kennedy, Santo Domingo",
            "abogado_contraparte": "Dr. Lorenzo Castillo",
            "contacto_abogado_contraparte": "809-540-3321 / lcastillo@castillolegal.com",
            "monto_demanda": 4800000.00,
            "fecha_audiencia": date(2026, 9, 20),
            "hora_audiencia": datetime.strptime("09:00", "%H:%M").time()
        },
        {
            "rnc_cliente": "00118822334", # Carlos Manuel Guerrero Santos
            "nombre_caso": "Divorcio por Mutuo Acuerdo - Guerrero & Mejía",
            "rol_firma": "Demandante",
            "rama_derecho": "Civil",
            "sub_categoria": "Divorcio",
            "tipo_accion": "Trámite de divorcio por mutuo acuerdo",
            "jurisdiccion_actual": "Primera Instancia",
            "tribunal_asignado": "Séptima Sala de la Cámara Civil y Comercial (Asuntos de Familia) del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-EFAM-00512",
            "juez_asignado": "Dra. Miriam Germain",
            "nombre_contraparte": "Laura Estela Mejía Pérez",
            "contacto_contraparte": "Calle El Vergel #33, Santo Domingo",
            "abogado_contraparte": "Licda. Rosa Alba",
            "contacto_abogado_contraparte": "809-565-1212 / ralba@albalegal.do",
            "monto_demanda": 0.00,
            "fecha_audiencia": date(2026, 8, 25),
            "hora_audiencia": datetime.strptime("10:30", "%H:%M").time()
        },
        {
            "rnc_cliente": "101887766", # Clínica Dental OdontoSalud, S.R.L.
            "nombre_caso": "Daños y Perjuicios por Difamación contra Yanet Núñez",
            "rol_firma": "Demandante",
            "rama_derecho": "Penal",
            "sub_categoria": "Acción Penal Privada",
            "tipo_accion": "Querella por difamación e injuria pública",
            "jurisdiccion_actual": "Primera Instancia",
            "tribunal_asignado": "Cuarta Sala de la Cámara Penal del Juzgado de Primera Instancia del Distrito Nacional",
            "numero_expediente_tribunal": "024-2026-EPEN-00995",
            "juez_asignado": "Dr. Teófilo Andújar",
            "nombre_contraparte": "Yanet del Carmen Núñez",
            "contacto_contraparte": "Calle Dr. Delgado #15, Santo Domingo",
            "abogado_contraparte": "Lic. Julio César López",
            "contacto_abogado_contraparte": "829-333-8877 / jclopez@abogados.com.do",
            "monto_demanda": 1500000.00,
            "fecha_audiencia": date(2026, 10, 5),
            "hora_audiencia": datetime.strptime("09:15", "%H:%M").time()
        }
    ]

    nuevos_exp_administrativos = [
        {
            "rnc_cliente": "03100554433", # Sofía Isabel Peralta Almonte
            "nombre_caso": "Registro Sanitario de Cosméticos 'Sofi Care'",
            "rol_firma": "Solicitante",
            "tipo_proceso": "Derecho Sanitario",
            "sub_proceso": "Obtención de Registro Sanitario de Producto Importado",
            "institucion_encargada": "Ministerio de Salud Pública (MISPAS)",
            "numero_solicitud_oficial": "MISPAS-RS-2026-1054",
            "descripcion_tramite": "Trámite de registro sanitario para línea de cremas faciales importadas de España.",
            "monto_tasas_impuestos": 35000.00
        },
        {
            "rnc_cliente": "102334455", # Inmobiliaria Hato Nuevo, S.A.
            "nombre_caso": "Saneamiento y Deslinde Parcela 12-B Higüey",
            "rol_firma": "Solicitante",
            "tipo_proceso": "Derecho Inmobiliario",
            "sub_proceso": "Saneamiento Catastral y Deslinde",
            "institucion_encargada": "Jurisdicción Inmobiliaria",
            "numero_solicitud_oficial": "JI-DESL-2026-9871",
            "descripcion_tramite": "Deslinde y saneamiento catastral para subdivisión de parcela de terreno con fines de desarrollo habitacional en Higüey.",
            "monto_tasas_impuestos": 45000.00
        }
    ]

    print("\nProcesando nuevos expedientes judiciales...")
    for ej in nuevos_exp_judiciales:
        cliente = clientes_db.get(ej["rnc_cliente"])
        if not cliente:
            print(f"Error: Cliente con RNC/Cédula {ej['rnc_cliente']} no encontrado.")
            continue
        
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
                tipo_tramite="Judicial",
                estado="Abierto"
            )
            db.session.add(nuevo_exp_j)
            db.session.flush()

            if ej["fecha_audiencia"]:
                comb_datetime = datetime.combine(ej["fecha_audiencia"], ej["hora_audiencia"])
                alerta = AlertaPlazoAudiencia(
                    expediente_id=nuevo_exp_j.id,
                    titulo_hito="Audiencia de Fondo / Primera Instancia",
                    fecha_vencimiento=comb_datetime,
                    estado_alerta='Pending',
                    fuente_origen='Firma',
                    es_audiencia=True
                )
                db.session.add(alerta)

            db.session.commit()
            print(f"Expediente judicial '{nuevo_exp_j.nombre_caso}' creado con éxito. Código: {nuevo_exp_j.codigo_firma}")

    print("\nProcesando nuevos expedientes administrativos...")
    for ea in nuevos_exp_administrativos:
        cliente = clientes_db.get(ea["rnc_cliente"])
        if not cliente:
            print(f"Error: Cliente con RNC/Cédula {ea['rnc_cliente']} no encontrado.")
            continue
        
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

    print("\n¡Inserción de datos nuevos finalizada con éxito!")
