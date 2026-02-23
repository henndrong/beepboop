from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document  
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma


import os
from openai import OpenAI


try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"").strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


if load_dotenv:
    load_dotenv()
else:
    load_env_file()

API_KEY = os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in your environment or in a .env file")

client = OpenAI(api_key=API_KEY)

def get_embedding_function():
    embeddings = OpenAIEmbeddings(
        model = "text-embedding-3-large",
    )
    return embeddings

def load_documents():
    document_loader = PyPDFDirectoryLoader("data")
    return document_loader.load()

def split_documents(documents: list[Document]):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=80,
        length_function=len,
        is_separator_regex=False,
    )
    return text_splitter.split_documents(documents)

def make_chunk_id(chunk: Document, chunk_index: int) -> str:
    source = str(chunk.metadata.get("source", "unknown"))
    page = str(chunk.metadata.get("page", "unknown"))
    return f"{source}:{page}:{chunk_index}"

def make_chunk_ids(chunks: list[Document]) -> list[str]:
    per_page_counts: dict[tuple[str, str], int] = {}
    ids: list[str] = []
    for chunk in chunks:
        source = str(chunk.metadata.get("source", "unknown"))
        page = str(chunk.metadata.get("page", "unknown"))
        key = (source, page)
        per_page_counts[key] = per_page_counts.get(key, 0) + 1
        chunk_id = make_chunk_id(chunk, per_page_counts[key])
        chunk.metadata["chunk_id"] = chunk_id
        ids.append(chunk_id)
    return ids

def get_chroma_db(
    persist_directory: str = "chroma_db",
    collection_name: str = "docs",
):
    return Chroma(
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding_function=get_embedding_function(),
    )

def add_chunks_to_chroma(db: Chroma, chunks: list[Document]) -> list[str]:
    ids = make_chunk_ids(chunks)
    db.add_documents(chunks, ids=ids)
    return ids

def scan_folder_and_add(
    folder: str = "data",
    persist_directory: str = "chroma_db",
    collection_name: str = "docs",
) -> list[str]:
    documents = PyPDFDirectoryLoader(folder).load()
    chunks = split_documents(documents)
    db = get_chroma_db(
        persist_directory=persist_directory,
        collection_name=collection_name,
    )
    return add_chunks_to_chroma(db, chunks)

documents = load_documents()
chunks = split_documents(documents)
print(chunks[3])

ids = scan_folder_and_add(folder="data", persist_directory="chroma_db", collection_name="docs")
print(f"Added {len(ids)} chunks")
