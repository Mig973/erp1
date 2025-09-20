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


# --- Product Module Tests ---

@pytest.fixture
def sample_product(test_client, admin_user_token_headers):
    product_data = {
        "sku": "TEST-001",
        "name": "Test Product",
        "description": "This is a test product.",
        "price": 99.99,
    }
    response = test_client.post(
        "/products/",
        json=product_data,
        headers=admin_user_token_headers,
    )
    assert response.status_code == 200
    return response.json()


def test_admin_can_create_product(sample_product):
    assert sample_product["sku"] == "TEST-001"
    assert sample_product["name"] == "Test Product"
    assert sample_product["inventory"] is not None
    assert sample_product["inventory"]["quantity"] == 0


def test_regular_user_cannot_create_product(test_client, regular_user_token_headers):
    product_data = {"sku": "FAIL-001", "name": "Fail Product", "price": 10.0}
    response = test_client.post(
        "/products/",
        json=product_data,
        headers=regular_user_token_headers,
    )
    assert response.status_code == 403


def test_create_product_duplicate_sku(test_client, admin_user_token_headers, sample_product):
    duplicate_product = {
        "sku": "TEST-001",
        "name": "Another Product",
        "price": 50.0,
    }
    response = test_client.post(
        "/products/",
        json=duplicate_product,
        headers=admin_user_token_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "SKU already registered"


def test_authenticated_user_can_read_products(test_client, regular_user_token_headers, sample_product):
    response = test_client.get("/products/", headers=regular_user_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["sku"] == sample_product["sku"]

    response = test_client.get(f"/products/{sample_product['id']}", headers=regular_user_token_headers)
    assert response.status_code == 200
    assert response.json()["name"] == sample_product["name"]


def test_unauthenticated_user_cannot_read_products(test_client, sample_product):
    response = test_client.get("/products/")
    assert response.status_code == 401

    response = test_client.get(f"/products/{sample_product['id']}")
    assert response.status_code == 401


def test_admin_can_update_product(test_client, admin_user_token_headers, sample_product):
    update_data = {"name": "Updated Test Product", "price": 120.50}
    response = test_client.put(
        f"/products/{sample_product['id']}",
        json=update_data,
        headers=admin_user_token_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Test Product"
    assert data["price"] == 120.50
    assert data["sku"] == sample_product["sku"]


def test_regular_user_cannot_update_product(test_client, regular_user_token_headers, sample_product):
    update_data = {"name": "Should Fail Update"}
    response = test_client.put(
        f"/products/{sample_product['id']}",
        json=update_data,
        headers=regular_user_token_headers,
    )
    assert response.status_code == 403


def test_admin_can_delete_product(test_client, admin_user_token_headers, sample_product):
    # Delete the product
    response = test_client.delete(
        f"/products/{sample_product['id']}", headers=admin_user_token_headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == sample_product["id"]

    # Verify it's gone
    verify_response = test_client.get(
        f"/products/{sample_product['id']}", headers=admin_user_token_headers
    )
    assert verify_response.status_code == 404


def test_regular_user_cannot_delete_product(test_client, regular_user_token_headers, sample_product):
    response = test_client.delete(
        f"/products/{sample_product['id']}", headers=regular_user_token_headers
    )
    assert response.status_code == 403


# --- Inventory Module Tests ---

def test_authenticated_user_can_read_inventory(test_client, regular_user_token_headers, sample_product):
    response = test_client.get("/inventory/", headers=regular_user_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Find our specific product's inventory
    inventory_item = next(
        (item for item in data if item["product_id"] == sample_product["id"]), None
    )
    assert inventory_item is not None
    assert inventory_item["quantity"] == 0


def test_admin_can_adjust_inventory(test_client, admin_user_token_headers, sample_product):
    # Add 50 units
    adjust_data = {"change": 50}
    response = test_client.post(
        f"/inventory/{sample_product['id']}/adjust",
        json=adjust_data,
        headers=admin_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 50

    # Subtract 20 units
    adjust_data = {"change": -20}
    response = test_client.post(
        f"/inventory/{sample_product['id']}/adjust",
        json=adjust_data,
        headers=admin_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 30


def test_regular_user_cannot_adjust_inventory(test_client, regular_user_token_headers, sample_product):
    adjust_data = {"change": 10}
    response = test_client.post(
        f"/inventory/{sample_product['id']}/adjust",
        json=adjust_data,
        headers=regular_user_token_headers,
    )
    assert response.status_code == 403
