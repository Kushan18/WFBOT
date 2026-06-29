import os
import pymongo
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import chromadb
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def build_chunk(scheme):
    parts = [
        f"Name: {scheme.get('name','')}",
        f"State: {scheme.get('state','')}",
        f"Description: {scheme.get('description','')}",
        f"Eligibility: {scheme.get('eligibility','')}",
        f"Documents: {scheme.get('documents','')}",
        f"Benefits: {scheme.get('benefits','')}",
        f"How to Apply: {scheme.get('how_to_apply','')}",
        f"Deadline: {scheme.get('deadline','Ongoing')}",
        f"Apply Link: {scheme.get('apply_link','')}",
    ]
    return "\n".join(parts).strip()

def run():
    client = pymongo.MongoClient(os.getenv('MONGODB_URI'))
    schemes = list(client['welfarebot']['schemes'].find())
    logger.info(f"loaded {len(schemes)} schemes")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    is_vercel = "VERCEL" in os.environ or os.path.exists("/tmp")
    chroma = chromadb.PersistentClient(path="/tmp/chroma_db" if is_vercel else "./chroma_db")
    try:
        chroma.delete_collection("welfare_schemes")
    except:
        pass
    collection = chroma.create_collection("welfare_schemes")
    chunks = [build_chunk(s) for s in schemes]
    ids = [f"scheme_{i}" for i in range(len(schemes))]
    metadatas = [{"name": s.get('name',''), "state": s.get('state','')} for s in schemes]
    embeddings = model.encode(chunks).tolist()
    collection.add(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)
    print(f"Done! {len(chunks)} schemes embedded into ChromaDB")

if __name__ == "__main__":
    run()
