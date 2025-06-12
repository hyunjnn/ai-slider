from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from backend.api.models.slide import FirestoreResult
from services.queue import QueueService


router = APIRouter()

@router.get("/results/{id}") 
async def get_slide_result(id: str, download: Optional[bool] = Query(False)):
    try:
        result : FirestoreResult = QueueService.get_result(id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Result not found: {e}")
    
    if download:
        return Response(
            content=result.pdfData,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=presentation-{id}.pdf"
            }
        )
    else:
        return HTMLResponse(
            content=result.htmlData,
            status_code=200
        )