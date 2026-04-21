from __future__ import annotations

import hashlib
import mimetypes
import os
import posixpath
import re
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://hotelcantodochafariz.com.br/"
ROOT_DIR = Path(r"c:\Users\kaita\Downloads\hotel-site-localhost")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"

START_PAGES = [
    "/",
    "/Index.aspx",
    "/Hotel.aspx",
    "/Acomodacoes.aspx",
    "/Galeria.aspx",
    "/Atrativos.aspx",
    "/Vesperata.aspx",
    "/Localizacao.aspx",
    "/Contato.aspx",
    "/checkin",
]

URL_PATTERN = re.compile(
    r"(?:href|src|action)=['\"]([^'\"]+)['\"]|url\(([^)]+)\)",
    re.IGNORECASE,
)
PAGE_EXTENSIONS = {"", ".aspx", ".html", ".htm"}
ASSET_EXTENSIONS = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".map",
    ".axd",
    ".ashx",
}


def fetch_resource(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request) as response:
        content_type = response.headers.get_content_type().lower()
        return response.read(), content_type


def iter_urls(text: str) -> Iterable[tuple[str, str]]:
    for match in URL_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2) or ""
        cleaned = unescape(raw.strip().strip("'\"")).strip()
        if cleaned:
            yield raw, cleaned


def normalize_url(raw_url: str, source_url: str) -> str | None:
    if raw_url.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    absolute = urljoin(source_url, raw_url)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc and parsed.netloc.lower() != "hotelcantodochafariz.com.br":
        return None
    return absolute


def page_filename(path: str) -> str:
    clean_path = path.strip("/")
    if clean_path == "":
        return "index.html"
    name = clean_path.replace("/", "-")
    stem, _ext = os.path.splitext(name)
    return f"{stem or 'index'}.html"


def local_path_from_url(url: str, content_type: str | None = None) -> Path:
    parsed = urlparse(url)
    path = parsed.path or "/"
    ext = Path(path).suffix.lower()

    if path.lower().endswith("/captcha.aspx") or path.lower() == "/captcha.aspx":
        return ROOT_DIR / "Captcha.png"

    if content_type and content_type.startswith("image/") and ext not in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}:
        guessed_ext = mimetypes.guess_extension(content_type) or ".bin"
        ext = guessed_ext
        path = f"{path}{guessed_ext}"

    if ext in PAGE_EXTENSIONS and not any(seg in path.lower() for seg in ("/img/", "/css/", "/js/", "/fonts/")):
        local_name = page_filename(path)
        return ROOT_DIR / local_name

    relative_path = path.lstrip("/") or "index.html"
    target = ROOT_DIR / relative_path

    if parsed.query:
        digest = hashlib.md5(parsed.query.encode("utf-8")).hexdigest()[:10]
        suffix = target.suffix
        if suffix:
            target = target.with_name(f"{target.stem}_{digest}{suffix}")
        else:
            target = target.with_name(f"{target.name}_{digest}")

    return target


def local_href(from_file: Path, to_file: Path) -> str:
    return posixpath.relpath(to_file.as_posix(), from_file.parent.as_posix())


def should_treat_as_page(url: str) -> bool:
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if parsed.path.lower().startswith("/img/"):
        return False
    if parsed.path.lower().startswith(("/js/", "/css/", "/fonts/", "/icon-fonts/")):
        return False
    return ext in PAGE_EXTENSIONS


def is_parseable_text(local_file: Path, content_type: str) -> bool:
    if content_type == "text/css":
        return True
    if content_type in {"text/html", "application/xhtml+xml"}:
        return True
    return local_file.suffix.lower() == ".css"


def is_html_page(local_file: Path, content_type: str, source_url: str) -> bool:
    if content_type in {"text/html", "application/xhtml+xml"}:
        return True
    return should_treat_as_page(source_url) and local_file.suffix.lower() == ".html"


def crawl() -> None:
    ROOT_DIR.mkdir(parents=True, exist_ok=True)
    queue = [urljoin(BASE_URL, page) for page in START_PAGES]
    queued = set(queue)
    downloaded: dict[str, Path] = {}

    while queue:
        current_url = queue.pop(0)
        local_file = local_path_from_url(current_url)

        if current_url in downloaded and local_file.exists():
            continue

        try:
            content, content_type = fetch_resource(current_url)
        except Exception as exc:
            print(f"skip {current_url} -> {exc}")
            continue

        local_file = local_path_from_url(current_url, content_type)

        text_mode = is_parseable_text(local_file, content_type)

        if text_mode:
            text = content.decode("utf-8", errors="ignore")
            replacements: dict[str, str] = {}

            discovered_urls = iter_urls(text)

            for raw_discovered, discovered in discovered_urls:
                normalized = normalize_url(discovered, current_url)
                if not normalized:
                    continue

                target_file = local_path_from_url(normalized)
                replacement = local_href(local_file, target_file)
                replacements[raw_discovered] = replacement
                replacements[discovered] = replacement
                replacements[normalized] = replacement
                replacements[normalized.replace("&", "&amp;")] = replacement.replace("&", "&amp;")

                if normalized not in downloaded and normalized not in queued:
                    queue.append(normalized)
                    queued.add(normalized)

            replacements[BASE_URL] = local_href(local_file, ROOT_DIR / "index.html")
            replacements[urljoin(BASE_URL, "Index.aspx")] = local_href(local_file, ROOT_DIR / "index.html")
            replacements["/Index.aspx"] = local_href(local_file, ROOT_DIR / "index.html")
            replacements["Index.aspx"] = local_href(local_file, ROOT_DIR / "index.html")
            replacements["Index.aspx#diamantina"] = f"{local_href(local_file, ROOT_DIR / 'index.html')}#diamantina"
            replacements["/Index.aspx#diamantina"] = f"{local_href(local_file, ROOT_DIR / 'index.html')}#diamantina"

            for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
                text = text.replace(old, new)

            content = text.encode("utf-8")

        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_bytes(content)
        downloaded[current_url] = local_file
        print(f"saved {current_url} -> {local_file}")


if __name__ == "__main__":
    crawl()