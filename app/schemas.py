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


class InventoryBase(BaseModel):
    quantity: int


class InventoryUpdate(BaseModel):
    change: int


class Inventory(InventoryBase):
    id: int
    product_id: int

    class Config:
        orm_mode = True


class Product(ProductBase):
    id: int
    inventory: Optional[Inventory] = None

    class Config:
        orm_mode = True


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
