
import re
from typing import List


_URL_PATTERN = re.compile(
    r'https?://\S+|www\.\S+',
    re.IGNORECASE,
)

def remove_urls(text: str) -> str:
    """Remove URLs (http://, https://, www.) from text."""
    if not text:
        return text
    return _URL_PATTERN.sub('', text)


_HTML_BR_PATTERN = re.compile(r'<br\s*/?>', re.IGNORECASE)
_HTML_P_PATTERN = re.compile(r'</p\s*>', re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(r'<.*?>', re.DOTALL)

def remove_html_tags(text: str) -> str:
    """Remove HTML tags, converting <br> and </p> to spaces."""
    if not text:
        return text
    text = _HTML_BR_PATTERN.sub(' ', text)
    text = _HTML_P_PATTERN.sub(' ', text)
    text = _HTML_TAG_PATTERN.sub('', text)
    return text


def case_fold(text: str) -> str:
    """Convert text to lowercase."""
    if not text:
        return text
    return text.lower()



_MULTI_SPACE = re.compile(r'\s+')

def normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespace into single space and strip."""
    if not text:
        return text
    return _MULTI_SPACE.sub(' ', text).strip()


def preprocess_text(text: str) -> str:
    """
    Apply all preprocessing steps in order:
    1. Remove URLs
    2. Remove HTML tags
    3. Case folding (lowercase)
    4. Normalize whitespace
    """
    if not text:
        return text
    text = remove_urls(text)
    text = remove_html_tags(text)
    text = case_fold(text)
    text = normalize_whitespace(text)
    return text
