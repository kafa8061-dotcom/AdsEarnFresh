import phonenumbers
from fastapi import HTTPException
from phonenumbers.phonenumberutil import region_code_for_country_code


def normalize_phone(region: str, number: str) -> tuple[str, str]:
    region = region.upper()
    if len(region) != 2 or not region.isalpha():
        raise HTTPException(status_code=422, detail="Select a valid country")
    try:
        parsed = phonenumbers.parse(number.strip(), region)
    except phonenumbers.NumberParseException as exc:
        raise HTTPException(status_code=422, detail="Enter a valid phone number") from exc
    if not phonenumbers.is_valid_number_for_region(parsed, region):
        raise HTTPException(status_code=422, detail="Enter a valid phone number for the selected country")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), f"+{parsed.country_code}"


def region_for_country_code(country_code: str) -> str:
    return region_code_for_country_code(int(country_code))
