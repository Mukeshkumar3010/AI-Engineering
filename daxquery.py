import os
import struct
import time
import base64
import re
import json
import subprocess
from pathlib import Path

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
WORKSPACE_ID = os.getenv("WORKSPACE_ID")
SEMANTIC_MODEL_ID = os.getenv("SEMANTIC_MODEL_ID", DATASET_ID)
SEMANTIC_MODEL_GIT_PATH = os.getenv("SEMANTIC_MODEL_GIT_PATH")

PBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
FABRIC_SCOPE = ["https://api.fabric.microsoft.com/.default"]

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, AZURE_SERVER, AZURE_DB, DATASET_ID,WORKSPACE_ID]):
    raise ValueError("Missing required Fabric database environment variables")


AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

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


def call_api(url, scope, payload=None):
    """Call a Fabric or Power BI API and wait for a Fabric async operation."""
    headers = {"Authorization": f"Bearer {get_access_token(scope)}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    if response.status_code != 202:
        raise RuntimeError(f"API request failed ({response.status_code}): {response.text}")

    operation_url = response.headers["Location"]
    while True:
        time.sleep(int(response.headers.get("Retry-After", "5")))
        response = requests.get(operation_url, headers=headers)
        response.raise_for_status()
        operation = response.json()
        if operation["status"] == "Succeeded":
            result_url = response.headers.get("Location")
            if not result_url:
                return operation
            result = requests.get(result_url, headers=headers)
            result.raise_for_status()
            return result.json()
        if operation["status"] in {"Failed", "Cancelled"}:
            raise RuntimeError(f"API operation {operation['status']}: {operation}")


def get_semantic_model_definition():
    """Retrieve the TMDL definition for the configured Fabric semantic model."""
    if not WORKSPACE_ID or not SEMANTIC_MODEL_ID:
        raise ValueError("Set WORKSPACE_ID and SEMANTIC_MODEL_ID in .env")

    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/"
        f"semanticModels/{SEMANTIC_MODEL_ID}/getDefinition"
    )
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {get_access_token(FABRIC_SCOPE)}"},
    )
    if response.status_code == 200:
        return response.json()
    if response.status_code != 202:
        raise RuntimeError(
            f"Fabric definition request failed ({response.status_code}): {response.text}"
        )

    operation_url = response.headers["Location"]
    while True:
        time.sleep(int(response.headers.get("Retry-After", "5")))
        response = requests.get(
            operation_url,
            headers={"Authorization": f"Bearer {get_access_token(FABRIC_SCOPE)}"},
        )
        response.raise_for_status()
        operation = response.json()
        if operation["status"] == "Succeeded":
            result_url = response.headers.get("Location")
            if not result_url:
                raise RuntimeError("Fabric operation completed without a result URL")
            result = requests.get(
                result_url,
                headers={"Authorization": f"Bearer {get_access_token(FABRIC_SCOPE)}"},
            )
            result.raise_for_status()
            return result.json()
        if operation["status"] in {"Failed", "Cancelled"}:
            raise RuntimeError(f"Fabric definition request {operation['status']}: {operation}")


# Fabric's getDefinition takes ~20s server-side to generate the TMDL export;
# that cost can't be reduced client-side, so cache the result on disk instead.
SCHEMA_CACHE_PATH = Path(".cache/semantic_model_definition.json")
SCHEMA_CACHE_TTL_SECONDS = 7 * 86400


def get_semantic_model_definition_cached(force_refresh=False):
    """Return the semantic-model definition, reusing a disk cache within the TTL."""
    if not force_refresh and SCHEMA_CACHE_PATH.exists():
        age = time.time() - SCHEMA_CACHE_PATH.stat().st_mtime
        if age < SCHEMA_CACHE_TTL_SECONDS:
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


SMART_SCHEMA_CACHE_PATH = Path(".cache/semantic_model_definition_smart.json")
SMART_SCHEMA_CACHE_TTL_SECONDS = 7 * 86400


def call_get_api(url, scope):
    """Call a Fabric or Power BI GET endpoint."""
    response = requests.get(url, headers={"Authorization": f"Bearer {get_access_token(scope)}"})
    if not response.ok:
        raise RuntimeError(f"API request failed ({response.status_code}): {response.text}")
    return response.json()


def get_fabric_semantic_model_metadata():
    """Return lightweight Fabric semantic-model metadata."""
    return call_get_api(
        f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/"
        f"semanticModels/{SEMANTIC_MODEL_ID}",
        FABRIC_SCOPE,
    )


