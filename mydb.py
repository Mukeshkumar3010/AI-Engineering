from azure.identity import InteractiveBrowserCredential, DefaultAzureCredential
import pyodbc
import pandas as pd
from dotenv import load_dotenv
import os
from connection import get_access_token
load_dotenv()




AZURE_SERVER = os.getenv("AZURE_SERVER")
AZURE_DB = os.getenv("AZURE_DB")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")


#credential = InteractiveBrowserCredential()
#credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
#token = credential.get_token(
#    "https://database.windows.net/.default"
#)

SQL_SCOPE = ["https://database.windows.net/.default"]
token = get_access_token()

access_token = token.encode("utf-16-le")

conn = pyodbc.connect(
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=" + AZURE_SERVER + ";"
    "Database=" + AZURE_DB + ";"
    "Encrypt=yes;",
    attrs_before={1256: access_token}
)

print("Connected to Fabric SQL endpoint.", flush=True)

query = "SELECT TOP 5 * FROM [SalesLT].[SalesOrderDetail]"

df = pd.read_sql(query, conn)

#print(df.shape)
print(df)