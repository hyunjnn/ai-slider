import logging
import time

from google.cloud import firestore
from models.task import FireStoreResult


class FirestoreService:
    
    
    def __init__(self):
        self.client = firestore.Client()
        
        
    def update_job_status(self, job_id: str, status: str, message: str, result_url: str = "") -> None:
        """Update the job document with new status and message
        """
        try: 
            now = int(time.time())
            updates = {
                "status": status,
                "message": message,
                "updatedAt": now
            }
            self.client.collection("jobs").document(job_id).update(updates)
            logging.info(f"Job {job_id} updated: status={status}, message={message}")           
        except Exception as e:
            logging.error(f"Faild to update job status in Firestore: {e}")
            raise  
        
        
    def set_job_completed(self, job_id: str, message: str, result_url: str = ""):
        """Mark the job as completed and set its expiration time
        """
        try:
            now = int(time.time())
            expires_at = now + 300
            updates = {
                "status": "completed",
                "message": message,
                "updatedAt": now,
                "expiresAt": expires_at
            }
            self.client.collection("jobs").document(job_id).update(updates)            
            logging.info(f"Job {job_id} completed adn will expire at {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at))}")           
        except Exception as e:
            logging.error(f"Failed to mark job as completed in Firestore: {e}")
            raise
        
        
    def store_result(self, job_id: str, result_url: str, pdf_data: bytes, html_data: bytes) -> None:
        """Store the final job result (PDF + HTML) in Firestore
        """
        try:
            now = int(time.time())
            expires_at = now + 3600
            result = FireStoreResult(
                id=job_id,
                resultUrl=result_url,
                pdfData=pdf_data,
                htmlData=html_data,
                createdAt=now,
                expiresAt=expires_at
            )
            self.client.collection("results").document(job_id).set(result.model_dump())
            logging.info(f"Stored result for job {job_id} (expires at {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires_at))})")   
        except Exception as e:
            logging.error(f"Failed to store result for job {job_id}: {e}")
            raise
        