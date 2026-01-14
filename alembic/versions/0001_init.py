"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-01-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usuario",
        sa.Column("id_usuario", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, index=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("rol", sa.String(), nullable=False, server_default="cliente"),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    );

    op.create_table(
        "inmueble",
        sa.Column("id_inmueble", sa.Integer(), primary_key=True),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("direccion", sa.String(), nullable=False),
        sa.Column("municipio", sa.String(), nullable=False),
        sa.Column("comunidad_autonoma", sa.String(), nullable=False),
        sa.Column("codigo_postal", sa.String(), nullable=True),
        sa.Column("superficie_m2", sa.Integer(), nullable=True),
        sa.Column("tipo_arrendamiento", sa.String(), nullable=False, server_default="vivienda_habitual"),
        sa.Column("tipo_arrendador", sa.String(), nullable=False, server_default="persona_fisica"),
        sa.Column("renta_propuesta", sa.Float(), nullable=False),
        sa.Column("renta_anterior", sa.Float(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
    )
    op.create_index("ix_inmueble_id_usuario", "inmueble", ["id_usuario"])
    op.create_index("ix_inmueble_activo", "inmueble", ["activo"])
    op.create_foreign_key("fk_inmueble_usuario", "inmueble", "usuario", ["id_usuario"], ["id_usuario"], ondelete="CASCADE")

    op.create_table(
        "rulerun",
        sa.Column("id_run", sa.Integer(), primary_key=True),
        sa.Column("id_inmueble", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fecha_analisis", sa.Date(), nullable=False),
        sa.Column("resultados_json", sa.Text(), nullable=False),
        sa.Column("alertas_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_rulerun_id_inmueble", "rulerun", ["id_inmueble"])
    op.create_foreign_key("fk_rulerun_inmueble", "rulerun", "inmueble", ["id_inmueble"], ["id_inmueble"], ondelete="CASCADE")

    op.create_table(
        "zonatensionada",
        sa.Column("id_zona", sa.Integer(), primary_key=True),
        sa.Column("comunidad_autonoma", sa.String(), nullable=False),
        sa.Column("municipio", sa.String(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("fuente_oficial", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_zona_ca", "zonatensionada", ["comunidad_autonoma"])
    op.create_index("ix_zona_mun", "zonatensionada", ["municipio"])

    op.create_table(
        "auditlog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("id_usuario", sa.Integer(), nullable=True),
        sa.Column("accion", sa.String(), nullable=False),
        sa.Column("entidad", sa.String(), nullable=True),
        sa.Column("entidad_id", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_audit_user", "auditlog", ["id_usuario"])
    op.create_index("ix_audit_accion", "auditlog", ["accion"])


def downgrade():
    op.drop_table("auditlog")
    op.drop_table("zonatensionada")
    op.drop_table("rulerun")
    op.drop_table("inmueble")
    op.drop_table("usuario")
