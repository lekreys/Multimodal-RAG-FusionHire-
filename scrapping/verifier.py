"""
Job availability verifier.

Visits each job URL via Selenium (httpx/requests get 403 from Glints) and
detects whether the listing is still open. Updates DataSkripsi:
  - status confirmed ACTIVE  → is_active=True, failed_check_count=0, last_verified_at=now
  - status confirmed CLOSED  → failed_check_count += 1; flip is_active=False at threshold
  - status UNKNOWN           → no DB write (preserves prior state, avoids false flagging)

Retrieval only honours is_active when env FILTER_INACTIVE_JOBS=true, so running
this script with the flag OFF is safe — it populates the column without changing
user-facing behaviour.

Use via the CLI runner: `python -m scripts.run_verifier --help`
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import DataSkripsi
from utils.logger import get_logger
from utils.selenium_driver import create_chrome_driver

logger = get_logger(__name__)


# Strike threshold before flipping is_active=False. Network glitches happen;
# we want 3 consecutive CLOSED detections before trusting the verdict.
STRIKE_THRESHOLD = 3

# Delay between page visits (seconds). Be polite — avoid rate-limit triggers.
REQUEST_DELAY_SECONDS = 2.0

# Per-page load timeout.
PAGE_LOAD_TIMEOUT = 20

# Cookie file path (mirrors GlintsScraper convention).
GLINTS_COOKIE_FILE = Path(__file__).parent / "glints_cookies.json"


class JobStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    job_id: str
    url: str
    status: JobStatus
    note: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Per-source detectors
# Each takes (driver_after_navigation, url) and returns a JobStatus.
# ──────────────────────────────────────────────────────────────────────────────


def detect_glints(driver: webdriver.Chrome, url: str) -> CheckResult:
    """
    Defense-in-depth detection for Glints closed listings.

    Checked in order from most to least reliable:
      1. __NEXT_DATA__ JSON contains "status":"CLOSED" (structured data, most stable)
      2. <title> contains "(closed) | glints" (SEO pattern, very stable)
      3. body text contains "lowongan ini telah ditutup" (UI text, can change)

    All three signals were observed on the same closed listing — agreement is the
    norm, so any one matching is enough to verdict CLOSED.
    """
    try:
        body_text = (driver.find_element("tag name", "body").text or "")
        page_html = driver.page_source or ""
        page_title = driver.title or ""
    except WebDriverException as e:
        return CheckResult("", url, JobStatus.UNKNOWN, f"page unreadable: {e}")

    text_lower = body_text.lower()
    html_lower = page_html.lower()
    title_lower = page_title.lower()

    # Signal 1: structured data in __NEXT_DATA__ — most reliable.
    if '"status":"closed"' in html_lower:
        return CheckResult("", url, JobStatus.CLOSED, "__NEXT_DATA__ status=CLOSED")

    # Signal 2: SEO title pattern.
    if "(closed) | glints" in title_lower:
        return CheckResult("", url, JobStatus.CLOSED, f"title marker: {page_title!r}")

    # Signal 3: user-facing text (fallback).
    closed_signals = [
        "lowongan ini telah ditutup",
        "lowongan ini sudah ditutup",
        "job is no longer accepting",
        "this job is closed",
    ]
    if any(sig in text_lower for sig in closed_signals):
        return CheckResult("", url, JobStatus.CLOSED, "matched closed text signal")

    # Sanity: an active listing usually has key sections. If none of these
    # appear, the page probably failed to load (don't penalise the job).
    active_signals = ["deskripsi pekerjaan", "job description", "tentang perusahaan", "about company"]
    if any(sig in text_lower for sig in active_signals):
        return CheckResult("", url, JobStatus.ACTIVE, "matched active signal")

    return CheckResult("", url, JobStatus.UNKNOWN, "no signal matched (page may have failed to load)")


def detect_jobstreet(driver: webdriver.Chrome, url: str) -> CheckResult:
    """
    Defense-in-depth detection for Jobstreet expired listings.

    Checked in order from most to least reliable:
      1. data-automation="expiredJobPage" attribute (test automation, very stable)
      2. "isExpired":true in SEEK_REDUX_DATA (GraphQL structured data)
      3. "jobStatus":"expired" in window.SK_DL (analytics data layer)
      4. body text "lowongan kerja ini tidak lagi diiklankan" (UI text, fallback)

    Active is confirmed positively via "isExpired":false in the same structured
    data — no UI text guessing needed.
    """
    try:
        body_text = driver.find_element("tag name", "body").text or ""
        page_html = driver.page_source or ""
    except WebDriverException as e:
        return CheckResult("", url, JobStatus.UNKNOWN, f"page unreadable: {e}")

    text_lower = body_text.lower()
    html_lower = page_html.lower()

    # Signal 1: data-automation="expiredJobPage" — test attribute, very stable.
    if 'data-automation="expiredjobpage"' in html_lower:
        return CheckResult("", url, JobStatus.CLOSED, 'data-automation=expiredJobPage')

    # Signal 2: SEEK_REDUX_DATA isExpired field — structured data.
    if '"isexpired":true' in html_lower:
        return CheckResult("", url, JobStatus.CLOSED, 'SEEK_REDUX_DATA isExpired=true')

    # Signal 3: SK_DL analytics data layer.
    if '"jobstatus":"expired"' in html_lower:
        return CheckResult("", url, JobStatus.CLOSED, 'SK_DL jobStatus=expired')

    # Signal 4: user-facing text (fallback).
    closed_signals = [
        "lowongan kerja ini tidak lagi diiklankan",
        "this job is no longer advertised",
        "this job is no longer being advertised",
    ]
    if any(sig in text_lower for sig in closed_signals):
        return CheckResult("", url, JobStatus.CLOSED, "matched closed text signal")

    # Positive active signal — same structured data flag as above, inverted.
    if '"isexpired":false' in html_lower:
        return CheckResult("", url, JobStatus.ACTIVE, "SEEK_REDUX_DATA isExpired=false")

    # Fallback active signal: page contains typical job-detail text.
    active_signals = ["deskripsi pekerjaan", "job description", "lamar sekarang", "quick apply"]
    if any(sig in text_lower for sig in active_signals):
        return CheckResult("", url, JobStatus.ACTIVE, "matched active text signal")

    return CheckResult("", url, JobStatus.UNKNOWN, "no signal matched (page may have failed to load)")


DETECTORS = {
    "glints": detect_glints,
    "jobstreet": detect_jobstreet,
}


# ──────────────────────────────────────────────────────────────────────────────
# Cookie loading
# ──────────────────────────────────────────────────────────────────────────────


def _load_glints_cookies(driver: webdriver.Chrome) -> None:
    if not GLINTS_COOKIE_FILE.exists():
        logger.warning("Glints cookie file not found: %s", GLINTS_COOKIE_FILE)
        return

    driver.get("https://glints.com/")
    time.sleep(2)

    try:
        with open(GLINTS_COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except Exception as e:
        logger.error("Failed to read glints cookies: %s", e)
        return

    loaded = 0
    for c in cookies:
        cookie = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".glints.com"),
            "path": c.get("path", "/"),
        }
        if "expirationDate" in c:
            try:
                cookie["expiry"] = int(c["expirationDate"])
            except Exception:
                pass
        try:
            driver.add_cookie(cookie)
            loaded += 1
        except Exception:
            pass
    logger.info("Loaded %d glints cookies", loaded)


# ──────────────────────────────────────────────────────────────────────────────
# Core verifier
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_detector(source: Optional[str]):
    """Lookup detector by substring match — handles source variants like
    'glints_scrape', 'Glints', 'jobstreet_v2', etc. without rigid exact match."""
    s = (source or "").lower()
    for key, fn in DETECTORS.items():
        if key in s:
            return fn
    return None


def check_one(driver: webdriver.Chrome, job: DataSkripsi) -> CheckResult:
    detector = _resolve_detector(job.source)
    if detector is None:
        return CheckResult(job.job_id, job.url, JobStatus.UNKNOWN, f"no detector for source={job.source!r}")

    try:
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        driver.get(job.url)
        time.sleep(1.5)  # let JS settle
    except TimeoutException:
        # DOM is usually ready well before all assets (ads, analytics) finish.
        # Stop pending loads and try the detector anyway — our signals live in
        # server-rendered HTML / inline script data, not in late-loaded JS.
        logger.warning("page load timeout for %s — stopping loads and trying detector", job.job_id)
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    except WebDriverException as e:
        return CheckResult(job.job_id, job.url, JobStatus.UNKNOWN, f"navigation error: {e}")

    result = detector(driver, job.url)
    result.job_id = job.job_id
    return result


def apply_result(db: Session, job: DataSkripsi, result: CheckResult, dry_run: bool) -> None:
    """Apply 3-strike rule to DB. UNKNOWN never writes."""
    if result.status == JobStatus.UNKNOWN:
        logger.info("[unknown ] %s | %s", job.job_id, result.note)
        return

    if result.status == JobStatus.ACTIVE:
        prev = "active" if job.is_active else "INACTIVE"
        logger.info("[ACTIVE  ] %s | prev=%s strikes=%d", job.job_id, prev, job.failed_check_count)
        if dry_run:
            return
        job.is_active = True
        job.failed_check_count = 0
        job.last_verified_at = datetime.utcnow()
        return

    # CLOSED → increment strike, flip if threshold reached.
    new_strikes = (job.failed_check_count or 0) + 1
    will_flip = new_strikes >= STRIKE_THRESHOLD and job.is_active
    logger.info(
        "[CLOSED  ] %s | strikes %d→%d%s",
        job.job_id, job.failed_check_count, new_strikes,
        " | FLIPPING to inactive" if will_flip else ""
    )
    if dry_run:
        return
    job.failed_check_count = new_strikes
    job.last_verified_at = datetime.utcnow()
    if will_flip:
        job.is_active = False


def run(
    limit: Optional[int] = None,
    source: Optional[str] = None,
    only_unverified: bool = False,
    dry_run: bool = False,
    headless: bool = True,
) -> None:
    db = SessionLocal()
    driver: Optional[webdriver.Chrome] = None
    try:
        q = db.query(DataSkripsi)
        if source:
            # Case-insensitive partial match — `--source glints` matches
            # 'glints', 'Glints', 'glints_scrape', etc.
            q = q.filter(DataSkripsi.source.ilike(f"%{source}%"))
        if only_unverified:
            q = q.filter(DataSkripsi.last_verified_at.is_(None))
        q = q.order_by(DataSkripsi.last_verified_at.asc().nullsfirst(), DataSkripsi.created_at.asc())
        if limit:
            q = q.limit(limit)

        jobs: List[DataSkripsi] = q.all()
        logger.info("Verifier starting: %d job(s) | dry_run=%s | source=%s",
                    len(jobs), dry_run, source or "all")

        if not jobs:
            logger.info("No jobs to verify, exiting.")
            return

        driver = create_chrome_driver(headless=headless)
        # Glints needs cookies for some listings; load once at start.
        # Substring match so variants like 'glints_scrape' also trigger cookie load.
        if any("glints" in (j.source or "").lower() for j in jobs):
            _load_glints_cookies(driver)

        counts = {JobStatus.ACTIVE: 0, JobStatus.CLOSED: 0, JobStatus.UNKNOWN: 0}
        flipped = 0

        for i, job in enumerate(jobs, 1):
            logger.info("(%d/%d) checking %s | %s", i, len(jobs), job.job_id, job.url)
            result = check_one(driver, job)
            counts[result.status] += 1

            was_active = job.is_active
            apply_result(db, job, result, dry_run)
            if was_active and not job.is_active:
                flipped += 1

            if not dry_run and i % 20 == 0:
                db.commit()

            time.sleep(REQUEST_DELAY_SECONDS)

        if not dry_run:
            db.commit()

        logger.info(
            "Verifier done | active=%d closed=%d unknown=%d | flipped_to_inactive=%d | dry_run=%s",
            counts[JobStatus.ACTIVE], counts[JobStatus.CLOSED], counts[JobStatus.UNKNOWN],
            flipped, dry_run,
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        db.close()
