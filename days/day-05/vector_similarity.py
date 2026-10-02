from openai import OpenAI
from dotenv import load_dotenv
from config import config
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

# client = OpenAI()
client = OpenAI(api_key=config.OPENAI_API_KEY)

def get_embedding(text: str):
    response = client.embeddings.create(
                                        model = 'text-embedding-3-small'
                                        ,input = text
                                        ,dimensions = 300
                                    )
    return(response.data[0].embedding)

documents = ["spark is a distributed system"
             , "databricks is a data and ai platform and uses spark as compute engine"
             , "snowflake is a data warehousing platform and has emerging as end to end data and AI platform"
             , "GenAI is emerging field for data engineers"
             , "Virat Kohli has awesome cover drive"
             , "I love playing football"
             ]

doc_embeddings = []
for text in documents:
    doc_embeddings.append(get_embedding(text))

query = "tell me about spark"
query_embedding = get_embedding(query)
# print(query_embedding)

similarity = cosine_similarity([query_embedding], doc_embeddings)
print(similarity)
