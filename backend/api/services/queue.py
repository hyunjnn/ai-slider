import logging
from google.cloud import firestore, storage, tasks_v2
from google.api_core.exceptions import NotFound
import os
import io
import time
import json

from models.slide import File, FirestoreJob, FirestoreResult, Job, JobUpdate, SlideSettings, FileReference, TaskPayload, JobStatus


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
    
    def upload_file_to_gcs(self, job_id: str, file: File) -> str:
        """Upload a file to Google Cloud Storage and return the path
        """
        object_path = f"{job_id}/{file.filename}"
        bucket = self.storage_client.bucket(self.bucket_name)
        
        # If the bucket does not exist, create a new one
        try:
            bucket.reload()
        except NotFound:  
            try:  
                bucket.create(location="asia-northeast3")
                logging.info(f"Created bucket {self.bucket_name}")
            except Exception as e:
                raise RuntimeError(f"Failed to create bucket: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to check bucket: {e}")
        
        blob = bucket.blob(object_path)
        
        try:
            blob.upload_from_file(io.BytesIO(file.data), content_type=file.type)
            logging.info("Success GCS Upload :%s", object_path)
        except Exception as e:
            logging.error("Failed GCS Upload : %s", str(e))
            raise RuntimeError(f"Failed to upload file to GCS: {e}")
        
        logging.info(f"Upload file {file.filename} to GCS: gs://{self.bucket_name}/{object_path}")    
        return object_path
    
    
    def add_job(self, job_id: str, theme: str, file_data: list[File], settings: SlideSettings) -> Job:
        """Create a Job in Firestore -> Upload a file to GCS -> Create a Cloud Task -> Return the Job structure
        """
        now = int(time.time())
        
        firestore_job = FirestoreJob(
            id=job_id,
            status=JobStatus.QUEUED.value,
            message="Job added to queue",
            createdAt=now,
            updatedAt=now,
        )
        
        try:
            logging.info(f"Saving Firestore job: {firestore_job.model_dump()}")
            self.collection().document(job_id).set(firestore_job.model_dump())
        except Exception as e:
            logging.error(f"Firestore save failed: {e}")
            raise RuntimeError("failed to store job")

        job = Job(
            id=job_id,
            theme=theme,
            files=file_data,
            settings=settings,
            status=JobStatus.QUEUED,
            message="Job added to queue",
            createdAt=now,
            updatedAt=now
        )
        
        file_refs = []
        for file in file_data:
            try:
                gcs_path = self.upload_file_to_gcs(job_id, file)
            except Exception as e:
                self.update_job_status(job, JobStatus.FAILED, f"Failed to upload file {file.filename}: {e}", "")
                raise RuntimeError(f"failed to upload file: {e}")
                
            file_refs.append(FileReference(filename=file.filename, type=file.type, gcsPath=gcs_path))

        task_payload = TaskPayload(
            jobID=job_id,
            theme=theme,
            files=file_refs,
            settings=settings
        )
        
        try:
            self._create_cloud_task(task_payload)
        except Exception as e:
            self.update_job_status(job, JobStatus.FAILED, f"Failed to queue job: {e}", "") 
            raise RuntimeError(f"failed to create Cloud Task: {e}")
        
        return job
    
    
    def _create_cloud_task(self, payload: TaskPayload):
        parent = self.tasks_client.queue_path(self.project_id, self.region, self.queue_id)
        task_url = f"{self.service_url}/tasks/process-slides"
        
        print("Sending TaskPayload: ", payload.model_dump())
        print("Task URL: ", task_url)
        
        try:
            payload_bytes = json.dumps(payload.model_dump()).encode()
        except Exception as e:
            raise RuntimeError(f"Failed to serialize task payload: {e}")

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": task_url,
                "headers": {"Content-Type": "application/json"},
                "body": payload_bytes,
                "oidc_token": {
                    "service_account_email": f"slides-service-invoker@{self.project_id}.iam.gserviceaccount.com",
                    "audience": task_url
                }
            }
        }

        self.tasks_client.create_task(request={"parent": parent, "task": task})
    
    
    def update_job_status(self, job: Job, status: JobStatus, message: str, result_url: str = ""):
        now = int(time.time())
        
        updates = {
            "status": status.value,
            "message": message,
            "updatedAt": now,
        }
        
        try: 
            self.collection().document(job.id).update(updates)
        except Exception as e:
            logging.error(f"Failed to update job status in Firestore: {e}")
            
        job.status = status
        job.message = message
        job.updatedAt = now
        if result_url:
            job.resultUrl = result_url
            
        logging.info(f"Job {job.id} updated: status={status}, message={message}")
    
    
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
    