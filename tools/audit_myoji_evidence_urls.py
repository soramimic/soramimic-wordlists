#!/usr/bin/env python3
"""Fetch and mechanically audit URLs in the myoji evidence ledger.

This is deliberately independent of the evidence ledger: it writes a separate,
resumable report and never changes the input file.
"""

import argparse
import bisect
import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit

KATA2HIRA = str.maketrans(
    {chr(c): chr(c - 0x60) for c in range(ord("ァ"), ord("ヶ") + 1)}
)
SCHEMA_VERSION = 3
_UNFETCHED = object()
DICT_HOSTS = (
    "name-power.net",
    "myoji-yurai.net",
    "myoji.jitenon.jp",
    "namedic.jp",
    "name.sijisuru.com",
    "japanese-names.info",
    "kakijun.com",
    "kanji.reader.bz",
    "tangorin.com",
    "kanshudo.com",
    "kanji.red",
    "enamae.net",
    "myoujijiten.web.fc2.com",
    "namaenomori.com",
)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style", "noscript", "template"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style", "noscript", "template") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalize(value):
    """Normalize HTML/PDF text and query strings for exact containment checks."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", html.unescape(value or "")))


def _token_line(value):
    """Normalize whitespace while retaining token separators for boundary checks."""
    value = unicodedata.normalize("NFKC", html.unescape(value or ""))
    # ``pdftotext -layout`` sometimes emits furigana one glyph at a time
    # (``た い よ う じ`` or ``こん だ い じ``).  Join only sequences with
    # at least two trailing one-glyph kana tokens.  Ordinary person-name
    # tokens such as ``コンダイジ ハルミ`` therefore keep their boundary.
    kana = r"ぁ-ゖァ-ヺー"
    spaced_kana = re.compile(
        rf"(?<![{kana}])([{kana}]{{1,2}}(?: [{kana}]){{2,}})(?! ?[{kana}])"
    )
    value = spaced_kana.sub(lambda match: match.group(1).replace(" ", ""), value)
    value = re.sub(r"\s+", " ", value).strip()
    # OCR/PDF table extraction may split a kanji name as ``団 村``.  Remove
    # only spaces between Han glyphs; kana spaces still delimit surname and
    # given-name readings (``ダンムラ ハナ``).
    return re.sub(r"(?<=[㐀-䶿一-鿿豈-﫿々〆]) (?=[㐀-䶿一-鿿豈-﫿々〆])", "", value)


def _is_kana(ch):
    return bool(ch) and ("ぁ" <= ch <= "ゖ" or "ァ" <= ch <= "ヺ" or ch == "ー")


def _parenthetical_full_name_match(text, surface, reading):
    """Find a full kanji name and its parenthetical full reading.

    Some official rosters write ``倉野内直子（くらのうちなおこ）``.  The
    surname reading is consequently embedded in the person's full reading,
    but the adjacent kanji name and parenthetical kana provide a structural
    pairing that an arbitrary longer kana substring does not.  Return the
    matching context, or ``None`` when that pairing is absent.
    """
    if not surface or not reading:
        return None
    reading_hira = reading.translate(KATA2HIRA)
    kanji = r"[㐀-䶿一-鿿豈-﫿々〆]"
    kana = r"[ぁ-ゖァ-ヺー]"
    pattern = re.compile(
        rf"(?P<full_surface>{kanji}+)[ \t]*[（(][ \t]*(?P<full_reading>{kana}+)[ \t]*[）)]"
    )
    for line in text.splitlines():
        candidate = _token_line(line)
        match = pattern.search(candidate)
        if not match:
            continue
        full_surface = match.group("full_surface")
        full_reading = match.group("full_reading")
        if not full_surface.startswith(surface) or len(full_surface) <= len(surface):
            continue
        if not (
            full_reading.startswith(reading)
            or full_reading.translate(KATA2HIRA).startswith(reading_hira)
        ):
            continue
        if len(full_reading) <= len(reading):
            continue
        return {
            "context": candidate[max(0, match.start() - 100) : match.end() + 100],
            "matched_reading_token": full_reading,
        }
    return None


def dictionary_host(url):
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in DICT_HOSTS)


def _html_text(body, content_type):
    charset = None
    m = re.search(
        r"charset\s*=\s*[\"']?([^;\s\"']+)", content_type or "", re.IGNORECASE
    )
    if m:
        charset = m.group(1)
    # Some older Japanese university/profile pages omit the HTTP charset and
    # use ISO-2022-JP escape sequences.  A strict UTF-8/CP932-only fallback
    # turns those pages into literal ``ESC $ B`` gibberish and hides names.
    fallbacks = (
        ["iso2022_jp", "utf-8", "cp932", "euc_jp"]
        if b"\x1b$" in body
        else ["utf-8", "iso2022_jp", "cp932", "euc_jp"]
    )
    for enc in ([charset] if charset else []) + fallbacks:
        try:
            decoded = body.decode(enc)
            break
        except (LookupError, UnicodeDecodeError):
            pass
    else:
        decoded = body.decode("utf-8", "replace")
    p = _Text()
    p.feed(decoded)
    return "\n".join(p.parts)


def _curl_resolve_args(url):
    """Validate one HTTPS hop and pin curl to its public DNS answers."""
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as exc:
        raise RuntimeError(f"unsafe_url: {exc}") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise RuntimeError("unsafe_url: public HTTPS URL required")
    try:
        ascii_host = host.encode("idna").decode("ascii")
        answers = socket.getaddrinfo(ascii_host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"unsafe_url: DNS resolution failed: {exc}") from exc
    addresses = sorted({answer[4][0] for answer in answers})
    if not addresses:
        raise RuntimeError("unsafe_url: DNS returned no addresses")
    parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    if any(not address.is_global for address in parsed_addresses):
        raise RuntimeError("unsafe_url: private or non-global address")
    args = []
    for address in addresses:
        value = f"[{address}]" if ":" in address else address
        args.extend(("--resolve", f"{ascii_host}:{port}:{value}"))
    return args


def fetch_document(url, timeout=20):
    # ``urlopen(..., timeout=...)`` does not impose a hard wall-clock bound on
    # every DNS/TLS/body-read path.  A single stuck response can therefore
    # keep a ThreadPoolExecutor alive indefinitely.  curl's process-level
    # max-time is a real upper bound, and max-filesize also prevents an
    # accidental unbounded download.
    with tempfile.TemporaryDirectory(prefix="myoji-fetch-") as directory:
        body_path = Path(directory) / "body"
        deadline = time.monotonic() + max(1.0, float(timeout))
        current_url = url
        metadata = None
        for redirect_count in range(11):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("curl_timeout_across_redirects")
            resolve_args = _curl_resolve_args(current_url)
            proc = subprocess.run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--proto",
                    "=https",
                    "--proto-redir",
                    "=https",
                    # A number of otherwise ordinary result pages intermittently
                    # terminate HTTP/2 streams with curl exit 92.  The audit is a
                    # bulk archival fetch, not a latency-sensitive browser, so use
                    # the more broadly reliable HTTP/1.1 path and let curl retry
                    # transient transport failures within the same hard deadline.
                    "--http1.1",
                    "--retry",
                    "2",
                    "--retry-delay",
                    "1",
                    "--retry-all-errors",
                    "--max-time",
                    str(max(1.0, remaining)),
                    "--connect-timeout",
                    str(max(1.0, min(remaining, 10.0))),
                    "--max-filesize",
                    str(50 * 1024 * 1024),
                    "--user-agent",
                    "Mozilla/5.0 (compatible; myoji-evidence-audit/1.0)",
                    "--header",
                    "Accept: text/html,application/pdf",
                    "--output",
                    str(body_path),
                    "--write-out",
                    "%{json}",
                    *resolve_args,
                    current_url,
                ],
                capture_output=True,
                timeout=max(2.0, remaining + 5.0),
                check=False,
            )
            if proc.returncode:
                detail = proc.stderr.decode("utf-8", "replace").strip()
                raise RuntimeError(f"curl_exit_{proc.returncode}: {detail}")
            metadata = json.loads(proc.stdout.decode("utf-8", "replace"))
            status = int(metadata.get("response_code") or 0)
            redirect_url = str(metadata.get("redirect_url") or "")
            if 300 <= status < 400 and redirect_url:
                current_url = urljoin(current_url, redirect_url)
                continue
            break
        else:
            raise RuntimeError("too_many_redirects")
        body = body_path.read_bytes()
    assert metadata is not None
    status = int(metadata.get("response_code") or 0)
    final_url = str(metadata.get("url_effective") or current_url)
    content_type = str(metadata.get("content_type") or "")
    content_type_lower = content_type.lower()
    is_pdf = "pdf" in content_type_lower or (
        urlsplit(final_url).path.lower().endswith(".pdf")
        and not content_type_lower.startswith(("text/", "application/json"))
    )
    if is_pdf:
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", "-", "-"],
                input=body,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            if proc.returncode:
                raise RuntimeError(f"pdftotext_exit_{proc.returncode}")
            text = proc.stdout.decode("utf-8", "replace")
        except FileNotFoundError:
            raise RuntimeError("pdftotext_unavailable")
    else:
        text = _html_text(body, content_type)
    return {
        "http_status": status,
        "final_url": final_url,
        "content_type": content_type,
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "text": text,
    }


def _base(row, number):
    return {
        "schema_version": SCHEMA_VERSION,
        "row_number": number,
        "surface": row.get("surface", ""),
        "pronunciation": row.get("pronunciation", ""),
        "source_url": row.get("source_url", ""),
        "ledger_status": row.get("status", ""),
        "audit_result": "error",
        "reason": "",
        "http_status": None,
        "final_url": "",
        "content_type": "",
        "content_sha256": "",
        "surface_found": False,
        "reading_found": False,
        "min_distance": None,
        "match_context": "",
        "reading_token_boundary": None,
        "matched_reading_token": "",
        "completed": True,
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


def _occurrences(text, needle):
    if not needle:
        return []
    result = []
    start = 0
    while True:
        at = text.find(needle, start)
        if at < 0:
            return result
        result.append((at, at + len(needle)))
        start = at + 1


def _near_match(text, surface, reading, max_distance):
    """Return nearest pair, requiring one line or a sufficiently small gap."""
    # Keep kana token boundaries while joining PDF-split kanji surnames.
    lines = [_token_line(line) for line in text.splitlines()]
    compact = "\n".join(lines)
    s_occ = _occurrences(compact, surface)
    raw_r_occ = [
        (a, b, compact[a:b])
        for needle in (reading, reading.translate(KATA2HIRA))
        for a, b in _occurrences(compact, needle)
    ]
    r_occ = []
    embedded = False
    for a, b, token in raw_r_occ:
        boundary = not (_is_kana(compact[a - 1 : a]) or _is_kana(compact[b : b + 1]))
        if boundary:
            r_occ.append((a, b, token))
        else:
            embedded = True
    if not s_occ or not r_occ:
        parenthetical = _parenthetical_full_name_match(text, surface, reading)
        if parenthetical:
            return {
                "min_distance": 0,
                "match_context": parenthetical["context"],
                "near": True,
                "reading_token_boundary": True,
                "matched_reading_token": parenthetical["matched_reading_token"],
            }
        return {
            "min_distance": None,
            "match_context": "",
            "near": False,
            "reading_token_boundary": False if embedded else None,
            "matched_reading_token": raw_r_occ[0][2] if raw_r_occ else "",
        }
    # A roster can contain the same place/name thousands of times.  Comparing
    # every surface occurrence with every reading occurrence is quadratic and
    # allowed a single large municipal PDF to pin one worker indefinitely.
    # For a fixed surface, the nearest interval must be adjacent by start
    # position; inspect those neighbours, plus all readings on the same line
    # because same-line evidence intentionally has priority over distance.
    newlines = [i for i, ch in enumerate(compact) if ch == "\n"]

    def line_at(position):
        return bisect.bisect_right(newlines, position)

    readings = sorted(r_occ, key=lambda item: item[0])
    reading_starts = [item[0] for item in readings]
    readings_by_line = {}
    for item in readings:
        readings_by_line.setdefault(line_at(item[0]), []).append(item)
    reading_starts_by_line = {
        line: [item[0] for item in items] for line, items in readings_by_line.items()
    }

    best = None
    best_score = None
    for ss, se in s_occ:
        same_line_readings = readings_by_line.get(line_at(ss), ())
        same_line_starts = reading_starts_by_line.get(line_at(ss), ())
        line_at_position = bisect.bisect_left(same_line_starts, ss)
        candidates = list(
            same_line_readings[max(0, line_at_position - 2) : line_at_position + 2]
        )
        at = bisect.bisect_left(reading_starts, ss)
        candidates.extend(readings[max(0, at - 2) : at + 2])
        seen = set()
        for rs, re_, token in candidates:
            occurrence = (rs, re_, token)
            if occurrence in seen:
                continue
            seen.add(occurrence)
            same_line = line_at(ss) == line_at(rs)
            gap = 0 if ss <= re_ and rs <= se else max(rs - se, ss - re_)
            candidate = (gap, same_line, min(ss, rs), max(se, re_), token)
            score = (0 if same_line else 1, gap)
            if best is None or score < best_score:
                best, best_score = candidate, score
    gap, same_line, begin, end, _token = best
    if not same_line and gap > max_distance:
        return {
            "min_distance": gap,
            "match_context": "",
            "near": False,
            "reading_token_boundary": True,
            "matched_reading_token": best[4],
        }
    context = compact[max(0, begin - 100) : min(len(compact), end + 100)].replace(
        "\n", " "
    )
    return {
        "min_distance": gap,
        "match_context": context,
        "near": True,
        "reading_token_boundary": True,
        "matched_reading_token": best[4],
    }


def audit_row(row, number, timeout=20, delay=0.0, max_distance=120, fetched=_UNFETCHED):
    """Audit one candidate/URL pair.

    ``fetched`` is an internal fast path used by the negative-result auditor:
    several candidates often share the same search-result URL, so the caller
    can fetch it once and evaluate the same document for every candidate.  An
    exception value replays one shared fetch failure without refetching.
    """
    out = _base(row, number)
    url = row.get("source_url", "")
    if not url:
        out.update(audit_result="skip", reason="missing_source_url")
        return out
    if dictionary_host(url):
        out.update(audit_result="reject", reason="surname_dictionary_host")
        return out
    try:
        if fetched is _UNFETCHED:
            if delay:
                time.sleep(max(0.0, delay))
            fetched = fetch_document(url, timeout=timeout)
        elif isinstance(fetched, BaseException):
            raise fetched
        out.update(
            {
                k: fetched[k]
                for k in ("http_status", "final_url", "content_type", "content_sha256")
            }
        )
        if dictionary_host(out["final_url"]):
            out.update(audit_result="reject", reason="surname_dictionary_redirect")
            return out
        text = "\n".join(normalize(line) for line in fetched["text"].splitlines())
        surface = normalize(row.get("surface", ""))
        reading = normalize(row.get("pronunciation", ""))
        sf = bool(surface) and surface in text
        rf = bool(reading) and (reading in text or reading.translate(KATA2HIRA) in text)
        out.update(surface_found=sf, reading_found=rf)
        near = (
            _near_match(fetched["text"], surface, reading, max_distance)
            if sf and rf
            else None
        )
        if near:
            out.update(
                min_distance=near["min_distance"],
                match_context=near["match_context"],
                reading_token_boundary=near["reading_token_boundary"],
                matched_reading_token=near["matched_reading_token"],
            )
        if out["http_status"] >= 400:
            out.update(audit_result="fail", reason=f"http_status_{out['http_status']}")
        elif sf and rf and near and near["near"] and near["reading_token_boundary"]:
            out.update(audit_result="pass", reason="surface_and_reading_nearby")
        elif sf and rf and near and near["reading_token_boundary"] is False:
            out.update(audit_result="fail", reason="reading_embedded_in_longer_kana")
        elif sf and rf:
            out.update(audit_result="fail", reason="surface_and_reading_far_apart")
        elif not sf and not rf:
            out.update(audit_result="fail", reason="surface_and_reading_missing")
        elif not sf:
            out.update(audit_result="fail", reason="surface_missing")
        else:
            out.update(audit_result="fail", reason="reading_missing")
    except HTTPError as exc:
        # HTTPError is also a response: preserve its status and final URL so
        # failed pages remain diagnosable and resumable.
        out.update(
            http_status=int(exc.code),
            final_url=getattr(exc, "url", url),
            audit_result="fail",
            reason=f"http_status_{exc.code}",
        )
    except Exception as exc:
        out.update(audit_result="error", reason=f"{type(exc).__name__}: {exc}")
    return out


def _load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if line.strip():
                rows.append((i, json.loads(line)))
    return rows


def _load_checkpoint(path):
    done = {}
    if not path.exists():
        return done
    # Discard a crash-truncated final line; complete lines remain usable.
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raw = raw[: raw.rfind(b"\n") + 1] if b"\n" in raw else b""
        path.write_bytes(raw)
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get("schema_version") == SCHEMA_VERSION:
                done[int(item["row_number"])] = item
    return done


def _save(path, done):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for number in sorted(done):
                f.write(
                    json.dumps(done[number], ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
        raise


def _fingerprint(row):
    return (
        row.get("surface", ""),
        row.get("pronunciation", ""),
        row.get("source_url", ""),
    )


def run(
    input_path,
    output_path,
    workers=4,
    delay=0.0,
    timeout=20,
    limit=None,
    max_distance=120,
    retry_errors=False,
):
    rows = _load(Path(input_path))
    rows = rows[:limit] if limit is not None else rows
    path = Path(output_path)
    done = _load_checkpoint(path)
    current = {number: row for number, row in rows}
    # Row numbers are only positional.  A pass-only ledger can compact after
    # rejected evidence is removed, so reuse a checkpoint only when the
    # evidence identity still matches the row now occupying that position.
    done = {
        number: item
        for number, item in done.items()
        if number in current and _fingerprint(item) == _fingerprint(current[number])
    }
    if retry_errors:
        done = {
            number: item
            for number, item in done.items()
            if item.get("audit_result") != "error"
        }
    pending = [(n, r) for n, r in rows if n not in done]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [
            pool.submit(audit_row, row, n, timeout, delay, max_distance)
            for n, row in pending
        ]
        for future in as_completed(futures):
            item = future.result()
            done[item["row_number"]] = item
            _save(path, done)
    return len(done), len(pending)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=Path("tools/myoji_web_evidence.jsonl"))
    p.add_argument(
        "--output", type=Path, default=Path("myoji_web_evidence_url_audit.jsonl")
    )
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--delay", type=float, default=0.0)
    p.add_argument("--timeout", type=float, default=20)
    p.add_argument("--limit", type=int)
    p.add_argument("--max-distance", type=int, default=120)
    p.add_argument("--retry-errors", action="store_true")
    a = p.parse_args()
    n, processed = run(
        a.input,
        a.output,
        a.workers,
        a.delay,
        a.timeout,
        a.limit,
        a.max_distance,
        a.retry_errors,
    )
    print(f"checkpoint={a.output} rows={n} processed={processed}")


if __name__ == "__main__":
    main()
