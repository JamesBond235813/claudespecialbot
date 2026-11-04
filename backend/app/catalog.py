from dataclasses import dataclass
from decimal import Decimal


SETTING_DEFAULTS = {
    "show_categories": "0",
    "welcome_text": "",
    "store_prompt": "请选择需要预约的数字服务：",
    "product_prompt": "请选择商品：",
    "terms_text": "",
}

CATEGORY_STEP_ROLLOUT_KEY = "category_step_rollout"

DEFAULT_TERMS = (
    "1. 商品内容、价格与交付时间以下单页为准。\n"
    "2. 预约后如需取消或退款，请在交付前联系支持。\n"
    "3. 因不可抗力无法按时交付时，将提供改期或退款方案。\n"
    "4. 客户应确保所购买和使用的具体服务符合适用规则与法律。"
)

QUANTITY_CHOICES = (1, 2, 5)


def format_usdt(amount) -> str:
    value = format(Decimal(amount), "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def parse_bool(value: str | bool | None, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parsed_store_settings(raw: dict[str, str] | None) -> dict:
    data = dict(SETTING_DEFAULTS)
    if raw:
        data.update({key: value for key, value in raw.items() if key in SETTING_DEFAULTS})
    return {
        "show_categories": parse_bool(data.get("show_categories"), default=False),
        "welcome_text": (data.get("welcome_text") or "").strip(),
        "store_prompt": (data.get("store_prompt") or SETTING_DEFAULTS["store_prompt"]).strip(),
        "product_prompt": (data.get("product_prompt") or SETTING_DEFAULTS["product_prompt"]).strip(),
        "terms_text": (data.get("terms_text") or "").strip(),
    }


def category_step_rollout(already_applied: bool) -> dict[str, str] | None:
    """Turn the category step off once on upgrade, then leave the switch alone."""
    if already_applied:
        return None
    return {"show_categories": "0", CATEGORY_STEP_ROLLOUT_KEY: "1"}


def compose_store_text(*, welcome_text: str, prompt: str, include_welcome: bool) -> str:
    chunks = []
    if include_welcome and welcome_text.strip():
        chunks.append(welcome_text.strip())
    chunks.append(prompt.strip() or SETTING_DEFAULTS["store_prompt"])
    return "\n\n".join(chunks)


def category_allows(category_name: str, categories) -> bool:
    match = next((category for category in categories if category.name == category_name), None)
    if match is None:
        return True
    return bool(match.is_visible)


def legacy_category_index(names: list[str], index: int) -> str | None:
    ordered = sorted(set(names))
    if index < 0 or index >= len(ordered):
        return None
    return ordered[index]


def _sort_order(item) -> int:
    value = getattr(item, "sort_order", 0)
    return 0 if value is None else value


@dataclass(frozen=True)
class StoreCatalog:
    mode: str
    categories: tuple
    products: tuple


def build_store_catalog(products, categories, *, show_categories: bool) -> StoreCatalog:
    by_name = {category.name: category for category in categories}
    visible_products = tuple(
        sorted(
            (
                product
                for product in products
                if category_allows(product.category, categories)
            ),
            key=lambda product: (_sort_order(product), product.id),
        )
    )
    if not show_categories:
        return StoreCatalog(mode="products", categories=(), products=visible_products)

    names = {product.category for product in visible_products}
    visible_categories = []
    for name in names:
        category = by_name.get(name)
        if category is None:
            visible_categories.append(_SyntheticCategory(name))
        elif category.is_visible:
            visible_categories.append(category)
    visible_categories.sort(key=lambda category: (_sort_order(category), category.name))
    return StoreCatalog(
        mode="categories",
        categories=tuple(visible_categories),
        products=visible_products,
    )


class _SyntheticCategory:
    def __init__(self, name: str) -> None:
        self.id = None
        self.name = name
        self.sort_order = 0
        self.is_visible = True


def category_menu_rows(categories) -> list[list[dict[str, str]]]:
    rows = []
    for index, category in enumerate(categories):
        callback = f"cat:{category.id}" if category.id else f"category:{index}"
        rows.append([{"text": f"📁 {category.name}", "callback_data": callback}])
    rows.append([{"text": "我的订单", "callback_data": "orders"}])
    return rows


def product_button_text(product) -> str:
    stock = "库存充足" if product.stock_quantity is None else f"库存 {product.stock_quantity}"
    price = "价格待确认" if Decimal(product.total_usdt) == 0 else f"{format_usdt(product.total_usdt)} USDT"
    return f"{product.name} · {price} · {stock}"


def product_menu_rows(products, *, back_to_categories: bool) -> list[list[dict[str, str]]]:
    rows = [
        [{"text": product_button_text(product), "callback_data": f"product:{product.id}"}]
        for product in products
    ]
    if back_to_categories:
        rows.append([{"text": "返回分类", "callback_data": "products"}])
    rows.append([{"text": "我的订单", "callback_data": "orders"}])
    return rows


def product_back_button(*, show_categories: bool, category_id: int | None) -> dict[str, str]:
    if show_categories and category_id:
        return {"text": "返回分类", "callback_data": f"cat:{category_id}"}
    if show_categories:
        return {"text": "返回分类", "callback_data": "products"}
    return {"text": "返回商品列表", "callback_data": "products"}


def quantity_rows(product_id: int, *, back: dict[str, str]) -> list[list[dict[str, str]]]:
    choices = [
        {"text": str(quantity), "callback_data": f"quantity:{product_id}:{quantity}"}
        for quantity in QUANTITY_CHOICES
    ]
    return [choices, [back]]


def confirm_rows(product_id: int, quantity: int) -> list[list[dict[str, str]]]:
    return [
        [{"text": "同意条款并预约", "callback_data": f"confirm:{product_id}:{quantity}"}],
        [{"text": "返回商品", "callback_data": f"product:{product_id}"}],
    ]
