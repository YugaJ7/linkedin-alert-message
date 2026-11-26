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

# ---- About you (from your resume) ----
# Your graduating batch. Jobs that name only other batches ("2025/2026 pass-outs") are skipped.
GRADUATION_YEAR = 2027
# Jobs whose description asks for more years than this ("3+ years", "4-6 yrs") are skipped.
MAX_EXPERIENCE_YEARS = 2

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
    '"software engineer" OR "software developer" OR "associate software engineer" OR "graduate engineer trainee"',
    f'"{GRADUATION_YEAR} batch" OR "{GRADUATION_YEAR} graduates" OR "{GRADUATION_YEAR} passout" OR "class of {GRADUATION_YEAR}"',
    '"backend developer" OR "python developer" OR "node.js developer" OR "AI engineer" OR "web developer"',
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
# These roles count at ANY fresher level: intern, trainee, junior, jr, associate,
# graduate, level 1, or no level at all (the search is already limited to
# internship + entry level). e.g. "Software Engineer", "Jr. Flutter Developer",
# "Associate Software Engineer", "SDE-1", "Python Developer", "AI Engineer".
JUNIOR_ROLE_PATTERN = re.compile(
    r"\b(software|sde|swe|developer|programmer|"
    r"flutter|dart|android|kotlin|jetpack compose|mobile|ios|"
    r"full[- ]?stack|mern|mean|back[- ]?end|front[- ]?end|"
    r"associate engineer|graduate engineer|(ai|ml|genai|llm) engineer)\b",
    re.I,
)
# These broader words count only as internships, e.g. "SE Intern", "SD Intern",
# "Data Engineer Intern", "Web Development Intern", "React Internship".
INTERN_ONLY_ROLE_PATTERN = re.compile(r"\b(se|sd|engineer(ing)?|development|stack|web|react)\b", re.I)
INTERN_PATTERN = re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)
# Titles matching either of these are always skipped: senior words, and level 2+
# such as "SDE-2", "SDE II", "Software Engineer 3", "Developer L3".
SENIOR_PATTERN = re.compile(
    r"\b(senior|sr|lead|principal|staff|manager|head|architect|director|vp|avp|svp|"
    r"vice president|experienced|intermediate|intmd|mid[- ]?level|expert|ii|iii|iv)\b"
    r"|\b(sde|swe|engineer|developer|l)\s*[-–]?\s*[2-9]\b",
    re.I,
)
EXCLUDE_PATTERN = re.compile(
    r"\b(sales|marketing|hr|human resources?|content|seo|bde|business develop(ment|er)|curriculum|"
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
    "Kotlin Multiplatform": r"kotlin multiplatform|kmp|compose multiplatform",
    "HTML/CSS": r"html5?|css3?",
    "Figma": r"figma",
    "DSA": r"dsa|data structures?(\s*(and|&)\s*algorithms?)?",
    "OOP": r"oops?|object[- ]oriented( programming)?",
}
# Max new jobs to check per run. Each check reads the job description (one extra
# LinkedIn request); jobs over the limit are checked on the next run.
MAX_JOBS_CHECKED_PER_RUN = 15

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
    title = title.replace("_", " ")  # "IN_Senior Associate_Java" -> words
    if EXCLUDE_PATTERN.search(title) or SENIOR_PATTERN.search(title):
        return False
    if JUNIOR_ROLE_PATTERN.search(title):
        return True
    return bool(INTERN_ONLY_ROLE_PATTERN.search(title) and INTERN_PATTERN.search(title))


def match_skills(text: str) -> list[str]:
    return [name for name, pattern in SKILL_PATTERNS.items() if pattern.search(text)]

# ============================ ELIGIBILITY ============================

_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                 "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
_NUMBER_WORD_PATTERN = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.I)
_YEARS = r"(?:years?|yrs?)'?"
_NUM = r"(?<![\d.])(\d{1,2}(?:\.\d)?)"
# Each pattern captures the MINIMUM years a job asks for.
_EXPERIENCE_PATTERNS = [
    re.compile(rf"{_NUM}\s*(?:-|–|to)\s*\d{{1,2}}(?!\d)\s*\+?\s*{_YEARS}", re.I),            # 2-4 years
    re.compile(rf"{_NUM}\s*\+\s*{_YEARS}", re.I),                                           # 3+ years
    re.compile(rf"{_NUM}\s*\+?\s*yoe\b", re.I),                                              # 5+ YOE
    re.compile(rf"(?:minimum|min\.?|at\s*least)\s*(?:of\s*)?{_NUM}\s*{_YEARS}", re.I),       # at least 3 years
    re.compile(rf"{_NUM}\s*{_YEARS}\s*(?:of\s*)?(?:[\w-]+\s+){{0,3}}?(?:experience|exp)\b", re.I),  # 4 years of relevant experience
    re.compile(rf"experience\s*(?:of|:|-|–)?\s*{_NUM}\s*{_YEARS}", re.I),                    # experience: 3 years
]
# "up to 3 years" / "less than 2 years" set no minimum.
_UPPER_BOUND_BEFORE = re.compile(r"(up\s*to|upto|max(imum)?|less than|under|below|within)\s*$", re.I)
# Bigger numbers are usually about the company ("25 years of experience in the industry").
_MAX_PLAUSIBLE_YEARS = 15

