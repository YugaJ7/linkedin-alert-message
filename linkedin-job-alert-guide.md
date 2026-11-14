# LinkedIn Intern Job Alert — Complete Setup Guide

Get an **instant phone notification** whenever a new internship matching your keywords (SDE intern, Software Engineer intern, Flutter intern, Mobile App intern, and similar titles) is posted on LinkedIn. Tap the notification to open the job.

**Stack:** Python script + GitHub Actions (runs in the cloud for free) + cron-job.org (reliable 5-minute timer) + ntfy (free push notifications).

**Total cost:** ₹0. **Setup time:** about 45 minutes.

---

## How it works

```
cron-job.org (every 5 min)
        │  triggers
        ▼
GitHub Actions  ──►  job_alert.py  ──►  LinkedIn public job search
                          │
                          ├─ filters titles by keywords and synonyms
                          ├─ skips jobs already sent (seen_jobs.json)
                          ▼
                     ntfy.sh  ──►  📱 push notification on your phone
                                     (tap → opens the LinkedIn job)
```

**Expected speed:** a job posted on LinkedIn usually reaches your phone within **5–7 minutes**.

---

## What you need

- A laptop or PC with internet access
- A GitHub account (free)
- A cron-job.org account (free)
- The ntfy app on your phone (free)

---

## Phase 1: Prepare your laptop

### Step 1: Install Python
1. Download Python 3.11 or newer from **https://www.python.org/downloads/**.
2. **Windows:** tick **"Add Python to PATH"** during installation.
3. Open Command Prompt and check that it installed:
   ```
   python --version
   ```

