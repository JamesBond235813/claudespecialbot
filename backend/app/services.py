import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .catalog import SETTING_DEFAULTS, format_usdt
from .config import get_settings
from .models import (
    AppSetting,
    Campaign,
    Category,
    Customer,
    Order,
    OrderStatus,
    OrderStatusHistory,
    Payment,
    PaymentStatus,
    Product,
)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def calculate_delivery_at(now: datetime | None = None) -> datetime:
    settings = get_settings()
    business_tz = ZoneInfo(settings.business_timezone)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(business_tz)
    local_delivery = datetime.combine(
        local_now.date() + timedelta(days=1),
        time(hour=settings.delivery_hour),
        tzinfo=business_tz,
    )
    return local_delivery.astimezone(timezone.utc).replace(tzinfo=None)


def business_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    settings = get_settings()
    business_tz = ZoneInfo(settings.business_timezone)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(business_tz)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=business_tz)
    end_local = start_local + timedelta(days=1)
    start = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start, end


def select_display_payment(payments) -> Payment | None:
    if not payments:
        return None
    pending = [
        payment
        for payment in payments
        if payment.status == PaymentStatus.PENDING and payment.tx_hash
    ]
    pool = pending or list(payments)
    return max(pool, key=lambda payment: payment.id)


def decimal_amount(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


async def upsert_customer(session: AsyncSession, telegram_user) -> Customer:
    customer = await session.scalar(
        select(Customer).where(Customer.telegram_user_id == telegram_user.id)
    )
    if customer is None:
        customer = Customer(telegram_user_id=telegram_user.id)
        session.add(customer)
    customer.username = telegram_user.username
    customer.first_name = telegram_user.first_name
    customer.language_code = telegram_user.language_code
    await session.flush()
    return customer


async def resolve_campaign(session: AsyncSession, code: str | None) -> Campaign | None:
    if not code:
        return None
    campaign = await session.scalar(select(Campaign).where(Campaign.code == code))
    if campaign is None:
        campaign = Campaign(code=code, name=f"自动归因：{code}", is_active=True)
        session.add(campaign)
        await session.flush()
    return campaign


async def create_order(
    session: AsyncSession,
    *,
    customer: Customer,
    product: Product,
    campaign: Campaign | None,
    actor: str,
    quantity: int = 1,
) -> tuple[Order, Payment | None]:
    if quantity < 1 or quantity > 100:
        raise ValueError("数量必须在 1 到 100 之间")
    reserved = await session.execute(
        update(Product)
        .where(
            Product.id == product.id,
            (Product.stock_quantity.is_(None)) | (Product.stock_quantity >= quantity),
        )
        .values(
            stock_quantity=case(
                (Product.stock_quantity.is_(None), None),
                else_=Product.stock_quantity - quantity,
            )
        )
    )
    if reserved.rowcount != 1:
        raise ValueError("商品库存不足")
    await session.refresh(product)
    initial_status = (
        OrderStatus.RESERVED if product.deposit_usdt == 0 else OrderStatus.DEPOSIT_PENDING
    )
    order = Order(
        customer_id=customer.id,
        product_id=product.id,
        campaign_id=campaign.id if campaign else None,
        status=initial_status,
        deposit_stars=product.deposit_stars,
        total_stars=product.total_stars,
        deposit_usdt=product.deposit_usdt * quantity,
        total_usdt=product.total_usdt * quantity,
        quantity=quantity,
        delivery_at=calculate_delivery_at(),
        terms_version=get_settings().terms_version,
        terms_accepted_at=utc_now_naive(),
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=None,
            to_status=initial_status.value,
            actor=actor,
            reason="客户确认条款并创建订单",
        )
    )

    payment = None
    if product.deposit_usdt > 0:
        payment = Payment(
            order_id=order.id,
            stage="deposit",
            amount=product.deposit_usdt * quantity,
            currency="USDT",
            network=get_settings().usdt_network or None,
            status=PaymentStatus.PENDING,
            invoice_payload=f"usdt-deposit:{order.public_id}:{uuid.uuid4().hex}",
        )
        session.add(payment)
        await session.flush()

    await session.commit()
    await session.refresh(order)
    return order, payment


async def submit_payment_tx_hash(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    order_public_id: str,
    tx_hash: str,
) -> tuple[Order, Payment] | None:
    result = await session.execute(
        select(Order, Payment)
        .join(Customer, Customer.id == Order.customer_id)
        .join(Payment, Payment.order_id == Order.id)
        .where(
            Customer.telegram_user_id == telegram_user_id,
            Order.public_id == order_public_id,
            Payment.status == PaymentStatus.PENDING,
        )
    )
    row = result.first()
    if row is None:
        return None
    order, payment = row
    duplicate = await session.scalar(
        select(Payment.id).where(Payment.tx_hash == tx_hash, Payment.id != payment.id)
    )
    if duplicate is not None:
        return None
    payment.tx_hash = tx_hash
    await session.commit()
    return order, payment


