from pydantic import BaseModel
from typing import Optional

class Item(BaseModel):
    id: Optional[int]
    name: Optional[str]
    price: Optional[float]
    stock: Optional[int]

class Customer(BaseModel):
    id: Optional[int]
    name: Optional[str]
    phone: Optional[str]
