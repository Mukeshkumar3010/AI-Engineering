from typing import Literal

from pydantic import BaseModel, Field


class DAXQueryOutput(BaseModel):
    query: str = Field(description="A valid DAX query for the configured semantic model")
    explanation: str = Field(description="A brief explanation of what the query returns")


class SQLQueryOutput(BaseModel):
    sql: str = Field(description="A valid SQL query for the configured Fabric database")
    explanation: str = Field(description="A brief explanation of what the query does")
    operation_type: Literal["INSERT", "DELETE", "SELECT", "UPDATE"]
    tables_used: list[str]
    clarity: int = Field(description="Rate the user's question clarity from 1 to 5", ge=1, le=5)
    filter_used: list[str] | None = None