async def create_balance_payment(session: AsyncSession, order: Order) -> Payment | None:
    remaining = order.total_usdt - order.deposit_usdt
    if remaining <= 0:
        return None
    pending = await session.scalar(
        select(Payment).where(
            Payment.order_id == order.id,
            Payment.stage == "balance",
            Payment.status == PaymentStatus.PENDING,
        )
    )
    if pending:
        return pending
    payment = Payment(
        order_id=order.id,
        stage="balance",
        amount=remaining,
        currency="USDT",
        network=get_settings().usdt_network or None,
        status=PaymentStatus.PENDING,
        invoice_payload=f"usdt-balance:{order.public_id}:{uuid.uuid4().hex}",
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def confirm_usdt_payment(
    session: AsyncSession,
    *,
    payment_id: int,
    actor: str,
    note: str | None = None,
) -> Order | None:
    payment = await session.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .options(selectinload(Payment.order))
    )
    if payment is None or payment.currency != "USDT" or not payment.tx_hash:
        return None
    if payment.status == PaymentStatus.SUCCEEDED:
        return payment.order
    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = utc_now_naive()
    order = payment.order
    old_status = order.status
    order.status = (
        OrderStatus.DELIVERING if payment.stage == "balance" else OrderStatus.DEPOSIT_PAID
    )
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=old_status.value,
            to_status=order.status.value,
            actor=actor,
            reason=note or f"人工确认 USDT {payment.stage} 到账，交易哈希 {payment.tx_hash}",
        )
    )
    await session.commit()
    return order


async def mark_payment_succeeded(
    session: AsyncSession,
    *,
    invoice_payload: str,
    telegram_charge_id: str,
    provider_charge_id: str | None,
    amount: int,
    currency: str,
) -> Order | None:
    payment = await session.scalar(
        select(Payment)
        .where(Payment.invoice_payload == invoice_payload)
        .options(selectinload(Payment.order))
    )
    if payment is None:
        return None
    if payment.status == PaymentStatus.SUCCEEDED:
        return payment.order
    if payment.amount != amount or payment.currency != currency:
        return None

    payment.status = PaymentStatus.SUCCEEDED
    payment.telegram_charge_id = telegram_charge_id
    payment.provider_charge_id = provider_charge_id
    payment.paid_at = utc_now_naive()
    order = payment.order
    old_status = order.status
    order.status = OrderStatus.DEPOSIT_PAID
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=old_status.value,
            to_status=order.status.value,
            actor="telegram-payment",
            reason="Telegram Stars 支付成功",
        )
    )
    await session.commit()
    return order


async def update_order_status(
    session: AsyncSession,
    *,
    order: Order,
    new_status: OrderStatus,
    actor: str,
    reason: str | None,
) -> Order:
    old_status = order.status
    if old_status == new_status:
        return order
    order.status = new_status
    if new_status in (OrderStatus.CANCELLED, OrderStatus.EXPIRED) and old_status not in (
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    ):
        product = await session.get(Product, order.product_id)
        if product is not None and product.stock_quantity is not None:
            product.stock_quantity += order.quantity
    if new_status == OrderStatus.COMPLETED:
        order.delivered_at = utc_now_naive()
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=old_status.value,
            to_status=new_status.value,
            actor=actor,
            reason=reason,
        )
    )
    await session.commit()
    await session.refresh(order)
    return order


async def get_store_settings(session: AsyncSession) -> dict[str, str]:
    stored = dict(SETTING_DEFAULTS)
    rows = (await session.scalars(select(AppSetting))).all()
    for row in rows:
        if row.key in stored:
            stored[row.key] = row.value
    return stored


async def save_store_settings(session: AsyncSession, values: dict[str, str]) -> dict[str, str]:
    for key, value in values.items():
        if key not in SETTING_DEFAULTS:
            continue
        row = await session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    await session.commit()
    return await get_store_settings(session)


async def ensure_category(session: AsyncSession, name: str) -> Category:
    cleaned = name.strip()
    category = await session.scalar(select(Category).where(Category.name == cleaned))
    if category is None:
        category = Category(name=cleaned, is_visible=True, sort_order=0)
        session.add(category)
        await session.flush()
    return category


async def dashboard_stats(session: AsyncSession) -> dict[str, int | str]:
    total_orders = await session.scalar(select(func.count(Order.id))) or 0
    pending_orders = await session.scalar(
        select(func.count(Order.id)).where(
            Order.status.in_(
                [
                    OrderStatus.RESERVED,
                    OrderStatus.DEPOSIT_PAID,
                    OrderStatus.PREPARING,
                    OrderStatus.READY,
                    OrderStatus.DELIVERING,
                ]
            )
        )
    ) or 0
    completed_orders = await session.scalar(
        select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)
    ) or 0
    active_products = await session.scalar(
        select(func.count(Product.id)).where(Product.is_active.is_(True))
    ) or 0
    customer_count = await session.scalar(select(func.count(Customer.id))) or 0
    start, end = business_day_bounds()
    today_orders = await session.scalar(
        select(func.count(Order.id)).where(Order.created_at >= start, Order.created_at < end)
    ) or 0
    pending_payment_count = await session.scalar(
        select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.PENDING,
            Payment.tx_hash.is_not(None),
        )
    ) or 0
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.SUCCEEDED
        )
    )
    pending_amount = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.PENDING,
            Payment.tx_hash.is_not(None),
        )
    )
    return {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "completed_orders": completed_orders,
        "active_products": active_products,
        "customer_count": customer_count,
        "today_orders": today_orders,
        "pending_payment_count": pending_payment_count,
        "revenue_usdt": format_usdt(decimal_amount(revenue)),
        "pending_payment_amount": format_usdt(decimal_amount(pending_amount)),
    }


async def dashboard_counts(session: AsyncSession) -> dict[str, int | str]:
    return await dashboard_stats(session)

