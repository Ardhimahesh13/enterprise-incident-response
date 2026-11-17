import os 
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec
from app.core.config import settings

# initialize the embeddings
embeddings = HuggingFaceEmbeddings(model_name = settings.EMBEDDING_MODEL)


# initialize the pineCone client
pc = Pinecone(api_key = settings.PINECONE_API_KEY)

def setup_pinecone_index() :
    existing_indexes = [index_info["name"] for index_info in pc.list_indexes()]
    if settings.PINECONE_INDEX_NAME not in existing_indexes :
        print(f"Creating new Pinecone index: {settings.PINECONE_INDEX_NAME}")
        pc.create_index(
            name = settings.PINECONE_INDEX_NAME,
            dimension=384,
            metric="cosine",
            spec = ServerlessSpec(cloud="aws", region="us-east-1")
        )
    return pc.Index(settings.PINECONE_INDEX_NAME)



def ingest_pdf_runbook(file_path: str):

    """Loads a PDF, chunks the text, and pushes the vectors to Pinecone."""

    print(f"Extracting text from: {file_path}")
    loader = PyPDFLoader(file_path)
    documents = loader.load()

    print("Chunking document into readable segments...")

    # Overlap ensures we don't cut critical troubleshooting steps in half

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)

    print(f"Pushing {len(chunks)} vectorized chunks to Pinecone...")
    setup_pinecone_index()
    
    PineconeVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
        index_name=settings.PINECONE_INDEX_NAME
    )
    print("Ingestion complete! Knowledge base updated.")

    return len(chunks)