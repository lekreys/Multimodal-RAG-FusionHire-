import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import quote

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils.logger import get_logger
from utils.selenium_driver import create_chrome_driver

logger = get_logger(__name__)


class GlintsScraper:
    
    BASE_URL = "https://glints.com/id/opportunities/jobs/explore"
    
    def __init__(self, cookie_file: str = None, headless: bool = True, keyword: str = "it"):
        self.cookie_file = cookie_file or str(Path(__file__).parent / "glints_cookies.json")
        self.headless = headless
        self.keyword = keyword
        self.driver = None
    
    def _create_driver(self) -> webdriver.Chrome:
        return create_chrome_driver(headless=self.headless, window_size="1440,900")
    
    def _load_cookies(self, driver: webdriver.Chrome):
        driver.get("https://glints.com/")
        time.sleep(2)
        
        try:
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            
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
                except Exception:
                    pass
            
            driver.get("https://glints.com/")
            time.sleep(2)
            logger.info("Cookies loaded successfully")

        except FileNotFoundError:
            logger.warning("Cookie file not found: %s", self.cookie_file)
        except Exception as e:
            logger.error("Error loading cookies: %s", e)
    
    def scrape_job_urls(self, start_page: int = 1, end_page: int = 2,
                        progress_callback: Callable[[str], None] = None,
                        max_jobs: int = None) -> List[str]:

        def log(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        params = f"keyword={quote(self.keyword)}&country=ID&locationName=All+Cities%2FProvinces"

        log(f"\n{'='*50}")
        log(f" SCRAPING JOB URLS (Keyword: '{self.keyword}', Pages {start_page}-{end_page}, max_jobs={max_jobs or 'unlimited'})")
        log(f"{'='*50}")

        driver = self._create_driver()
        all_links = set()
        
        try:
            log("\n Loading cookies...")
            self._load_cookies(driver)
            
            for page in range(start_page, end_page + 1):
                url = f"{self.BASE_URL}?{params}&page={page}"
                log(f"\n Page {page}/{end_page}: Loading...")
                driver.get(url)

                # Wait for job cards instead of fixed sleep — returns as soon as DOM is ready.
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'div[data-glints-tracking-view-element-id]')
                        )
                    )
                except Exception:
                    log("   Timeout waiting for job cards (page may be empty or blocked)")

                if "/login" in driver.current_url:
                    log("   Redirected to login! Cookies may be expired.")
                    break
                
                soup = BeautifulSoup(driver.page_source, "html.parser")
                job_cards = soup.find_all("div", attrs={"data-glints-tracking-view-element-id": True})
                log(f"    Found {len(job_cards)} job cards")
                
                for card in job_cards:
                    job_id = card.get("data-glints-tracking-view-element-id")
                    title_tag = card.find("h2")
                    if not title_tag:
                        continue

                    title = title_tag.get_text(strip=True)
                    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                    link = f"https://glints.com/id/opportunities/jobs/{slug}/{job_id}"
                    all_links.add(link)

                    if max_jobs is not None and len(all_links) >= max_jobs:
                        break

                log(f"    Total URLs collected: {len(all_links)}")

                if max_jobs is not None and len(all_links) >= max_jobs:
                    log(f"    Reached max_jobs={max_jobs}, stopping pagination")
                    break
            
        finally:
            driver.quit()
        
        log(f"\n Finished! Collected {len(all_links)} unique job URLs")
        return list(all_links)
    
    def _scrape_job_detail_with_driver(self, driver: webdriver.Chrome, url: str) -> Dict[str, Any]:

        def clean_text(x: str) -> str:
            return " ".join((x or "").split()).strip()
        
        try:
            driver.get(url)
            
            wait = WebDriverWait(driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'h1[aria-label="Job Title"]')))
            
            soup = BeautifulSoup(driver.page_source, "html.parser")
            
            title = None
            title_el = soup.select_one('h1[aria-label="Job Title"]')
            if title_el:
                title = clean_text(title_el.get_text(" ", strip=True))
            
            company = None
            company_el = soup.select_one('div[class*="JobOverViewCompanyName"] a[href*="/id/companies/"]')
            if company_el:
                company = clean_text(company_el.get_text(" ", strip=True))
            
            logo = None
            logo_el = soup.select_one('img[alt="Company Logo"]')
            if logo_el and logo_el.get("src"):
                logo = logo_el["src"].strip()
            
            salary = None
            sal_el = soup.select_one('span[class*="BasicSalary"]')
            if sal_el:
                salary = clean_text(sal_el.get_text(" ", strip=True))
            
            posted_at = None
            posted_el = soup.select_one('span[class*="PostedAt"]')
            if posted_el:
                posted_at = clean_text(posted_el.get_text(" ", strip=True))
            
            req_tags = []
            for tag in soup.select('div[class*="JobRequirement"] div[class*="TagContentWrapper"]'):
                t = clean_text(tag.get_text(" ", strip=True))
                if t:
                    req_tags.append(t)
            
            work_type = None
            work_type_el = soup.find(string=lambda s: isinstance(s, str) and "Kerja di kantor" in s)
            if work_type_el:
                work_type = "Kerja di kantor"
            
            experience = None
            for t in req_tags:
                if "tahun pengalaman" in t:
                    experience = t
                    break
            
            education = None
            for t in req_tags:
                if "Minimal" in t and "Diploma" in t:
                    education = t
                    break
            
            skills = []
            for s in soup.select('div[class*="Skill"] p[class*="TagName"]'):
                st = clean_text(s.get_text(" ", strip=True))
                if st:
                    skills.append(st)
            
            if not skills:
                for s in soup.select('div[class*="Skill"] div[class*="TagContentWrapper"]'):
                    st = clean_text(s.get_text(" ", strip=True))
                    if st and st.lower() not in {"skills"}:
                        skills.append(st)
            
            benefits = []
            for b in soup.select('div[class*="Benefits"] div[class*="TagContentWrapper"]'):
                bt = clean_text(b.get_text(" ", strip=True))
                if bt:
                    benefits.append(bt)
            
            description = None
            desc_container = soup.select_one('div[aria-label="Job Description"] div[class*="DraftjsReader"]')
            if desc_container:
                ps = [clean_text(p.get_text(" ", strip=True)) for p in desc_container.select("p")]
                ps = [p for p in ps if p]
                if ps:
                    description = "\n".join(ps)
            
            address = None
            addr_el = soup.select_one('div[class*="AddressWrapper"] p')
            if addr_el:
                address = clean_text(addr_el.get_text(" ", strip=True))
            
            job_id = url.split("/")[-1] if url else None
            
            return {
                "job_id": job_id,
                "url": url,
                "title": title,
                "company": company,
                "logo": logo,
                "salary": salary,
                "posted_at": posted_at,
                "work_type": work_type,
                "experience": experience,
                "education": education,
                "requirements_tags": req_tags,
                "skills": skills,
                "benefits": benefits,
                "description": description,
                "address": address,
                "source": "glints_scrape"
            }
            
        except Exception as e:
            return {
                "url": url,
                "error": str(e),
                "source": "glints_scrape"
            }
    
    def scrape_all_jobs(self, urls: List[str],
                        progress_callback: Callable[[str], None] = None,
                        batch_callback: Callable[[int, int, Dict], None] = None) -> List[Dict[str, Any]]:
        """Scrape all job details (OPTIMIZED: reuses single driver)."""

        def log(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)
        
        log(f"\n{'='*50}")
        log(f" SCRAPING JOB DETAILS ({len(urls)} jobs)")
        log(f"{'='*50}")
        
        results = []
        
        driver = self._create_driver()
        
        try:
            for i, url in enumerate(urls, 1):
                log(f"\n[{i}/{len(urls)}] Scraping: {url[:60]}...")
                
                try:
                    job_data = self._scrape_job_detail_with_driver(driver, url)
                    
                    if "error" in job_data:
                        log(f"    Error: {job_data['error']}")
                    else:
                        log(f"    {job_data.get('title', 'Unknown')} @ {job_data.get('company', 'Unknown')}")
                    
                    results.append(job_data)
                    
                    if batch_callback:
                        batch_callback(i, len(urls), job_data)
                    
                    time.sleep(1.5)
                    
                except Exception as e:
                    log(f"    Failed: {str(e)}")
                    results.append({"url": url, "error": str(e), "source": "glints_scrape"})
        
        finally:
            driver.quit()
        
        successful = sum(1 for r in results if "error" not in r)
        log(f"\n{'='*50}")
        log(f" SCRAPING COMPLETE: {successful}/{len(urls)} successful")
        log(f"{'='*50}")
        
        return results


def scrape_glints_jobs(start_page: int = 1, end_page: int = 2,
                       keyword: str = "it",
                       cookie_file: str = None, headless: bool = True,
                       progress_callback: Callable[[str], None] = None,
                       max_jobs: int = None) -> List[Dict[str, Any]]:

    scraper = GlintsScraper(cookie_file=cookie_file, headless=headless, keyword=keyword)
    urls = scraper.scrape_job_urls(start_page, end_page, progress_callback, max_jobs=max_jobs)
    if max_jobs is not None:
        urls = urls[:max_jobs]
    jobs = scraper.scrape_all_jobs(urls, progress_callback)
    return [j for j in jobs if "error" not in j]
