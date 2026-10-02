import os
from dotenv import load_dotenv
from pathlib import Path

# Force load the environment variables
load_dotenv()

class AppConfig:
    """Central Configuration Hub for the AI Application"""
    
    # 🔑 Authentication
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("CRITICAL ERROR: OPENAI_API_KEY is not set in the environment or .env file.")

    # 🤖 LLM Settings
    # Pulls from .env, falls back to safe defaults if the env variable isn't found
    MODEL_NAME = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    TEXT_EMBEDDING_MODEL_NAME = os.getenv("TEXT_EMBEDDING_MODEL_NAME", "text-embedding-3-small")
    TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.7)) # Cast to float
    MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 500))    # Cast to int

    # 📚 RAG Pipeline Parameters
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 500))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 100))

    # 🧩 Azure Configuration
    CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
    CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
    TENANT_ID = os.getenv("AZURE_TENANT_ID")
    AZURE_SERVER = os.getenv("AZURE_SERVER")
    AZURE_DB = os.getenv("AZURE_DB")

    # 🗂 Dataset and Workspace Configuration
    DATASET_ID = os.getenv("DATASET_ID")
    WORKSPACE_ID = os.getenv("WORKSPACE_ID")
    SEMANTIC_MODEL_ID = os.getenv("SEMANTIC_MODEL_ID", DATASET_ID)

    # 🔗 API Scopes and Cache Configuration
    SQL_SCOPE = ["https://database.windows.net/.default"]
    PBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
    FABRIC_SCOPE = ["https://api.fabric.microsoft.com/.default"]
    SCHEMA_CACHE_PATH = Path(".cache/semantic_model_definition.json")

    # 🏛 Authority URL for Microsoft Entra Authentication
    AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Instantiate a single configuration instance to be imported across files
config = AppConfig()
