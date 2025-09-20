from sqlalchemy.orm import Session

from . import models, schemas
from .security import get_password_hash


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)

    # Assign a default role
    default_role = get_role_by_name(db, name="user")
    if not default_role:
        default_role = create_role(db, role=schemas.RoleCreate(name="user"))

    db_user.roles.append(default_role)

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_role_by_name(db: Session, name: str):
    return db.query(models.Role).filter(models.Role.name == name).first()


def create_role(db: Session, role: schemas.RoleCreate):
    db_role = models.Role(name=role.name)
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role


def assign_role_to_user(db: Session, user: models.User, role: models.Role):
    user.roles.append(role)
    db.commit()
    db.refresh(user)
    return user


# --- Product CRUD ---

def get_product(db: Session, product_id: int):
    return db.query(models.Product).filter(models.Product.id == product_id).first()


def get_product_by_sku(db: Session, sku: str):
    return db.query(models.Product).filter(models.Product.sku == sku).first()


def list_products(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Product).offset(skip).limit(limit).all()


def create_product(db: Session, product: schemas.ProductCreate):
    db_product = models.Product(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    # Create inventory record for the new product
    db_inventory = models.Inventory(product_id=db_product.id, quantity=0)
    db.add(db_inventory)
    db.commit()
    db.refresh(db_inventory)

    return db_product


def update_product(db: Session, db_product: models.Product, product_in: schemas.ProductUpdate):
    product_data = product_in.dict(exclude_unset=True)
    for key, value in product_data.items():
        setattr(db_product, key, value)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def delete_product(db: Session, product_id: int):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product


# --- Inventory CRUD ---

def list_inventory(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Inventory).offset(skip).limit(limit).all()


def adjust_inventory(db: Session, product_id: int, change: int):
    inventory_item = (
        db.query(models.Inventory)
        .filter(models.Inventory.product_id == product_id)
        .first()
    )
    if inventory_item:
        inventory_item.quantity += change
        db.commit()
        db.refresh(inventory_item)
    return inventory_item


# --- Customer CRUD ---

def get_customer(db: Session, customer_id: int):
    return db.query(models.Customer).filter(models.Customer.id == customer_id).first()


def get_customer_by_email(db: Session, email: str):
    return db.query(models.Customer).filter(models.Customer.email == email).first()


def list_customers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Customer).offset(skip).limit(limit).all()


def create_customer(db: Session, customer: schemas.CustomerCreate):
    db_customer = models.Customer(**customer.dict())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


def update_customer(
    db: Session, db_customer: models.Customer, customer_in: schemas.CustomerUpdate
):
    customer_data = customer_in.dict(exclude_unset=True)
    for key, value in customer_data.items():
        setattr(db_customer, key, value)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


def delete_customer(db: Session, customer_id: int):
    db_customer = (
        db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    )
    if db_customer:
        db.delete(db_customer)
        db.commit()
    return db_customer


# --- Sales Order CRUD ---

def get_sales_order(db: Session, order_id: int):
    return (
        db.query(models.SalesOrder).filter(models.SalesOrder.id == order_id).first()
    )


def list_sales_orders(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.SalesOrder).offset(skip).limit(limit).all()


def create_sales_order(db: Session, order: schemas.SalesOrderCreate):
    # 1. Verify customer exists
    db_customer = get_customer(db, customer_id=order.customer_id)
    if not db_customer:
        return None  # Or raise exception

    total_amount = 0
    order_items_data = []

    # 2. Verify products and calculate total amount
    for item in order.items:
        db_product = get_product(db, product_id=item.product_id)
        if not db_product:
            raise ValueError(f"Product with id {item.product_id} not found")

        # Check for sufficient inventory
        if db_product.inventory.quantity < item.quantity:
            raise ValueError(f"Not enough stock for product {db_product.name}")

        item_total = db_product.price * item.quantity
        total_amount += item_total
        order_items_data.append(
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price_per_unit": db_product.price,
            }
        )

    # 3. Create the SalesOrder and SalesOrderItems
    db_order = models.SalesOrder(
        customer_id=order.customer_id, total_amount=total_amount
    )
    db.add(db_order)
    db.flush()  # Use flush to get the db_order.id before commit

    for item_data in order_items_data:
        db_item = models.SalesOrderItem(order_id=db_order.id, **item_data)
        db.add(db_item)
        # 4. Adjust inventory
        adjust_inventory(db, product_id=item_data["product_id"], change=-item_data["quantity"])

    db.commit()
    db.refresh(db_order)
    return db_order


# --- Supplier CRUD ---

def get_supplier(db: Session, supplier_id: int):
    return db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()


def get_supplier_by_email(db: Session, email: str):
    return db.query(models.Supplier).filter(models.Supplier.email == email).first()


def list_suppliers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Supplier).offset(skip).limit(limit).all()


def create_supplier(db: Session, supplier: schemas.SupplierCreate):
    db_supplier = models.Supplier(**supplier.dict())
    db.add(db_supplier)
    db.commit()
    db.refresh(db_supplier)
    return db_supplier


def update_supplier(
    db: Session, db_supplier: models.Supplier, supplier_in: schemas.SupplierUpdate
):
    supplier_data = supplier_in.dict(exclude_unset=True)
    for key, value in supplier_data.items():
        setattr(db_supplier, key, value)
    db.add(db_supplier)
    db.commit()
    db.refresh(db_supplier)
    return db_supplier


def delete_supplier(db: Session, supplier_id: int):
    db_supplier = (
        db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    )
    if db_supplier:
        db.delete(db_supplier)
        db.commit()
    return db_supplier


# --- Purchase Order CRUD ---

def get_purchase_order(db: Session, order_id: int):
    return (
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.id == order_id)
        .first()
    )


def list_purchase_orders(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.PurchaseOrder).offset(skip).limit(limit).all()


def create_purchase_order(db: Session, order: schemas.PurchaseOrderCreate):
    # 1. Verify supplier exists
    db_supplier = get_supplier(db, supplier_id=order.supplier_id)
    if not db_supplier:
        raise ValueError(f"Supplier with id {order.supplier_id} not found")

    total_amount = 0
    order_items_data = []

    # 2. Verify products and calculate total amount
    for item in order.items:
        db_product = get_product(db, product_id=item.product_id)
        if not db_product:
            raise ValueError(f"Product with id {item.product_id} not found")

        item_total = item.price_per_unit * item.quantity
        total_amount += item_total
        order_items_data.append(
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price_per_unit": item.price_per_unit,
            }
        )

    # 3. Create the PurchaseOrder and PurchaseOrderItems
    db_order = models.PurchaseOrder(
        supplier_id=order.supplier_id, total_amount=total_amount
    )
    db.add(db_order)
    db.flush()

    for item_data in order_items_data:
        db_item = models.PurchaseOrderItem(order_id=db_order.id, **item_data)
        db.add(db_item)

    db.commit()
    db.refresh(db_order)
    return db_order


def receive_purchase_order(db: Session, order_id: int):
    db_order = get_purchase_order(db, order_id=order_id)
    if not db_order or db_order.status == "received":
        return None

    for item in db_order.items:
        adjust_inventory(db, product_id=item.product_id, change=item.quantity)

    db_order.status = "received"
    db.commit()
    db.refresh(db_order)
    return db_order
