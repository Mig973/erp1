import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app, get_db
from app.database import Base
from app.models import User

# In-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Test database setup
@pytest.fixture(scope="function")
def db_session():
    """
    Create a new database session for a test.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_client(db_session):
    """
    Create a test client that uses the test database.
    """

    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# --- Tests ---

def test_create_user_success(test_client):
    """Test creating a user successfully."""
    response = test_client.post(
        "/users/",
        json={"email": "test@example.com", "password": "testpassword"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "hashed_password" not in data


def test_create_user_duplicate_email(test_client):
    """Test creating a user with an email that already exists."""
    # Create the first user
    test_client.post(
        "/users/",
        json={"email": "test@example.com", "password": "testpassword"},
    )
    # Attempt to create a second user with the same email
    response = test_client.post(
        "/users/",
        json={"email": "test@example.com", "password": "anotherpassword"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Email already registered"}


def test_login_for_access_token_success(test_client):
    """Test successful login and token generation."""
    # First, create a user to log in with
    test_client.post(
        "/users/",
        json={"email": "test@example.com", "password": "testpassword"},
    )
    # Now, log in
    response = test_client.post(
        "/token",
        data={"username": "test@example.com", "password": "testpassword"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_for_access_token_wrong_password(test_client):
    """Test login with a wrong password."""
    # Create a user
    test_client.post(
        "/users/",
        json={"email": "test@example.com", "password": "testpassword"},
    )
    # Attempt to log in with the wrong password
    response = test_client.post(
        "/token",
        data={"username": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}


def test_login_for_access_token_nonexistent_user(test_client):
    """Test login for a user that does not exist."""
    response = test_client.post(
        "/token",
        data={"username": "nosuchuser@example.com", "password": "anypassword"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}