### Step 2: Create the project folder
1. Create a folder called `linkedin-job-alert`.
2. Inside it, create these files with the contents given in the [Appendix](#appendix--project-files):
   ```
   linkedin-job-alert/
   ├── job_alert.py
   ├── requirements.txt
   └── .github/
       └── workflows/
           └── job-alert.yml
   ```
   **Windows tip:** File Explorer won't let you create a folder named `.github`. Create it from Command Prompt instead:
   ```
   cd path\to\linkedin-job-alert
   mkdir .github\workflows
   ```

### Step 3: Install the libraries
```
cd path\to\linkedin-job-alert
pip install -r requirements.txt
```

---

## Phase 2: Set up ntfy on your phone

### Step 4: Install the app
Search **ntfy** in the Play Store or App Store and install it. No sign-up is needed.

### Step 5: Choose a secret topic name
1. Make up a unique name that's hard to guess, for example `seven-jobs-x8k2q9`.
2. **Keep it private.** Anyone who knows the topic name can read your notifications.

### Step 6: Subscribe to your topic
1. Open ntfy and tap **+**.
2. Type your topic name and tap **Subscribe**.

### Step 7: Test from your laptop
**Windows:**
```
set NTFY_TOPIC=seven-jobs-x8k2q9
python job_alert.py --test
```
**Mac/Linux:**
```
export NTFY_TOPIC=seven-jobs-x8k2q9
python job_alert.py --test
```
You should get **"✅ Job alert is working"** on your phone. Tap it, and LinkedIn Jobs should open.

### Step 8: Give job alerts their own sound
**Android:**
1. **Long-press** the test notification and tap the **⚙ settings** icon.
2. This opens the settings for ntfy's **"Max priority"** notifications.
3. Tap **Sound** and choose a sound you'll recognize.
4. Turn on **Pop on screen**. If you want alerts even on silent, also turn on **Override Do Not Disturb**.
5. Go to **Phone Settings → Apps → ntfy → Battery** and select **Unrestricted**, so Android doesn't delay notifications.

**iPhone:** max-priority alerts arrive as "Time Sensitive" and get through Focus mode. iPhone doesn't allow custom sounds for ntfy.

### Step 9: Do a real check
```
python job_alert.py
```
If any matching jobs were posted in the last hour, you'll get one notification per job. `0 new relevant job(s)` in the output is also normal: it means nothing new was posted.

---

## Phase 3: Put it on GitHub

### Step 10: Create the repository
1. Sign in to **https://github.com** and click **New repository**.
2. Name it `linkedin-job-alert`.
3. Choose **Public**. Public repos get unlimited free GitHub Actions minutes; private repos get only 2,000 per month, which isn't enough for checking every 5 minutes.
   - Your topic name stays hidden in Secrets (Step 12), so nothing private is exposed.
4. Click **Create repository**.

### Step 11: Upload the files
1. Click **Add file → Upload files**, upload `job_alert.py` and `requirements.txt`, and click **Commit changes**.
2. Click **Add file → Create new file** and type this as the file name:
   ```
   .github/workflows/job-alert.yml
   ```
3. Paste in the workflow file contents from the Appendix and click **Commit changes**.

### Step 12: Add your secret
1. In your repo, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** and enter:
   - **Name:** `NTFY_TOPIC`
   - **Secret:** your topic name
3. Click **Add secret**.

### Step 13: Allow the bot to save its progress
1. Go to **Settings → Actions → General**.
2. Under **Workflow permissions**, select **Read and write permissions**.
3. Click **Save**.

### Step 14: Run it once by hand
1. Open the **Actions** tab. If GitHub asks, click **"I understand my workflows, go ahead and enable them"**.
2. Click **LinkedIn Intern Job Alert → Run workflow → Run workflow**.
3. Wait about a minute. A green ✅ means it worked.
4. A file called `seen_jobs.json` will appear in your repo. That's the bot's memory of jobs it has already sent you.

---

## Phase 4: Make it run every 5 minutes

GitHub's built-in timer (`schedule`) often runs 10–30 minutes late, so we use **cron-job.org** to start the workflow on time. GitHub's own timer stays as a backup.

### Step 15: Create a GitHub access token
1. On GitHub, click your profile picture → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. **Token name:** `cron trigger`
3. **Expiration:** 1 year. Set a reminder to renew it.
4. **Repository access:** choose **Only select repositories** and pick `linkedin-job-alert`.
5. **Permissions → Repository permissions → Actions:** choose **Read and write**.
6. Click **Generate token** and **copy it now**. It starts with `github_pat_`, and you can't view it again later.

### Step 16: Create the cron job
1. Sign up at **https://cron-job.org** and click **Create cronjob**.
2. **Common** tab:
   - **Title:** `Job alert`
   - **URL:** replace `YOUR_USERNAME` with your GitHub username:
     ```
     https://api.github.com/repos/YOUR_USERNAME/linkedin-job-alert/actions/workflows/job-alert.yml/dispatches
     ```
   - **Execution schedule:** every **5 minutes**
3. **Advanced** tab:
   - **Request method:** `POST`
   - **Headers:**

     | Key | Value |
     |---|---|
     | `Accept` | `application/vnd.github+json` |
     | `Authorization` | `Bearer github_pat_xxxxxxxx` |
     | `User-Agent` | `cron-job` |

   - **Request body:**
     ```json
     {"ref":"main"}
     ```
4. Click **Test run**. A response of **204** means success.
5. Click **Create**.

### Step 17: Confirm it's running
Open your repo's **Actions** tab. A new run should appear about every 5 minutes. 🎉 You're done.

---

## Phase 5: Customize it

All settings are at the top of `job_alert.py`, under `CONFIG`. Edit the file on GitHub by clicking it and then the ✏️ pencil icon.

| What you want | What to change |
|---|---|
| Add or remove search terms | `SEARCH_KEYWORDS`. Keep each line to about 3–4 `"..." OR "..."` terms. |
| Change cities | `LOCATIONS`, e.g. `"Bengaluru, Karnataka, India"` |
| Include or exclude remote jobs | Keep or remove `"India"` in `LOCATIONS` |
| Catch more job titles | Add words to `ROLE_PATTERN` |
| Block unwanted titles | Add words to `EXCLUDE_PATTERN` |
| Quieter notifications | Add a secret `NTFY_PRIORITY` = `3`, and add `NTFY_PRIORITY: ${{ secrets.NTFY_PRIORITY }}` under `env:` in the workflow |

**Keep the number of requests low.** Each run makes `len(SEARCH_KEYWORDS) × len(LOCATIONS)` requests (currently 4 × 4 = 16). Keep it under about 20, or LinkedIn may start blocking you.

---

## Phase 6: Using it day to day

- Each new job arrives as **one notification**. Tap it, or tap **Open job**. If the LinkedIn app is installed, the job usually opens in it.
- All past alerts stay listed inside the **ntfy app** under your topic.
- **Simple way to track applications:** delete a notification in ntfy after you apply, so what's left in the list is still to-do.

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Test notification never arrives | Wrong topic, or the app is battery-restricted | Check that the topic name matches exactly (Steps 6–7), and set ntfy's battery setting to **Unrestricted** |
| Actions log shows `HTTP 429` or `HTTP 999` | LinkedIn is blocking GitHub's servers | Wait a few hours, reduce `SEARCH_KEYWORDS` or `LOCATIONS`, or use laptop mode (below) |
| Log shows `0 new relevant job(s)` every time | Usually nothing new was posted | Normal. If it lasts for days, set `POSTED_WITHIN_SECONDS = 86400` once to test |
| cron-job.org shows `401` or `403` | Token is wrong, expired, or missing the Actions permission | Redo Step 15 and update the `Authorization` header |
| cron-job.org shows `404` | Wrong URL | Check your username, repo name, and the `job-alert.yml` file name |
| cron-job.org shows `422` | Branch name isn't `main` | Use your branch name in the body, e.g. `{"ref":"master"}` |
| Push error in "Save seen jobs" | Missing write permission | Redo Step 13 |
| Same job notified twice | Two runs overlapped before saving | Rare, and the `concurrency` setting prevents most cases; ignore it |
| Notifications arrive late | Phone battery optimization | Phone Settings → Apps → ntfy → Battery → **Unrestricted** |

### Laptop mode (fastest; works when GitHub gets blocked)
While your laptop is on:
```
set NTFY_TOPIC=seven-jobs-x8k2q9
python job_alert.py --loop 3
```
This checks every 3 minutes for as long as the window stays open. Don't go below 3 minutes. Laptop mode keeps its own `seen_jobs.json`, separate from GitHub's.

---

## Maintenance checklist

- **Every year:** renew the GitHub token (Step 15) and update it in cron-job.org.
- **If GitHub emails you that it "disabled a scheduled workflow" after 60 days of inactivity:** open the Actions tab and click **Enable workflow**. The cron-job.org trigger keeps working regardless.
- **If cron-job.org emails you about failures:** check the Troubleshooting table above.
- **If notifications stop entirely:** open the latest run in the Actions tab and read the log.

---

## Important notes

- This reads LinkedIn's **public, logged-out** job pages at a slow rate, for **personal use only**. That's technically against LinkedIn's terms of service, but the risk is low at this scale. **Never** add your LinkedIn login to this script.
- If LinkedIn changes its page layout, the script may stop finding jobs. The fix is usually updating the CSS selectors in `fetch_jobs()`.
- Your ntfy topic name works like a password. If it leaks, pick a new one: update the secret and resubscribe in the app.

---

## Appendix — Project files

### `requirements.txt`
```
requests
beautifulsoup4
```

### `.github/workflows/job-alert.yml`
```yaml
name: LinkedIn Intern Job Alert

on:
  schedule:
    - cron: "*/10 * * * *"   # backup timer (GitHub often runs this late)
  workflow_dispatch:          # cron-job.org triggers this every 5 minutes

concurrency:                  # never run two checks at the same time
  group: job-alert
  cancel-in-progress: false

permissions:
  contents: write             # lets the bot save seen_jobs.json

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install requests beautifulsoup4

      - name: Check for new jobs
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: python job_alert.py

      - name: Save seen jobs
        run: |
          git config user.name "job-alert-bot"
          git config user.email "bot@users.noreply.github.com"
          git add seen_jobs.json || true
          git diff --cached --quiet || git commit -m "update seen jobs [skip ci]"
          git pull --rebase || true
          git push || true
```

### `job_alert.py`
```python
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
```
