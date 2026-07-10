# SIGEX - Sistema de Gestión de Expedientes y Oficina de Abogados

**SIGEX** es una plataforma web moderna y segura diseñada para simplificar y centralizar las operaciones de firmas y oficinas de abogados. Facilita la gestión documental, el control de plazos procesales, el seguimiento de expedientes judiciales/administrativos, y proporciona paneles de control personalizados para cada rol de la organización.

---

## 🚀 Características Principales

*   **Gestión de Expedientes:** Control integral de expedientes judiciales (litigios) y administrativos (trámites migratorios, corporativos, etc.).
*   **Gestor de Documentos Digitales:** Carga de versiones físicas de archivos con control de versiones, visibilidad restringida (socios, abogados, clientes) y descarga segura.
*   **Checklist de Tareas y Plazos:** Gestor de tareas con prioridades (Alta, Media, Baja) y estados (Pendiente, En Progreso, Completada), con alertas automáticas de plazos vencidos o próximos a vencer.
*   **Modos de Acceso y Roles:** Paneles dedicados con permisos específicos según el rol de seguridad:
    *   *Socio / Administrador:* Control de finanzas, auditorías forenses, gestión de accesos y administración de usuarios.
    *   *Asociado:* Control de casos asignados, reporte de horas facturables y alertas de plazos procesales.
    *   *Paralegal:* Digitalización y carga de documentos, tareas de soporte y checklist administrativo.
    *   *Cliente:* Visualización de sus expedientes y descarga de sus documentos maestros aprobados.
*   **Bitácora de Auditoría Forense:** Registro inmutable de todas las acciones del sistema (creación, edición, accesos de visualización o descarga de documentos, etc.) para auditorías de cumplimiento y seguridad.

---

## 🛠️ Requisitos Previos

Antes de comenzar la instalación, asegúrate de tener instalados los siguientes componentes en tu sistema operativo:

1.  **Python 3.10 o superior:** Descárgalo de [python.org](https://www.python.org/downloads/) (marca la opción *"Add Python to PATH"* durante la instalación en Windows).
2.  **PostgreSQL (Base de Datos):** Descárgalo e instálalo desde [postgresql.org](https://www.postgresql.org/download/). Configura el puerto por defecto `5432` y recuerda la contraseña del usuario `postgres`.
3.  **Visual Studio Code (Recomendado):** Instala la extensión oficial **Python** de Microsoft para una mejor experiencia de desarrollo y depuración.

---

## ⚙️ Guía de Instalación y Configuración

Sigue estos pasos detallados desde la terminal para levantar el proyecto en tu entorno local:

### 1. Clonar el repositorio
Abre una terminal y clona el proyecto en tu máquina local:
```bash
git clone <URL_DEL_REPOSITORIO>
cd SIGEX
```

### 2. Crear y activar el Entorno Virtual (venv)
Es necesario aislar las dependencias del proyecto en un entorno virtual propio:

*   **En Windows (PowerShell / CMD):**
    ```powershell
    python -m venv venv
    .\venv\Scripts\activate
    ```
*   **En macOS / Linux:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

*(Sabrás que está activo porque aparecerá `(venv)` al inicio de la línea de comandos en tu terminal).*

### 3. Instalar las dependencias
Con el entorno virtual activo, instala todas las librerías necesarias del archivo `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Configurar el archivo de entorno (`.env`)
El sistema lee las credenciales del entorno desde un archivo `.env`. Copia la plantilla de ejemplo ` .env.example` para crear tu configuración local:

*   **En Windows (PowerShell):**
    ```powershell
    Copy-Item .env.example .env
    ```
*   **En macOS / Linux / Git Bash:**
    ```bash
    cp .env.example .env
    ```

Abre el archivo recién creado `.env` en tu editor de código y completa las variables:
*   `SECRET_KEY`: Genera una clave segura (ver el paso 5).
*   `DB_USER` y `DB_PASSWORD`: Tus credenciales de PostgreSQL locales.
*   `DB_NAME`: El nombre de la base de datos que creaste en PostgreSQL (ej. `sigex_db`).
*   `MAIL_USERNAME` y `MAIL_PASSWORD`: Tus datos de correo electrónico y Contraseña de Aplicación de Google para habilitar el envío real de correos de recuperación de contraseña.

### 5. Generar una clave secreta segura (`SECRET_KEY`)
Genera una clave criptográfica para asegurar las sesiones HTTP de la aplicación ejecutando este comando en la terminal:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Copia el string resultante de la consola y pégalo en la propiedad `SECRET_KEY` dentro de tu archivo `.env`.

### 6. Crear la Base de Datos en PostgreSQL
Abre **pgAdmin** o la consola de PostgreSQL (psql) y ejecuta la consulta para crear la base de datos del proyecto:
```sql
CREATE DATABASE sigex_db;
```

*(Asegúrate de que el nombre coincida con la propiedad `DB_NAME` de tu `.env`).*

### 7. Inicializar y migrar la Base de Datos
El proyecto utiliza Flask-Migrate para la creación de tablas. Ejecuta las migraciones para estructurar las tablas de la base de datos automáticamente:
```bash
flask db upgrade
```
*(Si es la primera vez o hay cambios estructurales, ejecuta `flask db migrate -m "comentario"` antes del upgrade).*

### 8. Crear Administrador e Insertar Datos de Prueba (Opcional)
Para facilitar las pruebas e inicio de sesión inicial, existen scripts listos para usar en la carpeta `scripts/`. Debes ejecutarlos desde la raíz del proyecto con tu entorno virtual activo:

1. **Crear usuario administrador inicial:**
   Crea un usuario administrador por defecto con las siguientes credenciales:
   - **Correo:** `naiferrosado@rosadomendez.com`
   - **Contraseña:** `naiferrosado123`
   ```bash
   python scripts/crear_admin.py
   ```

2. **Insertar datos ficticios:**
   *Importante: Requiere haber ejecutado primero el script de administrador para asignar correctamente los expedientes.*
   Inserta clientes, expedientes judiciales y administrativos de prueba para visualizar el funcionamiento de los paneles:
   ```bash
   python scripts/insertar_datos_ficticios.py
   ```

---

## 🏃 Cómo Ejecutar el Sistema

Una vez configurado todo el entorno, inicia la aplicación ejecutando:
```bash
python run.py
```

El servidor local se iniciará en modo desarrollo. Abre tu navegador web e ingresa a:
👉 [**http://127.0.0.1:5000**](http://127.0.0.1:5000)

*Para detener la ejecución del servidor, presiona `Ctrl + C` en la consola.*
