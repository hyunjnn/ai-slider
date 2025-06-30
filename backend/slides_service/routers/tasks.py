import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from models.task import File, TaskPayload
from services.infra.firestore import FirestoreService
from services.infra.gcs import GCSService
from services.slides.slides_service import SlideService

router = APIRouter()

slide_service = SlideService()
gcs_service = GCSService()
firestore_service = FirestoreService()  

@router.post("/tasks/process-slides")
async def process_slides(
    payload: TaskPayload
):
    """ Handle slide generation requests from Cloud Tasks
    """
    async def status_update(message: str):
        firestore_service.update_job_status(payload.jobID, "processing", message)

    try:
        await status_update("Starting slide generation...")
    except Exception as e:
        logging.error(f"Failed to update job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    files: list[File] = []
    for file_ref in payload.files:
        try:
            data, content_type = gcs_service.download_file_from_gcs(file_ref.gcsPath)
            files.append(File(filename=file_ref.filename, data=data, type=content_type))
        except Exception as e:
            logging.error(f"Failed to download file {file_ref.filename}: {e}")
            firestore_service.update_job_status(payload.jobID, "failed", f"Download error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    try:
        pdf_data, html_data = await slide_service.generate_slides(
            theme=payload.theme,
            files=files,
            settings=payload.settings,
            status_update_fn=status_update
        )
    except Exception as e:
        logging.error(f"Failed to generate slides: {e}")
        firestore_service.update_job_status(payload.jobID, "failed", f"Failed to generate slides: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    result_url = f"/results/{payload.jobID}"

    try:
        firestore_service.store_result(payload.jobID, result_url, pdf_data, html_data)
    except Exception as e:
        logging.error(f"Failed to store result: {e}")
        firestore_service.update_job_status(payload.jobID, "failed", f"Failed to store: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    for file_ref in payload.files:
        try:
            gcs_service.delete_file_from_gcs(file_ref.gcsPath)
            logging.info(f"Deleted file {file_ref.gcsPath} from GCS")
        except Exception as e:
            logging.warning(f"Failed to delete file {file_ref.gcsPath}: {e}")

    try:
        firestore_service.set_job_completed(payload.jobID, "Slides generated successfully", result_url)
    except Exception as e:
        logging.error(f"Failed to mark job as completed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(content={"status": "success", "jobID": payload.jobID})
    