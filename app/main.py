from datetime import timedelta
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import crud, models, schemas, security
from .database import SessionLocal, engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)


@app.post("/token", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# Instantiate the role checker for admin-only endpoints
# In a real app, the "admin" role would be created via a migration or a seed script.
# For simplicity, we ensure it exists when the app starts.
@app.on_event("startup")
def startup_event():
    with SessionLocal() as db:
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

admin_role_checker = security.RoleChecker(["admin"])
sales_role_checker = security.RoleChecker(["admin", "sales"])
purchasing_role_checker = security.RoleChecker(["admin", "purchasing"])


@app.get("/users/me", response_model=schemas.User)
async def read_users_me(
    current_user: models.User = Depends(security.get_current_active_user),
):
    return current_user


@app.post("/roles/", response_model=schemas.Role, dependencies=[Depends(admin_role_checker)])
def create_role(role: schemas.RoleCreate, db: Session = Depends(get_db)):
    db_role = crud.get_role_by_name(db, name=role.name)
    if db_role:
        raise HTTPException(status_code=400, detail="Role already exists")
    return crud.create_role(db=db, role=role)


@app.post("/users/{user_email}/roles", response_model=schemas.User, dependencies=[Depends(admin_role_checker)])
def assign_role_to_user(
    user_email: str, role_name: str, db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, email=user_email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = crud.get_role_by_name(db, name=role_name)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check if user already has the role
    if role in user.roles:
        raise HTTPException(status_code=400, detail="User already has this role")

    return crud.assign_role_to_user(db=db, user=user, role=role)


# --- Product Endpoints ---

@app.post(
    "/products/",
    response_model=schemas.Product,
    dependencies=[Depends(admin_role_checker)],
)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    db_product = crud.get_product_by_sku(db, sku=product.sku)
    if db_product:
        raise HTTPException(status_code=400, detail="SKU already registered")
    return crud.create_product(db=db, product=product)


@app.get(
    "/products/",
    response_model=List[schemas.Product],
    dependencies=[Depends(security.get_current_active_user)],
)
def read_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products = crud.list_products(db, skip=skip, limit=limit)
    return products


@app.get(
    "/products/{product_id}",
    response_model=schemas.Product,
    dependencies=[Depends(security.get_current_active_user)],
)
def read_product(product_id: int, db: Session = Depends(get_db)):
    db_product = crud.get_product(db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product


@app.put(
    "/products/{product_id}",
    response_model=schemas.Product,
    dependencies=[Depends(admin_role_checker)],
)
def update_product(
    product_id: int, product_in: schemas.ProductUpdate, db: Session = Depends(get_db)
):
    db_product = crud.get_product(db, product_id=product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    # Check for SKU uniqueness if it's being changed
    if product_in.sku and product_in.sku != db_product.sku:
        existing_product = crud.get_product_by_sku(db, sku=product_in.sku)
        if existing_product:
            raise HTTPException(status_code=400, detail="New SKU already registered")
    updated_product = crud.update_product(
        db=db, db_product=db_product, product_in=product_in
    )
    return updated_product


@app.delete(
    "/products/{product_id}",
    response_model=schemas.Product,
    dependencies=[Depends(admin_role_checker)],
)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    db_product = crud.delete_product(db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product


# --- Inventory Endpoints ---

@app.get(
    "/inventory/",
    response_model=List[schemas.Inventory],
    dependencies=[Depends(security.get_current_active_user)],
)
def read_inventory(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    inventory_list = crud.list_inventory(db, skip=skip, limit=limit)
    return inventory_list


@app.post(
    "/inventory/{product_id}/adjust",
    response_model=schemas.Inventory,
    dependencies=[Depends(admin_role_checker)],
)
def adjust_product_inventory(
    product_id: int,
    adjustment: schemas.InventoryUpdate,
    db: Session = Depends(get_db),
):
    db_product = crud.get_product(db, product_id=product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    updated_inventory = crud.adjust_inventory(
        db=db, product_id=product_id, change=adjustment.change
    )
    if not updated_inventory:
        # This case should ideally not be hit if a product exists
        raise HTTPException(status_code=404, detail="Inventory for product not found")
    return updated_inventory


# --- Customer Endpoints ---

@app.post(
    "/customers/",
    response_model=schemas.Customer,
    dependencies=[Depends(sales_role_checker)],
)
def create_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = crud.get_customer_by_email(db, email=customer.email)
    if db_customer:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_customer(db=db, customer=customer)


@app.get(
    "/customers/",
    response_model=List[schemas.Customer],
    dependencies=[Depends(security.get_current_active_user)],
)
def read_customers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    customers = crud.list_customers(db, skip=skip, limit=limit)
    return customers


@app.get(
    "/customers/{customer_id}",
    response_model=schemas.Customer,
    dependencies=[Depends(security.get_current_active_user)],
)
def read_customer(customer_id: int, db: Session = Depends(get_db)):
    db_customer = crud.get_customer(db, customer_id=customer_id)
    if db_customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return db_customer


@app.put(
    "/customers/{customer_id}",
    response_model=schemas.Customer,
    dependencies=[Depends(sales_role_checker)],
)
def update_customer(
    customer_id: int, customer_in: schemas.CustomerUpdate, db: Session = Depends(get_db)
):
    db_customer = crud.get_customer(db, customer_id=customer_id)
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer_in.email and customer_in.email != db_customer.email:
        existing_customer = crud.get_customer_by_email(db, email=customer_in.email)
        if existing_customer:
            raise HTTPException(status_code=400, detail="New email already registered")
    updated_customer = crud.update_customer(
        db=db, db_customer=db_customer, customer_in=customer_in
    )
    return updated_customer


@app.delete(
    "/customers/{customer_id}",
    response_model=schemas.Customer,
    dependencies=[Depends(sales_role_checker)],
)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    db_customer = crud.delete_customer(db, customer_id=customer_id)
    if db_customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return db_customer


# --- Sales Order Endpoints ---

@app.post(
    "/orders/",
    response_model=schemas.SalesOrder,
    dependencies=[Depends(sales_role_checker)],
)
def create_sales_order(
    order: schemas.SalesOrderCreate, db: Session = Depends(get_db)
):
    try:
        db_order = crud.create_sales_order(db=db, order=order)
        if not db_order:
            raise HTTPException(status_code=404, detail="Customer not found")
        return db_order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/orders/",
    response_model=List[schemas.SalesOrder],
    dependencies=[Depends(sales_role_checker)],
)
def read_sales_orders(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    orders = crud.list_sales_orders(db, skip=skip, limit=limit)
    return orders


@app.get(
    "/orders/{order_id}",
    response_model=schemas.SalesOrder,
    dependencies=[Depends(sales_role_checker)],
)
def read_sales_order(order_id: int, db: Session = Depends(get_db)):
    db_order = crud.get_sales_order(db, order_id=order_id)
    if db_order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return db_order


# --- Supplier Endpoints ---

@app.post(
    "/suppliers/",
    response_model=schemas.Supplier,
    dependencies=[Depends(purchasing_role_checker)],
)
def create_supplier(supplier: schemas.SupplierCreate, db: Session = Depends(get_db)):
    db_supplier = crud.get_supplier_by_email(db, email=supplier.email)
    if db_supplier:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_supplier(db=db, supplier=supplier)


@app.get(
    "/suppliers/",
    response_model=List[schemas.Supplier],
    dependencies=[Depends(security.get_current_active_user)],
)
def read_suppliers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    suppliers = crud.list_suppliers(db, skip=skip, limit=limit)
    return suppliers


@app.get(
    "/suppliers/{supplier_id}",
    response_model=schemas.Supplier,
    dependencies=[Depends(security.get_current_active_user)],
)
def read_supplier(supplier_id: int, db: Session = Depends(get_db)):
    db_supplier = crud.get_supplier(db, supplier_id=supplier_id)
    if db_supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return db_supplier


@app.put(
    "/suppliers/{supplier_id}",
    response_model=schemas.Supplier,
    dependencies=[Depends(purchasing_role_checker)],
)
def update_supplier(
    supplier_id: int, supplier_in: schemas.SupplierUpdate, db: Session = Depends(get_db)
):
    db_supplier = crud.get_supplier(db, supplier_id=supplier_id)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if supplier_in.email and supplier_in.email != db_supplier.email:
        existing_supplier = crud.get_supplier_by_email(db, email=supplier_in.email)
        if existing_supplier:
            raise HTTPException(status_code=400, detail="New email already registered")
    updated_supplier = crud.update_supplier(
        db=db, db_supplier=db_supplier, supplier_in=supplier_in
    )
    return updated_supplier


@app.delete(
    "/suppliers/{supplier_id}",
    response_model=schemas.Supplier,
    dependencies=[Depends(purchasing_role_checker)],
)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    db_supplier = crud.delete_supplier(db, supplier_id=supplier_id)
    if db_supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return db_supplier


# --- Purchase Order Endpoints ---

@app.post(
    "/purchase-orders/",
    response_model=schemas.PurchaseOrder,
    dependencies=[Depends(purchasing_role_checker)],
)
def create_purchase_order(
    order: schemas.PurchaseOrderCreate, db: Session = Depends(get_db)
):
    try:
        db_order = crud.create_purchase_order(db=db, order=order)
        return db_order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(
    "/purchase-orders/",
    response_model=List[schemas.PurchaseOrder],
    dependencies=[Depends(purchasing_role_checker)],
)
def read_purchase_orders(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    orders = crud.list_purchase_orders(db, skip=skip, limit=limit)
    return orders


@app.get(
    "/purchase-orders/{order_id}",
    response_model=schemas.PurchaseOrder,
    dependencies=[Depends(purchasing_role_checker)],
)
def read_purchase_order(order_id: int, db: Session = Depends(get_db)):
    db_order = crud.get_purchase_order(db, order_id=order_id)
    if db_order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return db_order


@app.post(
    "/purchase-orders/{order_id}/receive",
    response_model=schemas.PurchaseOrder,
    dependencies=[Depends(purchasing_role_checker)],
)
def receive_purchase_order(order_id: int, db: Session = Depends(get_db)):
    db_order = crud.receive_purchase_order(db, order_id=order_id)
    if db_order is None:
        raise HTTPException(
            status_code=404, detail="Order not found or already received"
        )
    return db_order
