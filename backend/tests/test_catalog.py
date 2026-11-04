from datetime import datetime, timezone
from types import SimpleNamespace

from app.catalog import (
    SETTING_DEFAULTS,
    build_store_catalog,
    category_allows,
    category_menu_rows,
    compose_store_text,
    confirm_rows,
    legacy_category_index,
    parse_bool,
    parsed_store_settings,
    product_back_button,
    product_menu_rows,
    quantity_rows,
)
from app.models import PaymentStatus
from app.services import business_day_bounds, select_display_payment


def product(product_id, name, category, sort_order=0, stock=None, price="10"):
    return SimpleNamespace(
        id=product_id,
        name=name,
        category=category,
        sort_order=sort_order,
        stock_quantity=stock,
        total_usdt=price,
    )


def category(category_id, name, sort_order=0, is_visible=True):
    return SimpleNamespace(id=category_id, name=name, sort_order=sort_order, is_visible=is_visible)


def test_category_step_lists_visible_categories_in_sort_order():
    catalog = build_store_catalog(
        [
            product(1, "A", "Claude", sort_order=2),
            product(2, "B", "其他", sort_order=0),
            product(3, "隐藏商品", "内部", sort_order=0),
        ],
        [
            category(10, "其他", sort_order=1),
            category(11, "Claude", sort_order=0),
            category(12, "内部", sort_order=0, is_visible=False),
            category(13, "空分类", sort_order=0),
        ],
        show_categories=True,
    )
    assert catalog.mode == "categories"
    assert [item.name for item in catalog.categories] == ["Claude", "其他"]
    assert [item.id for item in catalog.products] == [2, 1]


def test_category_step_off_lists_visible_products_directly():
    catalog = build_store_catalog(
        [
            product(5, "后", "Claude", sort_order=2),
            product(4, "先", "Claude", sort_order=1),
            product(6, "隐藏", "内部"),
        ],
        [category(1, "Claude"), category(2, "内部", is_visible=False)],
        show_categories=False,
    )
    assert catalog.mode == "products"
    assert catalog.categories == ()
    assert [item.id for item in catalog.products] == [4, 5]


def test_unknown_category_stays_visible_until_it_is_managed():
    catalog = build_store_catalog(
        [product(1, "新品", "未建档")],
        [],
        show_categories=True,
    )
    assert catalog.mode == "categories"
    assert catalog.categories[0].name == "未建档"
    assert category_allows("未建档", []) is True
    assert category_allows("内部", [category(1, "内部", is_visible=False)]) is False


def test_store_text_puts_products_first_and_keeps_optional_welcome_on_the_same_message():
    assert compose_store_text(welcome_text="欢迎", prompt="请选择商品：", include_welcome=False) == "请选择商品："
    assert (
        compose_store_text(welcome_text="欢迎光临", prompt="请选择商品：", include_welcome=True)
        == "欢迎光临\n\n请选择商品："
    )
    assert compose_store_text(welcome_text="  ", prompt="请选择商品：", include_welcome=True) == "请选择商品："


def test_default_settings_keep_the_category_step_on():
    parsed = parsed_store_settings({})
    assert parsed["show_categories"] is True
    assert parsed["store_prompt"] == SETTING_DEFAULTS["store_prompt"]
    assert parsed_store_settings({"show_categories": "0"})["show_categories"] is False
    assert parse_bool(None, default=True) is True
    assert parse_bool("off") is False


def test_legacy_category_index_matches_the_previous_alphabetical_order():
    assert legacy_category_index(["Claude", "其他", "Claude"], 0) == "Claude"
    assert legacy_category_index(["Claude", "其他"], 1) == "其他"
    assert legacy_category_index(["Claude"], 3) is None


def test_keyboards_keep_orders_quantities_and_terms_confirmation():
    categories = category_menu_rows([category(7, "Claude")])
    assert categories[0][0]["callback_data"] == "cat:7"
    assert categories[-1][0]["callback_data"] == "orders"

    flat = product_menu_rows([product(3, "月卡", "Claude", price="0")], back_to_categories=False)
    assert flat[0][0]["text"].startswith("月卡 · 价格待确认")
    assert flat[-1][0]["text"] == "我的订单"
    assert "返回分类" not in [button["text"] for row in flat for button in row]

    nested = product_menu_rows([product(3, "月卡", "Claude")], back_to_categories=True)
    assert nested[-2][0]["text"] == "返回分类"

    back = product_back_button(show_categories=False, category_id=7)
    assert back == {"text": "返回商品列表", "callback_data": "products"}
    quantities = quantity_rows(3, back=product_back_button(show_categories=True, category_id=7))
    assert [button["text"] for button in quantities[0]] == ["1", "2", "5"]
    assert quantities[1][0]["callback_data"] == "cat:7"
    assert confirm_rows(3, 2)[0][0] == {"text": "同意条款并预约", "callback_data": "confirm:3:2"}


def test_business_day_bounds_follow_the_configured_timezone():
    start, end = business_day_bounds(datetime(2026, 11, 2, 23, 30, tzinfo=timezone.utc))
    assert start == datetime(2026, 11, 2, 0, 0)
    assert end == datetime(2026, 11, 3, 0, 0)


def test_display_payment_prefers_a_submitted_pending_hash():
    older = SimpleNamespace(id=1, status=PaymentStatus.SUCCEEDED, tx_hash="a" * 20)
    pending = SimpleNamespace(id=2, status=PaymentStatus.PENDING, tx_hash="b" * 20)
    assert select_display_payment([older, pending]) is pending
    assert select_display_payment([older]) is older
    assert select_display_payment([]) is None
