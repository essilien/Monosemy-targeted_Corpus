#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weibo_crawler.py
=================

This script demonstrates how to collect the most recent Weibo posts for a list of
monosemous target words and save them in a structured format. It reads a
``monosemy_corpus.json`` file to obtain the target words, then uses an HTTP
session with a user‑supplied Cookie to send search requests against
``https://s.weibo.com``. For each word it fetches pages of search results
sorted by time until at least ``max_posts`` valid posts are collected. The
resulting usage‑level records are stored in a JSON file which can be used
for downstream processing (e.g. clustering or sense induction).

**Important:**

1. The script expects that you already have a valid authenticated session
   cookie for Weibo. You can find your cookie by inspecting network requests
   in your browser’s developer tools (see the example in the user’s prompt).
   Copy the entire ``Cookie`` header value and paste it into the ``COOKIE``
   constant below. Do *not* share your cookie publicly.

2. Weibo’s HTML structure changes frequently. The parser below is a best
   effort based on the current layout (as of early 2026). You may need to
   adjust the CSS selectors if Weibo changes their markup. Use your browser’s
   developer tools to inspect the HTML of search result pages and update
   selectors accordingly.

3. This script is provided for reference. Running it requires network
   connectivity to ``s.weibo.com`` from your machine. It cannot be executed
   from environments that block Weibo.

Usage::

    python weibo_crawler.py --cookie "<your-cookie-string>" --json monosemy_corpus.json \
                            --output raw_weibo_usage_corpus.json --max_posts 40

The script will print progress information and write a JSON file containing
usage‑level records with the following fields:

``usage_id``     – unique identifier for this usage instance
``word_id``      – identifier linking back to the word in the monosemy corpus
``target_word``  – the headword itself
``post_id``      – Weibo MID of the post
``timestamp``    – time string extracted from the post’s metadata
``raw_text``     – full text of the post as returned by Weibo (stripped of
                    redundant whitespace)
``normalized_text`` – lower‑cased raw text with common whitespace normalized
``target_start`` – character index of the first occurrence of the target word
``target_end``   – character index of the end of that occurrence
``left_context`` – text to the left of the target word
``target_token`` – the target word itself
``right_context`` – text to the right of the target word
``full_context`` – full post text (same as raw_text)
``source_platform`` – fixed string "Weibo"
``is_duplicate`` – boolean flag indicating whether the post ID was seen before
``is_short_context`` – boolean flag indicating whether the post text is too short
``is_noisy``     – boolean placeholder; always False here
``is_named_entity_like`` – boolean placeholder; always False here
``topic_cluster_hint`` – None; placeholder for manual annotation
``keep_for_analysis`` – boolean flag indicating whether the usage should be kept
                         (True unless duplicate or short context)

