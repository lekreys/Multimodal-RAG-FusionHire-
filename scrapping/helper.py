import time
import re
import hashlib
from typing import List, Dict, Any, Callable, Optional
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Use shared driver factory
from utils.selenium_driver import create_chrome_driver


class LokerScraper:
    
    BASE_URL = "https://www.loker.id/cari-lowongan-kerja"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.query = ""
    
    def _create_driver(self) -> webdriver.Chrome:
        """Create Chrome WebDriver using shared factory."""
        return create_chrome_driver(headless=self.headless, window_size="1920,1080")
    
    def _generate_job_id(self, url: str) -> str:
        parts = url.rstrip('/').split('/')
        if parts:
            slug = parts[-1]
            return f"loker_{slug[:50]}"
        return f"loker_{hashlib.md5(url.encode()).hexdigest()[:12]}"
    
    def scrape_job_urls(self, query: str, max_page: int = 2,
                        progress_callback: Callable[[str], None] = None) -> List[str]:

        def log(msg: str):
            print(msg)
            if progress_callback:
                progress_callback(msg)
        
        from urllib.parse import quote
        self.query = query
        
        log(f"\n{'='*50}")
        log(f"📋 SCRAPING LOKER.ID URLS (Query: '{query}', Pages 1-{max_page})")
        log(f"{'='*50}")
        
        driver = self._create_driver()
        all_links = []
        
        try:
            for page in range(1, max_page + 1):
                if page == 1:
                    url = f"{self.BASE_URL}?q={quote(query)}"
                else:
                    url = f"{self.BASE_URL}/page/{page}?q={quote(query)}"
                
                log(f"\n📄 Page {page}/{max_page}: Loading...")
                driver.get(url)
                
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(3)
                
                cards = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".card.relative.flex.flex-col.gap-3.h-full.group.will-change-transform"
                )
                
                log(f"   Found {len(cards)} job cards")
                
                if not cards:
                    log("   ⚠️ No cards found, stopping pagination")
                    break
                
                for card in cards:
                    try:
                        a_tag = card.find_element(By.TAG_NAME, "a")
                        href = a_tag.get_attribute("href")
                        if href and href not in all_links:
                            all_links.append(href)
                    except:
                        pass
                
                log(f"   ✅ Collected {len(all_links)} unique URLs so far")
                time.sleep(2)
                
        except Exception as e:
            log(f"   ❌ Error: {e}")
        finally:
            driver.quit()
        
        log(f"\n{'='*50}")
        log(f"✅ URL COLLECTION COMPLETE: {len(all_links)} URLs")
        log(f"{'='*50}")
        
        return all_links
    
    def _scrape_job_detail_with_driver(self, driver: webdriver.Chrome, url: str) -> Dict[str, Any]:
        """Scrape individual job page using existing driver (optimized)."""

        def normalize_education(s: str) -> str:
            if not s:
                return s
            s_low = s.lower()
            if "diploma" in s_low:
                return "Diploma (D1–D3)"
            if "sarjana" in s_low or "s1" in s_low:
                return "Sarjana (S1)"
            if "sma" in s_low or "smk" in s_low or "stm" in s_low:
                return "SMA / SMK / STM"
            return s

        def clean_skill(s: str) -> str:
            if not s:
                return s
            s = s.strip()
            s = re.sub(r"\.+$", "", s)
            s = re.sub(r"\s+", " ", s)
            return s

        def pick_name(x):
            if isinstance(x, dict):
                return x.get("name")
            return x

        def norm_label(s: str) -> str:
            s = (s or "").strip().lower()
            s = s.replace(":", "")
            s = re.sub(r"\s+", " ", s)
            return s

        try:
            driver.get(url)
            WebDriverWait(driver, 25).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.detail-job"))
            )
            time.sleep(1.5)
            html = driver.page_source
        except Exception as e:
            return {"error": str(e), "url": url}

        soup = BeautifulSoup(html, "html.parser")

        detail = (
            soup.select_one("div.card.default.overflow-hidden.detail-job") or
            soup.select_one("div.detail-job")
        )

        job_title = None
        company_name = None
        posted_relative = None
        posted_datetime = None

        if detail:
            title_el = detail.select_one("h1.title")
            job_title = title_el.get_text(strip=True) if title_el else None

            company_a = detail.select_one('a[href^="/profile/"]')
            if company_a:
                span = company_a.select_one("span")
                company_name = span.get_text(strip=True) if span else company_a.get_text(strip=True)

            time_el = detail.select_one("time.from-now")
            if time_el:
                posted_relative = time_el.get_text(strip=True)
                posted_datetime = time_el.get("datetime")

        def get_section_value(label: str):
            if not detail:
                return None

            target = norm_label(label)
            candidates = detail.select("div.font-bold, strong, b, p, span")
            for node in candidates:
                t = norm_label(node.get_text(" ", strip=True))
                if t == target:
                    container = node.parent
                    for _ in range(4):
                        if not container:
                            break

                        if target == "pendidikan":
                            links = container.select("a[href]")
                            vals = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
                            if vals:
                                return vals

                        a = container.select_one("a[href]")
                        if a and a.get_text(strip=True) and norm_label(a.get_text(strip=True)) != target:
                            return a.get_text(strip=True)

                        span = container.select_one("span")
                        if span and span.get_text(strip=True) and norm_label(span.get_text(strip=True)) != target:
                            return span.get_text(strip=True)

                        txt = container.get_text(" ", strip=True)
                        txt_norm = norm_label(txt)
                        if txt_norm.startswith(target):
                            raw = txt[len(label):].strip().lstrip(":").strip()
                            if raw:
                                return raw

                        container = container.parent

            return None

        location = get_section_value("Lokasi")
        job_type = get_section_value("Tipe Pekerjaan")
        job_level = get_section_value("Level Pekerjaan")
        job_function = get_section_value("Fungsi")
        education = get_section_value("Pendidikan") or []
        salary = get_section_value("Gaji")

        if isinstance(education, list):
            education = [normalize_education(e) for e in education if e]
            seen = set()
            education = [x for x in education if not (x in seen or seen.add(x))]
        else:
            education = []

        desc_container = soup.select_one("div.grid.grid-cols-1.gap-8.mt-4.md\\:mt-6")

        description = None
        skills = []

        if desc_container:
            for b in desc_container.select("div.badge"):
                t = clean_skill(b.get_text(" ", strip=True))
                if t:
                    skills.append(t)

            seen = set()
            skills = [x for x in skills if not (x.lower() in seen or seen.add(x.lower()))]

            parts = []
            for node in desc_container.find_all(["h2", "p", "li"], recursive=True):
                txt = node.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)
            description = "\n".join(parts).strip() if parts else None

        job_id = self._generate_job_id(url)

        glints_style = {
            "job_id": job_id,
            "url": url,
            "title": job_title,
            "company": company_name,
            "logo": "",
            "salary": salary,
            "posted_at": posted_relative,
            "work_type": pick_name(job_type),
            "experience": pick_name(job_level),
            "education": ", ".join(education) if education else "",
            "requirements_tags": education,
            "skills": skills,
            "benefits": [],
            "description": description,
            "address": pick_name(location),
            "source": "loker.id",
            "job_function": pick_name(job_function),
            "posted_datetime": posted_datetime,
        }

        return glints_style

    def scrape_job_detail(self, url: str) -> Dict[str, Any]:
        """Scrape individual job page (creates new driver - for single job use)."""
        driver = self._create_driver()
        try:
            return self._scrape_job_detail_with_driver(driver, url)
        finally:
            driver.quit()
    
    def scrape_all_jobs(self, urls: List[str],
                        progress_callback: Callable[[str], None] = None) -> List[Dict[str, Any]]:
        """Scrape all job details (OPTIMIZED: reuses single driver)."""

        def log(msg: str):
            print(msg)
            if progress_callback:
                progress_callback(msg)
        
        log(f"\n{'='*50}")
        log(f"🔍 SCRAPING {len(urls)} JOB DETAILS FROM LOKER.ID")
        log(f"{'='*50}")
        
        jobs = []
        successful = 0
        failed = 0
        
        # Create driver ONCE and reuse for all jobs
        driver = self._create_driver()
        
        try:
            for i, url in enumerate(urls, 1):
                log(f"\n[{i}/{len(urls)}] Scraping: {url[:60]}...")
                
                try:
                    job = self._scrape_job_detail_with_driver(driver, url)
                    
                    if "error" in job:
                        failed += 1
                        log(f"   ❌ Error: {job['error']}")
                    else:
                        successful += 1
                        jobs.append(job)
                        log(f"   ✅ {job.get('title', 'N/A')} @ {job.get('company', 'N/A')}")
                        
                except Exception as e:
                    failed += 1
                    log(f"   ❌ Exception: {e}")
                
                # Rate limiting (reduced since no driver restart overhead)
                time.sleep(1.5)
        
        finally:
            driver.quit()
        
        log(f"\n{'='*50}")
        log(f"✅ SCRAPING COMPLETE: {successful}/{len(urls)} successful")
        log(f"{'='*50}")
        
        return jobs


def scrape_loker_jobs(query: str, max_page: int = 2,
                      headless: bool = True,
                      progress_callback: Callable[[str], None] = None) -> List[Dict[str, Any]]:

    scraper = LokerScraper(headless=headless)
    urls = scraper.scrape_job_urls(query, max_page, progress_callback)
    jobs = scraper.scrape_all_jobs(urls, progress_callback)
    return [j for j in jobs if "error" not in j]
