import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import User, Role
from app import crud, schemas

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
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    # Manually trigger startup event logic for tests
    admin_role = crud.get_role_by_name(db, name="admin")
    if not admin_role:
        crud.create_role(db, role=schemas.RoleCreate(name="admin"))
    user_role = crud.get_role_by_name(db, name="user")
    if not user_role:
        crud.create_role(db, role=schemas.RoleCreate(name="user"))
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def regular_user_token_headers(test_client):
    test_client.post(
        "/users/", json={"email": "testuser@example.com", "password": "password"}
    )
    response = test_client.post(
        "/token", data={"username": "testuser@example.com", "password": "password"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_user_token_headers(test_client, db_session):
    # Create admin user
    user_schema = schemas.UserCreate(email="admin@example.com", password="adminpassword")
    user = crud.create_user(db=db_session, user=user_schema)
    # Assign admin role
    admin_role = crud.get_role_by_name(db=db_session, name="admin")
    crud.assign_role_to_user(db=db_session, user=user, role=admin_role)

    # Get token
    response = test_client.post(
        "/token", data={"username": "admin@example.com", "password": "adminpassword"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# --- Original Tests (Slightly Modified) ---

def test_create_user_success(test_client):
    response = test_client.post(
        "/users/", json={"email": "test@example.com", "password": "testpassword"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "roles" in data
    assert len(data["roles"]) == 1
    assert data["roles"][0]["name"] == "user"

# --- RBAC Tests ---

def test_read_users_me_success(test_client, regular_user_token_headers):
    response = test_client.get("/users/me", headers=regular_user_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testuser@example.com"

def test_read_users_me_unauthenticated(test_client):
    response = test_client.get("/users/me")
    assert response.status_code == 401 # Depends on OAuth2 scheme

# --- Admin Endpoint Tests ---

def test_admin_create_role_success(test_client, admin_user_token_headers):
    response = test_client.post(
        "/roles/",
        json={"name": "finance"},
        headers=admin_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "finance"

def test_admin_create_role_forbidden_for_regular_user(test_client, regular_user_token_headers):
    response = test_client.post(
        "/roles/",
        json={"name": "finance"},
        headers=regular_user_token_headers,
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "You don't have enough permissions"}

def test_admin_assign_role_success(test_client, admin_user_token_headers):
    # Create the user to be modified
    test_client.post("/users/", json={"email": "testuser@example.com", "password": "password"})

    response = test_client.post(
        "/users/testuser@example.com/roles?role_name=admin",
        headers=admin_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    role_names = {role["name"] for role in data["roles"]}
    assert "user" in role_names
    assert "admin" in role_names

def test_admin_assign_role_forbidden_for_regular_user(test_client, regular_user_token_headers):
    response = test_client.post(
        "/users/testuser@example.com/roles?role_name=admin",
        headers=regular_user_token_headers,
    )
    assert response.status_code == 403

def test_admin_assign_role_user_not_found(test_client, admin_user_token_headers):
    response = test_client.post(
        "/users/nobody@example.com/roles?role_name=admin",
        headers=admin_user_token_headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}

def test_admin_assign_role_role_not_found(test_client, admin_user_token_headers):
    # Create the user to be modified
    test_client.post("/users/", json={"email": "testuser@example.com", "password": "password"})

    response = test_client.post(
        "/users/testuser@example.com/roles?role_name=nonexistent",
        headers=admin_user_token_headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Role not found"}