def get_powerbi_dataset_metadata():
    """Return lightweight Power BI dataset metadata."""
    return call_get_api(
        f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{DATASET_ID}",
        PBI_SCOPE,
    )


def get_metadata_version(metadata):
    """Return a usable metadata version if the API exposes one."""
    for key in ("modifiedDateTime", "lastModifiedDateTime", "lastUpdatedDateTime", "modifiedDate", "updatedDate"):
        if metadata.get(key):
            return f"{key}:{metadata[key]}"
    return None


def get_semantic_model_definition_cached_with_metadata(force_refresh=False):
    """Use metadata version when available; otherwise use a long-lived cache TTL."""
    fabric_metadata = get_fabric_semantic_model_metadata()
    powerbi_metadata = get_powerbi_dataset_metadata()
    version = get_metadata_version(fabric_metadata) or get_metadata_version(powerbi_metadata)

    if not force_refresh and SMART_SCHEMA_CACHE_PATH.exists():
        cache = json.loads(SMART_SCHEMA_CACHE_PATH.read_text())
        age = time.time() - SMART_SCHEMA_CACHE_PATH.stat().st_mtime
        if version and cache.get("metadata_version") == version:
            return cache["definition"]
        if not version and age < SMART_SCHEMA_CACHE_TTL_SECONDS:
            return cache["definition"]

    definition = call_pbi_fabric_api(
        url=(
            f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/"
            f"semanticModels/{SEMANTIC_MODEL_ID}/getDefinition"
        ),
        scope=FABRIC_SCOPE,
    )
    SMART_SCHEMA_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SMART_SCHEMA_CACHE_PATH.write_text(
        json.dumps(
            {
                "metadata_version": version,
                "fabric_metadata": fabric_metadata,
                "powerbi_metadata": powerbi_metadata,
                "definition": definition,
            }
        )
    )
    return definition


GIT_SCHEMA_CACHE_PATH = Path(".cache/semantic_model_definition_git.json")


def get_semantic_model_git_version(path):
    """Return the latest commit hash that changed a Fabric Git model path."""
    try:
        return subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", path],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return None


def get_semantic_model_definition_cached_with_git(force_refresh=False):
    """Use Fabric Git versioning when available; otherwise use metadata/TTL cache."""
    git_version = None
    if SEMANTIC_MODEL_GIT_PATH:
        git_version = get_semantic_model_git_version(SEMANTIC_MODEL_GIT_PATH)

    if not git_version:
        return get_semantic_model_definition_cached_with_metadata(force_refresh)

    if not force_refresh and GIT_SCHEMA_CACHE_PATH.exists():
        cache = json.loads(GIT_SCHEMA_CACHE_PATH.read_text())
        if cache.get("git_version") == git_version:
            return cache["definition"]

    definition = call_pbi_fabric_api(
        url=(
            f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/"
            f"semanticModels/{SEMANTIC_MODEL_ID}/getDefinition"
        ),
        scope=FABRIC_SCOPE,
    )
    GIT_SCHEMA_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GIT_SCHEMA_CACHE_PATH.write_text(
        json.dumps(
            {
                "git_path": SEMANTIC_MODEL_GIT_PATH,
                "git_version": git_version,
                "definition": definition,
            }
        )
    )
    return definition


def decode_tmdl_parts(definition):
    """Decode Fabric's base64 TMDL files."""
    return {
        part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
        for part in definition["definition"]["parts"]
    }


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


def definition_to_schema_dataframes(definition):
    """Convert a Fabric semantic-model definition to schema DataFrames."""
    parts = decode_tmdl_parts(definition)
    columns, measures = extract_table_metadata(parts)
    relationships = extract_relationships(parts)
    return pd.DataFrame(columns), pd.DataFrame(measures), pd.DataFrame(relationships)


"""
Reference implementation using decode_tmdl_parts, extract_table_metadata,
and extract_relationships is retained above.
"""


