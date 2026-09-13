from azure.identity import EnvironmentCredential
from dotenv import load_dotenv
import os
import pandas as pd
import struct
import pyodbc

load_dotenv()

AZURE_SERVER = os.getenv("AZURE_SERVER")
AZURE_DB = os.getenv("AZURE_DB")

credential = EnvironmentCredential()


def get_access_token():
    token = credential.get_token(
        "https://database.windows.net/.default"
    )
    return token.token

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
def execute_query(query):
    with connect() as conn:
        df = pd.read_sql(query, conn)

    return df


#if __name__ == "__main__":
#    main()
result = execute_query("SELECT TOP 5 [SalesOrderID],"
      "[SalesOrderDetailID],"
      "[OrderQty],"
      "[ProductID],"
      "[UnitPrice] FROM [SalesLT].[SalesOrderDetail]")
print(result)