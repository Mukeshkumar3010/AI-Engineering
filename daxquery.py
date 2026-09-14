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

PBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]

if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID, AZURE_SERVER, AZURE_DB, DATASET_ID]):
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
    return response.json()

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
dax_query = """
EVALUATE
TOPN(
    10,
    'Sales'
)
"""
if __name__ == "__main__":
    data = pbi_connect(dax_query)
    rows = data["results"][0]["tables"][0]["rows"]
    df = pd.DataFrame(rows)
    print(df)