def definition_to_schema_dataframes_pandas(definition):
    """Convert TMDL metadata to DataFrames using pandas extraction helpers."""
    parts = pd.DataFrame(definition["definition"]["parts"])
    parts["content"] = parts["payload"].map(
        lambda payload: base64.b64decode(payload).decode("utf-8")
    )
    tables = parts[parts["path"].str.startswith("definition/tables/")].copy()
    tables["Table"] = tables["content"].str.extract(
        r"^\s*table (.+)$", flags=re.MULTILINE, expand=False
    ).str.strip("'")
    columns_df = pd.DataFrame(
        [
            {"Table": row.Table, "Name": quoted_name or plain_name}
            for row in tables.itertuples()
            for quoted_name, plain_name in re.findall(
                r"^[ \t]+column (?:'([^']+)'|([^\s=]+))", row.content, re.MULTILINE
            )
        ]
    )
    measures_df = pd.DataFrame(
        [
            {"Table": row.Table, "Name": name.strip("'")}
            for row in tables.itertuples()
            for name in re.findall(r"^\s+measure (.+?) =", row.content, re.MULTILINE)
        ]
    )
    relationship_content = parts.loc[
        parts["path"].eq("definition/relationships.tmdl"), "content"
    ].iloc[0]
    relationships_df = pd.DataFrame(
        re.findall(r"fromColumn: (.+)\n\s+toColumn: (.+)", relationship_content),
        columns=["from", "to"],
    )
    relationships_df[["FromTable", "FromColumn"]] = relationships_df.pop("from").str.rsplit(".", n=1, expand=True)
    relationships_df[["ToTable", "ToColumn"]] = relationships_df.pop("to").str.rsplit(".", n=1, expand=True)
    return columns_df, measures_df, relationships_df

def query_xmla_tables(dax_query):
    """Query XMLA endpoint for tables using a DAX query."""
    conn_str = f"""
    Provider=MSOLAP;
    Data Source=powerbi://api.powerbi.com/v1.0/myorg/Contoso;
    Initial Catalog=Sales;
    """
    from pyadomd import Pyadomd
    
    with Pyadomd(conn_str) as conn:
        with conn.cursor().execute(dax_query) as cur:
            tables = pd.DataFrame(cur.fetchall())
    return tables

'''
#Delegated permissions require a user login. Temporarily use device-code authentication
def get_access_token():
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
    )

    scopes = [
        "https://analysis.windows.net/powerbi/api/Dataset.Read.All"
    ]

    flow = app.initiate_device_flow(scopes=scopes)
    print(flow["message"])

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(result.get("error_description"))

    return result["access_token"]
'''

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

#from src.ai_engineering.fabric_db import pbi_connect
#api_base_url: str = "https://api.powerbi.com/v1.0/myorg"


'''
def execute_query(
        self,
        dataset_id: str,
        dax_query: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a DAX query against a Power BI dataset.
        
        This method sends the DAX query to the Power BI executeQueries endpoint
        and returns the raw JSON response.
        
        Args:
            dataset_id: The GUID of the Power BI dataset
            dax_query: The DAX query string to execute
            timeout: Timeout for query execution in seconds (uses default if None)
            
        Returns:
            Raw JSON response from Power BI API
            
        Raises:
            QueryTimeoutError: If the query execution times out
            QuerySyntaxError: If the DAX query has syntax errors
            DAXQueryError: For other query execution errors
        """
        timeout = timeout or self.default_timeout
        
        # Log query details (truncate query for logging)
        query_preview = dax_query[:200] + "..." if len(dax_query) > 200 else dax_query
        
        start_time = time.time()
        
        try:
            # Authenticate and get authorization header
            # auth_header = self.authenticator.get_authorization_header()
            
            # Build API endpoint URL
            url = f"{self.api_base_url}/datasets/{dataset_id}/executeQueries"
            
            # Prepare request payload
            payload = {
                "queries": [
                    {
                        "query": dax_query
                    }
                ],
                "serializerSettings": {
                    "includeNulls": True
                }
            }
            
            # Make POST request to execute query
            response = requests.post(
                url,
                json=payload,
                headers={
                    **auth_header,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            
            # Calculate execution duration
            duration = time.time() - start_time
            
            # Handle different response codes
            if response.status_code == 200:
                result = response.json()
                
                # Log successful execution
                logger.info(f"Query executed successfully in {duration:.2f}s")
                
                return result
def parse_response(self, response: Dict[str, Any]) -> pd.DataFrame:
        """
        Convert Power BI JSON response to pandas DataFrame.
        
        This method parses the Power BI API response structure and extracts
        the query results into a DataFrame. Handles empty result sets gracefully.
        
        Args:
            response: Raw JSON response from Power BI executeQueries API
            
        Returns:
            pandas DataFrame with query results
            
        Raises:
            DAXQueryError: If response cannot be parsed
        """
        
        try:
            # Extract results from response
            results = response.get("results", [])
            
            if not results:
                return pd.DataFrame()
            
            # Get first result (we only send one query)
            result = results[0]
            
            # Check for errors in result
            if "error" in result:
                error_msg = f"Query returned error: {result['error']}"
                raise DAXQueryError(error_msg)
            
            # Extract tables from result
            tables = result.get("tables", [])
            
            if not tables:
                return pd.DataFrame()
            
            # Get first table (DAX queries typically return one table)
            table = tables[0]
            
            # Extract rows
            rows = table.get("rows", [])
            
            if not rows:
                return pd.DataFrame()
            
            # Create DataFrame from rows
            df = pd.DataFrame(rows)
            
            return df
        
        except KeyError as e:
            error_msg = f"Unexpected response structure, missing key: {str(e)}"
            raise DAXQueryError(error_msg)
        
        except Exception as e:
            error_msg = f"Failed to parse response to DataFrame: {str(e)}"
            raise DAXQueryError(error_msg)
    
    def execute_query_to_dataframe(
        self,
        dataset_id: str,
        dax_query: str,
        timeout: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Execute DAX query and return results as DataFrame.
        
        This is a convenience method that combines execute_query and parse_response.
        
        Args:
            dataset_id: The GUID of the Power BI dataset
            dax_query: The DAX query string to execute
            timeout: Timeout for query execution in seconds (uses default if None)
            
        Returns:
            pandas DataFrame with query results
            
        Raises:
            QueryTimeoutError: If the query execution times out
            QuerySyntaxError: If the DAX query has syntax errors
            DAXQueryError: For other query execution errors
        """
        response = self.execute_query(dataset_id, dax_query, timeout)
        return self.parse_response(response)
'''
test_dax_query = """
EVALUATE
TOPN(
    10,
    'Sales'
)
"""
#print(test_dax_query)

