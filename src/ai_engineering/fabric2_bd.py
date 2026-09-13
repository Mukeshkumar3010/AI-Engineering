"""Shared Microsoft Entra authentication and Fabric SQL connection helpers."""

import os
import struct
import urllib.parse

import msal
import pyodbc
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_SERVER = os.getenv("AZURE_SERVER")
AZURE_DB = os.getenv("AZURE_DB")
SQL_SCOPE = ["https://database.windows.net/.default"]

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, AZURE_SERVER, AZURE_DB]):
    raise ValueError("Missing required Fabric database environment variables")


AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"


def get_access_token(scope=SQL_SCOPE):
    """Get an app-only Microsoft Entra access token."""
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=scope)
    if "access_token" not in result:
        raise RuntimeError(f"Failed to get token: {result.get('error_description')}")
    return result["access_token"]


def connect():
    """Open a Fabric SQL connection using the service principal token."""
    token_bytes = get_access_token().encode("utf-16-le")
    access_token = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    return pyodbc.connect(
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={AZURE_SERVER};"
        f"Database={AZURE_DB};"
        "Encrypt=yes;",
        attrs_before={1256: access_token},
    )


def get_engine():
    """Create a SQLAlchemy engine for Fabric SQL using the service principal token."""
    token_bytes = get_access_token().encode("utf-16-le")
    access_token = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    params = urllib.parse.quote_plus(
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={AZURE_SERVER};"
        f"Database={AZURE_DB};"
        "Encrypt=yes;"
    )
    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}",
        connect_args={"attrs_before": {1256: access_token}},
    )
