import os
import logging

from google.cloud import storage


class GCSService:
    
    
    def __init__(self):
        self.client = storage.Client()
        self.bucket = self.client.bucket(os.environ.get("GCS_BUCKET_NAME"))
        
        
    def download_file_from_gcs(self, gcs_path: str):
        try: 
            blob = self.bucket.blob(gcs_path)
            if not blob.exists():
                raise FileNotFoundError(f"Object {gcs_path} not found in bucket {self.bucket_name}")
            data = blob.download_as_bytes()
            content_type = blob.content_type or "application/actet-stream"
            return data, content_type
        except Exception as e:
            logging.error(f"Failed to download {gcs_path} from GCS: {e}")
            raise
        
        
    def delete_file_from_gcs(self, gcs_path: str) -> None:
        blob = self.bucket.blob(gcs_path)
        try:
            blob.delete()
            logging.info(f"Deleted file {gcs_path} from GCS")
        except Exception as e:
            logging.warning(f"Falied to delete file {gcs_path} from GCS: {e}")
            