# c_query = "EVALUATE INFO.COLUMNS()"
# columns_df = pbi_connect(c_query)
# measures_df = pbi_connect("EVALUATE INFO.MEASURES()")
# relationships_df = pbi_connect("EVALUATE INFO.RELATIONSHIPS()")

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

    # Fabric returns 202 + Location for long-running requests; poll until done.
    # operation_url = response.headers["Location"]
    # while response.status_code == 202:
    #     time.sleep(int(response.headers.get("Retry-After", "5")))
    #     response = requests.get(operation_url, headers=headers)
    # response.raise_for_status()
    # result_url = response.headers.get("Location")
    # if result_url:
    #     response = requests.get(result_url, headers=headers)
    #     response.raise_for_status()
    # return response.json()

    # Follow Location as long as one is given: first for polling (202), then for the result (200).
    while "Location" in response.headers:
        if response.status_code == 202:
            time.sleep(int(response.headers.get("Retry-After", "5")))
        response = requests.get(response.headers["Location"], headers=headers)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    # data = pbi_connect(dax_query)
    # rows = data["results"][0]["tables"][0]["rows"]
    # df = pd.DataFrame(rows)
    # print(df)

    # schema = build_pbi_schema_text(
    # columns_df,
    # measures_df,
    # relationships_df
    # )

    # print(json.dumps(schema, indent=2))


    
    # tables = query_xmla_tables("SELECT * FROM $SYSTEM.TMSCHEMA_TABLES")
    # print(tables.head())
    payload = {
        "queries": [{"query": test_dax_query}]
    }

    data = call_pbi_fabric_api(
        url=f"https://api.powerbi.com/v1.0/myorg/datasets/{DATASET_ID}/executeQueries",
        scope=PBI_SCOPE,
        payload=payload,
    )
    rows = data["results"][0]["tables"][0]["rows"]
    df = pd.DataFrame(rows)
    print(df)

    # definition_request = call_pbi_fabric_api(
    # url=(
    #     f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/"
    #     f"semanticModels/{SEMANTIC_MODEL_ID}/getDefinition"
    # ),
    # scope=FABRIC_SCOPE,
    # )

    # Use get_semantic_model_definition_cached() instead to skip Fabric's
    # ~20s generation time on repeated runs (cached to .cache/ for 1 hour).
    definition = get_semantic_model_definition_cached()
    columns_df, measures_df, relationships_df = definition_to_schema_dataframes(definition)
    print(build_pbi_schema_text(columns_df, measures_df, relationships_df))