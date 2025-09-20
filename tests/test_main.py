import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
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
    sales_role = crud.get_role_by_name(db, name="sales")
    if not sales_role:
        crud.create_role(db, role=schemas.RoleCreate(name="sales"))
    purchasing_role = crud.get_role_by_name(db, name="purchasing")
    if not purchasing_role:
        crud.create_role(db, role=schemas.RoleCreate(name="purchasing"))
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


# --- User Fixtures ---
@pytest.fixture(scope="function")
def regular_user_token_headers(test_client):
    test_client.post("/users/", json={"email": "testuser@example.com", "password": "password"})
    response = test_client.post("/token", data={"username": "testuser@example.com", "password": "password"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="function")
def admin_user_token_headers(test_client, db_session):
    user = crud.create_user(db=db_session, user=schemas.UserCreate(email="admin@example.com", password="adminpassword"))
    admin_role = crud.get_role_by_name(db=db_session, name="admin")
    crud.assign_role_to_user(db=db_session, user=user, role=admin_role)
    response = test_client.post("/token", data={"username": "admin@example.com", "password": "adminpassword"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="function")
def sales_user_token_headers(test_client, db_session):
    user = crud.create_user(db=db_session, user=schemas.UserCreate(email="sales@example.com", password="salespassword"))
    sales_role = crud.get_role_by_name(db=db_session, name="sales")
    crud.assign_role_to_user(db=db_session, user=user, role=sales_role)
    response = test_client.post("/token", data={"username": "sales@example.com", "password": "salespassword"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="function")
def purchasing_user_token_headers(test_client, db_session):
    user = crud.create_user(db=db_session, user=schemas.UserCreate(email="purchasing@example.com", password="purchasingpassword"))
    purchasing_role = crud.get_role_by_name(db=db_session, name="purchasing")
    crud.assign_role_to_user(db=db_session, user=user, role=purchasing_role)
    response = test_client.post("/token", data={"username": "purchasing@example.com", "password": "purchasingpassword"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Data Fixtures ---
@pytest.fixture
def sample_product(test_client, admin_user_token_headers):
    product_data = {"sku": "STK-001", "name": "Stocked Product", "price": 25.0}
    response = test_client.post("/products/", json=product_data, headers=admin_user_token_headers)
    assert response.status_code == 200
    product = response.json()

    # Add stock for sales order tests
    response = test_client.post(f"/inventory/{product['id']}/adjust", json={"change": 100}, headers=admin_user_token_headers)
    assert response.status_code == 200

    # Return the product dictionary, not the detached DB object
    product['inventory'] = response.json()
    return product

@pytest.fixture
def sample_customer(test_client, sales_user_token_headers):
    customer_data = {"name": "Test Customer Inc.", "email": "contact@testcustomer.com"}
    response = test_client.post("/customers/", json=customer_data, headers=sales_user_token_headers)
    return response.json()

@pytest.fixture
def sample_supplier(test_client, purchasing_user_token_headers):
    supplier_data = {"name": "Test Supplier Co.", "email": "supplies@testsupplier.com"}
    response = test_client.post("/suppliers/", json=supplier_data, headers=purchasing_user_token_headers)
    return response.json()

# --- Tests ---

def test_full_sales_cycle(test_client, sales_user_token_headers, admin_user_token_headers, sample_customer, sample_product):
    # 1. Check initial inventory
    assert sample_product["inventory"]["quantity"] == 100

    # 2. Create sales order
    order_data = {"customer_id": sample_customer["id"], "items": [{"product_id": sample_product["id"], "quantity": 10}]}
    response = test_client.post("/orders/", json=order_data, headers=sales_user_token_headers)
    assert response.status_code == 200

    # 3. Check final inventory
    response = test_client.get(f"/inventory/", headers=admin_user_token_headers)
    inventory_item = next(item for item in response.json() if item["product_id"] == sample_product["id"])
    assert inventory_item["quantity"] == 90

def test_full_purchase_cycle(test_client, purchasing_user_token_headers, admin_user_token_headers, sample_supplier, sample_product):
    # 1. Check initial inventory
    assert sample_product["inventory"]["quantity"] == 100

    # 2. Create purchase order
    order_data = {"supplier_id": sample_supplier["id"], "items": [{"product_id": sample_product["id"], "quantity": 50, "price_per_unit": 20.0}]}
    response = test_client.post("/purchase-orders/", json=order_data, headers=purchasing_user_token_headers)
    assert response.status_code == 200
    order_id = response.json()["id"]

    # 3. Inventory is unchanged
    response = test_client.get(f"/inventory/", headers=admin_user_token_headers)
    inventory_item = next(item for item in response.json() if item["product_id"] == sample_product["id"])
    assert inventory_item["quantity"] == 100

    # 4. Receive the order
    response = test_client.post(f"/purchase-orders/{order_id}/receive", headers=purchasing_user_token_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "received"

    # 5. Check final inventory
    response = test_client.get(f"/inventory/", headers=admin_user_token_headers)
    final_inventory = next(item for item in response.json() if item["product_id"] == sample_product["id"])
    assert final_inventory["quantity"] == 150

def test_permission_denials(test_client, regular_user_token_headers, sales_user_token_headers, purchasing_user_token_headers, sample_customer, sample_supplier, sample_product):
    # Regular user cannot create sales order
    order_data = {"customer_id": sample_customer["id"], "items": [{"product_id": sample_product["id"], "quantity": 1}]}
    response = test_client.post("/orders/", json=order_data, headers=regular_user_token_headers)
    assert response.status_code == 403

    # Regular user cannot create purchase order
    po_data = {"supplier_id": sample_supplier["id"], "items": [{"product_id": sample_product["id"], "quantity": 1, "price_per_unit": 1}]}
    response = test_client.post("/purchase-orders/", json=po_data, headers=regular_user_token_headers)
    assert response.status_code == 403

    # Sales user cannot create purchase order
    response = test_client.post("/purchase-orders/", json=po_data, headers=sales_user_token_headers)
    assert response.status_code == 403

    # Purchasing user cannot create sales order
    response = test_client.post("/orders/", json=order_data, headers=purchasing_user_token_headers)
    assert response.status_code == 403
