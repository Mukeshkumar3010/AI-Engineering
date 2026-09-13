import pandas as pd
from ai_engineering.fabric_db import connect


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