from app import create_app, db
from app.models import Usuario
import unittest

class FlaskAppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_catalog_endpoints(self):
        # Log in testadmin@example.com using session transaction
        with self.app.app_context():
            admin = Usuario.query.filter_by(email="testadmin@example.com").first()
            if not admin:
                admin = Usuario.query.first()
            
            with self.client.session_transaction() as sess:
                sess['_user_id'] = str(admin.id)
                sess['_fresh'] = True

        response = self.client.get('/api/materias?tipo=Administrativo')
        print(f"GET /api/materias?tipo=Administrativo - Status: {response.status_code}")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        
        # Verify that requires_procedure is present and correct
        jce = next((m for m in data if m['nombre'] == 'JCE'), None)
        ayuntamientos = next((m for m in data if m['nombre'] == 'Ayuntamientos'), None)
        trabajo = next((m for m in data if m['nombre'] == 'Ministerio de Trabajo'), None)
        migratorio = next((m for m in data if m['nombre'] == 'Migratorio'), None)
        
        self.assertIsNotNone(jce)
        self.assertFalse(jce['requiere_procedimiento'])
        self.assertIsNotNone(ayuntamientos)
        self.assertFalse(ayuntamientos['requiere_procedimiento'])
        self.assertIsNotNone(trabajo)
        self.assertFalse(trabajo['requiere_procedimiento'])
        
        if migratorio:
            self.assertTrue(migratorio['requiere_procedimiento'])

        response = self.client.get('/api/procedimientos?materia_id=1')
        print(f"GET /api/procedimientos?materia_id=1 - Status: {response.status_code}")
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/api/procedimientos/1/campos')
        print(f"GET /api/procedimientos/1/campos - Status: {response.status_code}")
        self.assertEqual(response.status_code, 200)

        # Test pages with login
        routes = [
            '/expedientes',
            '/expedientes/nuevo',
            '/expedientes/5/editar',
            '/expedientes/historial'
        ]
        for route in routes:
            response = self.client.get(route)
            print(f"GET {route} - Status: {response.status_code}")
            self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
