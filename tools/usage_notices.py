"""Validate optional, word-level usage notices independently of list categories."""

from urllib.parse import urlsplit


def validate_usage_notices(rows):
    by_id = {}
    for row in rows:
        notice = row.get("usage_notice", "")
        url = row.get("usage_terms_page", "")
        if notice not in ("", "guidelines"):
            raise ValueError(f"{row['original']}: invalid usage_notice: {notice!r}")
        if url:
            try:
                parsed = urlsplit(url)
                valid = (parsed.scheme in ("http", "https") and parsed.hostname
                         and not parsed.username and not parsed.password
                         and not any(c.isspace() for c in url))
            except ValueError:
                valid = False
            if not valid or notice != "guidelines":
                raise ValueError(f"{row['original']}: invalid usage_terms_page")
        identity = (notice, url)
        if by_id.setdefault(row["id"], identity) != identity:
            raise ValueError(f"{row['original']}: usage notice differs between name forms")
