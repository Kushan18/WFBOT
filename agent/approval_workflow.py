"""
Approval workflow for Phase 7/15 - Staging → Pending → Live
"""
from pymongo import MongoClient
from typing import List, Dict, Any
import os
import logging
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)

class ApprovalWorkflow:
    """Manage the approval workflow for new schemes from scraper."""
    
    def __init__(self, mongo_uri: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client['welfarebot']
        self.staging = self.db['staging']
        self.pending = self.db['pending_approval']
        self.schemes = self.db['schemes']
    
    def get_staging_schemes(self) -> List[Dict[str, Any]]:
        """Get all schemes in staging collection awaiting review."""
        return list(self.staging.find({"status": "pending"}).sort("scraped_at", -1))
    
    def approve_scheme(self, scheme_id: str) -> bool:
        """Move a scheme from staging to pending_approval collection."""
        try:
            oid = ObjectId(scheme_id) if isinstance(scheme_id, str) and len(scheme_id) == 24 else scheme_id
            scheme = self.staging.find_one({"_id": oid})
            if not scheme:
                logger.error(f"Scheme {scheme_id} not found in staging")
                return False
            
            # Remove staging-specific fields
            scheme.pop("_id", None)
            scheme.pop("scraped_at", None)
            scheme.pop("status", None)
            
            # Add approval metadata
            scheme["approval_status"] = "pending_review"
            scheme["submitted_for_approval"] = datetime.utcnow()
            
            # Insert into pending collection
            self.pending.insert_one(scheme)
            
            # Remove from staging
            self.staging.delete_one({"_id": oid})
            
            logger.info(f"Scheme {scheme_id} moved to pending_approval")
            return True
            
        except Exception as e:
            logger.error(f"Error approving scheme {scheme_id}: {e}")
            return False
    
    def reject_scheme(self, scheme_id: str, reason: str = "") -> bool:
        """Reject a scheme from staging (delete it)."""
        try:
            oid = ObjectId(scheme_id) if isinstance(scheme_id, str) and len(scheme_id) == 24 else scheme_id
            self.staging.delete_one({"_id": oid})
            logger.info(f"Scheme {scheme_id} rejected: {reason}")
            return True
        except Exception as e:
            logger.error(f"Error rejecting scheme {scheme_id}: {e}")
            return False
    
    def get_pending_schemes(self) -> List[Dict[str, Any]]:
        """Get all schemes in pending_approval collection."""
        return list(self.pending.find({"approval_status": "pending_review"}).sort("submitted_for_approval", -1))
    
    def publish_scheme(self, scheme_id: str) -> bool:
        """Move a scheme from pending_approval to live schemes collection."""
        try:
            oid = ObjectId(scheme_id) if isinstance(scheme_id, str) and len(scheme_id) == 24 else scheme_id
            scheme = self.pending.find_one({"_id": oid})
            if not scheme:
                logger.error(f"Scheme {scheme_id} not found in pending_approval")
                return False
            
            # Remove approval-specific fields
            scheme.pop("_id", None)
            scheme.pop("approval_status", None)
            scheme.pop("submitted_for_approval", None)
            
            # Add live metadata
            scheme["published_at"] = datetime.utcnow()
            scheme["status"] = "live"
            
            # Insert into live schemes collection
            self.schemes.insert_one(scheme)
            
            # Remove from pending
            self.pending.delete_one({"_id": oid})
            
            # Update ChromaDB with new scheme
            try:
                from agent.chroma_retrieval import populate_chroma_from_mongodb
                populate_chroma_from_mongodb(self.schemes)
            except Exception as chroma_error:
                logger.warning(f"Failed to update ChromaDB: {chroma_error}")
            
            logger.info(f"Scheme {scheme_id} published to live collection")
            return True
            
        except Exception as e:
            logger.error(f"Error publishing scheme {scheme_id}: {e}")
            return False
    
    def reject_pending_scheme(self, scheme_id: str, reason: str = "") -> bool:
        """Reject a scheme from pending_approval (delete it)."""
        try:
            oid = ObjectId(scheme_id) if isinstance(scheme_id, str) and len(scheme_id) == 24 else scheme_id
            self.pending.delete_one({"_id": oid})
            logger.info(f"Scheme {scheme_id} rejected from pending: {reason}")
            return True
        except Exception as e:
            logger.error(f"Error rejecting pending scheme {scheme_id}: {e}")
            return False
    
    def get_approval_stats(self) -> Dict[str, int]:
        """Get statistics about the approval workflow."""
        return {
            "staging_count": self.staging.count_documents({"status": "pending"}),
            "pending_count": self.pending.count_documents({"approval_status": "pending_review"}),
            "live_count": self.schemes.count_documents({"status": "live"})
        }
