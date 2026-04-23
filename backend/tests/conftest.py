import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg


@pytest.fixture(scope="session")
def migrated_engine(pg_container: PostgresContainer) -> Engine:
    url = pg_container.get_connection_url()
    os.environ["POSTGRES_USER"] = pg_container.username
    os.environ["POSTGRES_PASSWORD"] = pg_container.password
    os.environ["POSTGRES_DB"] = pg_container.dbname
    os.environ["POSTGRES_HOST"] = pg_container.get_container_host_ip()
    os.environ["POSTGRES_PORT"] = str(pg_container.get_exposed_port(5432))
    os.environ["REDIS_URL"] = "redis://unused:6379/0"

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return create_engine(url)
