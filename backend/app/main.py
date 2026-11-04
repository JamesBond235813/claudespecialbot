import asyncio
import contextlib
import logging
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from .api.admin import router as admin_router
from .bot import router as telegram_router
from .config import ROOT_DIR, get_settings
from .database import SessionLocal, engine
from .catalog import CATEGORY_STEP_ROLLOUT_KEY, SETTING_DEFAULTS, category_step_rollout
from .models import AppSetting, Base, Campaign, Category, Order, OrderStatus, Product
from sqlalchemy.orm import selectinload


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


async def delivery_reminder_loop(bot: Bot) -> None:
    while True:
        async with SessionLocal() as session:
            pending = list(
                (
                    await session.scalars(
                        select(Order)
                        .where(
                            Order.delivery_at <= func.utc_timestamp(),
                            Order.reminder_sent_at.is_(None),
                            Order.status.in_(
                                [
                                    OrderStatus.RESERVED,
                                    OrderStatus.DEPOSIT_PAID,
                                    OrderStatus.PREPARING,
                                    OrderStatus.READY,
                                ]
                            ),
                        )
                        .options(selectinload(Order.customer))
                        .order_by(Order.delivery_at)
                        .limit(50)
                    )
                ).all()
            )
            for order in pending:
                try:
                    await bot.send_message(
                        order.customer.telegram_user_id,
                        f"订单 {order.public_id} 已到预计交付时间。客服会尽快处理，如需帮助请联系 {settings.support_handle}。",
                    )
                    order.reminder_sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
                except Exception:
                    logger.exception("Delivery reminder failed for order %s", order.public_id)
            if pending:
                await session.commit()
        await asyncio.sleep(60)


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        migrations = {
            "products": {
                "category": "VARCHAR(100) NOT NULL DEFAULT '默认分类'",
                "stock_quantity": "INT NULL",
                "deposit_usdt": "DECIMAL(18, 6) NOT NULL DEFAULT 0.000000",
                "total_usdt": "DECIMAL(18, 6) NOT NULL DEFAULT 0.000000",
                "sort_order": "INT NOT NULL DEFAULT 0",
            },
            "orders": {
                "quantity": "INT NOT NULL DEFAULT 1",
                "deposit_usdt": "DECIMAL(18, 6) NOT NULL DEFAULT 0.000000",
                "total_usdt": "DECIMAL(18, 6) NOT NULL DEFAULT 0.000000",
            },
            "payments": {
                "network": "VARCHAR(32) NULL",
                "tx_hash": "VARCHAR(128) NULL",
            },
        }
        for table, columns in migrations.items():
            for column, definition in columns.items():
                exists = await connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = :table "
                        "AND column_name = :column"
                    ),
                    {"table": table, "column": column},
                )
                if not exists:
                    await connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    )
        await connection.execute(
            text("ALTER TABLE payments MODIFY COLUMN amount DECIMAL(18, 6) NOT NULL")
        )
        tx_index = await connection.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = 'payments' "
                "AND index_name = 'uq_payments_tx_hash'"
            )
        )
        if not tx_index:
            await connection.execute(
                text("CREATE UNIQUE INDEX uq_payments_tx_hash ON payments (tx_hash)")
            )
    async with SessionLocal() as session:
        product = await session.scalar(select(Product).limit(1))
        if product is None:
            session.add(
                Product(
                    name="标准数字服务（测试）",
                    description="用于验证预约、订单通知和次日人工交付流程的测试商品。",
                    deposit_stars=0,
                    total_stars=0,
                    delivery_note="次日 10:00 起人工交付",
                    is_active=True,
                )
            )
            await session.flush()
        product_count = await session.scalar(select(func.count(Product.id))) or 0
        for slot_number in range(product_count + 1, 7):
            session.add(
                Product(
                    name=f"商品槽位 {slot_number}（待配置）",
                    description="请在管理后台填写商品说明、价格与交付规则后再启用。",
                    deposit_stars=0,
                    total_stars=0,
                    delivery_note="次日人工交付",
                    is_active=False,
                )
            )
        campaign = await session.scalar(select(Campaign).where(Campaign.code == "x_default"))
        if campaign is None:
            session.add(Campaign(code="x_default", name="X 默认入口", is_active=True))
        category_names = list((await session.scalars(select(Product.category).distinct())).all())
        for name in category_names:
            if not name:
                continue
            existing_category = await session.scalar(select(Category).where(Category.name == name))
            if existing_category is None:
                session.add(Category(name=name, is_visible=True, sort_order=0))
        for key, value in SETTING_DEFAULTS.items():
            if await session.get(AppSetting, key) is None:
                session.add(AppSetting(key=key, value=value))
        await session.flush()
        rollout = category_step_rollout(
            await session.get(AppSetting, CATEGORY_STEP_ROLLOUT_KEY) is not None
        )
        if rollout is not None:
            for key, value in rollout.items():
                row = await session.get(AppSetting, key)
                if row is None:
                    session.add(AppSetting(key=key, value=value))
                else:
                    row.value = value
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_database()
    app.state.bot = None
    app.state.dispatcher = None
    app.state.polling_task = None
    app.state.reminder_task = None

    if settings.bot_enabled:
        bot = Bot(settings.telegram_bot_token)
        dispatcher = Dispatcher()
        dispatcher.include_router(telegram_router)
        app.state.bot = bot
        app.state.dispatcher = dispatcher
        app.state.reminder_task = asyncio.create_task(delivery_reminder_loop(bot))
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="进入商店"),
                BotCommand(command="products", description="查看商品"),
                BotCommand(command="orders", description="查询我的订单"),
                BotCommand(command="txid", description="提交 USDT 交易哈希"),
                BotCommand(command="terms", description="查看服务条款"),
                BotCommand(command="support", description="联系人工支持"),
                BotCommand(command="paysupport", description="支付问题支持"),
            ]
        )
        await bot.set_my_description(
            "数字服务预约与交付中心。选择商品、创建预约并随时查询订单进度。"
        )
        await bot.set_my_short_description("数字服务预约与次日人工交付")
        if settings.bot_mode == "polling":
            await bot.delete_webhook(drop_pending_updates=False)
            app.state.polling_task = asyncio.create_task(
                dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
            )
            logger.info("Telegram bot polling started")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is empty; API started without bot polling")

    yield

    if app.state.polling_task:
        app.state.polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.polling_task
    if app.state.reminder_task:
        app.state.reminder_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.reminder_task
    if app.state.bot:
        await app.state.bot.session.close()
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    database_ok = False
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            database_ok = True
    except Exception:
        logger.exception("Database health check failed")
    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "telegram_bot": settings.bot_enabled,
        "bot_mode": settings.bot_mode,
    }


