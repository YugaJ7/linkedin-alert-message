"""
LinkedIn Intern Job Alert -> ntfy push notification

Checks LinkedIn's public (logged-out) job search for intern and junior roles,
filters titles by keywords and short forms, skips jobs already sent, and sends
ONE push notification per new job via ntfy (https://ntfy.sh). Each notification
lists which of your skills the job description mentions.

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
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

# ============================ CONFIG ============================

# Each line is ONE LinkedIn search per location; LinkedIn understands OR.
# A quoted phrase also matches longer titles, so "flutter developer" finds
# "Junior Flutter Developer", "Jr. Flutter Developer" and "Flutter Developer Intern".
SEARCH_KEYWORDS = [
    '"SDE intern" OR "SDE internship" OR "software development engineer intern"',
    '"software engineer intern" OR "software engineering intern" OR "SE intern" OR "SWE intern"',
    '"software developer intern" OR "software development intern" OR "SD intern"',
    '"flutter developer" OR "flutter intern" OR "flutter internship" OR "flutter engineer"',
    '"android developer" OR "android intern" OR "android internship" OR "android engineer"',
    '"mobile app developer" OR "mobile application developer" OR "app developer intern" OR "kotlin developer"',
    '"SDE 1" OR "SDE I" OR "software development engineer I" OR "software engineer I"',
    '"full stack developer" OR "full stack engineer" OR "full stack intern" OR "full stack internship" OR "MERN stack developer"',
]

# "India" alone = anywhere in India: onsite, hybrid and remote.
LOCATIONS = ["India"]
# Locations listed here return only remote jobs, e.g. {"India"}.
REMOTE_ONLY_FOR: set[str] = set()

# Only look at jobs posted in the last N seconds (3600 = 1 hour).
POSTED_WITHIN_SECONDS = 3600
# LinkedIn experience levels: 1 = internship, 2 = entry level.
EXPERIENCE_LEVELS = "1,2"
# LinkedIn returns 10 jobs per page; read up to MAX_PAGES pages per search.
PAGE_SIZE = 10
MAX_PAGES = 2

# ---- Title filter (short forms included) ----
# Mobile and full stack roles count at intern OR junior level (the search is already
# limited to internship + entry level), e.g. "Flutter Developer", "Jr Full Stack Developer".
INTERN_OR_JUNIOR_ROLE_PATTERN = re.compile(
    r"\b(flutter|dart|android|kotlin|jetpack compose|mobile|ios|"
    r"app developer|application developer|full[- ]?stack|mern)\b",
    re.I,
)
# Software roles count only as internships, e.g. "SDE Intern", "SE Intern", "SD Intern".
SOFTWARE_ROLE_PATTERN = re.compile(
    r"\b(sde|swe|se|sd|software|developer|development|engineer(ing)?|programmer|"
    r"stack|full[- ]?stack|back[- ]?end|front[- ]?end|web|mern|mean|react)\b",
    re.I,
)
# Level-1 software roles are fresher roles, so they count without "intern":
# "SDE-1", "SDE 1", "SDE I", "SWE-I", "Software Engineer I", "Software Development Engineer 1".
LEVEL_ONE_PATTERN = re.compile(
    r"\b(sde|swe|software (development )?engineer|software developer)\s*[-–]?\s*(1|i)\b", re.I
)
INTERN_PATTERN = re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)
# Titles matching either of these are always skipped.
SENIOR_PATTERN = re.compile(
    r"\b(senior|sr|lead|principal|staff|manager|head|architect|director|ii|iii|iv)\b", re.I
)
EXCLUDE_PATTERN = re.compile(
    r"\b(sales|marketing|hr|human resources?|content|seo|bde|business development|"
    r"recruit(er|ing|ment)|talent acquisition|mechanical|civil|electrical|chemical)\b",
    re.I,
)

# ---- Your skills ----
# Listed in each notification when the job title or description mentions them.
# Shown name -> names and short forms to look for (regex, case-insensitive).
SKILLS = {
    "Flutter": r"flutter",
    "Dart": r"dart",
    "GetX": r"getx",
    "Kotlin": r"kotlin",
    "Jetpack Compose": r"jetpack compose",
    "MVVM": r"mvvm|viewmodel",
    "Firebase": r"firebase|firestore",
    "Hive": r"hive",
    "Node.js": r"node(\.?js)?",
    "Express.js": r"express\.?js",
    "REST APIs": r"rest(ful)?[ -]?apis?|restful",
    "LLM APIs": r"llms?|large language models?|openai|gpt|gemini",
    "RAG": r"rag|retrieval[- ]augmented( generation)?",
    "GenAI": r"gen[ -]?ai|generative ai",
    "Python": r"python",
    "Java": r"java",
    "C/C++": r"c\+\+|cpp|c/c\+\+",
    "SQL": r"sql|mysql|postgres(ql)?",
    "MongoDB": r"mongo(db)?",
    "Git/GitHub": r"git|github|gitlab",
    "CI/CD": r"ci\s*/\s*cd|ci-cd|github actions",
    "Postman": r"postman",
    "Clean Architecture": r"clean architecture",
    "Atomic Design": r"atomic design",
}
# Max job descriptions to read per run (each one is an extra LinkedIn request).
MAX_DETAIL_FETCHES = 15

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
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

# Whole-word match that also works for names like "C++" and "Node.js".
SKILL_PATTERNS = {
    name: re.compile(rf"(?<!\w)(?:{pattern})(?!\w)", re.I) for name, pattern in SKILLS.items()
}

# ============================ LINKEDIN ============================


def _pause(low: float = 1.5, high: float = 3.5) -> None:
    time.sleep(random.uniform(low, high))  # be polite to LinkedIn


def _get(url: str, params: dict[str, str] | None = None, label: str = "") -> str | None:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"[warn] request failed ({label}): {e}")
        return None
    if r.status_code != 200:
        print(f"[warn] HTTP {r.status_code} for {label}")
        return None
    return r.text


def _text(card: Tag, selector: str) -> str:
    el = card.select_one(selector)
    return el.get_text(strip=True) if el else ""


def _job_id(card: Tag, link: str) -> str:
    urn = str(card.get("data-entity-urn") or "")
    if urn:
        return urn.split(":")[-1]
    m = re.search(r"-(\d+)/?$", link)
    return m.group(1) if m else link


def parse_cards(html: str) -> list[dict[str, str]]:
    """Turn one page of LinkedIn search results into job dicts."""
    jobs = []
    for card in BeautifulSoup(html, "html.parser").select("div.base-card, div.job-search-card"):
        title = _text(card, "h3.base-search-card__title")
        link_el = card.select_one("a.base-card__full-link")
        link = str(link_el.get("href") or "").split("?")[0] if link_el else ""
        job_id = _job_id(card, link)
        if not title or not job_id:
            continue
        jobs.append({
            "id": job_id,
            "title": title,
            "company": _text(card, "h4.base-search-card__subtitle"),
            "location": _text(card, "span.job-search-card__location"),
            "link": link,
        })
    return jobs


def fetch_jobs(keyword: str, location: str) -> list[dict[str, str]]:
    params = {
        "keywords": keyword,
        "location": location,
        "f_TPR": f"r{POSTED_WITHIN_SECONDS}",  # posted within
        "f_E": EXPERIENCE_LEVELS,
        "sortBy": "DD",                          # newest first
    }
    if location in REMOTE_ONLY_FOR:
        params["f_WT"] = "2"  # remote

    jobs: list[dict[str, str]] = []
    for page in range(MAX_PAGES):
        label = f"{location!r} / {keyword[:40]!r} / page {page + 1}"
        html = _get(SEARCH_URL, {**params, "start": str(page * PAGE_SIZE)}, label)
        if html is None:
            break
        page_jobs = parse_cards(html)
        jobs.extend(page_jobs)
        if len(page_jobs) < PAGE_SIZE:
            break
        _pause()
    return jobs


def fetch_description(job_id: str) -> str:
    html = _get(DETAIL_URL.format(job_id=job_id), label=f"job {job_id}")
    if html is None:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("div.show-more-less-html__markup, div.description__text")
    return (el or soup).get_text(" ", strip=True)


def is_relevant(title: str) -> bool:
    if EXCLUDE_PATTERN.search(title) or SENIOR_PATTERN.search(title):
        return False
    if INTERN_OR_JUNIOR_ROLE_PATTERN.search(title) or LEVEL_ONE_PATTERN.search(title):
        return True
    return bool(SOFTWARE_ROLE_PATTERN.search(title) and INTERN_PATTERN.search(title))


def match_skills(text: str) -> list[str]:
    return [name for name, pattern in SKILL_PATTERNS.items() if pattern.search(text)]

# ============================ NTFY ============================


def build_message(job: dict[str, str], skills: list[str]) -> str:
    lines = [f"🏢 {job['company']}", f"📍 {job['location']}"]
    if skills:
        lines.append("🧩 " + ", ".join(skills))
    return "\n".join(lines)


def send_ntfy(title: str, message: str, click: str = "") -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("[error] NTFY_TOPIC is not set.")
        return False
    payload: dict[str, Any] = {
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


def find_new_jobs(seen: set[str]) -> dict[str, dict[str, str]]:
    new_jobs: dict[str, dict[str, str]] = {}
    for kw in SEARCH_KEYWORDS:
        for loc in LOCATIONS:
            for job in fetch_jobs(kw, loc):
                if job["id"] in seen or job["id"] in new_jobs:
                    continue
                if is_relevant(job["title"]):
                    new_jobs[job["id"]] = job
            _pause()
    return new_jobs


def run_once() -> None:
    seen = load_seen()
    new_jobs = find_new_jobs(set(seen))
    print(f"[info] {len(new_jobs)} new relevant job(s)")

    for i, job in enumerate(new_jobs.values()):
        skills: list[str] = []
        if i < MAX_DETAIL_FETCHES:
            skills = match_skills(job["title"] + " " + fetch_description(job["id"]))
            _pause(1.0, 2.0)
        if send_ntfy(job["title"], build_message(job, skills), job["link"]):
            seen = [*seen, job["id"]]
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
