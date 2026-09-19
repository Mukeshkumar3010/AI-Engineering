import pandas as pd
from ai_engineering.fabric_db import sql_connect, pbi_query, get_semantic_model_definition_cached, definition_to_schema_dataframes, build_pbi_schema_text

def execute_sql_query(query):
    with sql_connect() as conn:
        df = pd.read_sql(query, conn)

    return df

def get_sql_schema(table_name):
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
    return pbi_query(dax_query)

def get_fabric_schema():
    definition = get_semantic_model_definition_cached()
    columns_df, measures_df, relationships_df = definition_to_schema_dataframes(definition)
    return(build_pbi_schema_text(columns_df, measures_df, relationships_df))


# result = get_sql_schema("SalesOrderDetail")
# print(result)

# result = execute_query("SELECT TOP 5 [SalesOrderID],"
#       "[SalesOrderDetailID],"
#       "[OrderQty],"
#       "[ProductID],"
#       "[UnitPrice] FROM [SalesLT].[SalesOrderDetail]")
# print(result)