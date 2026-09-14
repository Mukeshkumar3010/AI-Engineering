import pandas as pd
from ai_engineering.fabric_db import sql_connect, pbi_connect


def execute_sql_query(query):
    with sql_connect() as conn:
        df = pd.read_sql(query, conn)

    return df

def get_schema(table_name):
    query = f"""
        SELECT TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = 'SalesLT'
        AND TABLE_NAME = '{table_name}'
    """
    schema = execute_sql_query(query)
    return schema

def execute_dax_query(dax_query):
    data = pbi_connect(dax_query)
    rows = data["results"][0]["tables"][0]["rows"]
    df = pd.DataFrame(rows)
    
    return df

# result = get_schema("SalesOrderDetail")
# print(result)

# result = execute_query("SELECT TOP 5 [SalesOrderID],"
#       "[SalesOrderDetailID],"
#       "[OrderQty],"
#       "[ProductID],"
#       "[UnitPrice] FROM [SalesLT].[SalesOrderDetail]")
# print(result)