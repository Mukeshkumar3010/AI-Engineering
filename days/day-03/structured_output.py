from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Literal, Optional

load_dotenv()

client = OpenAI()

# Define the structured output model for SQL queries
class SQLOutput(BaseModel):
    sql : str
    explanation : str = Field(description = 'this is the explanation of the answer generated')
    operation_type : Literal["INSERT", " DELETE", "SELECT", "UPDATE"]
    tables_used : list[str]
    clarity : int = Field(description = 'rate the user question based on clarity', le=5, ge=1)
    filter_used : Optional[list[str]]


history = []

history.append({"role" : "system", "content" : " You are an expert in Data Engineering"})

while True:
    user_input = input("ask your question: ")
    if user_input == "exit":
        break
    response = client.responses.parse( 
                                        model = 'gpt-5.6-luna',
                                        input = user_input,
                                        text_format = SQLOutput
                                    )
    result = response.output_parsed
    print(result.sql)
    print(result.explanation)   
    print(result.operation_type)
    print(result.tables_used)
    print(result.clarity)
    print(result.filter_used)                                     