from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
# import sys

# sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_engineering.config import config
from query_models import DAXQueryOutput
import pandas as pd
import os
from fabric_queries import get_sql_schema, get_fabric_schema, execute_sql_query, execute_dax_query
load_dotenv()

# we can use os below to get the environment variable for the OpenAI API key
# and use it to initialize the OpenAI client with the API key parameter.

#my_key = os.getenv('OPENAI_API_KEY')
#client = OpenAI(api_key=my_key)

# we can also directly rely on the OpenAI client to read the API key from the environment variable without explicitly passing it.
# openai_client = OpenAI()

# Initialize client using the key verified by config
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

fabric_schema = get_fabric_schema()
sql_schema = get_sql_schema('SalesOrderDetail')

history = []
while True:
    user_input = input("Please enter your prompt: ")
    if not user_input or user_input == "exit":
        break

    # we need to pass whole prompt with better context for the model to understand

    final_sql_prompt = f'''generate a sql statement based on below schema
                {sql_schema}
                question: {user_input}

                Just give me the SQL only.
                Add the TABLE_SCHEMA in the table references of the query.
            '''

    final_fabric_prompt = f'''generate a dax query based on below schema
                {fabric_schema}
                question: {user_input}

                Just give me the DAX query only.
            '''
# create a response using the OpenAI client
    history.append({"role" : "user", "content" : user_input})
    print(history)
    # response = openai_client.responses.create(
    #                                             model= config.MODEL_NAME, #"gpt-5.6-luna", #gpt-4o-mini",
    #                                             input= final_fabric_prompt
                                                
    #                                         )
    
    # history.append({"role": "assistant", "content" : response.output_text})
    # # print(response.output_text)
    # query = response.output_text

    response = openai_client.responses.parse(
                                                model=config.MODEL_NAME,
                                                input=final_fabric_prompt,
                                                text_format=DAXQueryOutput,
                                            )
    generated = response.output_parsed
    if generated is None:
        raise RuntimeError("The model did not return a structured DAX query.")

    history.append({"role": "assistant", "content": generated.query})
    print(generated.explanation)
    query = generated.query

    result = execute_dax_query(query)

    print(query)
    print(result)

# response_id = None
# while True:
#     user_input = input("Please enter your prompt: ")
#     if not user_input or user_input == "exit":
#         break
# create a response using the OpenAI client
    # response = openai_client.responses.create(
    #                                             model=config.MODEL_NAME,
    #                                             input= user_input, #final_fabric_prompt
    #                                             previous_response_id = response_id
    #                                         )
    
    # response_id = response.id
    # print(response.output_text)