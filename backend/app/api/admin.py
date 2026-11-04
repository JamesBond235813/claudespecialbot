import contextlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..config import get_settings
from ..models import Campaign, Order, OrderStatus, Payment, PaymentStatus, Product
from ..schemas import (
    CampaignCreate,
    CampaignOut,
    DeliveryRequest,
    OrderOut,
    OrderStatusUpdate,
    PaymentConfirmation,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from ..security import require_admin_key
from ..services import (
    confirm_usdt_payment,
    create_balance_payment,
    dashboard_counts,
    format_usdt,
    update_order_status,
)


router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_key)])


@router.get("/payment-config")
async def payment_config() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "configured": bool(settings.usdt_network and settings.usdt_receiving_address),
        "network": settings.usdt_network,
        "receiving_address": settings.usdt_receiving_address,
    }


def serialize_order(order: Order) -> OrderOut:
    payment = order.payments[0] if order.payments else None
    return OrderOut(
        id=order.id,
        public_id=order.public_id,
        status=order.status,
        deposit_usdt=order.deposit_usdt,
        total_usdt=order.total_usdt,
        payment_status=payment.status.value if payment else None,
        payment_amount_usdt=payment.amount if payment else None,
        payment_network=payment.network if payment else None,
        payment_tx_hash=payment.tx_hash if payment else None,
        delivery_at=order.delivery_at,
        delivered_at=order.delivered_at,
        created_at=order.created_at,
        customer_telegram_user_id=order.customer.telegram_user_id,
        customer_username=order.customer.username,
        product_name=order.product.name,
        campaign_code=order.campaign.code if order.campaign else None,
    )


def order_load_options():
    return (
        selectinload(Order.customer),
        selectinload(Order.product),
        selectinload(Order.campaign),
        selectinload(Order.payments),
    )


@router.get("/dashboard")
async def get_dashboard(session: AsyncSession = Depends(get_session)) -> dict[str, int]:
    return await dashboard_counts(session)


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[OrderOut]:
    orders = list(
        (
            await session.scalars(
                select(Order)
                .options(*order_load_options())
                .order_by(Order.id.desc())
                .limit(limit)
            )
        ).all()
    )
    return [serialize_order(order) for order in orders]


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
async def patch_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OrderOut:
    if payload.status == OrderStatus.COMPLETED:
        raise HTTPException(status_code=422, detail="Use the delivery action to complete an order")
    order = await session.scalar(select(Order).where(Order.id == order_id).options(*order_load_options()))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if payload.status == OrderStatus.READY and order.deposit_usdt > 0:
        paid_deposit = await session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.order_id == order.id,
                Payment.stage == "deposit",
                Payment.currency == "USDT",
                Payment.status == PaymentStatus.SUCCEEDED,
            )
        )
        if paid_deposit < order.deposit_usdt:
            raise HTTPException(status_code=409, detail="USDT deposit must be confirmed before preparing delivery")
    await update_order_status(
        session,
        order=order,
        new_status=payload.status,
        actor="admin-api",
        reason=payload.reason,
    )
    bot = request.app.state.bot
    if payload.status == OrderStatus.READY:
        balance_payment = await create_balance_payment(session, order)
        settings = get_settings()
        if bot and balance_payment and settings.usdt_network and settings.usdt_receiving_address:
            with contextlib.suppress(Exception):
                await bot.send_message(
                    order.customer.telegram_user_id,
                    f"订单 {order.public_id} 已准备完成，请支付尾款。\n\n"
                    f"金额：{format_usdt(balance_payment.amount)} USDT\n"
                    f"网络：{settings.usdt_network}\n"
                    f"收款地址：<code>{settings.usdt_receiving_address}</code>\n\n"
                    f"转账后发送：/txid {order.public_id} 交易哈希",
                    parse_mode="HTML",
                )
    if bot:
        with contextlib.suppress(Exception):
            await bot.send_message(
                order.customer.telegram_user_id,
                f"订单 {order.public_id} 状态已更新：{payload.status.value}",
            )
    return serialize_order(order)


