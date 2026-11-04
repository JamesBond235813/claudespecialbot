import contextlib
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import String, and_, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..catalog import DEFAULT_TERMS, parsed_store_settings
from ..config import get_settings
from ..database import get_session
from ..models import (
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
from ..schemas import (
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    CustomerOut,
    CustomerUpdate,
    DashboardOut,
    DeliveryRequest,
    OrderDetail,
    OrderNotesUpdate,
    OrderOut,
    OrderStatusUpdate,
    PaymentConfirmation,
    PaymentOut,
    PaymentRejection,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    StatusHistoryOut,
    StoreSettings,
    StoreSettingsOut,
)
from ..security import require_admin_key
from ..services import (
    confirm_usdt_payment,
    create_balance_payment,
    dashboard_stats,
    decimal_amount,
    ensure_category,
    format_usdt,
    get_store_settings,
    save_store_settings,
    select_display_payment,
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


def order_load_options(*, with_history: bool = False):
    options = (
        selectinload(Order.customer),
        selectinload(Order.product),
        selectinload(Order.campaign),
        selectinload(Order.payments),
    )
    if with_history:
        options += (selectinload(Order.history),)
    return options


def serialize_payment(payment: Payment) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        stage=payment.stage,
        amount=payment.amount,
        currency=payment.currency,
        network=payment.network,
        tx_hash=payment.tx_hash,
        status=payment.status,
        paid_at=payment.paid_at,
        created_at=payment.created_at,
    )


def serialize_order(order: Order) -> OrderOut:
    payment = select_display_payment(order.payments)
    return OrderOut(
        id=order.id,
        public_id=order.public_id,
        status=order.status,
        deposit_usdt=order.deposit_usdt,
        total_usdt=order.total_usdt,
        quantity=order.quantity,
        payment_status=payment.status.value if payment else None,
        payment_stage=payment.stage if payment else None,
        payment_amount_usdt=payment.amount if payment else None,
        payment_network=payment.network if payment else None,
        payment_tx_hash=payment.tx_hash if payment else None,
        payment_id=payment.id if payment else None,
        delivery_at=order.delivery_at,
        delivered_at=order.delivered_at,
        created_at=order.created_at,
        customer_telegram_user_id=order.customer.telegram_user_id,
        customer_username=order.customer.username,
        customer_first_name=order.customer.first_name,
        product_id=order.product_id,
        product_name=order.product.name,
        campaign_code=order.campaign.code if order.campaign else None,
        notes=order.notes,
    )


def serialize_detail(order: Order) -> OrderDetail:
    return OrderDetail(
        **serialize_order(order).model_dump(),
        terms_version=order.terms_version,
        terms_accepted_at=order.terms_accepted_at,
        history=[
            StatusHistoryOut(
                id=item.id,
                from_status=item.from_status,
                to_status=item.to_status,
                actor=item.actor,
                reason=item.reason,
                created_at=item.created_at,
            )
            for item in sorted(order.history, key=lambda item: item.id)
        ],
        payments=[
            serialize_payment(payment)
            for payment in sorted(order.payments, key=lambda item: item.id)
        ],
    )


async def load_order(
    session: AsyncSession,
    order_id: int,
    *,
    with_history: bool = False,
) -> Order | None:
    return await session.scalar(
        select(Order).where(Order.id == order_id).options(*order_load_options(with_history=with_history))
    )


def order_filters(status: OrderStatus | None, q: str | None, campaign: str | None) -> list:
    conditions = []
    if status is not None:
        conditions.append(Order.status == status)
    if campaign and campaign.strip():
        conditions.append(Order.campaign.has(Campaign.code == campaign.strip()))
    if q and q.strip():
        term = f"%{q.strip()}%"
        conditions.append(
            or_(
                Order.public_id.like(term),
                Order.customer.has(
                    or_(
                        Customer.username.like(term),
                        Customer.first_name.like(term),
                        cast(Customer.telegram_user_id, String).like(term),
                    )
                ),
                Order.product.has(Product.name.like(term)),
            )
        )
    return conditions


async def notify(bot, telegram_user_id: int, text: str, *, parse_mode: str | None = None) -> None:
    if bot is None:
        return
    with contextlib.suppress(Exception):
        await bot.send_message(telegram_user_id, text, parse_mode=parse_mode)


def settings_out(raw: dict[str, str]) -> StoreSettingsOut:
    parsed = parsed_store_settings(raw)
    settings = get_settings()
    return StoreSettingsOut(
        show_categories=parsed["show_categories"],
        welcome_text=parsed["welcome_text"],
        store_prompt=parsed["store_prompt"],
        product_prompt=parsed["product_prompt"],
        terms_text=parsed["terms_text"],
        terms_version=settings.terms_version,
        terms_default=DEFAULT_TERMS,
        support_handle=settings.support_handle,
        usdt_network=settings.usdt_network,
        usdt_receiving_address=settings.usdt_receiving_address,
        usdt_configured=bool(settings.usdt_network and settings.usdt_receiving_address),
        bot_username=settings.telegram_bot_username,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(session: AsyncSession = Depends(get_session)) -> dict[str, int | str]:
    return await dashboard_stats(session)


@router.get("/settings", response_model=StoreSettingsOut)
async def get_settings_api(session: AsyncSession = Depends(get_session)) -> StoreSettingsOut:
    return settings_out(await get_store_settings(session))


@router.put("/settings", response_model=StoreSettingsOut)
async def put_settings(
    payload: StoreSettings,
    session: AsyncSession = Depends(get_session),
) -> StoreSettingsOut:
    stored = await save_store_settings(
        session,
        {
            "show_categories": "1" if payload.show_categories else "0",
            "welcome_text": payload.welcome_text,
            "store_prompt": payload.store_prompt,
            "product_prompt": payload.product_prompt,
            "terms_text": payload.terms_text,
        },
    )
    return settings_out(stored)


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    response: Response,
    status: OrderStatus | None = None,
    q: str | None = None,
    campaign: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[OrderOut]:
    conditions = order_filters(status, q, campaign)
    total = await session.scalar(select(func.count(Order.id)).where(*conditions)) or 0
    response.headers["X-Total-Count"] = str(total)
    orders = list(
        (
            await session.scalars(
                select(Order)
                .where(*conditions)
                .options(*order_load_options())
                .order_by(Order.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return [serialize_order(order) for order in orders]


@router.get("/orders/{order_id}", response_model=OrderDetail)
async def get_order(order_id: int, session: AsyncSession = Depends(get_session)) -> OrderDetail:
    order = await load_order(session, order_id, with_history=True)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return serialize_detail(order)


@router.patch("/orders/{order_id}/notes", response_model=OrderDetail)
async def patch_order_notes(
    order_id: int,
    payload: OrderNotesUpdate,
    session: AsyncSession = Depends(get_session),
) -> OrderDetail:
    order = await load_order(session, order_id, with_history=True)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    order.notes = payload.notes
    await session.commit()
    reloaded = await load_order(session, order_id, with_history=True)
    if reloaded is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return serialize_detail(reloaded)


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
async def patch_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OrderOut:
    if payload.status == OrderStatus.COMPLETED:
        raise HTTPException(status_code=422, detail="请使用交付操作完成订单")
    order = await load_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
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
            raise HTTPException(status_code=409, detail="确认定金到账后才能进入待交付")
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
            await notify(
                bot,
                order.customer.telegram_user_id,
                f"订单 {order.public_id} 已准备完成，请支付尾款。\n\n"
                f"金额：{format_usdt(balance_payment.amount)} USDT\n"
                f"网络：{settings.usdt_network}\n"
                f"收款地址：<code>{settings.usdt_receiving_address}</code>\n\n"
                f"转账后发送：/txid {order.public_id} 交易哈希",
                parse_mode="HTML",
            )
    await notify(
        bot,
        order.customer.telegram_user_id,
        f"订单 {order.public_id} 状态已更新：{payload.status.value}",
    )
    reloaded = await load_order(session, order_id)
    if reloaded is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return serialize_order(reloaded)


@router.post("/orders/{order_id}/deliver", response_model=OrderOut)
async def deliver_order(
    order_id: int,
    payload: DeliveryRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OrderOut:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="请先确认交付")
    order = await load_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status not in (OrderStatus.READY, OrderStatus.DELIVERING):
        raise HTTPException(status_code=409, detail="订单当前不能交付")
    bot = request.app.state.bot
    if bot is None:
        raise HTTPException(status_code=503, detail="Telegram 机器人未连接")

    paid_total = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.order_id == order.id,
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.currency == "USDT",
        )
    )
    if order.total_usdt > 0 and paid_total < order.total_usdt:
        raise HTTPException(status_code=409, detail="尾款确认前不能交付")

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
        raise HTTPException(status_code=502, detail="Telegram 发送失败，订单保持交付中") from exc

    await update_order_status(
        session,
        order=order,
        new_status=OrderStatus.COMPLETED,
        actor="admin-api",
        reason="人工交付已发送；交付正文未写入订单日志",
    )
    reloaded = await load_order(session, order_id)
    if reloaded is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return serialize_order(reloaded)


@router.get("/products", response_model=list[ProductOut])
async def list_products(session: AsyncSession = Depends(get_session)) -> list[Product]:
    return list(
        (await session.scalars(select(Product).order_by(Product.sort_order, Product.id))).all()
    )


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    payload: ProductCreate,
    session: AsyncSession = Depends(get_session),
) -> Product:
    if payload.deposit_usdt > payload.total_usdt:
        raise HTTPException(status_code=422, detail="定金不能大于总价")
    await ensure_category(session, payload.category)
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
        raise HTTPException(status_code=404, detail="商品不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("category"):
        await ensure_category(session, data["category"])
    for field, value in data.items():
        setattr(product, field, value)
    if product.deposit_usdt > product.total_usdt:
        raise HTTPException(status_code=422, detail="定金不能大于总价")
    await session.commit()
    await session.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int, session: AsyncSession = Depends(get_session)) -> None:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    order_count = await session.scalar(select(func.count(Order.id)).where(Order.product_id == product.id)) or 0
    if order_count:
        raise HTTPException(status_code=409, detail="该商品已有订单，不能删除，请改为停用")
    await session.delete(product)
    await session.commit()


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(session: AsyncSession = Depends(get_session)) -> list[CategoryOut]:
    categories = list(
        (await session.scalars(select(Category).order_by(Category.sort_order, Category.id))).all()
    )
    counts = dict(
        (
            await session.execute(
                select(Product.category, func.count(Product.id)).group_by(Product.category)
            )
        ).all()
    )
    return [
        CategoryOut(
            id=category.id,
            name=category.name,
            is_visible=category.is_visible,
            sort_order=category.sort_order,
            product_count=counts.get(category.name, 0),
            created_at=category.created_at,
            updated_at=category.updated_at,
        )
        for category in categories
    ]


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    existing = await session.scalar(select(Category).where(Category.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail="分类名称已存在")
    category = Category(name=payload.name, is_visible=payload.is_visible, sort_order=payload.sort_order)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    count = await session.scalar(select(func.count(Product.id)).where(Product.category == category.name)) or 0
    return CategoryOut(
        id=category.id,
        name=category.name,
        is_visible=category.is_visible,
        sort_order=category.sort_order,
        product_count=count,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def patch_category(
    category_id: int,
    payload: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    data = payload.model_dump(exclude_unset=True)
    new_name = data.get("name")
    if new_name and new_name != category.name:
        conflict = await session.scalar(
            select(Category).where(Category.name == new_name, Category.id != category.id)
        )
        if conflict:
            raise HTTPException(status_code=409, detail="分类名称已存在")
        await session.execute(
            update(Product).where(Product.category == category.name).values(category=new_name)
        )
        category.name = new_name
    if "is_visible" in data:
        category.is_visible = data["is_visible"]
    if "sort_order" in data and data["sort_order"] is not None:
        category.sort_order = data["sort_order"]
    await session.commit()
    await session.refresh(category)
    count = await session.scalar(select(func.count(Product.id)).where(Product.category == category.name)) or 0
    return CategoryOut(
        id=category.id,
        name=category.name,
        is_visible=category.is_visible,
        sort_order=category.sort_order,
        product_count=count,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session)) -> None:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    count = await session.scalar(select(func.count(Product.id)).where(Product.category == category.name)) or 0
    if count:
        raise HTTPException(status_code=409, detail="该分类下还有商品，请先转移或删除商品")
    await session.delete(category)
    await session.commit()


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
            "customer_username": payment.order.customer.username,
            "product_name": payment.order.product.name,
            "created_at": payment.created_at,
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
        raise HTTPException(status_code=422, detail="请先确认已经核对到账")
    order = await confirm_usdt_payment(
        session,
        payment_id=payment_id,
        actor="admin-api",
        note=payload.note,
    )
    if order is None:
        raise HTTPException(status_code=404, detail="没有找到待确认的 USDT 付款")
    reloaded = await load_order(session, order.id)
    if reloaded is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    await notify(
        request.app.state.bot,
        reloaded.customer.telegram_user_id,
        f"已确认收到订单 {reloaded.public_id} 的 USDT 付款，订单状态已更新：{reloaded.status.value}。",
    )
    return serialize_order(reloaded)


@router.post("/payments/{payment_id}/reject", response_model=OrderOut)
async def reject_payment(
    payment_id: int,
    payload: PaymentRejection,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> OrderOut:
    payment = await session.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .options(selectinload(Payment.order).selectinload(Order.customer))
    )
    if payment is None or payment.status != PaymentStatus.PENDING or not payment.tx_hash:
        raise HTTPException(status_code=404, detail="没有找到可驳回的待核验付款")
    payment.tx_hash = None
    order = payment.order
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=order.status.value,
            to_status=order.status.value,
            actor="admin-api",
            reason=f"驳回交易哈希：{payload.reason}",
        )
    )
    await session.commit()
    await notify(
        request.app.state.bot,
        order.customer.telegram_user_id,
        f"订单 {order.public_id} 的交易哈希未通过核验：{payload.reason}\n请核对后重新提交 /txid。",
    )
    reloaded = await load_order(session, order.id)
    if reloaded is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return serialize_order(reloaded)


async def campaign_stats(session: AsyncSession) -> tuple[dict[int, int], dict[int, Decimal]]:
    counts = dict(
        (
            await session.execute(
                select(Order.campaign_id, func.count(Order.id))
                .where(Order.campaign_id.is_not(None))
                .group_by(Order.campaign_id)
            )
        ).all()
    )
    revenues = {
        campaign_id: decimal_amount(amount)
        for campaign_id, amount in (
            await session.execute(
                select(Order.campaign_id, func.coalesce(func.sum(Payment.amount), 0))
                .join(Payment, Payment.order_id == Order.id)
                .where(
                    Order.campaign_id.is_not(None),
                    Payment.status == PaymentStatus.SUCCEEDED,
                )
                .group_by(Order.campaign_id)
            )
        ).all()
    }
    return counts, revenues


def serialize_campaign(campaign: Campaign, counts: dict[int, int], revenues: dict[int, Decimal]) -> CampaignOut:
    return CampaignOut(
        id=campaign.id,
        code=campaign.code,
        name=campaign.name,
        source_url=campaign.source_url,
        is_active=campaign.is_active,
        created_at=campaign.created_at,
        order_count=counts.get(campaign.id, 0),
        revenue_usdt=revenues.get(campaign.id, Decimal("0")),
    )


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(session: AsyncSession = Depends(get_session)) -> list[CampaignOut]:
    campaigns = list((await session.scalars(select(Campaign).order_by(Campaign.id.desc()))).all())
    counts, revenues = await campaign_stats(session)
    return [serialize_campaign(campaign, counts, revenues) for campaign in campaigns]


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    existing = await session.scalar(select(Campaign).where(Campaign.code == payload.code))
    if existing:
        raise HTTPException(status_code=409, detail="来源码已存在")
    campaign = Campaign(**payload.model_dump(), is_active=True)
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return serialize_campaign(campaign, {}, {})


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def patch_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    session: AsyncSession = Depends(get_session),
) -> CampaignOut:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(campaign, field, value)
    await session.commit()
    await session.refresh(campaign)
    counts, revenues = await campaign_stats(session)
    return serialize_campaign(campaign, counts, revenues)


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: int, session: AsyncSession = Depends(get_session)) -> None:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    count = await session.scalar(select(func.count(Order.id)).where(Order.campaign_id == campaign.id)) or 0
    if count:
        raise HTTPException(status_code=409, detail="该来源已有订单，不能删除，可以停用")
    await session.delete(campaign)
    await session.commit()


@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[CustomerOut]:
    statement = select(Customer)
    if q and q.strip():
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Customer.username.like(term),
                Customer.first_name.like(term),
                cast(Customer.telegram_user_id, String).like(term),
            )
        )
    customers = list(
        (await session.scalars(statement.order_by(Customer.id.desc()).limit(limit))).all()
    )
    if not customers:
        return []
    ids = [customer.id for customer in customers]
    stats = {
        customer_id: (order_count, decimal_amount(spent))
        for customer_id, order_count, spent in (
            await session.execute(
                select(
                    Order.customer_id,
                    func.count(func.distinct(Order.id)),
                    func.coalesce(func.sum(Payment.amount), 0),
                )
                .outerjoin(
                    Payment,
                    and_(Payment.order_id == Order.id, Payment.status == PaymentStatus.SUCCEEDED),
                )
                .where(Order.customer_id.in_(ids))
                .group_by(Order.customer_id)
            )
        ).all()
    }
    return [
        CustomerOut(
            id=customer.id,
            telegram_user_id=customer.telegram_user_id,
            username=customer.username,
            first_name=customer.first_name,
            language_code=customer.language_code,
            is_blocked=customer.is_blocked,
            created_at=customer.created_at,
            order_count=stats.get(customer.id, (0, Decimal("0")))[0],
            spent_usdt=stats.get(customer.id, (0, Decimal("0")))[1],
        )
        for customer in customers
    ]


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
async def patch_customer(
    customer_id: int,
    payload: CustomerUpdate,
    session: AsyncSession = Depends(get_session),
) -> CustomerOut:
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    customer.is_blocked = payload.is_blocked
    await session.commit()
    await session.refresh(customer)
    order_count = await session.scalar(
        select(func.count(Order.id)).where(Order.customer_id == customer.id)
    ) or 0
    spent = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Order.id == Payment.order_id)
        .where(Order.customer_id == customer.id, Payment.status == PaymentStatus.SUCCEEDED)
    )
    return CustomerOut(
        id=customer.id,
        telegram_user_id=customer.telegram_user_id,
        username=customer.username,
        first_name=customer.first_name,
        language_code=customer.language_code,
        is_blocked=customer.is_blocked,
        created_at=customer.created_at,
        order_count=order_count,
        spent_usdt=decimal_amount(spent),
    )
