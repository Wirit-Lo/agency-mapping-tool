"""API tests — verify the HTTP layer preserves byte-exact output."""
import pytest
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)

FILES = [
    "RA_AgencyScheme.txt", "RA_AgencyFieldData.txt", "RA_AgencyPostingData.txt",
    "RA_AgencyDerivedData.txt", "RA_AgencyValidationData.txt", "RA_AgencyLookup.txt",
    "RA_AgencyBarcodeDetails.txt", "RA_AgencyBarcodeParsingData.txt",
]


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_generate_returns_eight_files():
    r = client.post("/api/generate", json={"source": "excel"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["files"]) == 8
    assert data["total_objects"] > 4000


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Agency Data Mapping" in r.text


@pytest.mark.parametrize("name", FILES)
def test_download_byte_identical(name):
    client.post("/api/generate", json={"source": "excel"})
    api_bytes = client.get(f"/api/download/{name}").content
    golden = open(f"tests/golden/{name}", "rb").read()
    assert api_bytes == golden


def test_google_sheets_requires_service_account():
    r = client.post("/api/generate", json={"source": "google_sheets"})
    assert r.status_code == 400
    assert "service_account" in r.json()["detail"].lower()
