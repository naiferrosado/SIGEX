"""separar nombre en nombres y apellidos en clientes

Revision ID: eb9a5f0ca9e3
Revises: eaf00d09fc4c
Create Date: 2026-06-30 21:55:48.986888

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eb9a5f0ca9e3'
down_revision = 'eaf00d09fc4c'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Agregar SOLO las columnas que realmente faltan, como nullable
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nombres',   sa.String(150), nullable=True))
        batch_op.add_column(sa.Column('apellidos', sa.String(150), nullable=True))

    # 2. Migrar datos: copiar 'nombre' a 'nombres', apellidos vacío
    op.execute("""
        UPDATE clientes
        SET nombres   = nombre,
            apellidos = ''
        WHERE nombres IS NULL
    """)

    # 3. Aplicar NOT NULL ahora que todas las filas tienen valor
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.alter_column('nombres',   nullable=False)
        batch_op.alter_column('apellidos', nullable=False)

    # 4. Eliminar la columna vieja
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.drop_column('nombre')


def downgrade():
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nombre', sa.String(300), nullable=True))

    op.execute("""
        UPDATE clientes
        SET nombre = TRIM(nombres || ' ' || apellidos)
    """)

    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.alter_column('nombre', nullable=False)
        batch_op.drop_column('nombres')
        batch_op.drop_column('apellidos')

    # ### end Alembic commands ###
