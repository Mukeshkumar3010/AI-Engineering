from openai import OpenAI
from dotenv import load_dotenv
import os
load_dotenv()

# we can use os below to get the environment variable for the OpenAI API key
# and use it to initialize the OpenAI client with the API key parameter.

#my_key = os.getenv('OPENAI_API_KEY')
#client = OpenAI(api_key=my_key)

# we can also directly rely on the OpenAI client to read the API key from the environment variable without explicitly passing it.
openai_client = OpenAI()

# create a response using the OpenAI client
response = openai_client.responses.create(
                                            model='gpt-4o-mini',
                                            input=prompt
                                        )
print(response.output_text)