@router.post("/orders/{order_id}/deliver", response_model=OrderOut)
async def deliver_order(
    order_id: int,
    payload: DeliveryRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OrderOut:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Confirm the delivery before sending")
    order = await session.scalar(
        select(Order).where(Order.id == order_id).options(*order_load_options())
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in (OrderStatus.READY, OrderStatus.DELIVERING):
        raise HTTPException(status_code=409, detail="Order is not ready for delivery")
    bot = request.app.state.bot
    if bot is None:
        raise HTTPException(status_code=503, detail="Telegram bot is unavailable")

    paid_total = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.order_id == order.id,
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.currency == "USDT",
        )
    )
    if order.total_usdt > 0 and paid_total < order.total_usdt:
        raise HTTPException(status_code=409, detail="USDT balance must be confirmed before delivery")

    if order.status != OrderStatus.DELIVERING:
        await update_order_status(
            session,
            order=order,
            new_status=OrderStatus.DELIVERING,
            actor="admin-api",
            reason="运营人员开始发送交付内容",
        )
    try:
        await bot.send_message(order.customer.telegram_user_id, payload.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Telegram delivery failed; order remains in delivery state") from exc

    await update_order_status(
        session,
        order=order,
        new_status=OrderStatus.COMPLETED,
        actor="admin-api",
        reason="人工交付已发送；交付正文未写入订单日志",
    )
    order = await session.scalar(
        select(Order).where(Order.id == order_id).options(*order_load_options())
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize_order(order)


@router.get("/products", response_model=list[ProductOut])
async def list_products(session: AsyncSession = Depends(get_session)) -> list[Product]:
    return list((await session.scalars(select(Product).order_by(Product.id))).all())


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    payload: ProductCreate,
    session: AsyncSession = Depends(get_session),
) -> Product:
    if payload.deposit_usdt > payload.total_usdt:
        raise HTTPException(status_code=422, detail="Deposit cannot exceed total")
    product = Product(**payload.model_dump())
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
async def patch_product(
    product_id: int,
    payload: ProductUpdate,
    session: AsyncSession = Depends(get_session),
) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    if product.deposit_usdt > product.total_usdt:
        raise HTTPException(status_code=422, detail="Deposit cannot exceed total")
    await session.commit()
    await session.refresh(product)
    return product


@router.get("/payments/pending")
async def list_pending_payments(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(Payment.status == PaymentStatus.PENDING, Payment.tx_hash.is_not(None))
                .options(
                    selectinload(Payment.order).selectinload(Order.customer),
                    selectinload(Payment.order).selectinload(Order.product),
                )
                .order_by(Payment.id)
            )
        ).all()
    )
    return [
        {
            "id": payment.id,
            "order_id": payment.order.id,
            "public_id": payment.order.public_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "stage": payment.stage,
            "network": payment.network,
            "tx_hash": payment.tx_hash,
            "customer_telegram_user_id": payment.order.customer.telegram_user_id,
            "product_name": payment.order.product.name,
        }
        for payment in payments
    ]


@router.post("/payments/{payment_id}/confirm", response_model=OrderOut)
async def confirm_payment(
    payment_id: int,
    payload: PaymentConfirmation,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OrderOut:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Only confirmed receipts can be marked paid")
    order = await confirm_usdt_payment(
        session,
        payment_id=payment_id,
        actor="admin-api",
        note=payload.note,
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Pending USDT payment not found")
    order = await session.scalar(
        select(Order).where(Order.id == order.id).options(*order_load_options())
    )
    bot = request.app.state.bot
    if bot and order:
        with contextlib.suppress(Exception):
            await bot.send_message(
                order.customer.telegram_user_id,
                f"已确认收到订单 {order.public_id} 的 USDT 付款，订单状态已更新：{order.status.value}。",
            )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize_order(order)


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(session: AsyncSession = Depends(get_session)) -> list[Campaign]:
    return list((await session.scalars(select(Campaign).order_by(Campaign.id))).all())


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    session: AsyncSession = Depends(get_session),
) -> Campaign:
    existing = await session.scalar(select(Campaign).where(Campaign.code == payload.code))
    if existing:
        raise HTTPException(status_code=409, detail="Campaign code already exists")
    campaign = Campaign(**payload.model_dump(), is_active=True)
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return campaign
