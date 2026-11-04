from datetime import datetime, timezone

from app.services import calculate_delivery_at


def test_calculate_delivery_at_is_next_business_day():
    now = datetime(2026, 11, 2, 15, 30, tzinfo=timezone.utc)
    delivery = calculate_delivery_at(now)
    assert delivery == datetime(2026, 11, 3, 10, 0)

