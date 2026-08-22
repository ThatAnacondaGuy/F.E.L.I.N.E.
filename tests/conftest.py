"""Shared test fixtures."""
import pytest
import sqlite3

@pytest.fixture
def db_conn():
    """In-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def mock_ollama():
    """Mock Ollama client."""
    class MockClient:
        def generate(self, prompt):
            return "Mocked response"
    return MockClient()

@pytest.fixture
def sample_task():
    return {"id": "t1", "title": "Study for AI (PCC301COM)"}
