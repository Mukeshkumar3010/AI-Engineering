from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

# Initialize conversation history
history = []

# Start the conversation loop with the user input and assistant responses to maintain context
# while True:
#     user_input = input("Input your prompt: ")
#     if not user_input or user_input == "exit" :
#         break
#     history.append({"role" : "user", "content" : user_input})
#     response = client.responses.create(
#                                         model='gpt-5.6-luna',
#                                         input= history
#                                     )
#     history.append({"role" : "assistant", "content" : response.output_text})
#     print(response.output_text)

response_id = None
while True:
    user_input = input("Input your prompt: ")
    if user_input == "exit" :
        break
    response = client.responses.create( 
                                        model = 'gpt-5.6-luna',
                                        input = user_input,
                                        previous_response_id = response_id                                    
                                    )
    response_id = response.id
    print(response.output_text)