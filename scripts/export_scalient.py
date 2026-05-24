from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests import HTTPError


ROOT_URL = "https://scalient.webflow.io/"
GOOGLE_FONTS_URL = "https://fonts.googleapis.com/css2?family=Italianno&display=swap"
OUTPUT_DIR = Path(__file__).resolve().parents[1]
INDEX_PATH = OUTPUT_DIR / "index.html"
ASSET_ROOT = OUTPUT_DIR / "assets"
MIRROR_ROOT = ASSET_ROOT / "mirror"
FONTS_DIR = ASSET_ROOT / "fonts"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        )
    }
)

URL_ATTRS = ("src", "href", "poster")
SRCSET_ATTRS = ("srcset",)
STYLE_ATTRS = ("style",)
EXTRA_URL_ATTRS = ("data-src",)
LOCALIZED_TAGS = {"script", "img", "source", "link"}
STYLESHEET_RELS = {"stylesheet", "shortcut icon", "icon", "apple-touch-icon"}
CSS_URL_RE = re.compile(r"url\((?P<quote>['\"]?)(?P<url>.*?)(?P=quote)\)")

download_cache: dict[str, Path] = {}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def is_remote(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def sanitize_segment(segment: str) -> str:
    decoded = unquote(segment)
    decoded = re.sub(r"[<>:\"/\\|?*]", "_", decoded)
    return decoded or "_"


def path_for_url(url: str) -> Path:
    split = urlsplit(url)
    host = sanitize_segment(split.netloc)
    parts = [sanitize_segment(part) for part in split.path.split("/") if part]
    if not parts:
        parts = ["index"]

    target = MIRROR_ROOT / host
    for part in parts[:-1]:
        target /= part

    filename = parts[-1]
    if split.query:
        stem, dot, suffix = filename.partition(".")
        query_hash = hashlib.sha1(split.query.encode("utf-8")).hexdigest()[:10]
        filename = f"{stem}__{query_hash}"
        if dot:
            filename += f".{suffix}"
    return target / filename


def relpath(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_path.parent)).as_posix()


def fetch(url: str) -> requests.Response:
    response = SESSION.get(url, timeout=60)
    response.raise_for_status()
    return response


def rewrite_css_urls(text: str, css_path: Path, base_url: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group("url").strip()
        if not raw_url or raw_url.startswith(("data:", "#", "blob:")):
            return match.group(0)

        absolute_url = urljoin(base_url, raw_url)
        if not is_remote(absolute_url):
            return match.group(0)

        local_path = download_asset(absolute_url)
        quote = match.group("quote") or ""
        return f"url({quote}{relpath(css_path, local_path)}{quote})"

    return CSS_URL_RE.sub(replace, text)


def download_asset(url: str) -> Path:
    absolute_url = urljoin(ROOT_URL, url)
    cached = download_cache.get(absolute_url)
    if cached:
        return cached

    target_path = path_for_url(absolute_url)
    try:
        response = fetch(absolute_url)
    except HTTPError:
        if absolute_url.endswith("/plugins/Basic/assets/placeholder.60f9b1840c.svg"):
            ensure_parent(target_path)
            target_path.write_text(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="24" '
                    'height="24" viewBox="0 0 24 24" aria-hidden="true"></svg>'
                ),
                encoding="utf-8",
            )
            download_cache[absolute_url] = target_path
            return target_path
        raise

    ensure_parent(target_path)

    if target_path.suffix.lower() == ".css":
        css_text = rewrite_css_urls(response.text, target_path, absolute_url)
        target_path.write_text(css_text, encoding="utf-8")
    else:
        target_path.write_bytes(response.content)

    download_cache[absolute_url] = target_path
    return target_path


def rewrite_srcset(value: str, document_path: Path) -> str:
    rewritten_entries: list[str] = []
    for entry in value.split(","):
        item = entry.strip()
        if not item:
            continue

        parts = item.split()
        url = parts[0]
        absolute_url = urljoin(ROOT_URL, url)
        if is_remote(absolute_url):
            local_path = download_asset(absolute_url)
            parts[0] = relpath(document_path, local_path)
        rewritten_entries.append(" ".join(parts))
    return ", ".join(rewritten_entries)


