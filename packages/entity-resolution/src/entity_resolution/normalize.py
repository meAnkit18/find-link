from __future__ import annotations

import re

import phonenumbers
import pycountry
from email_validator import EmailNotValidError, validate_email


def normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    try:
        num = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def normalize_email(raw: str) -> str | None:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return None


def normalize_passport_number(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw).upper()


def normalize_iban(raw: str) -> str:
    return re.sub(r"\s", "", raw).upper()


def normalize_country(raw: str) -> dict | None:
    raw = raw.strip()
    try:
        found = pycountry.countries.lookup(raw)
        return {"name": found.name, "iso2": found.alpha_2}
    except LookupError:
        results = pycountry.countries.search_fuzzy(raw) if len(raw) > 3 else []
        if results:
            return {"name": results[0].name, "iso2": results[0].alpha_2}
    return None


def compute_deterministic_key(entity_type: str, payload: dict) -> str | None:
    if entity_type == "email":
        v = normalize_email(payload.get("address") or payload.get("label", ""))
        return f"email:{v}" if v else None
    if entity_type == "phone":
        v = normalize_phone(payload.get("number") or payload.get("label", ""))
        return f"phone:{v}" if v else None
    if entity_type == "passport":
        raw = payload.get("number") or payload.get("label", "")
        v = normalize_passport_number(raw)
        return f"passport:{v}" if v else None
    if entity_type == "bank_account":
        raw = payload.get("iban") or payload.get("account_number") or payload.get("label", "")
        v = normalize_iban(raw)
        return f"account:{v}" if v else None
    if entity_type == "vehicle":
        plate = payload.get("plate") or payload.get("registration")
        if plate:
            return f"vehicle:{re.sub(r'[^A-Z0-9]', '', plate.upper())}"
    if entity_type == "country":
        c = normalize_country(payload.get("label", ""))
        return f"country:{c['iso2']}" if c else None
    return None
