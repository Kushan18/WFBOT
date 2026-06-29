"""
ChromaDB retrieval for Phase 8 - First tier of scheme detail retrieval
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import os
import logging

logger = logging.getLogger(__name__)

# Initialize ChromaDB client
is_vercel = "VERCEL" in os.environ or os.path.exists("/tmp")
chroma_client = chromadb.PersistentClient(path="/tmp/chroma_db" if is_vercel else "chroma_db")
schemes_collection = chroma_client.get_or_create_collection(
    name="welfare_schemes",
    metadata={"hnsw:space": "cosine"}
)

def populate_chroma_from_mongodb(mongo_collection):
    """
    Populate ChromaDB with scheme data from MongoDB.
    This should be called periodically or when schemes are updated.
    """
    try:
        schemes = list(mongo_collection.find({}))
        
        if not schemes:
            logger.warning("No schemes found in MongoDB to populate ChromaDB")
            return 0
        
        documents = []
        metadatas = []
        ids = []
        
        for scheme in schemes:
            # Create a searchable text document
            doc_text = f"""
            Scheme Name: {scheme.get('name', '')}
            Description: {scheme.get('description', '')}
            Category: {scheme.get('category', '')}
            State: {scheme.get('eligibility_rules', {}).get('state', '')}
            Caste Category: {scheme.get('eligibility_rules', {}).get('caste_category', '')}
            Occupation: {scheme.get('eligibility_rules', {}).get('occupation', '')}
            Required Documents: {', '.join(scheme.get('required_documents', []))}
            Apply Link: {scheme.get('apply_link', '')}
            Deadline: {scheme.get('deadline', '')}
            """
            
            documents.append(doc_text)
            metadatas.append({
                "name": scheme.get('name', ''),
                "state": scheme.get('eligibility_rules', {}).get('state', ''),
                "category": scheme.get('category', ''),
                "apply_link": scheme.get('apply_link', '')
            })
            ids.append(str(scheme.get('_id', '')))
        
        # Get existing IDs to avoid duplicates
        try:
            existing = schemes_collection.get()
            existing_ids = existing['ids'] if existing and 'ids' in existing else []
            if existing_ids:
                schemes_collection.delete(ids=existing_ids)
        except Exception as e:
            logger.warning(f"Could not clear existing ChromaDB data: {e}")
        
        # Add new data
        schemes_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        logger.info(f"Populated ChromaDB with {len(schemes)} schemes")
        return len(schemes)
        
    except Exception as e:
        logger.error(f"Error populating ChromaDB: {e}")
        return 0

def search_chroma(query: str, n_results: int = 3) -> List[Dict[str, Any]]:
    """
    Search ChromaDB for relevant schemes based on query.
    Returns list of matching scheme documents with metadata.
    """
    try:
        results = schemes_collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        if not results or not results['documents'] or not results['documents'][0]:
            return []
        
        matched_schemes = []
        for i in range(len(results['documents'][0])):
            matched_schemes.append({
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i] if results['distances'] else None
            })
        
        return matched_schemes
        
    except Exception as e:
        logger.error(f"Error searching ChromaDB: {e}")
        return []

def get_scheme_details_from_chroma(scheme_name: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific scheme from ChromaDB.
    Returns the scheme document if found, None otherwise.
    """
    try:
        # Search for the specific scheme name
        results = schemes_collection.query(
            query_texts=[scheme_name],
            n_results=1
        )
        
        if not results or not results['documents'] or not results['documents'][0]:
            return None
        
        # Check if the top result matches the scheme name
        top_result = results['metadatas'][0][0]
        if scheme_name.lower() in top_result.get('name', '').lower():
            return {
                "text": results['documents'][0][0],
                "metadata": top_result,
                "found": True
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting scheme from ChromaDB: {e}")
        return None
