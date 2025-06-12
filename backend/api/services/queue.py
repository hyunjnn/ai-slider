import logging
from google.cloud import firestore, storage, tasks_v2
from google.api_core.exceptions import NotFound
import os
import time

from models.slide import FirestoreResult


class QueueService:
    def __init__(self):
        # self.db = firestore.AsyncClient()
        self.db = firestore.Client()
        self.storage_client = storage.Client()
        self.tasks_client = tasks_v2.CloudTasksClient()

        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.region = os.getenv("CLOUD_TASKS_REGION", "asia-northeast3")
        self.queue_id = os.getenv("CLOUD_TASKS_QUEUE_ID", "slides-generation-queue")
        self.service_url = os.getenv("SLIDES_SERVICE_URL")
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "ai-slider-files")


    def collection(self):
        return self.db.collection("jobs")
    

    def results_collection(self):
        return self.db.collection("results")
    
    
    def get_result(self, job_id: str) -> FirestoreResult:
        """
        Retrieve the slide generation result from Firestore.

        If the result is missing or expired, raises an exception.
        Returns a FirestoreResult object containing the PDF/HTML content and metadata.

        Args:
            job_id (str): The ID of the job to retrieve
            
        Raises:
            RuntimeError: If the result is not found, expired, or cannot be parsed

        Returns:
            FirestoreResult: Contains presentation result data and timestamps
        """
        try:
            doc = self.results_collection().document(job_id).get()
        except NotFound:
            raise RuntimeError("result not found")
        except Exception as e:
            raise RuntimeError(f"error retrieving result: {e}")

        if not doc.exists:
            raise RuntimeError("result not found")

        result_data = doc.to_dict()
        if result_data is None:
            raise RuntimeError("result data is empty")

        
        now = int(time.time())
        expires_at = result_data.get("expiresAt", 0)
        if expires_at > 0 and now > expires_at:
            try:
                self.results_collection().document(job_id).delete()
                logging.info(f"Deleted expired result {job_id}")
            except Exception as e:
                logging.warning(f"Failed to delete expired result {job_id}: {e}")
            raise RuntimeError("result has expired")

        return FirestoreResult(**result_data)
    