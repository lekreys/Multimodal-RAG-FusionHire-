import time
import re
import json
import hashlib
from typing import List, Dict, Any, Callable, Optional
from urllib.parse import urljoin, quote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from utils.selenium_driver import create_chrome_driver
from utils.logger import get_logger

logger = get_logger(__name__)


class JobStreetScraper:
    
    BASE_URL = "https://id.jobstreet.com"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.query = ""
    
    def _create_driver(self) -> webdriver.Chrome:
        return create_chrome_driver(headless=self.headless, window_size="1366,768")
    
    def _generate_job_id(self, url: str) -> str:
        match = re.search(r'/job/(\d+)', url)
        if match:
            return f"jobstreet_{match.group(1)}"
        return f"jobstreet_{hashlib.md5(url.encode()).hexdigest()[:12]}"
    
    def scrape_job_urls(self, query: str, max_page: int = 2,
                        progress_callback: Callable[[str], None] = None) -> List[str]:
        
        def log(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)
        
        self.query = query
        query_slug = re.sub(r'\s+', '-', query.strip().lower())
        
        log(f"\n{'='*50}")
        log(f" SCRAPING JOBSTREET URLS (Query: '{query}', Pages 1-{max_page})")
        log(f"{'='*50}")
        
        driver = self._create_driver()
        all_links = []
        prev_page_links = set()
        
        try:
            for page in range(1, max_page + 1):
                if page == 1:
                    url = f"{self.BASE_URL}/id/{query_slug}-jobs"
                else:
                    url = f"{self.BASE_URL}/id/{query_slug}-jobs?page={page}"
                
                log(f"\n Page {page}/{max_page}: Loading {url}")
                
                old_elements = None
                if page > 1:
                    try:
                        old_elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/id/job/"]')
                    except:
                        pass
                
                driver.get(url)
                
                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'a[href*="/id/job/"]')
                        )
                    )
                except:
                    log("    Timeout waiting for job links")
                
                if page > 1 and old_elements:
                    try:
                        from selenium.webdriver.support.expected_conditions import staleness_of
                        WebDriverWait(driver, 10).until(staleness_of(old_elements[0]))
                        log("    Page content refreshed")
                    except:
                        log("    Waiting extra time for SPA re-render...")
                        time.sleep(4)
                
                time.sleep(4)
                
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
                time.sleep(2)
                
                soup = BeautifulSoup(driver.page_source, "html.parser")
                
                page_links = []
                for a in soup.find_all("a", href=re.compile(r"^/id/job/\d+")):
                    href = a["href"]
                    clean_href = re.sub(r'\?.*$', '', href)
                    full_url = urljoin(self.BASE_URL, clean_href)
                    if full_url not in page_links:
                        page_links.append(full_url)
                
                log(f"   Found {len(page_links)} job links on page {page}")
                
                if not page_links:
                    log("    No job links found, stopping pagination")
                    break
                
                current_set = set(page_links)
                new_links = [l for l in page_links if l not in all_links]
                
                if page > 1 and len(new_links) == 0:
                    log(f"   No new URLs found (all {len(page_links)} are duplicates), stopping")
                    break
                
                for link in page_links:
                    if link not in all_links:
                        all_links.append(link)
                
                log(f"    New: {len(new_links)}, Total: {len(all_links)}")
                prev_page_links = current_set
                time.sleep(2)
                
        except Exception as e:
            log(f"    Error: {e}")
        finally:
            driver.quit()
        
        log(f"\n{'='*50}")
        log(f" URL COLLECTION COMPLETE: {len(all_links)} URLs")
        log(f"{'='*50}")
        
        return all_links
    
    def _scrape_job_detail_with_driver(self, driver: webdriver.Chrome, url: str) -> Dict[str, Any]:
        
        def el_text(el) -> str:
            return el.get_text(" ", strip=True) if el else ""
        
        def clean_text(x: str) -> str:
            return " ".join((x or "").split()).strip()
        
        def is_valid_skill(s: str) -> bool:
            x = clean_text(s).lower()
            if not x or len(x) < 2 or len(x) > 50:
                return False
            
            blacklist_exact = {
                "bagaimana anda cocok",
                "kecocokan berdasarkan riwayat karir anda",
                "tidak ditemukan di profil anda",
                "apakah keterampilan ini akurat?",
                "sembunyikan semua",
                "ya", "tidak", "help",
            }
            if x in blacklist_exact:
                return False
            
            blacklist_contains = ["bantu kami", "mencocokkan", "tambahkan"]
            for bad in blacklist_contains:
                if bad in x:
                    return False
            
            return True
        
        try:
            driver.get(url)
            
            try:
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            except:
                pass
            
            for frac in [0.25, 0.55, 0.85]:
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {frac});")
                time.sleep(0.8)
            
            html = driver.page_source
            
        except Exception as e:
            return {"error": str(e), "url": url, "source": "jobstreet"}
        
        soup = BeautifulSoup(html, "html.parser")
        
        data = {
            "job_id": self._generate_job_id(url),
            "url": url,
            "title": "",
            "company": "",
            "logo": "",
            "salary": "",
            "posted_at": "",
            "work_type": "",
            "experience": "",
            "education": "",
            "requirements_tags": [],
            "skills": [],
            "benefits": [],
            "description": "",
            "address": "",
            "source": "jobstreet",
            "posted_datetime": "",
        }
        
        jsonld_job = None
        for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = (sc.string or "").strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except:
                continue

            candidates = [parsed] if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
            for item in candidates:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    jsonld_job = item
                    break
            if jsonld_job:
                break

        if jsonld_job:
            data["title"] = (jsonld_job.get("title") or "").strip()

            hiring_org = jsonld_job.get("hiringOrganization")
            if isinstance(hiring_org, dict):
                data["company"] = (hiring_org.get("name") or "").strip()

            job_loc = jsonld_job.get("jobLocation")
            loc_obj = None
            if isinstance(job_loc, list) and job_loc:
                loc_obj = job_loc[0]
            elif isinstance(job_loc, dict):
                loc_obj = job_loc

            address = {}
            if isinstance(loc_obj, dict) and isinstance(loc_obj.get("address"), dict):
                address = loc_obj["address"]

            loc_parts = []
            for k in ["addressLocality", "addressRegion", "addressCountry"]:
                v = address.get(k)
                if v:
                    loc_parts.append(str(v))
            data["address"] = ", ".join(loc_parts).strip(", ")

            data["work_type"] = (jsonld_job.get("employmentType") or "").strip()
            data["posted_datetime"] = (jsonld_job.get("datePosted") or "").strip()

            desc = (jsonld_job.get("description") or "").strip()
            desc = re.sub(r"<br\s*/?>", "\n", desc, flags=re.I)
            desc = re.sub(r"</p\s*>", "\n", desc, flags=re.I)
            desc = re.sub(r"<.*?>", "", desc, flags=re.S)
            data["description"] = desc.strip()

        if not data["title"]:
            h1 = soup.find("h1")
            data["title"] = el_text(h1)

        if not data["company"]:
            company_el = soup.select_one('[data-automation="advertiser-name"]')
            if not company_el:
                company_el = soup.select_one('[data-automation="job-company-name"]')
            if not company_el:
                company_el = soup.select_one('a[href*="companies"], a[href*="company"]')
            data["company"] = el_text(company_el)

        if not data["address"]:
            loc_el = soup.select_one('[data-automation="job-detail-location"]')
            data["address"] = el_text(loc_el)

        if not data["work_type"]:
            wt_el = soup.select_one('[data-automation="job-detail-work-type"]')
            data["work_type"] = el_text(wt_el)

        if not data["posted_at"]:
            posted_el = soup.select_one('[data-automation="job-detail-date"]')
            data["posted_at"] = el_text(posted_el)

        if not data["description"]:
            desc_el = soup.select_one('[data-automation="jobAdDetails"]') or soup.select_one('[data-testid="job-description"]')
            data["description"] = el_text(desc_el)

        skills = []
        for btn in soup.find_all("button"):
            aria_label = btn.get("aria-label", "")
            if aria_label.startswith("Tambahkan "):
                skill = aria_label.replace("Tambahkan ", "").strip()
                if skill and is_valid_skill(skill):
                    skills.append(skill)

        if not skills:
            how_match_section = None
            for tag in soup.find_all(True):
                text = tag.get_text(strip=True) if hasattr(tag, 'get_text') else ""
                if text == "Bagaimana Anda cocok":
                    parent = tag
                    for _ in range(15):
                        if parent.parent:
                            parent = parent.parent
                            title_divs = parent.find_all(attrs={"title": True})
                            if len(title_divs) >= 5:
                                how_match_section = parent
                                break
                    break
            
            if how_match_section:
                for el in how_match_section.find_all(attrs={"title": True}):
                    title = el.get("title", "").strip()
                    if title and is_valid_skill(title):
                        skills.append(title)

        if not skills:
            for div in soup.find_all("div", attrs={"title": True}):
                title = div.get("title", "").strip()
                parent = div.parent
                has_add_button = False
                if parent:
                    for btn in parent.find_all("button"):
                        if "Tambahkan" in btn.get("aria-label", ""):
                            has_add_button = True
                            break
                
                if title and is_valid_skill(title) and has_add_button:
                    skills.append(title)

        seen = set()
        clean_skills = []
        for s in skills:
            key = clean_text(s).lower()
            if key in seen:
                continue
            seen.add(key)
            clean_skills.append(s)

        data["skills"] = clean_skills
        
        return data
    
    def scrape_all_jobs(self, urls: List[str],
                        progress_callback: Callable[[str], None] = None) -> List[Dict[str, Any]]:
        
        def log(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)
        
        log(f"\n{'='*50}")
        log(f" SCRAPING {len(urls)} JOB DETAILS FROM JOBSTREET")
        log(f"{'='*50}")
        
        jobs = []
        successful = 0
        failed = 0
        
        driver = self._create_driver()
        
        try:
            for i, url in enumerate(urls, 1):
                log(f"\n[{i}/{len(urls)}] Scraping: {url[:60]}...")
                
                try:
                    job = self._scrape_job_detail_with_driver(driver, url)
                    
                    if "error" in job:
                        failed += 1
                        log(f"    Error: {job['error']}")
                    else:
                        successful += 1
                        jobs.append(job)
                        log(f"    {job.get('title', 'N/A')} @ {job.get('company', 'N/A')}")
                        
                except Exception as e:
                    failed += 1
                    log(f"    Exception: {e}")
                
                time.sleep(1.5)
        
        finally:
            driver.quit()
        
        log(f"\n{'='*50}")
        log(f" SCRAPING COMPLETE: {successful}/{len(urls)} successful")
        log(f"{'='*50}")
        
        return jobs


def scrape_jobstreet_jobs(query: str, max_page: int = 2,
                          headless: bool = True,
                          progress_callback: Callable[[str], None] = None) -> List[Dict[str, Any]]:
    """Convenience function to scrape JobStreet jobs."""
    scraper = JobStreetScraper(headless=headless)
    urls = scraper.scrape_job_urls(query, max_page, progress_callback)
    jobs = scraper.scrape_all_jobs(urls, progress_callback)
    return [j for j in jobs if "error" not in j]
