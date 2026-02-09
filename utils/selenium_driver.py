"""
Shared Selenium WebDriver factory for all scrapers.
Creates Chrome driver with anti-detection options.
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def create_chrome_driver(headless: bool = True, window_size: str = "1920,1080") -> webdriver.Chrome:
    """
    Create and configure Chrome WebDriver with anti-detection options.
    
    Args:
        headless: Run browser in headless mode
        window_size: Browser window size (width,height)
    
    Returns:
        Configured Chrome WebDriver instance
    """
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless=new")
    
    # Anti-detection options
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"--window-size={window_size}")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--log-level=3")
    
    return webdriver.Chrome(options=chrome_options)
