from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional


class RoleBase(BaseModel):
    name: str


class RoleCreate(RoleBase):
    pass


class Role(RoleBase):
    id: int

    class Config:
        orm_mode = True


# --- Purchase Order Schemas ---

class PurchaseOrderItemBase(BaseModel):
    product_id: int
    quantity: int
    price_per_unit: float


class PurchaseOrderItemCreate(PurchaseOrderItemBase):
    pass


class PurchaseOrderItem(PurchaseOrderItemBase):
    id: int

    class Config:
        orm_mode = True


class PurchaseOrderBase(BaseModel):
    supplier_id: int


class PurchaseOrderCreate(PurchaseOrderBase):
    items: List[PurchaseOrderItemCreate]


class PurchaseOrder(PurchaseOrderBase):
    id: int
    status: str
    total_amount: float
    created_at: datetime
    items: List[PurchaseOrderItem] = []

    class Config:
        orm_mode = True


class SupplierBase(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class Supplier(SupplierBase):
    id: int

    class Config:
        orm_mode = True


class InventoryBase(BaseModel):
    quantity: int


class InventoryUpdate(BaseModel):
    change: int


class Inventory(InventoryBase):
    id: int
    product_id: int

    class Config:
        orm_mode = True


class ProductBase(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    price: float


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None


class Product(ProductBase):
    id: int
    inventory: Optional[Inventory] = None

    class Config:
        orm_mode = True


class CustomerBase(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class Customer(CustomerBase):
    id: int

    class Config:
        orm_mode = True


# --- Sales Order Schemas ---

class SalesOrderItemBase(BaseModel):
    product_id: int
    quantity: int


class SalesOrderItemCreate(SalesOrderItemBase):
    pass


class SalesOrderItem(SalesOrderItemBase):
    id: int
    price_per_unit: float

    class Config:
        orm_mode = True


class SalesOrderBase(BaseModel):
    customer_id: int


class SalesOrderCreate(SalesOrderBase):
    items: List[SalesOrderItemCreate]


class SalesOrder(SalesOrderBase):
    id: int
    status: str
    total_amount: float
    created_at: datetime
    items: List[SalesOrderItem] = []

    class Config:
        orm_mode = True


# --- Auth Schemas ---

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: str | None = None


class UserBase(BaseModel):
    email: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    is_active: bool
    roles: List[Role] = []

    class Config:
        orm_mode = True