def refresh_admin_bundle() -> None:
    frontend = ROOT_DIR / "frontend"
    dist_index = frontend / "dist" / "index.html"
    source_files = [path for path in (frontend / "src").rglob("*") if path.is_file()]
    if not source_files:
        return
    newest_source = max(path.stat().st_mtime for path in source_files)
    if dist_index.exists() and dist_index.stat().st_mtime >= newest_source:
        return
    npm = shutil.which("npm")
    if npm is None:
        logger.warning("Admin source is newer than frontend/dist, but npm is not installed")
        return
    logger.info("Rebuilding admin UI from frontend/src")
    try:
        if not (frontend / "node_modules").exists():
            subprocess.run([npm, "install"], cwd=frontend, check=True, timeout=300)
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True, timeout=180)
    except Exception:
        logger.exception("Admin rebuild failed; serving the bundled admin if present")


def admin_static_dir() -> Path | None:
    refresh_admin_bundle()
    candidates = []
    for path in (ROOT_DIR / "frontend" / "dist", ROOT_DIR / "backend" / "static" / "admin"):
        index = path / "index.html"
        if index.is_file():
            candidates.append((index.stat().st_mtime, path))
    if not candidates:
        return None
    return max(candidates)[1]


admin_dir = admin_static_dir()
if admin_dir is not None:
    app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")

