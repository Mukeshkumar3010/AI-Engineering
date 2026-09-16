"""Shared Microsoft Entra authentication and Fabric SQL connection helpers."""

from pathlib import Path
import time
import struct
import json
import base64
import re

import msal
import pyodbc
import requests
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_SERVER = os.getenv("AZURE_SERVER")
AZURE_DB = os.getenv("AZURE_DB")
DATASET_ID = os.getenv("DATASET_ID")
WORKSPACE_ID = os.getenv("WORKSPACE_ID")
SEMANTIC_MODEL_ID = os.getenv("SEMANTIC_MODEL_ID", DATASET_ID)

SQL_SCOPE = ["https://database.windows.net/.default"]
PBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
FABRIC_SCOPE = ["https://api.fabric.microsoft.com/.default"]
SCHEMA_CACHE_PATH = Path(".cache/semantic_model_definition.json")
#SCHEMA_CACHE_TTL_SECONDS = 7 * 86400

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
    data = response.json()
    rows = data["results"][0]["tables"][0]["rows"]
    df = pd.DataFrame(rows)
    return df


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

# Helper function to call Power BI or Fabric APIs and handle async operations
def call_pbi_fabric_api(url, scope, payload=None):
    """Call a Fabric or Power BI API and wait for a Fabric async operation."""
    headers = {"Authorization": f"Bearer {get_access_token(scope)}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    if response.status_code != 202:
        raise RuntimeError(f"API request failed ({response.status_code}): {response.text}")
    # Follow Location as long as one is given: first for polling (202), then for the result (200).
    while "Location" in response.headers:
        if response.status_code == 202:
            time.sleep(int(response.headers.get("Retry-After", "5")))
        response = requests.get(response.headers["Location"], headers=headers)
    response.raise_for_status()
    return response.json()

# TMDL parsing and metadata extraction functions
def decode_tmdl_parts(definition):
    """Decode Fabric's base64 TMDL files."""
    return {
        part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
        for part in definition["definition"]["parts"]
    }


# Helper function to extract table metadata from TMDL parts
def extract_table_metadata(parts):
    """Extract columns and measures from TMDL table files."""
    columns = []
    measures = []
    for path, content in parts.items():
        if not path.startswith("definition/tables/"):
            continue
        table_match = re.search(r"^table (.+)$", content, re.MULTILINE)
        if not table_match:
            continue
        table_name = table_match.group(1).strip("'")
        columns.extend(
            {"Table": table_name, "Name": quoted_name or plain_name}
            for quoted_name, plain_name in re.findall(
                r"^[ \t]+column (?:'([^']+)'|([^\s=]+))", content, re.MULTILINE
            )
        )
        measures.extend(
            {"Table": table_name, "Name": name.strip("'")}
            for name in re.findall(r"^\s+measure (.+?) =", content, re.MULTILINE)
        )
    return columns, measures

# Helper function to extract relationships from TMDL parts
def extract_relationships(parts):
    """Extract relationships from the TMDL relationship file."""
    relationships = []
    content = parts.get("definition/relationships.tmdl", "")
    for from_column, to_column in re.findall(r"fromColumn: (.+)\n\s+toColumn: (.+)", content):
        from_table, from_name = from_column.rsplit(".", 1)
        to_table, to_name = to_column.rsplit(".", 1)
        relationships.append(
            {
                "FromTable": from_table,
                "FromColumn": from_name,
                "ToTable": to_table,
                "ToColumn": to_name,
            }
        )
    return relationships

# Helper function to build a textual representation of the Power BI schema
def build_pbi_schema_text(columns_df, measures_df, relationships_df):

    measures_map = (
        measures_df.groupby("Table")["Name"]
        .apply(list)
        .to_dict()
    )

    tables_text = "\n\n".join(
        (
            f"Table: {table}\n"
            f"Columns: {', '.join(g['Name'])}\n"
            f"Measures: {', '.join(measures_map.get(table, []))}"
        )
        for table, g in columns_df.groupby("Table")
    )

    relationships_text = "\n".join(
        f"{r['FromTable']}.{r['FromColumn']} -> "
        f"{r['ToTable']}.{r['ToColumn']}"
        for _, r in relationships_df.iterrows()
    )

    return (
        f"SCHEMA\n\n"
        f"{tables_text}\n\n"
        f"RELATIONSHIPS\n"
        f"{relationships_text}"
    )

# Convert a Fabric semantic-model definition to schema DataFrames and return them.
def definition_to_schema_dataframes(definition):
    """Convert a Fabric semantic-model definition to schema DataFrames."""
    parts = decode_tmdl_parts(definition)
    columns, measures = extract_table_metadata(parts)
    relationships = extract_relationships(parts)
    return pd.DataFrame(columns), pd.DataFrame(measures), pd.DataFrame(relationships)


# Get the cached semantic-model definition, refreshing it if necessary.
def get_semantic_model_definition_cached(force_refresh=False):
    """Return the semantic-model definition, reusing a disk cache within the TTL."""
    if not force_refresh and SCHEMA_CACHE_PATH.exists():
        # age = time.time() - SCHEMA_CACHE_PATH.stat().st_mtime
        # if age < SCHEMA_CACHE_TTL_SECONDS:
        return json.loads(SCHEMA_CACHE_PATH.read_text())

    definition = call_pbi_fabric_api(
        url=(
            f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/"
            f"semanticModels/{SEMANTIC_MODEL_ID}/getDefinition"
        ),
        scope=FABRIC_SCOPE,
    )
    SCHEMA_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_CACHE_PATH.write_text(json.dumps(definition))
    return definition

# Execute a DAX query against the Power BI dataset.
def pbi_query(dax_query):
    data = call_pbi_fabric_api(
        url=(
            f"https://api.powerbi.com/v1.0/myorg/datasets/{DATASET_ID}/executeQueries"
        ),
        scope=PBI_SCOPE,
        payload={"queries": [{"query": dax_query}]},
    )
    rows = data["results"][0]["tables"][0]["rows"]
    df = pd.DataFrame(rows)
    return df
