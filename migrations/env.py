from logging.config import fileConfig

from sqlalchemy import pool
from alembic import context

from apps.core.base import Base
from apps.core.database import get_engine

# Import all model modules so their tables are registered on Base.metadata.
# Add a new import here whenever you create a new models.py file.
import apps.auth.models  # noqa: F401
import apps.ingestion.models  # noqa: F401
import apps.chat.models  # noqa: F401
import apps.query.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Only autogenerate for tables that are declared in our models.

    This prevents Alembic from emitting DROP TABLE for tables that exist in
    the database but haven't been modelled in Python yet.
    """
    if type_ == "table" and name not in target_metadata.tables:
        return False
    return True


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection (used for dry-run / review)."""
    # Offline mode needs a URL; provide a placeholder — actual schema dialect
    # is still correct because we write the SQL to stdout, not execute it.
    context.configure(
        url="postgresql+pg8000://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against the live Cloud SQL database."""
    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
