import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="gcl_test_")
os.environ["GCL_DATA_DIR"] = _tmp
os.environ["GCL_EE_PROJECT"] = ""        # hermetic: never use the developer .env or live credentials in tests
os.environ["GCL_EE_SERVICE_ACCOUNT"] = ""
os.environ["GCL_RATE_LIMIT_PER_MIN"] = "0"       # the limiter is enabled explicitly in its own test
os.environ["GCL_EE_PRIVATE_KEY_FILE"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def sample(client):   # regenerated per test: some tests delete the sample store
    r = client.post("/api/datasets/sample?region=banni")
    assert r.status_code == 200
    return r.json()
