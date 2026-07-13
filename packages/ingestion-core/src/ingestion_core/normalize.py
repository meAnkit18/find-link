from __future__ import annotations

import re

import phonenumbers
import pycountry
from dateutil import parser as dateparser
from email_validator import EmailNotValidError, validate_email

from ingestion_core.canonical import ExtractedEntity, ExtractionResult


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


def normalize_date(raw: str) -> str | None:
    try:
        return dateparser.parse(raw, dayfirst=True).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def normalize_passport_number(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw).upper()


def normalize_iban(raw: str) -> str:
    return re.sub(r"\s", "", raw).upper()


def normalize_person_name(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw).strip()
    return " ".join(
        w.capitalize() if not (len(w) == 2 and w.endswith(".")) else w.upper()
        for w in cleaned.split(" ")
    )


def deterministic_key(entity: ExtractedEntity) -> str | None:
    t, attrs = entity.type.value, entity.attributes
    if t == "Email":
        v = normalize_email(attrs.get("address") or entity.name)
        return f"email:{v}" if v else None
    if t == "Phone":
        v = normalize_phone(attrs.get("number") or entity.name)
        return f"phone:{v}" if v else None
    if t == "Passport":
        raw = attrs.get("number") or entity.name
        v = normalize_passport_number(raw)
        return f"passport:{v}" if v else None
    if t == "BankAccount":
        raw = attrs.get("iban") or attrs.get("account_number") or entity.name
        v = normalize_iban(raw)
        return f"account:{v}" if v else None
    if t == "Vehicle":
        plate = attrs.get("plate") or attrs.get("registration")
        if plate:
            return f"vehicle:{re.sub(r'[^A-Z0-9]', '', plate.upper())}"
    if t == "Country":
        c = normalize_country(entity.name)
        return f"country:{c['iso2']}" if c else None
    return None


def normalize_extraction(result: ExtractionResult) -> ExtractionResult:
    for ent in result.entities:
        t, attrs = ent.type.value, ent.attributes

        if t == "Person":
            ent.name = normalize_person_name(ent.name)
            if dob := attrs.get("dob"):
                if norm := normalize_date(str(dob)):
                    attrs["dob"] = norm
        elif t == "Phone":
            if norm := normalize_phone(attrs.get("number") or ent.name):
                attrs["number"] = norm
                ent.name = norm
        elif t == "Email":
            if norm := normalize_email(attrs.get("address") or ent.name):
                attrs["address"] = norm
                ent.name = norm
        elif t == "Passport":
            raw = attrs.get("number") or ent.name
            attrs["number"] = normalize_passport_number(raw)
            ent.name = attrs["number"]
            for k in ("issue_date", "expiry_date", "dob"):
                if k in attrs and (norm := normalize_date(str(attrs[k]))):
                    attrs[k] = norm
        elif t == "Country":
            if c := normalize_country(ent.name):
                ent.name, attrs["iso2"] = c["name"], c["iso2"]
        elif t == "BankAccount":
            raw = attrs.get("iban") or attrs.get("account_number") or ent.name
            attrs["iban"] = normalize_iban(raw)
            ent.name = attrs["iban"]
        elif t in ("Company", "Organization"):
            ent.name = re.sub(r"\s+", " ", ent.name).strip()
        elif t == "Address":
            ent.name = re.sub(r"\s+", " ", ent.name).strip().title()
    return result
