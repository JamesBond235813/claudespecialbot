import asyncio
import contextlib
import html
import logging
from datetime import timezone
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import get_settings
from .database import SessionLocal
from .models import Campaign, Customer, Order, OrderStatus, Product
from .services import (
    create_order,
    format_usdt,
    resolve_campaign,
    submit_payment_tx_hash,
    upsert_customer,
)


logger = logging.getLogger(__name__)
settings = get_settings()
router = Router()
_campaign_by_user: dict[int, str] = {}


def product_keyboard(products: list[Product]) -> InlineKeyboardMarkup:
    categories = sorted({product.category for product in products})
    rows = [[InlineKeyboardButton(text=f"📁 {name}", callback_data=f"category:{index}")] for index, name in enumerate(categories)]
    rows.append([InlineKeyboardButton(text="我的订单", callback_data="orders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="同意条款并预约", callback_data=f"confirm:{product_id}")],
            [InlineKeyboardButton(text="返回商品列表", callback_data="products")],
        ]
    )


async def active_products() -> list[Product]:
    async with SessionLocal() as session:
        return list(
            (
                await session.scalars(
                    select(Product).where(Product.is_active.is_(True)).order_by(Product.id)
                )
            ).all()
        )


async def send_products(message: Message) -> None:
    products = await active_products()
    if not products:
        await message.answer("当前没有可预约的服务，请稍后再试或联系人工客服。")
        return
    await message.answer("请选择需要预约的数字服务：", reply_markup=product_keyboard(products))


async def send_category(message: Message, category: str) -> None:
    products = [product for product in await active_products() if product.category == category]
    if not products:
        await message.answer("这个分类当前没有在售服务。")
        return
    rows = []
    for product in products:
        stock = "库存充足" if product.stock_quantity is None else f"库存 {product.stock_quantity}"
        price = "价格待确认" if product.total_usdt == 0 else f"{format_usdt(product.total_usdt)} USDT"
        rows.append([InlineKeyboardButton(
            text=f"{product.name} · {price} · {stock}", callback_data=f"product:{product.id}"
        )])
    rows.append([InlineKeyboardButton(text="返回分类", callback_data="products")])
    await message.answer(f"📁 {category}\n请选择商品：", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(CommandStart())
async def command_start(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    campaign_code = command.args.strip()[:64] if command.args else None
    async with SessionLocal() as session:
        await upsert_customer(session, message.from_user)
        campaign = await resolve_campaign(session, campaign_code)
        await session.commit()
        if campaign:
            _campaign_by_user[message.from_user.id] = campaign.code

    await message.answer(
        "欢迎使用数字服务预约中心。\n\n"
        "你可以在这里选择服务、预约次日交付并查询订单进度。"
    )
    await send_products(message)


@router.message(Command("products"))
async def command_products(message: Message) -> None:
    await send_products(message)


@router.callback_query(F.data == "products")
async def callback_products(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await send_products(callback.message)


@router.callback_query(F.data.startswith("category:"))
async def callback_category(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        products = await active_products()
        categories = sorted({product.category for product in products})
        try:
            category = categories[int(callback.data.split(":", 1)[1])]
        except (ValueError, IndexError):
            await callback.message.answer("分类已更新，请重新打开商品列表。")
            return
        await send_category(callback.message, category)


@router.callback_query(F.data.startswith("product:"))
async def callback_product(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    product_id = int(callback.data.split(":", 1)[1])
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
    if product is None or not product.is_active:
        await callback.message.answer("该服务当前不可预约。")
        return
    deposit_text = "无需定金" if product.deposit_usdt == 0 else f"定金：{format_usdt(product.deposit_usdt)} USDT / 件"
    price_text = "价格待人工确认" if product.total_usdt == 0 else f"总价：{format_usdt(product.total_usdt)} USDT"
    stock = "库存充足" if product.stock_quantity is None else f"剩余库存：{product.stock_quantity}"
    if product.stock_quantity == 0:
        await callback.message.answer(f"{html.escape(product.name)} 当前已售罄。")
        return
    quantity_rows = [[InlineKeyboardButton(text=str(qty), callback_data=f"quantity:{product.id}:{qty}") for qty in (1, 2, 5)]]
    quantity_rows.append([InlineKeyboardButton(text="返回商品分类", callback_data="products")])
    await callback.message.answer(
        f"<b>{html.escape(product.name)}</b>\n\n{html.escape(product.description)}\n\n"
        f"{deposit_text}\n{price_text}\n{stock}\n预计交付：{html.escape(product.delivery_note)}\n\n"
        "点击下方按钮表示你已阅读并同意 /terms 中的服务条款。",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=quantity_rows),
    )


@router.callback_query(F.data.startswith("quantity:"))
async def callback_quantity(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return
    _, product_id_raw, quantity_raw = callback.data.split(":")
    async with SessionLocal() as session:
        product = await session.get(Product, int(product_id_raw))
    quantity = int(quantity_raw)
    if product is None or not product.is_active:
        await callback.message.answer("该服务当前不可预约。")
        return
    if product.stock_quantity is not None and quantity > product.stock_quantity:
        await callback.message.answer(f"库存不足，当前剩余 {product.stock_quantity} 件。")
        return
    total = product.total_usdt * quantity
    total_text = "下单后由客服确认" if total == 0 else f"{format_usdt(total)} USDT"
    await callback.message.answer(
        f"<b>订单确认</b>\n\n商品：{html.escape(product.name)}\n数量：{quantity}\n"
        f"总计：{total_text}\n预计交付：{html.escape(product.delivery_note)}\n\n"
        "确认预约即表示同意 /terms 中的服务条款。",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="同意条款并预约", callback_data=f"confirm:{product.id}:{quantity}")],
            [InlineKeyboardButton(text="返回商品", callback_data=f"product:{product.id}")],
        ]),
    )


@router.callback_query(F.data.startswith("confirm:"))
async def callback_confirm(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if callback.from_user is None or callback.message is None:
        return
    _, product_id_raw, quantity_raw = callback.data.split(":")
    product_id = int(product_id_raw)
    quantity = int(quantity_raw)
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(Order)
            .join(Customer)
            .where(
                Customer.telegram_user_id == callback.from_user.id,
                Order.product_id == product_id,
                Order.status.in_(
                    [
                        OrderStatus.RESERVED,
                        OrderStatus.DEPOSIT_PENDING,
                        OrderStatus.DEPOSIT_PAID,
                        OrderStatus.PREPARING,
                    ]
                ),
            )
            .order_by(Order.id.desc())
        )
        if existing:
            await callback.message.answer(f"你已有进行中的订单：{existing.public_id}")
            return

        customer = await upsert_customer(session, callback.from_user)
        product = await session.get(Product, product_id)
        if product is None or not product.is_active:
            await callback.message.answer("该服务当前不可预约。")
            return
        campaign = None
        campaign_code = _campaign_by_user.get(callback.from_user.id)
        if campaign_code:
            campaign = await session.scalar(select(Campaign).where(Campaign.code == campaign_code))
        try:
            order, payment = await create_order(
                session,
                customer=customer,
                product=product,
                campaign=campaign,
                actor=f"telegram:{callback.from_user.id}",
                quantity=quantity,
            )
        except ValueError as exc:
            await session.rollback()
            await callback.message.answer(f"无法创建订单：{html.escape(str(exc))}。请刷新商品后重试。")
            return

    delivery_display = (
        order.delivery_at.replace(tzinfo=timezone.utc)
        .astimezone(ZoneInfo(settings.business_timezone))
        .strftime("%Y-%m-%d %H:%M")
    )
    if payment is None:
        await callback.message.answer(
            f"预约成功！\n订单号：<code>{order.public_id}</code>\n"
            f"商品：{html.escape(product.name)} × {quantity}\n"
            f"预计交付时间：{delivery_display}\n\n可发送 /orders 查询进度。",
            parse_mode=ParseMode.HTML,
        )
    else:
        if settings.usdt_network and settings.usdt_receiving_address:
            await callback.message.answer(
                f"订单 {order.public_id} 已创建，当前状态：等待 USDT 定金。\n\n"
                f"商品：{html.escape(product.name)} × {quantity}\n"
                f"金额：{format_usdt(payment.amount)} USDT\n"
                f"网络：{settings.usdt_network}\n"
                f"收款地址：<code>{settings.usdt_receiving_address}</code>\n\n"
                "请务必使用上方指定网络转账。转账后发送：\n"
                f"<code>/txid {order.public_id} 交易哈希</code>\n"
                "到账由人工核验后确认订单。",
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.answer(
                f"订单 {order.public_id} 已创建。USDT 收款网络和地址尚未配置，"
                f"请联系 {settings.support_handle} 完成定金支付。"
            )

    if settings.telegram_admin_chat_id:
        with contextlib.suppress(Exception):
            await bot.send_message(
                settings.telegram_admin_chat_id,
                f"新订单 {order.public_id}\n商品：{product.name}\n客户：{callback.from_user.id}",
            )


@router.message(Command("txid"))
async def command_txid(message: Message, command: CommandObject, bot: Bot) -> None:
    if message.from_user is None:
        return
    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer("格式：/txid 订单号 交易哈希")
        return
    async with SessionLocal() as session:
        result = await submit_payment_tx_hash(
            session,
            telegram_user_id=message.from_user.id,
            order_public_id=parts[0].upper(),
            tx_hash=parts[1],
        )
    if result is None:
        await message.answer("没有找到该用户的待核验 USDT 订单，或该笔付款已经提交。")
        return
    order, payment = result
    await message.answer(f"已提交订单 {order.public_id} 的交易哈希，核验通过后会通知你。")
    if settings.telegram_admin_chat_id:
        with contextlib.suppress(Exception):
            await bot.send_message(
                settings.telegram_admin_chat_id,
                f"待核验 USDT 定金\n订单：{order.public_id}\n"
                f"金额：{format_usdt(payment.amount)} USDT\n网络：{payment.network or settings.usdt_network}\n"
                f"交易哈希：{payment.tx_hash}",
            )


@router.message(Command("orders"))
async def command_orders(message: Message) -> None:
    if message.from_user is None:
        return
    await send_orders_for_user(message, message.from_user.id)


async def send_orders_for_user(message: Message, telegram_user_id: int) -> None:
    async with SessionLocal() as session:
        orders = list(
            (
                await session.scalars(
                    select(Order)
                    .join(Customer)
                    .where(Customer.telegram_user_id == telegram_user_id)
                    .options(selectinload(Order.product))
                    .order_by(Order.id.desc())
                    .limit(10)
                )
            ).all()
        )
    if not orders:
        await message.answer("你还没有订单。")
        return
    lines = ["最近订单："]
    for order in orders:
        lines.append(f"• {order.public_id}｜{order.product.name} × {order.quantity}｜{order.status.value}")
    await message.answer("\n".join(lines))


@router.callback_query(F.data == "orders")
async def callback_orders(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await send_orders_for_user(callback.message, callback.from_user.id)


@router.message(Command("terms"))
async def command_terms(message: Message) -> None:
    await message.answer(
        f"服务条款（版本 {settings.terms_version}）\n\n"
        "1. 商品内容、价格与交付时间以下单页为准。\n"
        "2. 预约后如需取消或退款，请在交付前联系支持。\n"
        "3. 因不可抗力无法按时交付时，将提供改期或退款方案。\n"
        "4. 客户应确保所购买和使用的具体服务符合适用规则与法律。"
    )


@router.message(Command("support"))
@router.message(Command("paysupport"))
async def command_support(message: Message) -> None:
    await message.answer(f"人工支持：{settings.support_handle}\n请同时提供订单号。")


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def run_polling(bot: Bot, dispatcher: Dispatcher) -> None:
    logger.info("Starting Telegram long polling")
    await bot.delete_webhook(drop_pending_updates=False)
    await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


async def stop_polling(dispatcher: Dispatcher, task: asyncio.Task | None) -> None:
    if task is None:
        return
    await dispatcher.stop_polling()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

