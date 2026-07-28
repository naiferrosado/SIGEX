import unittest
from decimal import Decimal
from datetime import date, timedelta
from app import create_app, db
import uuid
from app.models import (
    Cliente,
    ExpedienteJudicial,
    ContratoHonorarios,
    CronogramaCobro,
    FacturaHonorario,
    ParametroFiscal,
    ReciboInterno,
    TransaccionPago,
    GastoReembolsable
)
from app.services.billing_service import BillingService

class TestBillingRedesign(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Asegurar que el parámetro fiscal existe
        param = ParametroFiscal.query.filter_by(clave='itbis_default').first()
        if not param:
            param = ParametroFiscal(clave='itbis_default', valor=Decimal('18.00'), descripcion='ITBIS Standard')
            db.session.add(param)
            db.session.commit()

    def tearDown(self):
        db.session.rollback()
        # Limpiar registros temporales
        clientes_temp = Cliente.query.filter(Cliente.nombres.like('Cliente%')).all()
        for c in clientes_temp:
            # Eliminar en cascada
            from app.models import Expediente
            Expediente.query.filter_by(cliente_id=c.id).delete()
            ContratoHonorarios.query.filter_by(cliente_id=c.id).delete()
            FacturaHonorario.query.filter_by(cliente_id=c.id).delete()
            ReciboInterno.query.filter_by(cliente_id=c.id).delete()
            db.session.delete(c)
        db.session.commit()
        self.app_context.pop()

    def test_calcular_itbis(self):
        # Con ITBIS habilitado
        itbis, total = BillingService.calcular_itbis(Decimal('100.00'), True)
        self.assertEqual(itbis, Decimal('18.00'))
        self.assertEqual(total, Decimal('118.00'))

        # Con ITBIS inhabilitado
        itbis_none, total_none = BillingService.calcular_itbis(Decimal('100.00'), False)
        self.assertEqual(itbis_none, Decimal('0.00'))
        self.assertEqual(total_none, Decimal('100.00'))

    def test_generar_cronograma_defecto(self):
        cliente = Cliente(nombres="Cliente", apellidos="Test", rnc_cedula="101010101", tipo_cliente="Física", email_contacto="test@example.com")
        db.session.add(cliente)
        db.session.commit()

        contrato = ContratoHonorarios(
            cliente_id=cliente.id,
            tipo_cobro='Fijo',
            moneda='DOP',
            aplica_itbis=True,
            porcentaje_itbis=Decimal('18.00'),
            subtotal=Decimal('50000.00'),
            itbis=Decimal('9000.00'),
            total_contrato=Decimal('59000.00'),
            estado='Borrador'
        )
        db.session.add(contrato)
        db.session.commit()

        # Generar cronograma
        BillingService.generar_cronograma(contrato)

        cuotas = CronogramaCobro.query.filter_by(contrato_id=contrato.id).all()
        self.assertEqual(len(cuotas), 1)
        self.assertEqual(cuotas[0].monto, Decimal('59000.00'))
        self.assertEqual(cuotas[0].estado, 'Pendiente')

    def test_generar_cronograma_multiples_cuotas(self):
        cliente = Cliente(nombres="Cliente Test", apellidos="Multi", rnc_cedula="202020202", tipo_cliente="Física", email_contacto="test@example.com")
        db.session.add(cliente)
        db.session.commit()

        contrato = ContratoHonorarios(
            cliente_id=cliente.id,
            tipo_cobro='Cuotas',
            moneda='DOP',
            aplica_itbis=True,
            porcentaje_itbis=Decimal('18.00'),
            subtotal=Decimal('60000.00'),
            itbis=Decimal('10800.00'),
            total_contrato=Decimal('70800.00'),
            estado='Borrador'
        )
        db.session.add(contrato)
        db.session.commit()

        cuotas_data = [
            {'descripcion': 'Anticipo', 'monto': Decimal('23600.00'), 'fecha_vencimiento': date.today()},
            {'descripcion': 'Cuota 2', 'monto': Decimal('23600.00'), 'fecha_vencimiento': date.today() + timedelta(days=30)},
            {'descripcion': 'Cuota 3', 'monto': Decimal('23600.00'), 'fecha_vencimiento': date.today() + timedelta(days=60)},
        ]

        # Generar cronograma
        BillingService.generar_cronograma(contrato, cuotas_data)

        cuotas = CronogramaCobro.query.filter_by(contrato_id=contrato.id).order_by(CronogramaCobro.orden).all()
        self.assertEqual(len(cuotas), 3)
        self.assertEqual(cuotas[0].descripcion, 'Anticipo')
        self.assertEqual(cuotas[0].monto, Decimal('23600.00'))
        self.assertEqual(cuotas[2].orden, 3)

    def test_pagos_parciales_y_recibos(self):
        cliente = Cliente(nombres="Cliente Pagos", apellidos="Test", rnc_cedula="303030303", tipo_cliente="Física", email_contacto="test@example.com")
        db.session.add(cliente)
        db.session.commit()

        import uuid
        unique_ncf1 = f"B02{uuid.uuid4().hex[:10].upper()}"
        factura = FacturaHonorario(
            cliente_id=cliente.id,
            ncf=unique_ncf1,
            tipo_comprobante="02",
            monto_subtotal=Decimal('10000.00'),
            monto_itbis=Decimal('1800.00'),
            monto_total=Decimal('11800.00'),
            estado_pago="Pendiente"
        )
        db.session.add(factura)
        db.session.commit()

        # 1. Pago parcial
        recibo1, err1 = BillingService.registrar_pago(factura.id, Decimal('5000.00'), 'Efectivo', 'Abono 1')
        self.assertIsNone(err1)
        self.assertIsNotNone(recibo1)
        self.assertEqual(factura.estado_pago, 'Cobrado Parcial')
        self.assertEqual(factura.total_pagado, Decimal('5000.00'))
        self.assertEqual(factura.total_pendiente, Decimal('6800.00'))

        # 2. Completar pago
        recibo2, err2 = BillingService.registrar_pago(factura.id, Decimal('6800.00'), 'Transferencia', 'Abono 2')
        self.assertIsNone(err2)
        self.assertIsNotNone(recibo2)
        self.assertEqual(factura.estado_pago, 'Cobrado')
        self.assertEqual(factura.total_pagado, Decimal('11800.00'))
        self.assertEqual(factura.total_pendiente, Decimal('0.00'))

    def test_resumen_financiero_expediente(self):
        cliente = Cliente(nombres="Cliente Resumen", apellidos="Test", rnc_cedula="404040404", tipo_cliente="Física", email_contacto="test@example.com")
        db.session.add(cliente)
        db.session.commit()

        expediente = ExpedienteJudicial(
            codigo_firma="EXP-TEST",
            cliente_id=cliente.id,
            nombre_caso="Caso Test",
            rol_firma="Demandado",
            rama_derecho="Civil",
            sub_categoria="Cobro de pesos",
            tipo_accion="Cobro de pesos",
            jurisdiccion_actual="Primera Instancia",
            tipo_tramite="Judicial",
            estado="Activo",
            prioridad="Alta",
            nivel_riesgo="Alto",
            probabilidad_exito="Alta",
            fecha_contratacion=date.today()
        )
        db.session.add(expediente)
        db.session.commit()

        contrato = ContratoHonorarios(
            cliente_id=cliente.id,
            expediente_id=expediente.id,
            tipo_cobro='Fijo',
            moneda='DOP',
            aplica_itbis=True,
            porcentaje_itbis=Decimal('18.00'),
            subtotal=Decimal('100000.00'),
            itbis=Decimal('18000.00'),
            total_contrato=Decimal('118000.00'),
            estado='Vigente'
        )
        db.session.add(contrato)
        db.session.commit()

        # Generar cronograma
        BillingService.generar_cronograma(contrato)
        cuota = CronogramaCobro.query.filter_by(contrato_id=contrato.id).first()

        # Facturar la cuota
        unique_ncf2 = f"B02{uuid.uuid4().hex[:10].upper()}"
        factura = FacturaHonorario(
            cliente_id=cliente.id,
            expediente_id=expediente.id,
            contrato_id=contrato.id,
            cuota_id=cuota.id,
            ncf=unique_ncf2,
            tipo_comprobante="02",
            monto_subtotal=Decimal('100000.00'),
            monto_itbis=Decimal('18000.00'),
            monto_total=Decimal('118000.00'),
            estado_pago="Pendiente"
        )
        db.session.add(factura)
        db.session.commit()

        # Registrar un pago
        BillingService.registrar_pago(factura.id, Decimal('50000.00'), 'Efectivo')

        # Obtener resumen
        resumen = BillingService.obtener_resumen_expediente(expediente.id)
        self.assertEqual(resumen['monto_contratado'], 118000.00)
        self.assertEqual(resumen['monto_facturado'], 118000.00)
        self.assertEqual(resumen['monto_cobrado'], 50000.00)
        self.assertEqual(resumen['balance_pendiente'], 68000.00)

if __name__ == '__main__':
    unittest.main()
