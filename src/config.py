"""
config.py - every setting lives here, so nothing is hard-coded in other files.
(Think of it as a header file full of #define constants.)
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

# ---- Database login --------------------------------------------------------
# Read from environment variables so the password is never saved in the code.
# If a variable is not set, the second value is used as the default.
DB_HOST = os.getenv("PF_DB_HOST", "localhost")
DB_PORT = int(os.getenv("PF_DB_PORT", "3306"))
DB_USER = os.getenv("PF_DB_USER", "root")
DB_PASSWORD = os.getenv("PF_DB_PASSWORD", "")
DB_NAME = os.getenv("PF_DB_NAME", "pharmaflow")

# NOTE: the business thresholds (7 days = at risk, 60 days = excess) are stored in the
# MySQL table kpi_thresholds (created in sql/02_kpis.sql), so SQL and Python share one value.


def get_engine(with_database=True):
    """Return a SQLAlchemy engine = a reusable connection to MySQL.
    with_database=False connects to the server only (needed to CREATE DATABASE)."""
    url = URL.create(
        "mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME if with_database else None,
    )
    return create_engine(url)
