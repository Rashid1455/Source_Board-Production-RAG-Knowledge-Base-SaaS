from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from .config import settings


@contextmanager
def database():
    with psycopg.connect(settings().database_url, row_factory=dict_row, connect_timeout=5) as connection:
        yield connection
