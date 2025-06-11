from google.cloud import firestore, storage, tasks_v2
import os


class QueueService:
    def __init__(self):
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
    