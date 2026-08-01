import sys
import os
from decimal import Decimal
from datetime import datetime, date, timedelta

# Asegurar que el path del proyecto esté en python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import (
    Cliente, Presupuesto, PresupuestoDetalle, ContratoHonorarios,
    CronogramaCobro, FacturaHonorario, DetalleFactura, TransaccionPago, ReciboInterno
)

app = create_app()

with app.app_context():
    print("Iniciando inserción de 5 ejemplos del ciclo de facturación...")

    # Definir clientes y datos
    ejemplos = [
        # Ejemplo 1: Constitucion de SRL
        {
            "rnc_cedula": "131849502",
            "nombres": "Constructora del",
            "apellidos": "Caribe, S.R.L.",
            "tipo_cliente": "Persona jurídica",
            "direccion": "Av. Anacaona #220, Los Cacicazgos, Santo Domingo",
            "telefono": "809-555-8822",
            "email_contacto": "contacto@constructoracaribe.com.do",
            "presupuesto": {
                "titulo": "Constitución de Constructora del Caribe SRL",
                "materia": "Corporativo",
                "tipo_asunto": "Constitución de Sociedad",
                "descripcion": "Honorarios por constitución de sociedad de responsabilidad limitada en la Rep. Dom.",
                "aplica_itbis": True,
                "partidas": [
                    {"descripcion": "Honorarios por redacción de estatutos y asamblea de constitución", "cantidad": 1, "precio": Decimal("35000.00")},
                    {"descripcion": "Gastos de registro de nombre comercial (ONAPI) y registro mercantil", "cantidad": 1, "precio": Decimal("10000.00")}
                ]
            },
            "contrato": {
                "tipo_cobro": "Fijo",
                "moneda": "DOP",
                "observaciones": "Contrato por honorarios de constitución. 50% de anticipo y 50% contra entrega.",
                "anticipo": Decimal("26550.00")
            },
            "pago": {
                "monto_abono": Decimal("26550.00"),
                "metodo_pago": "Transferencia",
                "referencia": "Transf. Banreservas #89321",
                "tipo_comprobante": "31" # Factura de Crédito Fiscal
            }
        },
        # Ejemplo 2: Divorcio por Mutuo Acuerdo
        {
            "rnc_cedula": "00115824961",
            "nombres": "Juan Carlos",
            "apellidos": "Pérez Martínez",
            "tipo_cliente": "Persona física",
            "direccion": "Av. Winston Churchill #105, Ensanche Piantini, Santo Domingo",
            "telefono": "809-555-0192",
            "email_contacto": "juan.perez@example.com",
            "presupuesto": {
                "titulo": "Divorcio por Mutuo Acuerdo - Pérez & Gómez",
                "materia": "Civil",
                "tipo_asunto": "Divorcio",
                "descripcion": "Honorarios profesionales para tramitación de divorcio por mutuo acuerdo.",
                "aplica_itbis": True,
                "partidas": [
                    {"descripcion": "Redacción de acuerdo de estipulaciones y convenciones", "cantidad": 1, "precio": Decimal("40000.00")},
                    {"descripcion": "Representación y trámites ante la Cámara Civil y Comercial", "cantidad": 1, "precio": Decimal("20000.00")}
                ]
            },
            "contrato": {
                "tipo_cobro": "Cuotas",
                "moneda": "DOP",
                "observaciones": "Contrato de divorcio financiado en 3 cuotas mensuales consecutivas de RD$ 23,600.00.",
                "anticipo": Decimal("0.00")
            },
            "pago": {
                "monto_abono": Decimal("23600.00"), # Pago de la primera cuota
                "metodo_pago": "Tarjeta",
                "referencia": "Card Visa *4321 Auth 5542",
                "tipo_comprobante": "31"
            }
        },
        # Ejemplo 3: Demanda en Cobro de Pesos (Litigio)
        {
            "rnc_cedula": "101759283",
            "nombres": "Inversiones",
            "apellidos": "Falcon, S.A.",
            "tipo_cliente": "Persona jurídica",
            "direccion": "Calle Lope de Vega #12, Naco, Santo Domingo",
            "telefono": "809-555-9000",
            "email_contacto": "legal@inversionesfalcon.com",
            "presupuesto": {
                "titulo": "Representación Demanda en Cobro de Pesos contra deudores",
                "materia": "Civil",
                "tipo_asunto": "Litigio Civil",
                "descripcion": "Honorarios por representación en demanda judicial de cobro de pesos.",
                "aplica_itbis": True,
                "partidas": [
                    {"descripcion": "Honorarios de litigación civil primera instancia", "cantidad": 1, "precio": Decimal("120000.00")},
                    {"descripcion": "Gastos de notificaciones de Alguacil y emplazamientos", "cantidad": 1, "precio": Decimal("30000.00")}
                ]
            },
            "contrato": {
                "tipo_cobro": "Etapas",
                "moneda": "DOP",
                "observaciones": "Cobro por hitos del litigio: 40% a la firma, 30% a la audiencia de pruebas, 30% con sentencia.",
                "anticipo": Decimal("0.00")
            },
            "pago": {
                "monto_abono": Decimal("70800.00"), # Pago primera etapa (40% de 177,000)
                "metodo_pago": "Cheque",
                "referencia": "Cheque BHD #90842",
                "tipo_comprobante": "32" # Factura de Consumo
            }
        },
        # Ejemplo 4: Registro de Marca
        {
            "rnc_cedula": "03100984711",
            "nombres": "Pedro Luis",
            "apellidos": "Espinal Gómez",
            "tipo_cliente": "Persona física",
            "direccion": "Av. 27 de Febrero #300, Sector La Julia, Santo Domingo",
            "telefono": "849-555-4721",
            "email_contacto": "pedro.espinal@example.com",
            "presupuesto": {
                "titulo": "Registro de Marca Comercial 'Caribe Built'",
                "materia": "Propiedad Intelectual",
                "tipo_asunto": "Registro de Marca",
                "descripcion": "Gestión de registro de marca de fábrica ante la ONAPI.",
                "aplica_itbis": True,
                "partidas": [
                    {"descripcion": "Búsqueda, análisis de factibilidad and solicitud", "cantidad": 1, "precio": Decimal("10000.00")},
                    {"descripcion": "Tasas oficiales de publicación en el periódico oficial", "cantidad": 1, "precio": Decimal("15000.00")}
                ]
            },
            "contrato": {
                "tipo_cobro": "Fijo",
                "moneda": "DOP",
                "observaciones": "Gestión de registro de marca. Pago único fijo de RD$ 29,500.00.",
                "anticipo": Decimal("0.00")
            },
            "pago": {
                "monto_abono": Decimal("15000.00"), # Abono parcial de RD$ 15,000.00
                "metodo_pago": "Depósito",
                "referencia": "Depósito Banreservas Boleto #44921",
                "tipo_comprobante": "31"
            }
        },
        # Ejemplo 5: Asesoría Mensual (Iguala Corporativa)
        {
            "rnc_cedula": "00201948572",
            "nombres": "María Altagracia",
            "apellidos": "Rodríguez Tejeda",
            "tipo_cliente": "Persona física",
            "direccion": "Calle El Sol #45, Santiago de los Caballeros",
            "telefono": "829-555-3847",
            "email_contacto": "maria.rodriguez@example.com",
            "presupuesto": {
                "titulo": "Iguala de Asesoría Legal Corporativa Mensual",
                "materia": "Corporativo",
                "tipo_asunto": "Iguala Mensual",
                "descripcion": "Servicio continuo de asesoría jurídica general corporativa.",
                "aplica_itbis": True,
                "partidas": [
                    {"descripcion": "Servicios de asesoría corporativa continua e iguala mensual", "cantidad": 1, "precio": Decimal("30000.00")}
                ]
            },
            "contrato": {
                "tipo_cobro": "Iguala",
                "moneda": "DOP",
                "observaciones": "Contrato de iguala legal de renovación mensual.",
                "anticipo": Decimal("0.00")
            },
            "pago": {
                "monto_abono": Decimal("35400.00"), # Pago total del primer mes
                "metodo_pago": "Transferencia",
                "referencia": "Transf. Banco Popular #4439120",
                "tipo_comprobante": "31"
            }
        }
    ]

    for ex in ejemplos:
        # 1. Obtener o crear Cliente
        cliente = Cliente.query.filter_by(rnc_cedula=ex["rnc_cedula"]).first()
        if not cliente:
            cliente = Cliente(
                rnc_cedula=ex["rnc_cedula"],
                nombres=ex["nombres"],
                apellidos=ex["apellidos"],
                tipo_cliente=ex["tipo_cliente"],
                direccion=ex["direccion"],
                telefono=ex["telefono"],
                email_contacto=ex["email_contacto"],
                consentimiento_datos=True,
                fecha_consentimiento=datetime.utcnow()
            )
            db.session.add(cliente)
            db.session.flush()
            print(f"Cliente creado: {cliente.nombre_completo}")
        else:
            print(f"Cliente existente utilizado: {cliente.nombre_completo}")

        # 2. Crear Presupuesto
        pres_data = ex["presupuesto"]
        subtotal = Decimal("0.00")
        for p in pres_data["partidas"]:
            subtotal += p["cantidad"] * p["precio"]
        
        itbis = (subtotal * Decimal("0.18")).quantize(Decimal("0.01")) if pres_data["aplica_itbis"] else Decimal("0.00")
        total = subtotal + itbis

        presupuesto = Presupuesto(
            cliente_id=cliente.id,
            titulo=pres_data["titulo"],
            materia=pres_data["materia"],
            tipo_asunto=pres_data["tipo_asunto"],
            descripcion=pres_data["descripcion"],
            monto_subtotal=subtotal,
            monto_itbis=itbis,
            monto_total=total,
            estado="Aceptado", # Marcado directamente como Aceptado para simular el ciclo
            fecha_emision=datetime.utcnow()
        )
        db.session.add(presupuesto)
        db.session.flush()

        for p in pres_data["partidas"]:
            det = PresupuestoDetalle(
                presupuesto_id=presupuesto.id,
                descripcion=p["descripcion"],
                cantidad=p["cantidad"],
                precio_unitario=p["precio"],
                subtotal=p["cantidad"] * p["precio"]
            )
            db.session.add(det)
        print(f"Presupuesto creado y aceptado: #{presupuesto.id} - {presupuesto.titulo}")

        # 3. Crear Contrato de Honorarios
        contr_data = ex["contrato"]
        contrato = ContratoHonorarios(
            cliente_id=cliente.id,
            presupuesto_id=presupuesto.id,
            fecha_firma=date.today(),
            fecha_inicio=date.today(),
            estado="Vigente",
            observaciones=contr_data["observaciones"],
            tipo_cobro=contr_data["tipo_cobro"],
            moneda=contr_data["moneda"],
            aplica_itbis=pres_data["aplica_itbis"],
            porcentaje_itbis=Decimal("18.00"),
            subtotal=subtotal,
            itbis=itbis,
            total_contrato=total
        )
        db.session.add(contrato)
        db.session.flush()
        print(f"Contrato firmado: #{contrato.id} - Esquema: {contrato.tipo_cobro}")

        # Generar cuotas en el cronograma
        cuotas_creadas = []
        if contr_data["tipo_cobro"] == "Fijo":
            cuota = CronogramaCobro(
                contrato_id=contrato.id,
                descripcion="Pago de Honorarios - Contrato",
                fecha_vencimiento=date.today() + timedelta(days=30),
                monto=total,
                estado="Pendiente",
                orden=1,
                tipo="Cuota"
            )
            db.session.add(cuota)
            cuotas_creadas.append(cuota)
        elif contr_data["tipo_cobro"] == "Cuotas":
            for c_idx in range(3):
                m_cuota = (total / 3).quantize(Decimal("0.01"))
                cuota = CronogramaCobro(
                    contrato_id=contrato.id,
                    descripcion=f"Cuota {c_idx+1}/3 de Honorarios",
                    fecha_vencimiento=date.today() + timedelta(days=30 * (c_idx + 1)),
                    monto=m_cuota,
                    estado="Pendiente",
                    orden=c_idx + 1,
                    tipo="Cuota"
                )
                db.session.add(cuota)
                cuotas_creadas.append(cuota)
        elif contr_data["tipo_cobro"] == "Etapas":
            m_firma = (total * Decimal("0.4")).quantize(Decimal("0.01"))
            m_audiencia = (total * Decimal("0.3")).quantize(Decimal("0.01"))
            m_sentencia = (total - m_firma - m_audiencia)

            cuotas_def = [
                ("Etapa 1: Firma de Contrato (40%)", m_firma),
                ("Etapa 2: Audiencia de pruebas (30%)", m_audiencia),
                ("Etapa 3: Sentencia final (30%)", m_sentencia)
            ]
            for c_idx, (c_desc, c_monto) in enumerate(cuotas_def):
                cuota = CronogramaCobro(
                    contrato_id=contrato.id,
                    descripcion=c_desc,
                    fecha_vencimiento=date.today() + timedelta(days=45 * (c_idx + 1)),
                    monto=c_monto,
                    estado="Pendiente",
                    orden=c_idx + 1,
                    tipo="Cuota"
                )
                db.session.add(cuota)
                cuotas_creadas.append(cuota)
        elif contr_data["tipo_cobro"] == "Iguala":
            cuota = CronogramaCobro(
                contrato_id=contrato.id,
                descripcion="Iguala Mensual - Primer Mes",
                fecha_vencimiento=date.today() + timedelta(days=30),
                monto=total,
                estado="Pendiente",
                orden=1,
                tipo="Iguala"
            )
            db.session.add(cuota)
            cuotas_creadas.append(cuota)

        db.session.flush()

        # 4. Crear Factura NCF
        pago_data = ex["pago"]
        # Determinar el monto de la factura (será igual a la cuota a la que se le abonará/pagará)
        # Para simplificar, facturamos la primera cuota
        primera_cuota = cuotas_creadas[0]
        f_subtotal = (primera_cuota.monto / Decimal("1.18")).quantize(Decimal("0.01")) if pres_data["aplica_itbis"] else primera_cuota.monto
        f_itbis = primera_cuota.monto - f_subtotal

        # Generar un NCF correlativo secuencial
        tipo_comp = pago_data["tipo_comprobante"]
        last_invoice = FacturaHonorario.query.filter(
            FacturaHonorario.tipo_comprobante == tipo_comp,
            FacturaHonorario.ncf.like(f"B{tipo_comp}%")
        ).order_by(FacturaHonorario.id.desc()).first()
        
        if last_invoice and last_invoice.ncf:
            suffix = last_invoice.ncf[3:]
            next_num = int(suffix) + 1
            ncf = f"B{tipo_comp}{next_num:08d}"
        else:
            ncf = f"B{tipo_comp}00000001"

        factura = FacturaHonorario(
            cliente_id=cliente.id,
            ncf=ncf,
            tipo_comprobante=tipo_comp,
            monto_subtotal=f_subtotal,
            monto_itbis=f_itbis,
            monto_total=primera_cuota.monto,
            fecha_emision=datetime.utcnow(),
            fecha_vencimiento=date.today() + timedelta(days=30),
            estado_pago="Pendiente",
            plazo_pago_dias=30,
            contrato_id=contrato.id,
            cuota_id=primera_cuota.id
        )
        db.session.add(factura)
        db.session.flush()

        f_det = DetalleFactura(
            factura_id=factura.id,
            descripcion=f"Cobro de Honorarios - {primera_cuota.descripcion}",
            cantidad=1,
            precio_unitario=f_subtotal,
            subtotal=f_subtotal
        )
        db.session.add(f_det)
        primera_cuota.estado = "Facturado"
        print(f"Factura NCF creada: {factura.ncf} (Monto: RD$ {factura.monto_total:,.2f})")

        # 5. Registrar Abono / Pago y Generar Recibo Interno
        monto_pago = pago_data["monto_abono"]
        recibos_count = ReciboInterno.query.count() + 1
        num_recibo = f"REC-{recibos_count:06d}"
        recibo = ReciboInterno(
            numero_recibo=num_recibo,
            cliente_id=cliente.id,
            fecha_emision=datetime.utcnow(),
            monto_total=monto_pago,
            observaciones=f"Pago recibido para Factura NCF {factura.ncf or 'Sin NCF'}"
        )
        db.session.add(recibo)
        db.session.flush()

        transaccion = TransaccionPago(
            factura_id=factura.id,
            recibo_id=recibo.id,
            monto=monto_pago,
            fecha_pago=datetime.utcnow(),
            metodo_pago=pago_data["metodo_pago"],
            referencia=pago_data["referencia"]
        )
        db.session.add(transaccion)

        # Actualizar estado de la factura y cuota
        if monto_pago >= factura.monto_total:
            factura.estado_pago = "Cobrado"
            primera_cuota.estado = "Pagado"
            print(f"Factura {factura.ncf} marcada como COBRADA. Emitido Recibo {recibo.numero_recibo}")
        else:
            factura.estado_pago = "Cobrado Parcial"
            print(f"Factura {factura.ncf} pagada parcialmente por RD$ {monto_pago:,.2f}. Emitido Recibo {recibo.numero_recibo}")

    db.session.commit()
    print("\n¡Ejemplos creados y guardados con éxito en la base de datos de SIGEX!")
