import pytest

from app.subscriptions import normalize_subscription, validate_status, validate_subscription_id


def test_validate_subscription_status_is_case_insensitive():
    assert validate_status("active") == "ACTIVE"
    assert validate_status(None) is None


def test_validate_subscription_status_rejects_unknown_values():
    with pytest.raises(ValueError):
        validate_status("PAYMENT_CAPTURE")


def test_validate_subscription_id_rejects_path_injection():
    with pytest.raises(ValueError):
        validate_subscription_id("../orders")


def test_normalize_subscription_omits_payment_source_and_shipping_data():
    raw = {
        "id": "I-ABC123456789",
        "status": "ACTIVE",
        "plan_id": "P-PLAN123",
        "subscriber": {
            "email_address": "buyer@example.com",
            "name": {"given_name": "Alex", "surname": "Morgan"},
            "shipping_address": {"address_line_1": "123 Secret Street"},
            "payment_source": {"card": {"last_digits": "1234"}},
        },
        "billing_info": {
            "next_billing_time": "2026-12-01T00:00:00Z",
            "failed_payments_count": 1,
            "last_payment": {"amount": {"currency_code": "USD", "value": "49.00"}, "time": "2026-10-01T00:00:00Z"},
            "last_failed_payment": {"reason_code": "PAYMENT_DENIED", "time": "2026-11-01T00:00:00Z"},
        },
        "payment_source": {"card": {"last_digits": "1234"}},
        "create_time": "2026-01-01T00:00:00Z",
    }
    result = normalize_subscription(raw, include_plan=True)
    assert result["subscriber"] == {"name": "Alex Morgan", "email_address": "buyer@example.com"}
    assert result["billing_info"]["failed_payments_count"] == 1
    assert "payment_source" not in result
    assert "shipping_address" not in result["subscriber"]
    assert result["billing_info"]["last_failed_payment"]["reason_code"] == "PAYMENT_DENIED"
