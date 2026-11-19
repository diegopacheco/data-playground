import pytest

from order_counter.config import load


def test_credentials_come_from_the_strimzi_secret_env() -> None:
    settings = load({"KAFKA_BOOTSTRAP": "b:9092", "KAFKA_USER": "order-consumer", "KAFKA_PASSWORD": "p"})
    assert settings.user == "order-consumer"
    assert settings.password == "p"
    assert settings.topic == "orders"
    assert settings.group == "order-counter"


def test_missing_password_fails_fast_instead_of_connecting_anonymously() -> None:
    with pytest.raises(ValueError, match="KAFKA_PASSWORD"):
        load({"KAFKA_BOOTSTRAP": "b:9092", "KAFKA_USER": "order-consumer"})
