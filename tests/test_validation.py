from bot.validation import is_valid_address, is_valid_name, normalize_phone


def test_accepts_russian_mobile_formats() -> None:
    assert normalize_phone("+7 914 497-60-60") == "+79144976060"
    assert normalize_phone("8 (914) 497 60 60") == "+79144976060"
    assert normalize_phone("79144976060") == "+79144976060"
    assert normalize_phone("9144976060") == "+79144976060"


def test_rejects_zero_and_short_phones() -> None:
    assert normalize_phone("0000000") is None
    assert normalize_phone("0000000000") is None
    assert normalize_phone("1111111111") is None
    assert normalize_phone("123") is None
    assert normalize_phone("") is None


def test_name_rejects_phone_dump() -> None:
    assert is_valid_name("Александр")
    assert not is_valid_name("Александр, 0000000")
    assert not is_valid_name("+79144976060")
    assert not is_valid_name("А")


def test_address_needs_real_text() -> None:
    assert is_valid_address("Чита, ул. Бабушкина, 153")
    assert not is_valid_address("кв.")
    assert not is_valid_address("0000000")
