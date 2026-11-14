"""
LinkedIn Intern Job Alert -> ntfy push notification

Checks LinkedIn's public (logged-out) job search for intern roles,
filters titles by keywords/synonyms, skips jobs already sent,
and sends ONE push notification per new job via ntfy (https://ntfy.sh).

Usage:
  pip install requests beautifulsoup4
  set NTFY_TOPIC=your-secret-topic        (Windows)   |  export NTFY_TOPIC=...  (Mac/Linux)
  python job_alert.py --test               send a test notification
  python job_alert.py                      check once
  python job_alert.py --loop 3             check every 3 minutes (laptop mode)
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ============================ CONFIG ============================

# LinkedIn job search understands OR, so each line is ONE request.
SEARCH_KEYWORDS = [
    '"SDE intern" OR "software engineer intern" OR "software development engineer intern"',
    '"software developer intern" OR "software engineering intern" OR "SDE internship"',
    '"flutter intern" OR "flutter developer intern" OR "flutter internship"',
    '"mobile application intern" OR "mobile app developer intern" OR "android developer intern" OR "app developer intern"',
]

LOCATIONS = [
    "Delhi, India",
    "Noida, Uttar Pradesh, India",
    "Gurugram, Haryana, India",
    "India",  # remote-only, see REMOTE_ONLY_FOR
]
REMOTE_ONLY_FOR = {"India"}

# Only look at jobs posted in the last N seconds (3600 = 1 hour).
POSTED_WITHIN_SECONDS = 3600

# A title must match BOTH of these to count...
ROLE_PATTERN = re.compile(
    r"\b(sde|software|flutter|mobile|android|ios|app(lication)?|developer|engineer(ing)?|dart)\b", re.I
)
INTERN_PATTERN = re.compile(r"\b(intern|internship|trainee)\b", re.I)
# ...and must NOT match this.
EXCLUDE_PATTERN = re.compile(r"\b(sales|marketing|hr|human resource|content|seo|bde)\b", re.I)

SEEN_FILE = Path(__file__).with_name("seen_jobs.json")
MAX_SEEN = 3000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# ============================ LINKEDIN ============================


def fetch_jobs(keyword: str, location: str) -> list[dict]:
    params = {
        "keywords": keyword,
        "location": location,
        "f_TPR": f"r{POSTED_WITHIN_SECONDS}",  # posted within
        "f_E": "1,2",                            # internship + entry level
        "start": "0",
    }
    if location in REMOTE_ONLY_FOR:
        params["f_WT"] = "2"  # remote

    try:
        r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"[warn] request failed ({location}): {e}")
        return []
    if r.status_code != 200:
        print(f"[warn] HTTP {r.status_code} for {location!r} / {keyword[:40]!r}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    jobs = []
    for card in soup.select("div.base-card, div.job-search-card"):
        title_el = card.select_one("h3.base-search-card__title")
        if not title_el:
            continue
        company_el = card.select_one("h4.base-search-card__subtitle")
        loc_el = card.select_one("span.job-search-card__location")
        link_el = card.select_one("a.base-card__full-link")

        link = link_el["href"].split("?")[0] if link_el and link_el.has_attr("href") else ""
        urn = card.get("data-entity-urn", "")
        job_id = urn.split(":")[-1] if urn else None
        if not job_id and link:
            m = re.search(r"-(\d+)/?$", link)
            job_id = m.group(1) if m else link

        jobs.append({
            "id": job_id,
            "title": title_el.get_text(strip=True),
            "company": company_el.get_text(strip=True) if company_el else "",
            "location": loc_el.get_text(strip=True) if loc_el else "",
            "link": link,
        })
    return jobs


def is_relevant(title: str) -> bool:
    return (
        bool(INTERN_PATTERN.search(title))
        and bool(ROLE_PATTERN.search(title))
        and not EXCLUDE_PATTERN.search(title)
    )

# ============================ NTFY ============================


def send_ntfy(title: str, message: str, click: str = "") -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("[error] NTFY_TOPIC is not set.")
        return False
    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "tags": ["briefcase"],
        "priority": int(os.environ.get("NTFY_PRIORITY", "5")),  # 5 = max: own sound, pops on screen
    }
    if click:
        payload["click"] = click
        payload["actions"] = [{"action": "view", "label": "Open job", "url": click}]
    try:
        r = requests.post("https://ntfy.sh", json=payload, timeout=30)
        print(f"[ntfy] {r.status_code} - {title}")
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"[error] ntfy failed: {e}")
        return False

# ============================ STATE ============================


def load_seen() -> list[str]:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return []


def save_seen(seen: list[str]) -> None:
    SEEN_FILE.write_text(json.dumps(seen[-MAX_SEEN:]))

# ============================ MAIN ============================


def run_once() -> None:
    seen = load_seen()
    seen_set = set(seen)
    new_jobs: dict[str, dict] = {}

    for kw in SEARCH_KEYWORDS:
        for loc in LOCATIONS:
            for job in fetch_jobs(kw, loc):
                if not job["id"] or job["id"] in seen_set or job["id"] in new_jobs:
                    continue
                if is_relevant(job["title"]):
                    new_jobs[job["id"]] = job
            time.sleep(random.uniform(1.5, 3.5))  # be polite

    print(f"[info] {len(new_jobs)} new relevant job(s)")
    for job in new_jobs.values():
        if send_ntfy(job["title"], f"🏢 {job['company']}\n📍 {job['location']}", job["link"]):
            seen.append(job["id"])
        time.sleep(1)
    save_seen(seen)


def main() -> None:
    if "--test" in sys.argv:
        send_ntfy("✅ Job alert is working", "Tap to open LinkedIn Jobs", "https://www.linkedin.com/jobs/")
        return

    if "--loop" in sys.argv:
        i = sys.argv.index("--loop")
        minutes = float(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 3
        while True:
            try:
                run_once()
            except Exception as e:
                print(f"[error] run failed: {e}")
            print(f"[info] next check in {minutes} min")
            time.sleep(minutes * 60)

    run_once()


if __name__ == "__main__":
    main()
