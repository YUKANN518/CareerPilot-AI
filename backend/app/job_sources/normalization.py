import hashlib
import html
import ipaddress
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from pydantic import JsonValue

from app.job_sources.types import RawJob, SourceAdapterError
from app.schemas.jobs import NormalizedJob


def validate_network_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceAdapterError("INVALID_SOURCE_URL", "Source URL must use HTTP or HTTPS")
    if parsed.username or parsed.password:
        raise SourceAdapterError("INVALID_SOURCE_URL", "Source URL must not contain credentials")

    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise SourceAdapterError("UNSAFE_SOURCE_URL", "Local network source URLs are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return url
    if not address.is_global:
        raise SourceAdapterError("UNSAFE_SOURCE_URL", "Private network source URLs are not allowed")
    return url


def normalize_source_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    hostname = parsed.hostname.casefold()
    port = parsed.port
    netloc = hostname if port in {None, 80, 443} else f"{hostname}:{port}"
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query, ""))


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = html.unescape(html.unescape(str(value)))
    if re.search(r"</?[a-zA-Z][^>]*>", text):
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    cleaned = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _salary_pair(raw: RawJob) -> tuple[Decimal | None, Decimal | None]:
    salary_min = _decimal(raw.get("salary_min"))
    salary_max = _decimal(raw.get("salary_max"))
    if salary_min is not None or salary_max is not None:
        return salary_min, salary_max
    salary_text = _clean_text(raw.get("salary"))
    if salary_text is None:
        return None, None
    values = re.findall(r"\d[\d,]*(?:\.\d+)?", salary_text)
    parsed = [_decimal(value) for value in values[:2]]
    return (
        parsed[0] if parsed else None,
        parsed[1] if len(parsed) > 1 else parsed[0] if parsed else None,
    )


def _datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            parsed = None
            for pattern in ("%d/%m/%Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
                try:
                    parsed = datetime.strptime(str(value).strip(), pattern)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return None
    assert parsed is not None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else re.split(r"[,;|/]", str(value))
    return [cleaned for item in values if (cleaned := _clean_text(item)) is not None]


def _json_safe(raw: RawJob) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], json.loads(json.dumps(raw, default=str)))


def normalize_job_record(source_id: int | None, raw: RawJob) -> NormalizedJob:
    title = _clean_text(raw.get("title"))
    company = _clean_text(raw.get("company"))
    description = _clean_text(raw.get("description"))
    if title is None or company is None or description is None:
        raise SourceAdapterError(
            "INVALID_JOB_RECORD",
            "A job record requires title, company, and description",
        )

    location = _clean_text(raw.get("location"))
    responsibilities = _clean_text(raw.get("responsibilities"))
    requirements = _clean_text(raw.get("requirements"))
    salary_min, salary_max = _salary_pair(raw)
    source_url = _clean_text(raw.get("source_url"))
    normalized_url = normalize_source_url(source_url)
    canonical = {
        "title": title.casefold(),
        "company": company.casefold(),
        "location": (location or "").casefold(),
        "description": description,
        "responsibilities": responsibilities or "",
        "requirements": requirements or "",
    }
    content_hash = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    currency = _clean_text(raw.get("currency"))

    return NormalizedJob(
        source_id=source_id,
        external_job_id=_clean_text(raw.get("external_job_id")),
        title=title,
        company=company,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency.upper() if currency else None,
        employment_type=_clean_text(raw.get("employment_type")),
        experience_level=_clean_text(raw.get("experience_level")),
        education_requirement=_clean_text(raw.get("education_requirement")),
        language_requirements=_string_list(raw.get("language_requirements")),
        description=description,
        responsibilities=responsibilities,
        requirements=requirements,
        source_url=source_url,
        normalized_source_url=normalized_url,
        published_at=_datetime(raw.get("published_at")),
        content_hash=content_hash,
        raw_data=_json_safe(raw),
        status=_clean_text(raw.get("status")) or "ACTIVE",
    )
