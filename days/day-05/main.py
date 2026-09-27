from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

# while True:
#     user_input = input("Ask your question: ")
#     if user_input == 'break':
#         break

  # response = client.responses.create(
  #                                    model = 'gpt-5.6-luna'
  #                                    ,input = user_input
                                )
# print(response.output_text)
response = client.embeddings.create(
                                    model = 'text-embedding-3-small'
                                    ,input = "spark is distrubuted system"
                                    ,dimensions = 4
                                )
print(response.data[0].embedding)
