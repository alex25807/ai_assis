from __future__ import annotations

import re

_PHONE_RE = re.compile(r"\d+")


def normalize_phone(raw: str) -> str | None:
    """Return +7XXXXXXXXXX or None if the number is unusable."""
    digits = "".join(_PHONE_RE.findall(raw or ""))
    if not digits:
        return None

    if len(digits) == 11 and digits[0] in {"7", "8"}:
        national = digits[1:]
    elif len(digits) == 10:
        national = digits
    else:
        return None

    if len(national) != 10:
        return None
    if set(national) == {"0"}:
        return None
    if len(set(national)) == 1:
        return None
    if national.startswith("000"):
        return None
    return "+7" + national


def is_valid_name(raw: str) -> bool:
    text = (raw or "").strip()
    if len(text) < 2:
        return False
    if normalize_phone(text):
        return False
    if re.search(r"0{6,}", text):
        return False
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", text)
    return len(letters) >= 2


def is_valid_address(raw: str) -> bool:
    text = (raw or "").strip()
    if len(text) < 5:
        return False
    if re.fullmatch(r"[\d\s\-\+\(\)]+", text):
        return False
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", text)
    return len(letters) >= 3
