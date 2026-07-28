import sys
import os

# Asegurar que el path del proyecto esté disponible
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import Usuario, Expediente, ExpedienteJudicial, Cliente

def test_multiple_lawyers_assignment():
    app = create_app()
    with app.app_context():
        print("Iniciando prueba de asignación de múltiples abogados...")
        
        # 1. Obtener o crear usuarios de prueba
        abogado1 = Usuario.query.filter_by(email="abogado1@test.com").first()
        if not abogado1:
            abogado1 = Usuario(nombre="Abogado de Prueba 1", email="abogado1@test.com", rol="Asociado", password_hash="dummy")
            db.session.add(abogado1)
            
        abogado2 = Usuario.query.filter_by(email="abogado2@test.com").first()
        if not abogado2:
            abogado2 = Usuario(nombre="Abogado de Prueba 2", email="abogado2@test.com", rol="Asociado", password_hash="dummy")
            db.session.add(abogado2)
            
        cliente = Cliente.query.first()
        if not cliente:
            cliente = Cliente(nombres="Cliente", apellidos="Prueba", rnc_cedula="000-0000000-0", email="cliente@test.com")
            db.session.add(cliente)
            
        db.session.commit()
        print(f"Abogados creados/obtenidos: {abogado1.nombre} (ID: {abogado1.id}), {abogado2.nombre} (ID: {abogado2.id})")
        print(f"Cliente obtenido: {cliente.nombre_completo} (ID: {cliente.id})")
        
        # 2. Crear un nuevo expediente asignando múltiples abogados
        nuevo_caso = ExpedienteJudicial(
            codigo_firma="TEST-MULTIPLE-ABOGADOS",
            cliente_id=cliente.id,
            nombre_caso="Caso de Prueba Múltiples Abogados",
            rol_firma="Demandante",
            materia_id=1,
            tipo_tramite="Judicial",
            estado="Activo"
        )
        
        # Asignar la relación muchos a muchos
        nuevo_caso.abogados = [abogado1, abogado2]
        
        # Asignar el primer abogado como responsable principal
        nuevo_caso.abogado_responsable_id = abogado1.id
        
        db.session.add(nuevo_caso)
        db.session.commit()
        print("Expediente creado con éxito!")
        
        # 3. Consultar y verificar desde la base de datos
        exp_verif = Expediente.query.filter_by(codigo_firma="TEST-MULTIPLE-ABOGADOS").first()
        assert exp_verif is not None, "El expediente no fue guardado"
        assert len(exp_verif.abogados) == 2, f"Se esperaban 2 abogados asignados, se encontraron: {len(exp_verif.abogados)}"
        assert exp_verif.abogado_responsable_id == abogado1.id, "El abogado responsable principal no coincide"
        
        print("--- VERIFICACIÓN DE ABOGADOS ---")
        for a in exp_verif.abogados:
            print(f"- Abogado asignado: {a.nombre} (Rol: {a.rol})")
        print(f"Abogado Principal (Responsable): {exp_verif.abogado_responsable.nombre}")
        
        # 4. Validar que la búsqueda por any() funciona correctamente
        # Buscar expedientes donde el abogado 2 está asignado
        casos_abogado2 = Expediente.query.filter(Expediente.abogados.any(Usuario.id == abogado2.id)).all()
        assert any(c.id == exp_verif.id for c in casos_abogado2), "El filtro any() no devolvió el caso del abogado 2"
        print("Filtro filter(Expediente.abogados.any(...)) funciona correctamente!")
        
        # 5. Limpieza
        db.session.delete(exp_verif)
        db.session.commit()
        print("Expediente de prueba eliminado y base de datos limpia.")
        print("Prueba completada exitosamente sin fallos!")

if __name__ == '__main__':
    test_multiple_lawyers_assignment()
