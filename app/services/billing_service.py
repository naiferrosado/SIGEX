from app import db
from app.models import (
    ParametroFiscal,
    ContratoHonorarios,
    CronogramaCobro,
    FacturaHonorario,
    TransaccionPago,
    ReciboInterno,
    GastoReembolsable,
    rd_now,
    rd_today
)
from decimal import Decimal
from datetime import datetime

class BillingService:
    @staticmethod
    def get_itbis_percentage():
        param = ParametroFiscal.query.filter_by(clave='itbis_default').first()
        if param:
            return Decimal(str(param.valor))
        return Decimal('18.00')

    @staticmethod
    def calcular_itbis(subtotal, aplica_itbis):
        subtotal = Decimal(str(subtotal))
        if not aplica_itbis:
            return Decimal('0.00'), subtotal

        porcentaje = BillingService.get_itbis_percentage() / Decimal('100.00')
        itbis = (subtotal * porcentaje).quantize(Decimal('0.01'))
        total = subtotal + itbis
        return itbis, total

    @staticmethod
    def generar_cronograma(contrato, cuotas_data=None):
        """
        cuotas_data: list of dicts like [{'descripcion': '...', 'monto': ..., 'fecha_vencimiento': Date/Str}]
        """
        # Eliminar cronograma existente si es borrador
        if contrato.estado == 'Borrador':
            CronogramaCobro.query.filter_by(contrato_id=contrato.id).delete()

        if not cuotas_data:
            # Generar cuota única por defecto
            cuota = CronogramaCobro(
                contrato_id=contrato.id,
                descripcion='Pago de Honorarios - Contrato',
                fecha_vencimiento=contrato.fecha_inicio or rd_today(),
                monto=contrato.total_contrato,
                estado='Pendiente',
                orden=1,
                tipo='Cuota'
            )
            db.session.add(cuota)
        else:
            for idx, c_data in enumerate(cuotas_data):
                fecha_v = c_data.get('fecha_vencimiento')
                if isinstance(fecha_v, str):
                    fecha_v = datetime.strptime(fecha_v, '%Y-%m-%d').date()
                
                cuota = CronogramaCobro(
                    contrato_id=contrato.id,
                    descripcion=c_data.get('descripcion', f'Cuota {idx+1}'),
                    fecha_vencimiento=fecha_v or rd_today(),
                    monto=Decimal(str(c_data.get('monto', 0))),
                    estado='Pendiente',
                    orden=idx + 1,
                    tipo=c_data.get('tipo', 'Cuota')
                )
                db.session.add(cuota)
        db.session.commit()

    @staticmethod
    def registrar_pago(factura_id, monto, metodo_pago, referencia=None):
        factura = FacturaHonorario.query.get(factura_id)
        if not factura:
            return None, "Factura no encontrada"

        monto = Decimal(str(monto))
        if monto <= 0:
            return None, "El monto del pago debe ser mayor a cero"

        total_pendiente = Decimal(str(factura.total_pendiente))
        if monto > total_pendiente:
            return None, f"El pago no puede exceder el monto pendiente de RD$ {total_pendiente:,.2f}"

        # 1. Crear Recibo Interno
        recibos_count = ReciboInterno.query.count() + 1
        num_recibo = f"REC-{recibos_count:06d}"
        recibo = ReciboInterno(
            numero_recibo=num_recibo,
            cliente_id=factura.cliente_id,
            fecha_emision=rd_now(),
            monto_total=monto,
            observaciones=f"Pago recibido para Factura NCF {factura.ncf or 'Sin NCF'}"
        )
        db.session.add(recibo)
        db.session.flush() # Obtener el ID de recibo

        # 2. Crear Transacción de Pago
        pago = TransaccionPago(
            factura_id=factura.id,
            recibo_id=recibo.id,
            monto=monto,
            fecha_pago=rd_now(),
            metodo_pago=metodo_pago,
            referencia=referencia
        )
        db.session.add(pago)

        # 3. Actualizar estado de la factura
        nuevo_total_pagado = Decimal(str(factura.total_pagado)) + monto
        if nuevo_total_pagado >= Decimal(str(factura.monto_total)):
            factura.estado_pago = 'Cobrado'
            # Si tiene cuota vinculada, actualizar estado de la cuota
            if factura.cuota_id:
                cuota = CronogramaCobro.query.get(factura.cuota_id)
                if cuota:
                    cuota.estado = 'Pagado'
        else:
            factura.estado_pago = 'Cobrado Parcial'
            if factura.cuota_id:
                cuota = CronogramaCobro.query.get(factura.cuota_id)
                if cuota:
                    cuota.estado = 'Pendiente' # Sigue pendiente hasta completar

        db.session.commit()
        return recibo, None

    @staticmethod
    def obtener_resumen_expediente(expediente_id):
        contratos = ContratoHonorarios.query.filter_by(expediente_id=expediente_id).all()
        
        monto_contratado = Decimal('0.00')
        monto_facturado = Decimal('0.00')
        monto_cobrado = Decimal('0.00')

        contrato_ids = []
        for c in contratos:
            if c.estado in ['Vigente', 'Finalizado']:
                monto_contratado += Decimal(str(c.total_contrato))
                contrato_ids.append(c.id)

        # Facturas
        facturas = FacturaHonorario.query.filter_by(expediente_id=expediente_id).filter(
            FacturaHonorario.estado_pago != 'Anulado'
        ).all()

        for f in facturas:
            monto_facturado += Decimal(str(f.monto_total))
            monto_cobrado += Decimal(str(f.total_pagado))

        balance_pendiente = monto_contratado - monto_cobrado

        # Próxima cuota y vencimiento
        proxima_cuota = None
        proximo_vencimiento = None
        
        if contrato_ids:
            next_installment = CronogramaCobro.query.filter(
                CronogramaCobro.contrato_id.in_(contrato_ids),
                CronogramaCobro.estado == 'Pendiente'
            ).order_by(CronogramaCobro.fecha_vencimiento.asc()).first()
            
            if next_installment:
                proxima_cuota = next_installment.monto
                proximo_vencimiento = next_installment.fecha_vencimiento.strftime('%d/%m/%Y')

        # Última factura
        ultima_factura_str = '—'
        last_f = FacturaHonorario.query.filter_by(expediente_id=expediente_id).filter(
            FacturaHonorario.estado_pago != 'Anulado'
        ).order_by(FacturaHonorario.fecha_emision.desc()).first()
        if last_f:
            ultima_factura_str = f"{last_f.ncf or 'Sin NCF'} ({last_f.fecha_emision.strftime('%d/%m/%Y')})"

        # Último pago
        ultimo_pago_str = '—'
        fact_ids = [f.id for f in facturas]
        if fact_ids:
            last_pago = TransaccionPago.query.filter(
                TransaccionPago.factura_id.in_(fact_ids)
            ).order_by(TransaccionPago.fecha_pago.desc()).first()
            if last_pago:
                ultimo_pago_str = f"RD$ {last_pago.monto:,.2f} ({last_pago.fecha_pago.strftime('%d/%m/%Y')})"

        return {
            "contratos_count": len(contratos),
            "monto_contratado": float(monto_contratado),
            "monto_facturado": float(monto_facturado),
            "monto_cobrado": float(monto_cobrado),
            "balance_pendiente": float(balance_pendiente),
            "proxima_cuota": float(proxima_cuota) if proxima_cuota else None,
            "proximo_vencimiento": proximo_vencimiento,
            "ultima_factura": ultima_factura_str,
            "ultimo_pago": ultimo_pago_str
        }