def rewrite_style_value(value: str, document_path: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_url = match.group("url").strip()
        if not raw_url or raw_url.startswith(("data:", "#", "blob:")):
            return match.group(0)

        absolute_url = urljoin(ROOT_URL, raw_url)
        if not is_remote(absolute_url):
            return match.group(0)

        local_path = download_asset(absolute_url)
        quote = match.group("quote") or ""
        return f"url({quote}{relpath(document_path, local_path)}{quote})"

    return CSS_URL_RE.sub(replace, value)


def localize_font_css() -> Path:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    css_path = FONTS_DIR / "google-fonts.css"
    css_text = fetch(GOOGLE_FONTS_URL).text
    css_text = rewrite_css_urls(css_text, css_path, GOOGLE_FONTS_URL)
    css_path.write_text(css_text, encoding="utf-8")
    return css_path


def should_localize_link(tag) -> bool:
    rels = {rel.lower() for rel in tag.get("rel", [])}
    return bool(rels & STYLESHEET_RELS)


def rewrite_html() -> None:
    html = fetch(ROOT_URL).text
    soup = BeautifulSoup(html, "lxml")

    for tag in soup.find_all("link", rel=True):
        rels = {rel.lower() for rel in tag.get("rel", [])}
        href = tag.get("href", "")
        if "preconnect" in rels and (
            "fonts.googleapis.com" in href or "fonts.gstatic.com" in href
        ):
            tag.decompose()

    for script in soup.find_all("script"):
        src = script.get("src", "")
        if "ajax.googleapis.com/ajax/libs/webfont/" in src:
            script.decompose()
            continue
        if script.string and "WebFont.load(" in script.string:
            script.decompose()

    font_css_path = localize_font_css()
    head = soup.head
    font_link = soup.new_tag(
        "link",
        href=relpath(INDEX_PATH, font_css_path),
        rel="stylesheet",
        type="text/css",
    )
    first_stylesheet = head.find("link", rel=lambda value: value and "stylesheet" in value)
    if first_stylesheet:
        first_stylesheet.insert_after(font_link)
    else:
        head.append(font_link)

    for tag in soup.find_all(True):
        if tag.name in LOCALIZED_TAGS:
            for attr in URL_ATTRS:
                if attr not in tag.attrs:
                    continue
                if tag.name == "link" and attr == "href" and not should_localize_link(tag):
                    continue
                value = tag.get(attr)
                if not value:
                    continue
                if not is_remote(value):
                    continue
                absolute_url = value
                local_path = download_asset(absolute_url)
                tag[attr] = relpath(INDEX_PATH, local_path)
                tag.attrs.pop("integrity", None)
                tag.attrs.pop("crossorigin", None)

        for attr in EXTRA_URL_ATTRS:
            if attr not in tag.attrs:
                continue
            value = tag.get(attr)
            if not value or not is_remote(value):
                continue
            local_path = download_asset(value)
            tag[attr] = relpath(INDEX_PATH, local_path)

        for attr in SRCSET_ATTRS:
            if attr in tag.attrs:
                tag[attr] = rewrite_srcset(tag[attr], INDEX_PATH)

        for attr in STYLE_ATTRS:
            if attr in tag.attrs:
                tag[attr] = rewrite_style_value(tag[attr], INDEX_PATH)

    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string.replace_with(
                rewrite_style_value(style_tag.string, INDEX_PATH)
            )

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href in {"/", ROOT_URL, "https://scalient.webflow.io"}:
            anchor["href"] = "index.html"
            continue
        if href.startswith("/") or href.startswith("https://scalient.webflow.io/"):
            anchor["href"] = "#"

    for meta in soup.find_all("meta", content=True):
        content = meta["content"]
        if not is_remote(content):
            continue
        local_path = download_asset(content)
        meta["content"] = relpath(INDEX_PATH, local_path)

    output_html = str(soup)
    if not output_html.lstrip().lower().startswith("<!doctype"):
        output_html = "<!DOCTYPE html>\n" + output_html

    INDEX_PATH.write_text(output_html, encoding="utf-8")


def main() -> None:
    rewrite_html()
    print(f"Exported offline page to {INDEX_PATH}")


if __name__ == "__main__":
    main()