You can extend the code to include additional metadata (e.g. number of likes or
shares) by inspecting the HTML and adding extra fields.
"""

import argparse
import json
import sys
import time
import urllib.parse
from typing import Dict, List, Optional

import bs4  # type: ignore
import requests


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Crawl recent Weibo posts for target words.")
    parser.add_argument(
        "--cookie",
        type=str,
        default=None,
        help=(
            "Authentication cookie for Weibo. You can pass it directly via this flag or "
            "leave it unset to use the COOKIE constant in the script."
        ),
    )
    parser.add_argument("--json", type=str, default="monosemy_corpus.json", help="Path to JSON file containing monosemous words.")
    parser.add_argument(
        "--output",
        type=str,
        default="raw_weibo_usage_corpus.json",
        help="Path to write the usage‑level corpus JSON.",
    )
    parser.add_argument(
        "--max_posts",
        type=int,
        default=40,
        help="Number of posts to collect per word (default: 40).",
    )
    return parser.parse_args()


# Replace this cookie string with your actual Weibo Cookie (from browser dev tools).
COOKIE = "Apache=4132228690362.7534.1773331107098; ULV=1773331107117:3:1:1:4132228690362.7534.1773331107098:1769590701708; _s_tentry=weibo.com; ALF=02_1775923090; SUB=_2A25EtpLCDeRhGeRP7VsY9CzKzziIHXVnzaoKrDV8PUNbmtANLUTnkW9NUB964Id1PJ-8yGKCSW15_7eXPuPwts5a; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WFkGIOomNldCUCK8SureYJA5JpX5KzhUgL.FozpSo.4ShzcShB2dJLoIpHSdcf_w-fy9sHS9-fyMcySw-fVKPet; PC_TOKEN=468861ca87; SINAGLOBAL=5398570673908.707.1768225631347; SCF=Au8emMCE23slZC4wbgYueD6pJZLMmHE7_Ym0KTPF-anx_kLt7UXUuoksRJsG8MGr9Yp8VG2ZUFxFHMN-MB4QBPA."


HEADERS_TEMPLATE = {
    # The cookie will be filled dynamically based on CLI args or COOKIE constant.
    "Cookie": "",
    # The following headers mimic a Safari browser. You may adjust them if necessary.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh-Hans;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://weibo.com/",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
}


def fetch_weibo_search_page(session: requests.Session, word: str, page: int = 1) -> Optional[str]:
    """Retrieve the HTML content of a search result page for the given word and page number.

    Parameters
    ----------
    session : requests.Session
        Session object with headers and cookies configured.
    word : str
        The target word to search for. This will be URL‑encoded.
    page : int
        Page index (starting from 1).

    Returns
    -------
    Optional[str]
        Raw HTML of the search results page, or None if the request fails.
    """
    base_url = "https://s.weibo.com/weibo"
    params = {
        "q": word,
        # Sort by time to get latest posts. Other values may be "hot".
        "sort": "time",
        # Page number (Weibo uses 1‑based indexing).
        "page": str(page),
    }
    url = f"{base_url}?{urllib.parse.urlencode(params, safe='') }"
    try:
        response = session.get(url, timeout=10)
    except requests.RequestException as exc:
        print(f"[WARN] Request failed for '{word}' page {page}: {exc}", file=sys.stderr)
        return None
    if response.status_code != 200:
        print(f"[WARN] Received status {response.status_code} for '{word}' page {page}", file=sys.stderr)
        return None
    return response.text


def parse_posts_from_html(html: str) -> List[Dict[str, str]]:
    """Parse Weibo search HTML and extract post information.

    This function extracts a list of dictionaries with keys ``post_id``, ``timestamp`` and ``text``.
    The parser is based on Weibo's HTML structure as of early 2026. If Weibo changes its
    markup, you may need to adjust the CSS selectors accordingly.
    """
    soup = bs4.BeautifulSoup(html, "html.parser")
    posts: List[Dict[str, str]] = []

    # Weibo search results appear under 'div.card' elements with a 'data-mid' attribute.
    for card in soup.find_all("div", attrs={"mid": True}):
        post_id = card.get("mid")
        # Extract post text; in Weibo search, text content is within a <p> tag with class 'txt'
        text_tag = card.find("p", class_=lambda cls: cls and "txt" in cls)
        if not text_tag:
            continue
        # Extract full text (with visible text only; remove HTML tags)
        raw_text = text_tag.get_text(separator=" ", strip=True)
        if not raw_text:
            continue
        # Extract timestamp; search results include a <p class='from'>
        time_tag = card.find("p", class_=lambda cls: cls and "from" in cls)
        if time_tag:
            # Time may be within an <a> tag inside the 'from' container
            a_tag = time_tag.find("a")
            timestamp = a_tag.get_text(strip=True) if a_tag else time_tag.get_text(strip=True)
        else:
            timestamp = ""
        posts.append({"post_id": post_id, "timestamp": timestamp, "text": raw_text})
    return posts


def build_usage_record(target_word: str, post: Dict[str, str]) -> Dict[str, object]:
    """Transform a raw post dictionary into a usage‑level record with context fields."""
    text = post.get("text", "")
    normalized = " ".join(text.strip().split())  # normalize whitespace
    # Find first occurrence of the target word in the post
    idx = normalized.find(target_word)
    if idx == -1:
        # If the target word is not found (rare), place markers at the start
        target_start = 0
        target_end = 0
        left_context = ""
        target_token = target_word
        right_context = normalized
    else:
        target_start = idx
        target_end = idx + len(target_word)
        left_context = normalized[:target_start]
        target_token = normalized[target_start:target_end]
        right_context = normalized[target_end:]
    record = {
        "usage_id": "",  # to be filled later
        "word_id": "",
        "target_word": target_word,
        "post_id": post.get("post_id", ""),
        "timestamp": post.get("timestamp", ""),
        "raw_text": text,
        "normalized_text": normalized,
        "target_start": target_start,
        "target_end": target_end,
        "left_context": left_context,
        "target_token": target_token,
        "right_context": right_context,
        "full_context": normalized,
        "source_platform": "Weibo",
        "is_duplicate": False,
        "is_short_context": len(normalized) < 10,
        "is_noisy": False,
        "is_named_entity_like": False,
        "topic_cluster_hint": None,
        "keep_for_analysis": True,
    }
    return record


def collect_posts_for_word(session: requests.Session, target_word: str, max_posts: int) -> List[Dict[str, str]]:
    """Collect up to ``max_posts`` posts for the given target word."""
    collected: List[Dict[str, str]] = []
    seen_ids: set = set()
    page = 1
    while len(collected) < max_posts:
        html = fetch_weibo_search_page(session, target_word, page)
        if not html:
            break
        posts = parse_posts_from_html(html)
        if not posts:
            break
        for post in posts:
            if post["post_id"] in seen_ids:
                continue
            seen_ids.add(post["post_id"])
            collected.append(post)
            if len(collected) >= max_posts:
                break
        page += 1
        # Be respectful and avoid hammering the server
        time.sleep(1.5)
    return collected


def main() -> None:
    args = parse_arguments()
    cookie = args.cookie if args.cookie else COOKIE
    if not cookie:
        print(
            "Error: You must provide a Cookie via --cookie or set the COOKIE constant in the script.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read monosemy words
    with open(args.json, "r", encoding="utf-8") as f:
        monosemy_data = json.load(f)
    # Create a session and set headers
    session = requests.Session()
    headers = HEADERS_TEMPLATE.copy()
    headers["Cookie"] = cookie
    session.headers.update(headers)

    usage_records: List[Dict[str, object]] = []
    for idx, item in enumerate(monosemy_data):
        word = item.get("word")
        if not word:
            continue
        print(f"Collecting posts for '{word}'...", file=sys.stderr)
        posts = collect_posts_for_word(session, word, args.max_posts)
        print(f"  Retrieved {len(posts)} posts for '{word}'.", file=sys.stderr)
        for i, post in enumerate(posts, start=1):
            record = build_usage_record(word, post)
            record["usage_id"] = f"{word}_{i}"
            # Construct a simple word_id (padded index)
            record["word_id"] = f"w_{idx:04d}"
            # Mark duplicates and short contexts in metadata fields
            record["is_duplicate"] = False  # duplicates removed via seen_ids
            record["is_short_context"] = len(record["normalized_text"]) < 10
            record["keep_for_analysis"] = not record["is_short_context"]
            usage_records.append(record)

    # Write usage records to output file
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(usage_records, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(usage_records)} usage records to {args.output}.")


if __name__ == "__main__":
    main()