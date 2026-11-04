from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .models import OrderStatus


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(default="默认分类", min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=4000)
    deposit_usdt: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=6)
    total_usdt: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=6)
    delivery_note: str = Field(default="次日人工交付", max_length=500)
    stock_quantity: int | None = Field(default=None, ge=0)
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    deposit_usdt: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    total_usdt: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    delivery_note: str | None = Field(default=None, max_length=500)
    stock_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductOut(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    reason: str | None = Field(default=None, max_length=500)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    public_id: str
    status: OrderStatus
    deposit_usdt: Decimal
    total_usdt: Decimal
    quantity: int = 1
    payment_status: str | None = None
    payment_amount_usdt: Decimal | None = None
    payment_network: str | None = None
    payment_tx_hash: str | None = None
    delivery_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    customer_telegram_user_id: int
    customer_username: str | None
    product_name: str
    campaign_code: str | None


class TxHashSubmission(BaseModel):
    tx_hash: str = Field(min_length=20, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class PaymentConfirmation(BaseModel):
    confirmed: bool
    note: str | None = Field(default=None, max_length=500)


class DeliveryRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    confirmed: bool


class CampaignCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=255)
    source_url: str | None = Field(default=None, max_length=1024)


class CampaignOut(CampaignCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: datetime

