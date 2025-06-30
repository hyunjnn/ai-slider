from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from routers import tasks

app = FastAPI()

app.include_router(tasks.router)

@app.get("/")
def health_check():
    return {"message": "Service Server is alive"}
