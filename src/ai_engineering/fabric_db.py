"""Shared Microsoft Entra authentication and Fabric SQL connection helpers."""

import os
import struct

import msal
import pyodbc
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_SERVER = os.getenv("AZURE_SERVER")
AZURE_DB = os.getenv("AZURE_DB")
DATASET_ID = os.getenv("DATASET_ID")

SQL_SCOPE = ["https://database.windows.net/.default"]
PBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, AZURE_SERVER, AZURE_DB, DATASET_ID]):
    raise ValueError("Missing required Fabric database environment variables")


AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Microsoft Entra authentication helper
def get_access_token(scope):
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


# Power BI connection helper using service principal token
def pbi_connect(dax_query):
    """Open a Power BI connection using the service principal token."""
    access_token = get_access_token(PBI_SCOPE)
    # DAX query
    payload = {
        "queries": [
            {
                "query": dax_query
            }
        ]
    }

    url = f"https://api.powerbi.com/v1.0/myorg/datasets/{DATASET_ID}/executeQueries"
    print(url)
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if not response.ok:
        raise RuntimeError(
            f"Power BI API request failed ({response.status_code}): {response.text}"
        )
    return response.json()


# Fabric SQL connection helper using service principal token
def sql_connect():
    """Open a Fabric SQL connection using the service principal token."""
    token_bytes = get_access_token(SQL_SCOPE).encode("utf-16-le")
    access_token = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    return pyodbc.connect(
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={AZURE_SERVER};"
        f"Database={AZURE_DB};"
        "Encrypt=yes;",
        attrs_before={1256: access_token},
    )
