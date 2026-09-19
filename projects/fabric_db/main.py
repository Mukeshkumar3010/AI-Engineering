from openai import OpenAI
from dotenv import load_dotenv
import pandas as pd
import os
from fabdb import get_sql_schema, get_fabric_schema, execute_sql_query, execute_dax_query
load_dotenv()

# we can use os below to get the environment variable for the OpenAI API key
# and use it to initialize the OpenAI client with the API key parameter.

#my_key = os.getenv('OPENAI_API_KEY')
#client = OpenAI(api_key=my_key)

# we can also directly rely on the OpenAI client to read the API key from the environment variable without explicitly passing it.
openai_client = OpenAI()

user_input = input("Please enter your prompt: ")

fabric_schema = get_fabric_schema()
sql_schema = get_sql_schema('SalesOrderDetail')
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
response = openai_client.responses.create(
                                            model='gpt-5.6-luna',
                                            input= final_fabric_prompt
                                        )
query = response.output_text

result = execute_dax_query(query)

print(query)
print(result)

