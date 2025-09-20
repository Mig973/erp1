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
def purchasing_user_token_headers(test_client, db_session):
    # Manually ensure purchasing role exists
    purchasing_role = crud.get_role_by_name(db=db_session, name="purchasing")
    if not purchasing_role:
        purchasing_role = crud.create_role(db=db_session, role=schemas.RoleCreate(name="purchasing"))

    # Create purchasing user
    user_schema = schemas.UserCreate(email="purchasing@example.com", password="purchasingpassword")
    user = crud.create_user(db=db_session, user=user_schema)
    crud.assign_role_to_user(db=db_session, user=user, role=purchasing_role)

    # Get token
    response = test_client.post(
        "/token", data={"username": "purchasing@example.com", "password": "purchasingpassword"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_user_token_headers(test_client, db_session):
    user_schema = schemas.UserCreate(email="admin@example.com", password="adminpassword")
    user = crud.create_user(db=db_session, user=user_schema)
    admin_role = crud.get_role_by_name(db=db_session, name="admin")
    crud.assign_role_to_user(db=db_session, user=user, role=admin_role)
    response = test_client.post(
        "/token", data={"username": "admin@example.com", "password": "adminpassword"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def sales_user_token_headers(test_client, db_session):
    user_schema = schemas.UserCreate(email="sales@example.com", password="salespassword")
    user = crud.create_user(db=db_session, user=user_schema)
    sales_role = crud.get_role_by_name(db=db_session, name="sales")
    crud.assign_role_to_user(db=db_session, user=user, role=sales_role)
    response = test_client.post(
        "/token", data={"username": "sales@example.com", "password": "salespassword"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Previous Module Tests (Condensed for brevity) ---

def test_create_user_and_login(regular_user_token_headers):
    assert regular_user_token_headers is not None

def test_admin_can_manage_roles(test_client, admin_user_token_headers):
    # Create a user to assign a role to
    test_client.post("/users/", json={"email": "roletest@example.com", "password": "password"})
    response = test_client.post(
        "/users/roletest@example.com/roles?role_name=admin",
        headers=admin_user_token_headers,
    )
    assert response.status_code == 200
    role_names = {role["name"] for role in response.json()["roles"]}
    assert "admin" in role_names

def test_product_and_inventory_flow(test_client, admin_user_token_headers, regular_user_token_headers):
    # Admin creates product
    product_data = {"sku": "FLOW-001", "name": "Flow Product", "price": 10.0}
    response = test_client.post("/products/", json=product_data, headers=admin_user_token_headers)
    assert response.status_code == 200
    product = response.json()
    assert product["inventory"]["quantity"] == 0

    # Regular user can read it
    response = test_client.get(f"/products/{product['id']}", headers=regular_user_token_headers)
    assert response.status_code == 200

    # Admin adjusts inventory
    response = test_client.post(f"/inventory/{product['id']}/adjust", json={"change": 100}, headers=admin_user_token_headers)
    assert response.status_code == 200
    assert response.json()["quantity"] == 100

    # Regular user cannot adjust inventory
    response = test_client.post(f"/inventory/{product['id']}/adjust", json={"change": 10}, headers=regular_user_token_headers)
    assert response.status_code == 403


# --- Customer Module Tests ---

@pytest.fixture
def sample_customer(test_client, sales_user_token_headers):
    customer_data = {
        "name": "Test Customer Inc.",
        "email": "contact@testcustomer.com",
        "phone": "555-1234",
        "address": "123 Test St, Testville",
    }
    response = test_client.post(
        "/customers/", json=customer_data, headers=sales_user_token_headers
    )
    assert response.status_code == 200
    return response.json()


def test_sales_user_can_create_customer(sample_customer):
    assert sample_customer["name"] == "Test Customer Inc."


def test_admin_user_can_create_customer(test_client, admin_user_token_headers):
    customer_data = {"name": "Admin Customer", "email": "contact@admincustomer.com"}
    response = test_client.post(
        "/customers/", json=customer_data, headers=admin_user_token_headers
    )
    assert response.status_code == 200


def test_regular_user_cannot_create_customer(test_client, regular_user_token_headers):
    customer_data = {"name": "Fail Customer", "email": "contact@failcustomer.com"}
    response = test_client.post(
        "/customers/", json=customer_data, headers=regular_user_token_headers
    )
    assert response.status_code == 403


def test_authenticated_user_can_read_customers(test_client, regular_user_token_headers, sample_customer):
    response = test_client.get("/customers/", headers=regular_user_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["email"] == sample_customer["email"]


def test_sales_user_can_update_customer(test_client, sales_user_token_headers, sample_customer):
    update_data = {"phone": "555-5678"}
    response = test_client.put(
        f"/customers/{sample_customer['id']}",
        json=update_data,
        headers=sales_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "555-5678"


def test_regular_user_cannot_update_customer(test_client, regular_user_token_headers, sample_customer):
    update_data = {"phone": "555-9999"}
    response = test_client.put(
        f"/customers/{sample_customer['id']}",
        json=update_data,
        headers=regular_user_token_headers,
    )
    assert response.status_code == 403


def test_sales_user_can_delete_customer(test_client, sales_user_token_headers, sample_customer):
    response = test_client.delete(
        f"/customers/{sample_customer['id']}", headers=sales_user_token_headers
    )
    assert response.status_code == 200

    # Verify it's gone
    verify_response = test_client.get(
        f"/customers/{sample_customer['id']}", headers=sales_user_token_headers
    )
    assert verify_response.status_code == 404


# --- Sales Order Module Tests ---

@pytest.fixture
def product_with_stock(test_client, admin_user_token_headers):
    # Create product
    product_data = {"sku": "STK-001", "name": "Stocked Product", "price": 25.0}
    response = test_client.post("/products/", json=product_data, headers=admin_user_token_headers)
    product = response.json()

    # Add stock
    response = test_client.post(f"/inventory/{product['id']}/adjust", json={"change": 100}, headers=admin_user_token_headers)
    assert response.status_code == 200
    assert response.json()["quantity"] == 100

    return product


def test_sales_user_can_create_order(test_client, sales_user_token_headers, admin_user_token_headers, sample_customer, product_with_stock):
    order_data = {
        "customer_id": sample_customer["id"],
        "items": [{"product_id": product_with_stock["id"], "quantity": 10}],
    }
    response = test_client.post("/orders/", json=order_data, headers=sales_user_token_headers)

    assert response.status_code == 200
    order = response.json()
    assert order["customer_id"] == sample_customer["id"]
    assert order["total_amount"] == 250.0  # 10 * 25.0
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 10

    # Verify inventory was reduced
    response = test_client.get(f"/inventory/", headers=admin_user_token_headers)
    inventory_item = next(item for item in response.json() if item["product_id"] == product_with_stock["id"])
    assert inventory_item["quantity"] == 90  # 100 - 10


def test_create_order_insufficient_stock(test_client, sales_user_token_headers, sample_customer, product_with_stock):
    order_data = {
        "customer_id": sample_customer["id"],
        "items": [{"product_id": product_with_stock["id"], "quantity": 200}], # We only have 100
    }
    response = test_client.post("/orders/", json=order_data, headers=sales_user_token_headers)
    assert response.status_code == 400
    assert "Not enough stock" in response.json()["detail"]


def test_regular_user_cannot_create_order(test_client, regular_user_token_headers, sample_customer, product_with_stock):
    order_data = {
        "customer_id": sample_customer["id"],
        "items": [{"product_id": product_with_stock["id"], "quantity": 5}],
    }
    response = test_client.post("/orders/", json=order_data, headers=regular_user_token_headers)
    assert response.status_code == 403


# --- Supplier Module Tests ---

@pytest.fixture
def sample_supplier(test_client, purchasing_user_token_headers):
    supplier_data = {
        "name": "Test Supplier Co.",
        "email": "sales@testsupplier.com",
        "phone": "111-222-3333",
    }
    response = test_client.post(
        "/suppliers/", json=supplier_data, headers=purchasing_user_token_headers
    )
    assert response.status_code == 200
    return response.json()


def test_purchasing_user_can_create_supplier(sample_supplier):
    assert sample_supplier["name"] == "Test Supplier Co."


def test_admin_user_can_create_supplier(test_client, admin_user_token_headers):
    supplier_data = {"name": "Admin Supplier", "email": "contact@adminsupplier.com"}
    response = test_client.post(
        "/suppliers/", json=supplier_data, headers=admin_user_token_headers
    )
    assert response.status_code == 200


def test_regular_user_cannot_create_supplier(test_client, regular_user_token_headers):
    supplier_data = {"name": "Fail Supplier", "email": "contact@failsupplier.com"}
    response = test_client.post(
        "/suppliers/", json=supplier_data, headers=regular_user_token_headers
    )
    assert response.status_code == 403


def test_authenticated_user_can_read_suppliers(test_client, regular_user_token_headers, sample_supplier):
    response = test_client.get("/suppliers/", headers=regular_user_token_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["email"] == sample_supplier["email"]


def test_purchasing_user_can_delete_supplier(test_client, purchasing_user_token_headers, sample_supplier):
    response = test_client.delete(
        f"/suppliers/{sample_supplier['id']}", headers=purchasing_user_token_headers
    )
    assert response.status_code == 200

    # Verify it's gone
    verify_response = test_client.get(
        f"/suppliers/{sample_supplier['id']}", headers=purchasing_user_token_headers
    )
    assert verify_response.status_code == 404


# --- Purchase Order Module Tests ---

@pytest.fixture
def product_for_purchase(test_client, admin_user_token_headers):
    product_data = {"sku": "PUR-001", "name": "Purchasable Product", "price": 50.0}
    response = test_client.post("/products/", json=product_data, headers=admin_user_token_headers)
    assert response.status_code == 200
    return response.json()

def test_purchasing_user_can_create_purchase_order(test_client, purchasing_user_token_headers, sample_supplier, product_for_purchase):
    order_data = {
        "supplier_id": sample_supplier["id"],
        "items": [{"product_id": product_for_purchase["id"], "quantity": 20, "price_per_unit": 45.0}],
    }
    response = test_client.post("/purchase-orders/", json=order_data, headers=purchasing_user_token_headers)

    assert response.status_code == 200
    order = response.json()
    assert order["supplier_id"] == sample_supplier["id"]
    assert order["total_amount"] == 900.0  # 20 * 45.0
    assert order["status"] == "pending"
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 20

    # Verify inventory has NOT changed yet
    response = test_client.get(f"/inventory/", headers=purchasing_user_token_headers)
    inventory_item = next(item for item in response.json() if item["product_id"] == product_for_purchase["id"])
    assert inventory_item["quantity"] == 0


def test_receiving_purchase_order_increases_inventory(test_client, purchasing_user_token_headers, sample_supplier, product_for_purchase):
    # 1. Create a purchase order
    order_data = {
        "supplier_id": sample_supplier["id"],
        "items": [{"product_id": product_for_purchase["id"], "quantity": 75, "price_per_unit": 45.0}],
    }
    response = test_client.post("/purchase-orders/", json=order_data, headers=purchasing_user_token_headers)
    assert response.status_code == 200
    order_id = response.json()["id"]

    # 2. Receive the order
    response = test_client.post(f"/purchase-orders/{order_id}/receive", headers=purchasing_user_token_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "received"

    # 3. Verify inventory has increased
    response = test_client.get(f"/inventory/", headers=purchasing_user_token_headers)
    inventory_item = next(item for item in response.json() if item["product_id"] == product_for_purchase["id"])
    assert inventory_item["quantity"] == 75


def test_regular_user_cannot_create_purchase_order(test_client, regular_user_token_headers, sample_supplier, product_for_purchase):
    order_data = {
        "supplier_id": sample_supplier["id"],
        "items": [{"product_id": product_for_purchase["id"], "quantity": 10, "price_per_unit": 50.0}],
    }
    response = test_client.post("/purchase-orders/", json=order_data, headers=regular_user_token_headers)
    assert response.status_code == 403
