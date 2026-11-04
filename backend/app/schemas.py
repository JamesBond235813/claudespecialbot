from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import OrderStatus, PaymentStatus


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(default="默认分类", min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=4000)
    deposit_usdt: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=6)
    total_usdt: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=6)
    delivery_note: str = Field(default="次日人工交付", max_length=500)
    stock_quantity: int | None = Field(default=None, ge=0)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000)

    @field_validator("name", "category", "description", "delivery_note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    deposit_usdt: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    total_usdt: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    delivery_note: str | None = Field(default=None, max_length=500)
    stock_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)

    @field_validator("name", "category", "description", "delivery_note")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned


class ProductOut(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_visible: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_visible: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned


class CategoryOut(BaseModel):
    id: int
    name: str
    is_visible: bool
    sort_order: int
    product_count: int
    created_at: datetime
    updated_at: datetime


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    reason: str | None = Field(default=None, max_length=500)


class OrderNotesUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class PaymentOut(BaseModel):
    id: int
    stage: str
    amount: Decimal
    currency: str
    network: str | None
    tx_hash: str | None
    status: PaymentStatus
    paid_at: datetime | None
    created_at: datetime


class StatusHistoryOut(BaseModel):
    id: int
    from_status: str | None
    to_status: str
    actor: str
    reason: str | None
    created_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    public_id: str
    status: OrderStatus
    deposit_usdt: Decimal
    total_usdt: Decimal
    quantity: int = 1
    payment_status: str | None = None
    payment_stage: str | None = None
    payment_amount_usdt: Decimal | None = None
    payment_network: str | None = None
    payment_tx_hash: str | None = None
    payment_id: int | None = None
    delivery_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    customer_telegram_user_id: int
    customer_username: str | None
    customer_first_name: str | None = None
    product_id: int
    product_name: str
    campaign_code: str | None
    notes: str | None = None


class OrderDetail(OrderOut):
    terms_version: str
    terms_accepted_at: datetime
    history: list[StatusHistoryOut]
    payments: list[PaymentOut]


class TxHashSubmission(BaseModel):
    tx_hash: str = Field(min_length=20, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class PaymentConfirmation(BaseModel):
    confirmed: bool
    note: str | None = Field(default=None, max_length=500)


class PaymentRejection(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned


class DeliveryRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    confirmed: bool


class CampaignCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=255)
    source_url: str | None = Field(default=None, max_length=1024)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned

    @field_validator("source_url")
    @classmethod
    def strip_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source_url: str | None = Field(default=None, max_length=1024)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("不能为空")
        return cleaned

    @field_validator("source_url")
    @classmethod
    def strip_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CampaignOut(BaseModel):
    id: int
    code: str
    name: str
    source_url: str | None
    is_active: bool
    created_at: datetime
    order_count: int
    revenue_usdt: Decimal


class CustomerUpdate(BaseModel):
    is_blocked: bool


class CustomerOut(BaseModel):
    id: int
    telegram_user_id: int
    username: str | None
    first_name: str | None
    language_code: str | None
    is_blocked: bool
    created_at: datetime
    order_count: int
    spent_usdt: Decimal


class StoreSettings(BaseModel):
    show_categories: bool = True
    welcome_text: str = Field(default="", max_length=2000)
    store_prompt: str = Field(default="请选择需要预约的数字服务：", max_length=500)
    product_prompt: str = Field(default="请选择商品：", max_length=500)
    terms_text: str = Field(default="", max_length=4000)

    @field_validator("welcome_text", "terms_text", "store_prompt", "product_prompt")
    @classmethod
    def strip_copy(cls, value: str) -> str:
        return value.strip()

    @field_validator("store_prompt", "product_prompt")
    @classmethod
    def require_prompt(cls, value: str) -> str:
        if not value:
            raise ValueError("不能为空")
        return value


class StoreSettingsOut(StoreSettings):
    terms_version: str
    terms_default: str
    support_handle: str
    usdt_network: str
    usdt_receiving_address: str
    usdt_configured: bool
    bot_username: str


class DashboardOut(BaseModel):
    total_orders: int
    pending_orders: int
    completed_orders: int
    active_products: int
    customer_count: int
    today_orders: int
    pending_payment_count: int
    revenue_usdt: str
    pending_payment_amount: str
