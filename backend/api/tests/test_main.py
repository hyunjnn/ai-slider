from fastapi.testclient import TestClient
from main import app


client = TestClient(app)

def test_read_main():
    """루트 경로에 GET 요청 시 성공 메시지를 반환한다."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "API Server is alive"}
    