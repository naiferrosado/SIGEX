import sys
import os

# Asegurar que el path del proyecto esté disponible
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import Usuario, Expediente, ExpedienteJudicial, Cliente, Tarea

def test_multiple_task_assignees():
    app = create_app()
    with app.app_context():
        print("Iniciando prueba de asignación de múltiples abogados a una tarea...")
        
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
        
        expediente = Expediente.query.first()
        if not expediente:
            expediente = ExpedienteJudicial(
                codigo_firma="TEST-EXP-TAREA",
                cliente_id=cliente.id,
                nombre_caso="Caso de Prueba para Tarea",
                rol_firma="Demandante",
                materia_id=1,
                tipo_tramite="Judicial",
                estado="Activo"
            )
            db.session.add(expediente)
            db.session.commit()
            
        # 2. Crear una nueva tarea con múltiples asignados
        nueva_tarea = Tarea(
            titulo="Tarea de Prueba Múltiples Asignados",
            descripcion="Descripción de la tarea de prueba",
            prioridad="Alta",
            estado="Pendiente",
            expediente_id=expediente.id,
            creado_por_id=abogado1.id
        )
        
        # Asignar relación muchos a muchos
        nueva_tarea.asignados = [abogado1, abogado2]
        
        # Asignar el primer abogado como responsable principal
        nueva_tarea.asignado_a_id = abogado1.id
        
        db.session.add(nueva_tarea)
        db.session.commit()
        print("Tarea creada con éxito!")
        
        # 3. Consultar y verificar desde la base de datos
        tarea_verif = Tarea.query.filter_by(titulo="Tarea de Prueba Múltiples Asignados").first()
        assert tarea_verif is not None, "La tarea no fue guardada"
        assert len(tarea_verif.asignados) == 2, f"Se esperaban 2 asignados, se encontraron: {len(tarea_verif.asignados)}"
        assert tarea_verif.asignado_a_id == abogado1.id, "El asignado principal no coincide"
        
        print("--- VERIFICACIÓN DE ASIGNADOS A TAREA ---")
        for a in tarea_verif.asignados:
            print(f"- Asignado: {a.nombre} (Rol: {a.rol})")
        print(f"Asignado Principal (Responsable): {tarea_verif.asignado_a.nombre}")
        
        # 4. Validar que la búsqueda por any() funciona correctamente
        # Buscar tareas donde el abogado 2 está asignado
        tareas_abogado2 = Tarea.query.filter(Tarea.asignados.any(Usuario.id == abogado2.id)).all()
        assert any(t.id == tarea_verif.id for t in tareas_abogado2), "El filtro any() no devolvió la tarea del abogado 2"
        print("Filtro filter(Tarea.asignados.any(...)) funciona correctamente!")
        
        # 5. Limpieza
        db.session.delete(tarea_verif)
        db.session.commit()
        print("Tarea de prueba eliminada y base de datos limpia.")
        print("Prueba de asignación de tareas completada exitosamente sin fallos!")

if __name__ == '__main__':
    test_multiple_task_assignees()
