import os
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

class Settings:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    
    # Pinecone configuration
    PINECONE_INDEX_NAME = "runbooks"
    
    # Using a lightweight, free HuggingFace model for local embeddings
    EMBEDDING_MODEL = "all-MiniLM-L6-v2" 

settings = Settings()