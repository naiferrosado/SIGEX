import psycopg2
from psycopg2 import OperationalError

def test_passwords():
    passwords = ["postgres", "admin", "root", "123456", "password", "sigex", "naiferrosado123", "naiferrosado", "marlin"]
    for pwd in passwords:
        try:
            connection = psycopg2.connect(
                user="postgres",
                password=pwd,
                host="localhost",
                port="5432"
            )
            print(f"¡Éxito! Conexión a PostgreSQL establecida con la contraseña: '{pwd}'")
            connection.close()
            return pwd
        except OperationalError as e:
            if "authentication failed" in str(e).lower() or "password authentication failed" in str(e).lower():
                # Password incorrect
                continue
            else:
                print(f"Error diferente para '{pwd}': {e}")
                return None
    print("Ninguna de las contraseñas comunes funcionó.")
    return None

if __name__ == "__main__":
    test_passwords()
