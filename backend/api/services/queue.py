import asyncio
import io
import json
import logging
import os
import time
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import Request
from google.api_core.exceptions import NotFound
from google.cloud import firestore, storage, tasks_v2

from models.slide import (
    File,
    FileReference,
    FirestoreJob,
    FirestoreResult,
    Job,
    JobStatus,
    SlideSettings,
    TaskPayload,
)


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
    
    
    def add_job(self, theme: str, file_data: list[File], settings: SlideSettings) -> Job:
        """Create a Job in Firestore -> Upload a file to GCS -> Create a Cloud Task -> Return the Job structure
        """
        job_id = str(uuid4())
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
            self.__create_cloud_task(task_payload)
        except Exception as e:
            self.update_job_status(job, JobStatus.FAILED, f"Failed to queue job: {e}", "") 
            raise RuntimeError(f"failed to create Cloud Task: {e}")
        
        return job
    
    
    def __create_cloud_task(self, payload: TaskPayload):
        parent = self.tasks_client.queue_path(self.project_id, self.region, self.queue_id)
        task_url = f"{self.service_url}/tasks/process-slides"
        
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
    
    
    def get_job_by_id(self, job_id: str):
        try:
            doc = self.collection().document(job_id).get()
        except NotFound:
            logging.info(f"Job {job_id} not found in Firestore")
            return None
        except Exception as e:
            logging.error(f"Error retrieving job {job_id}: {e}")
            return None
        
        if not doc.exists:
            logging.info(f"Job {job_id} does not exise")
            return None
        
        firestore_job_data = doc.to_dict()
        if firestore_job_data is None:
            logging.warning("Job data is None")
            return None
        
        now = int(time.time())
        expires_at = firestore_job_data.get("expiresAt", 0)
        if expires_at is not None and expires_at > 0 and now > expires_at:
            try:
                self.collection().document(job_id).delete()
                logging.info(f"Deleted expired job {job_id}")
            except Exception as e:
                logging.error(f"Failed to delete expired job {job_id}: {e}")
            return None
        
        result_url = None
        if firestore_job_data.get("status") == JobStatus.COMPLETED.value:
            try:
                result_doc = self.results_collection().document(job_id).get()
                if result_doc.exists:
                    result_data = result_doc.to_dict()
                    result_data = result_data.get("resultUrl")
            except Exception as e:
                logging.warning(f"Failed to fetch result for job {job_id}: {e}")

        return {
            "id": firestore_job_data["id"],
            "status": JobStatus(firestore_job_data["status"]),
            "message": firestore_job_data["message"],
            "resultUrl": result_url,
            "createdAt": firestore_job_data["createdAt"],
            "updatedAt": firestore_job_data["updatedAt"],
        }    
        
    
    async def stream_events(self, request: Request, job_id: str) -> AsyncGenerator[str, None]:
        """Streams real-time job status updates via Server-Sent Events (SSE).
        """
        queue: asyncio.Queue = asyncio.Queue()

        watch_task = asyncio.create_task(self.watch_job(job_id, queue))

        try:
            while True:
                if await request.is_disconnected():
                    watch_task.cancel()
                    break

                try:
                    update = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue

                if update is None:
                    break

                yield f"event: update\ndata: {json.dumps(update)}\n\n"

                if update["status"] in ("completed", "failed"):
                    yield f"event: close\ndata: {json.dumps({ 'id': update['id'], 'status': update['status'], 'message': 'Stream closing normally' })}\n\n"
                    await asyncio.sleep(0.3)
                    break
        finally:
            watch_task.cancel()
        
  
    async def watch_job(self, job_id: str, updates: asyncio.Queue) -> None:
        loop = asyncio.get_event_loop()

        doc_ref = self.db.collection("jobs").document(job_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise ValueError("job not found")

        data = doc.to_dict()
        await updates.put({
            "id": job_id,
            "status": data.get("status"),
            "message": data.get("message"),
            "resultUrl": data.get("resultUrl"),
            "updatedAt": data.get("updatedAt")
        })

        if data.get("status") in [JobStatus.COMPLETED, JobStatus.FAILED]:
            return

        stop_event = asyncio.Event()

        def on_snapshot(docs, changes, read_time):
            for doc in docs:
                data = doc.to_dict()
                result_url = data.get("resultUrl")
                
                if data.get("status") == JobStatus.COMPLETED.value:
                    try:
                        result_doc = self.db.collection("results").document(job_id).get()
                        if result_doc.exists:
                            result_data = result_doc.to_dict()
                            result_url = result_data.get("resultUrl", result_url)
                    except Exception as e:
                        print(f"Failed to fetch resultUrl from results/{job_id}: {e}")

                update = {
                    "id": job_id,
                    "status": data.get("status"),
                    "message": data.get("message"),
                    "resultUrl": result_url,
                    "updatedAt": data.get("updatedAt"),
                }

                asyncio.run_coroutine_threadsafe(updates.put(update), loop)

                if update["status"] in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
                    asyncio.run_coroutine_threadsafe(stop_event.set(), loop)

        unsubscribe = doc_ref.on_snapshot(on_snapshot)

        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe() 
    
    
    def get_result_by_id(self, job_id: str) -> FirestoreResult:
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
    