_BATCH_WORDS = r"batch(?:es)?|pass(?:ed|ing)?[\s-]?outs?|graduat\w*|grads?|class of|year of passing|yop"
_YEAR_LIST = r"20\d{2}(?:\s*(?:,|/|&|and|or|-|–|to)\s*(?:20)?\d{2}(?!\d))*"
_BATCH_PATTERNS = [
    re.compile(rf"(?<!\d)({_YEAR_LIST})[^\d\n.]{{0,15}}?\b(?:{_BATCH_WORDS})", re.I),  # "2025/2026 batch"
    re.compile(rf"\b(?:{_BATCH_WORDS})[^\d\n.]{{0,20}}?({_YEAR_LIST})(?!\d)", re.I),   # "Batch: 2025, 2026"
]
_OPEN_ENDED_AFTER = re.compile(r"^\W*(onwards|and above|& above|or later|and later|& later|and after|\+)", re.I)


def required_experience(text: str) -> float | None:
    """Minimum years of experience the job asks for (its first mention), or None."""
    text = _NUMBER_WORD_PATTERN.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], text)
    mentions: list[tuple[int, float]] = []
    for pattern in _EXPERIENCE_PATTERNS:
        for m in pattern.finditer(text):
            years = float(m.group(1))
            if _UPPER_BOUND_BEFORE.search(text[max(0, m.start() - 15):m.start()]):
                years = 0.0
            if years <= _MAX_PLAUSIBLE_YEARS:
                mentions.append((m.start(), years))
    return min(mentions)[1] if mentions else None


def _expand_years(group: str, open_ended: bool) -> set[int]:
    found = [int(y) if len(y) == 4 else 2000 + int(y) for y in re.findall(r"\d{2,4}", group)]
    found = [y for y in found if 2015 <= y <= 2035]
    if not found:
        return set()
    if open_ended:
        return set(range(min(found), 2036))
    if len(found) == 2 and re.search(r"-|–|to", group):
        return set(range(min(found), max(found) + 1))
    return set(found)


def batch_years(text: str) -> set[int]:
    """Graduation years the job is open to, e.g. {2025, 2026}; empty if not stated."""
    years: set[int] = set()
    for pattern in _BATCH_PATTERNS:
        for m in pattern.finditer(text):
            open_ended = bool(_OPEN_ENDED_AFTER.search(text[m.end():m.end() + 15]))
            years |= _expand_years(m.group(1), open_ended)
    return years


def ineligible_reason(text: str) -> str | None:
    years = required_experience(text)
    if years is not None and years > MAX_EXPERIENCE_YEARS:
        return f"asks for {years:g}+ years of experience"
    batches = batch_years(text)
    if batches and GRADUATION_YEAR not in batches:
        return "only for batch " + ", ".join(map(str, sorted(batches)))
    return None


def check_job(job: dict[str, str]) -> tuple[str, list[str]]:
    """Read the job description: ("send", skills), ("skip", []) or ("retry", [])."""
    description = fetch_description(job["id"])
    if not description:
        return "retry", []  # LinkedIn didn't answer; try again next run
    text = f"{job['title']}\n{description}"
    reason = ineligible_reason(text)
    if reason:
        print(f"[skip] {job['title']} - {reason}")
        return "skip", []
    return "send", match_skills(text)

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
    new_jobs = list(find_new_jobs(set(seen)).values())
    print(f"[info] {len(new_jobs)} new relevant job(s)")
    if len(new_jobs) > MAX_JOBS_CHECKED_PER_RUN:
        print(f"[info] checking {MAX_JOBS_CHECKED_PER_RUN} now, the rest next run")

    for job in new_jobs[:MAX_JOBS_CHECKED_PER_RUN]:
        status, skills = check_job(job)
        _pause(1.0, 2.0)
        sent = status == "send" and send_ntfy(job["title"], build_message(job, skills), job["link"])
        if status == "skip" or sent:
            seen = [*seen, job["id"]]  # never check this job again
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
