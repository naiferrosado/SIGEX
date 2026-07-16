import os
import threading
import time
from app import create_app

app = create_app()

def start_alert_scheduler(app_instance):
    def run_scheduler():
        # Esperar 5 segundos a que la aplicación web inicialice
        time.sleep(5)
        print("[PLANIFICADOR] Hilo de alertas preventivas en segundo plano iniciado.")
        while True:
            try:
                with app_instance.app_context():
                    from app.routes import procesar_alertas_preventivas
                    procesar_alertas_preventivas()
            except Exception as e:
                print(f"[PLANIFICADOR] Error al procesar alertas preventivas en segundo plano: {e}")
            # Ejecutar cada 12 horas (43200 segundos)
            time.sleep(43200)

    # Arranca el hilo de segundo plano si es el proceso principal (evita doble ejecución con Werkzeug reloader)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app_instance.debug:
        thread = threading.Thread(target=run_scheduler, daemon=True)
        thread.start()

start_alert_scheduler(app)

if __name__ == '__main__':
# Arranca el servidor local en modo debug para ver los cambios en tiempo real
    app.run(debug=True, use_reloader=True)