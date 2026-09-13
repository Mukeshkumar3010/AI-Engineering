import pandas as pd
from sqlalchemy import text
from ai_engineering.fabric_db import get_engine


def execute_query(query):
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    print(df)
    return df


if __name__ == "__main__":
    execute_query("SELECT TOP 5 * FROM [SalesLT].[SalesOrderDetail]")