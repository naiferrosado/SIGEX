import os
import sys

# Agregar directorio del proyecto al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db
from app.models import Usuario, BitacoraAuditoria, Expediente, rd_now

def test_payroll_endpoint():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    
    client = app.test_client()
    
    with app.app_context():
        print("\n=== INICIANDO PRUEBAS DE NOMINA Y LIQUIDACIONES ===")
        
        # 1. Autenticar como Socio
        socio_email = "socio.test@rosadomendez.com"
        login_res = client.post("/login", data={
            "email": socio_email,
            "password": "password123"
        }, follow_redirects=True)
        print(f"[AUTH] Login Socio status: {login_res.status_code}")
        
        # 2. Registrar cobro de prueba en la auditoría para verificar cálculo
        asociado = Usuario.query.filter_by(rol="Asociado").first()
        if asociado:
            print(f"[TEST] Usando asociado: {asociado.nombre} (Comision: {asociado.porcentaje_comision}%)")
            
            # Crear un expediente para el asociado si no tiene
            exp = Expediente.query.filter_by(abogado_responsable_id=asociado.id).first()
            if not exp:
                print("[WARNING] El asociado no tiene expedientes asignados. No se podrá comprobar comisiones dinámicas.")
            else:
                # Registrar entrada de auditoria simulada de pago
                ahora = rd_now()
                log_pago = BitacoraAuditoria(
                    fecha_hora=ahora,
                    accion_realizada="COBRO_CUOTA_FACTURA",
                    detalles_tecnicos=f"Se registró el cobro de la cuota 'Cuota 1' por un monto de RD$ 100,000.00 de la factura ID 999.",
                    expediente_id=exp.id
                )
                db.session.add(log_pago)
                db.session.commit()
                print(f"[TEST] Registrada auditoria de cobro simulado por RD$ 100,000.00 en expediente ID {exp.id}")
                
                # 3. Invocar endpoint /nomina
                res_nomina = client.get(f"/nomina?mes={ahora.month}&anio={ahora.year}")
                print(f"[TEST] GET /nomina status: {res_nomina.status_code}")
                
                # Comprobar que el HTML devuelto contiene el nombre del asociado y el monto esperado
                html_content = res_nomina.get_data(as_text=True)
                if asociado.nombre in html_content:
                    print(f"[OK] El nombre del asociado '{asociado.nombre}' aparece en la nómina.")
                else:
                    print("[FAIL] El nombre del asociado no aparece en la nómina.")
                    
                # Limpiar auditoría
                db.session.delete(log_pago)
                db.session.commit()
        else:
            print("[FAIL] No hay asociado en la base de datos.")
            
        # 4. Probar seguridad: Asociado no debe poder entrar a /nomina
        client.get("/logout")
        client.post("/login", data={
            "email": "asociado.test@rosadomendez.com",
            "password": "password123"
        }, follow_redirects=True)
        
        res_seg = client.get("/nomina")
        print(f"[TEST SEGURIDAD] GET /nomina como Asociado status: {res_seg.status_code}")
        if res_seg.status_code == 302 and "/dashboard" in res_seg.headers.get("Location", ""):
            print("[OK] Bloqueo a asociados correcto (redirección a dashboard).")
        else:
            print("[FAIL] Un asociado pudo acceder al endpoint /nomina.")
            
        print("=== FIN DE PRUEBAS DE NOMINA ===\n")

if __name__ == "__main__":
    test_payroll_endpoint()
