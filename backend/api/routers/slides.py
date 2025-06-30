import json
import logging
import mimetypes
from typing import Optional

from fastapi import APIRouter
from fastapi import File as FastAPIFile
from fastapi import Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from models.slide import (File, FirestoreResult, Job, SlideRequest,
                          SlideResponse)
from services.queue import QueueService
from utils.mime import validate_file_type

router = APIRouter()

service = QueueService()

@router.post("/slides")
async def generate_slides(
    data: str = Form(...),
    files: list[UploadFile] = FastAPIFile(...)
):
    # Parse JSON from the 'data' form field
    try:
        req_data = json.loads(data)
        slide_req = SlideRequest(**req_data)
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid request format: {str(e)}")

    if slide_req.theme not in SlideRequest.valid_themes:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid theme: {slide_req.theme}. Supported themes are: {', '.join(SlideRequest.valid_themes)}")

    if slide_req.settings.slideDetail and slide_req.settings.slideDetail not in SlideRequest.valid_slide_details:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid slideDetail: {slide_req.settings.slideDetail}. Supported values are: {', '.join(SlideRequest.valid_slide_details)}")

    if slide_req.settings.audience and slide_req.settings.audience not in SlideRequest.valid_audiences:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid audience: {slide_req.settings.audience}. Supported values are: {', '.join(SlideRequest.valid_audiences)}")

    if not files:
        raise HTTPException(
            status_code=400, 
            detail="No files uploaded")

    file_data_list = []
    for file in files:
        try:
            content = await file.read()
            mime_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
            if not validate_file_type(file.filename):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file type: {file.filename}. Only PDF, Markdown, and TXT files are allowed")

            file_data_list.append(File(filename=file.filename, data=content, type=mime_type))
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to read file {file.filename}: {str(e)}")

    # Add Job to Queue
    try:
        job : Job = service.add_job(slide_req.theme, file_data_list, slide_req.settings)
    except Exception as e:
        raise HTTPException(
            status_code=503, 
            detail=str(e))

    logging.info(f"Received slide generation request: Theme: {slide_req.theme}, Files count: {len(file_data_list)}, Settings: {slide_req.settings}")

    return JSONResponse(
        status_code=202,
        content=SlideResponse(
            id=job.id,
            status=job.status,
            message=job.message,
            createdAt=job.createdAt,
            updatedAt=job.updatedAt
        ).model_dump()
    )
             
@router.get("/slides/{id}")
async def stream_slide_status(
    request: Request, 
    id: str
):
    """Returns slide status via SSE or JSON. 
       Closes stream when job is completed or failed.
    """
    job : Job = service.get_job_by_id(id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    accept_header = request.headers.get("Accept", "")
    
    if "text/event-stream" not in accept_header:
        return JSONResponse({
            "id": job.id,
            "status": job.status,
            "message": job.message,
            "resultUrl": job.resultUrl,
            "updatedAt": job.updatedAt
        })  

    return StreamingResponse(
        service.stream_events(request, id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
            "Access-Control-Allow-Origin": "https://ai-slider-frontend-987235114382.asia-northeast3.run.app",
            "X-Accel-Buffering": "no",
        }
    ) 
    
@router.get("/results/{id}") 
async def get_slide_result(
    id: str, 
    download: Optional[bool] = Query(False)
):
    """Returns slide result (PDF or HTML).  
       Automatically deletes the result if it is expired.
    """
    try:
        result : FirestoreResult = service.get_result_by_id(id)
    except Exception as e:
        raise HTTPException(
            status_code=404, 
            detail=f"Result not found: {e}")
    
    if download:
        return Response(
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=presentation-{id}.pdf"
            },
            content=result.pdfData
        )
    else:
        return HTMLResponse(
            status_code=200, 
            content=result.htmlData)
        