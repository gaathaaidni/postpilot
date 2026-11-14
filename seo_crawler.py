"""
PostPilot Technical SEO Crawler (seo_crawler.py)
Polite, asynchronous, SSRF-safe crawler for property health audits.
Evaluates technical SEO, generates health scores (0-100), and stages actionable recommendations.
"""
import collections
import ipaddress
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)

USER_AGENT = "PostPilot-Intelligence-Bot/1.0 (+https://postpilot.gaatha.tech; internal SEO auditor)"
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_DEPTH = 3
DEFAULT_REQUEST_DELAY = 1.0  # 1 second polite rate limit between requests
REQUEST_TIMEOUT = 10.0


class SEOHTMLParser(HTMLParser):
    """Extracts SEO elements from HTML content."""
    def __init__(self):
        super().__init__()
        self.title = None
        self._in_title = False
        self.meta_tags = []
        self.canonical = None
        self.h1_tags = []
        self._in_h1 = False
        self._current_h1 = []
        self.links = []
        self.images = []
        self.json_ld = []
        self._in_script_ld = False
        self._current_script = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v for k, v in attrs if k}
        tag_lower = tag.lower()

        if tag_lower == 'title':
            self._in_title = True
        elif tag_lower == 'meta':
            self.meta_tags.append(attrs_dict)
        elif tag_lower == 'link':
            rel = (attrs_dict.get('rel') or '').lower()
            if rel == 'canonical':
                self.canonical = attrs_dict.get('href')
        elif tag_lower == 'h1':
            self._in_h1 = True
            self._current_h1 = []
        elif tag_lower == 'a':
            href = attrs_dict.get('href')
            if href:
                self.links.append(href)
        elif tag_lower == 'img':
            self.images.append({
                'src': attrs_dict.get('src'),
                'alt': attrs_dict.get('alt')
            })
        elif tag_lower == 'script':
            script_type = (attrs_dict.get('type') or '').lower()
            if script_type == 'application/ld+json':
                self._in_script_ld = True
                self._current_script = []

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == 'title':
            self._in_title = False
        elif tag_lower == 'h1':
            self._in_h1 = False
            text = ''.join(self._current_h1).strip()
            if text:
                self.h1_tags.append(text)
        elif tag_lower == 'script':
            if self._in_script_ld:
                self._in_script_ld = False
                self.json_ld.append(''.join(self._current_script))

    def handle_data(self, data):
        if self._in_title:
            if self.title is None:
                self.title = data
            else:
                self.title += data
        elif self._in_h1:
            self._current_h1.append(data)
        elif self._in_script_ld:
            self._current_script.append(data)


def is_ssrf_safe_url(url: str) -> bool:
    """Verifies that a URL does not point to internal, private, loopback, or cloud-metadata IPs."""
    if os.environ.get('POSTPILOT_ALLOW_LOCAL_CRAWL') == '1':
        return True
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        hostname_lower = hostname.lower()
        if hostname_lower in ('localhost', '127.0.0.1', '::1', '0.0.0.0', '169.254.169.254'):
            return False
        
        # Resolve to IP
        ip_addr = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip_addr)
        if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_reserved or ip_obj.is_link_local:
            return False
        return True
    except Exception as e:
        logger.warning(f"SSRF check rejected URL {url}: {e}")
        return False


def normalize_url(url: str) -> str:
    """Normalizes URL by stripping fragments and trailing query noise."""
    parsed = urllib.parse.urlsplit(url)
    clean = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or '/', parsed.query, ''))
    return clean


def parse_robots_txt(base_url: str) -> Optional[urllib.robotparser.RobotFileParser]:
    """Fetches and parses robots.txt for the given base URL."""
    try:
        parsed = urllib.parse.urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        req = urllib.request.Request(robots_url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            rp.parse(content.splitlines())
            return rp
    except Exception:
        return None


def fetch_sitemap_urls(base_url: str) -> List[str]:
    """Attempts to discover URLs from /sitemap.xml."""
    urls = []
    try:
        parsed = urllib.parse.urlparse(base_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        req = urllib.request.Request(sitemap_url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            found = re.findall(r'<loc>\s*(https?://[^<\s]+)\s*</loc>', content, re.IGNORECASE)
            for u in found:
                urls.append(normalize_url(u))
    except Exception:
        pass
    return urls


def analyze_page_seo(url: str, html_content: str, status_code: int, response_time_ms: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """
    Parses and evaluates SEO factors for a single page.
    Returns:
      (page_record, page_issues, discovered_links)
    """
    parser = SEOHTMLParser()
    try:
        parser.feed(html_content)
    except Exception as e:
        logger.warning(f"HTML parse error on {url}: {e}")

    title = (parser.title or '').strip()
    canonical = (parser.canonical or '').strip()
    h1 = parser.h1_tags[0] if parser.h1_tags else None
    
    # Meta description & OpenGraph extraction
    meta_desc = None
    og_title = None
    og_desc = None
    og_image = None

    for m in parser.meta_tags:
        name = (m.get('name') or '').lower()
        prop = (m.get('property') or '').lower()
        content = m.get('content') or ''

        if name == 'description':
            meta_desc = content.strip()
        elif prop == 'og:title':
            og_title = content.strip()
        elif prop == 'og:description':
            og_desc = content.strip()
        elif prop == 'og:image':
            og_image = content.strip()

    has_og = bool(og_title or og_desc or og_image)

    # Schema JSON-LD parsing
    schema_types = []
    for raw_json in parser.json_ld:
        try:
            s_obj = json.loads(raw_json)
            if isinstance(s_obj, dict):
                st = s_obj.get('@type')
                if st:
                    schema_types.append(str(st))
            elif isinstance(s_obj, list):
                for item in s_obj:
                    if isinstance(item, dict) and item.get('@type'):
                        schema_types.append(str(item.get('@type')))
        except Exception:
            pass

    # Issues evaluation
    issues = []

    # 1. HTTP Status
    if status_code >= 400:
        issues.append({
            'severity': 'critical',
            'category': 'http_status',
            'message': f"Page returned HTTP error code {status_code}."
        })

    # 2. Canonical Tag Inspection
    placeholder_canonical_domains = ('yourwebsite.com', 'example.com', 'your-domain.com', 'localhost')
    if not canonical:
        issues.append({
            'severity': 'warning',
            'category': 'canonical',
            'message': "Missing rel='canonical' tag."
        })
    else:
        can_parsed = urllib.parse.urlparse(canonical)
        can_domain = (can_parsed.netloc or '').lower()
        if any(ph in can_domain for ph in placeholder_canonical_domains):
            issues.append({
                'severity': 'critical',
                'category': 'canonical_placeholder',
                'message': f"Placeholder canonical URL detected: '{canonical}'. Must be updated to production domain.",
                'current_value': canonical
            })

    # 3. Title Inspection
    if not title:
        issues.append({
            'severity': 'critical',
            'category': 'title_missing',
            'message': "Page is missing a <title> tag."
        })
    elif len(title) < 30:
        issues.append({
            'severity': 'warning',
            'category': 'title_too_short',
            'message': f"Page title is too short ({len(title)} chars). Recommended 30-60 characters.",
            'current_value': title
        })
    elif len(title) > 60:
        issues.append({
            'severity': 'warning',
            'category': 'title_too_long',
            'message': f"Page title is too long ({len(title)} chars). Recommended 30-60 characters.",
            'current_value': title
        })

    # 4. Meta Description Inspection
    if not meta_desc:
        issues.append({
            'severity': 'warning',
            'category': 'meta_description_missing',
            'message': "Page is missing a meta description."
        })
    elif len(meta_desc) < 70:
        issues.append({
            'severity': 'warning',
            'category': 'meta_desc_too_short',
            'message': f"Meta description is too short ({len(meta_desc)} chars). Recommended 70-160 characters.",
            'current_value': meta_desc
        })
    elif len(meta_desc) > 160:
        issues.append({
            'severity': 'warning',
            'category': 'meta_desc_too_long',
            'message': f"Meta description is too long ({len(meta_desc)} chars). Recommended 70-160 characters.",
            'current_value': meta_desc
        })

    # 5. Heading Structure
    if not parser.h1_tags:
        issues.append({
            'severity': 'warning',
            'category': 'h1_missing',
            'message': "Page has no <h1> heading tag."
        })
    elif len(parser.h1_tags) > 1:
        issues.append({
            'severity': 'warning',
            'category': 'h1_multiple',
            'message': f"Multiple <h1> tags found ({len(parser.h1_tags)}). Recommended 1 primary H1 per page."
        })

    # 6. OpenGraph
    if not has_og:
        issues.append({
            'severity': 'info',
            'category': 'og_missing',
            'message': "Page is missing OpenGraph social share tags (og:title, og:description, og:image)."
        })

    # 7. Images without alt
    missing_alt = sum(1 for img in parser.images if not (img.get('alt') or '').strip())
    if missing_alt > 0:
        issues.append({
            'severity': 'warning',
            'category': 'image_alt_missing',
            'message': f"{missing_alt} image(s) missing alt text attributes."
        })

    # 8. Performance check
    if response_time_ms > 2000:
        issues.append({
            'severity': 'warning',
            'category': 'slow_response',
            'message': f"Slow server response time: {response_time_ms}ms."
        })

    # Extract outbound links
    discovered_links = []
    for link in parser.links:
        link_str = str(link).strip()
        if not link_str or link_str.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            continue
        joined = urllib.parse.urljoin(url, link_str)
        cleaned = normalize_url(joined)
        discovered_links.append(cleaned)

    page_record = {
        'url': url,
        'status_code': status_code,
        'response_time_ms': response_time_ms,
        'title': title,
        'meta_description': meta_desc,
        'canonical_url': canonical,
        'h1_tag': h1,
        'has_og_tags': has_og,
        'schemas': schema_types,
        'broken_links_count': 0,
        'issues': issues
    }

    return page_record, issues, discovered_links


def run_seo_crawl(
    property_id: int,
    organization_id: int,
    entry_urls: List[str],
    allowed_domains: List[str],
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    delay_sec: float = DEFAULT_REQUEST_DELAY
) -> Dict[str, Any]:
    """
    Executes a polite crawl across the specified entry URLs and allowed domains.
    Returns audit summary, page findings, and staged recommendations.
    """
    visited_urls: Set[str] = set()
    queue = collections.deque()  # elements: (url, depth)
    pages_results: List[Dict[str, Any]] = []
    staged_recommendations: List[Dict[str, Any]] = []

    # Initialize queue with entry URLs
    for eu in entry_urls:
        norm = normalize_url(eu)
        if norm not in visited_urls:
            queue.append((norm, 0))
            visited_urls.add(norm)

    # Attempt sitemap lookup on primary entry
    if entry_urls:
        sitemap_urls = fetch_sitemap_urls(entry_urls[0])
        for su in sitemap_urls:
            if su not in visited_urls and len(queue) < max_pages:
                queue.append((su, 1))
                visited_urls.add(su)

    # Robots parser cache per domain
    robots_parsers: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    start_time = time.time()
    last_request_time = 0.0

    while queue and len(pages_results) < max_pages:
        url, depth = queue.popleft()

        # SSRF check
        if not is_ssrf_safe_url(url):
            logger.warning(f"Skipping SSRF-unsafe URL: {url}")
            continue

        # Check domain scope
        parsed_url = urllib.parse.urlparse(url)
        domain = (parsed_url.netloc or '').lower()
        if not any(domain == ad or domain.endswith('.' + ad) for ad in allowed_domains):
            continue

        # Respect robots.txt
        if domain not in robots_parsers:
            robots_parsers[domain] = parse_robots_txt(f"{parsed_url.scheme}://{domain}")
        rp = robots_parsers[domain]
        if rp and not rp.can_fetch(USER_AGENT, url):
            logger.info(f"URL disallowed by robots.txt: {url}")
            continue

        # Rate limiting: polite delay
        elapsed_since_last = time.time() - last_request_time
        if elapsed_since_last < delay_sec:
            time.sleep(delay_sec - elapsed_since_last)

        # Execute HTTP request
        req_start = time.time()
        status_code = 0
        html_body = ""
        response_time_ms = 0

        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            last_request_time = time.time()
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status_code = resp.getcode()
                response_time_ms = int((time.time() - req_start) * 1000)
                content_type = resp.headers.get('Content-Type', '')
                if 'text/html' in content_type:
                    html_body = resp.read(500000).decode('utf-8', errors='ignore')  # max 500KB
        except urllib.error.HTTPError as he:
            status_code = he.code
            response_time_ms = int((time.time() - req_start) * 1000)
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            status_code = 504
            response_time_ms = int((time.time() - req_start) * 1000)

        # Evaluate page
        page_rec, issues, discovered_links = analyze_page_seo(
            url=url,
            html_content=html_body,
            status_code=status_code,
            response_time_ms=response_time_ms
        )
        pages_results.append(page_rec)

        # Generate staged recommendations from issues
        for iss in issues:
            cat = iss.get('category')
            sev = iss.get('severity')
            rec = None

            if cat == 'canonical_placeholder':
                rec = {
                    'target_url': url,
                    'category': 'canonical',
                    'issue_description': f"Placeholder canonical tag detected: '{iss.get('current_value')}'. This prevents search engines from indexing the page.",
                    'proposed_action': "Replace placeholder domain with production canonical URL.",
                    'current_content': iss.get('current_value'),
                    'recommended_content': f"https://{domain}{parsed_url.path}"
                }
            elif cat == 'title_missing':
                rec = {
                    'target_url': url,
                    'category': 'title',
                    'issue_description': "Page is missing a <title> tag.",
                    'proposed_action': "Add a descriptive title between 30 and 60 characters.",
                    'current_content': "",
                    'recommended_content': f"{domain.capitalize()} - Official Product"
                }
            elif cat == 'title_too_short':
                rec = {
                    'target_url': url,
                    'category': 'title',
                    'issue_description': f"Title is only {len(iss.get('current_value') or '')} chars.",
                    'proposed_action': "Expand title with brand and keyword context (30-60 characters).",
                    'current_content': iss.get('current_value'),
                    'recommended_content': f"{iss.get('current_value')} | Gaatha Ecosystem"
                }
            elif cat == 'meta_description_missing':
                rec = {
                    'target_url': url,
                    'category': 'meta_description',
                    'issue_description': "Page lacks a meta description.",
                    'proposed_action': "Add an informative 70-160 character description summarizing page value.",
                    'current_content': "",
                    'recommended_content': f"Discover {domain} solutions powered by Gaatha and Aidni Global."
                }
            elif cat == 'h1_missing':
                rec = {
                    'target_url': url,
                    'category': 'heading',
                    'issue_description': "Missing <h1> tag.",
                    'proposed_action': "Add a single primary <h1> heading tag at top of content.",
                    'current_content': "",
                    'recommended_content': f"<h1>Welcome to {domain}</h1>"
                }
            elif cat == 'og_missing':
                rec = {
                    'target_url': url,
                    'category': 'social',
                    'issue_description': "Missing OpenGraph tags.",
                    'proposed_action': "Add og:title, og:description, and og:image tags for rich link previews.",
                    'current_content': "",
                    'recommended_content': f"<meta property='og:title' content='{page_rec.get('title') or domain}' />"
                }

            if rec:
                staged_recommendations.append(rec)

        # Enqueue discovered links if within depth limit
        if depth < max_depth:
            for dl in discovered_links:
                if dl not in visited_urls and len(visited_urls) < (max_pages * 2):
                    dl_parsed = urllib.parse.urlparse(dl)
                    dl_domain = (dl_parsed.netloc or '').lower()
                    if any(dl_domain == ad or dl_domain.endswith('.' + ad) for ad in allowed_domains):
                        visited_urls.add(dl)
                        queue.append((dl, depth + 1))

    # Calculate overall health score
    total_crawled = len(pages_results)
    pages_with_issues = sum(1 for p in pages_results if p['issues'])
    pages_passed = total_crawled - pages_with_issues

    critical_count = sum(sum(1 for i in p['issues'] if i['severity'] == 'critical') for p in pages_results)
    warning_count = sum(sum(1 for i in p['issues'] if i['severity'] == 'warning') for p in pages_results)

    # Formula: 100 - (critical * 15) - (warning * 3)
    if total_crawled > 0:
        penalty = (critical_count * 15) + (warning_count * 3)
        health_score = max(0.0, min(100.0, 100.0 - penalty))
    else:
        health_score = 100.0

    audit_summary = {
        'status': 'completed',
        'pages_crawled': total_crawled,
        'pages_passed': pages_passed,
        'pages_with_issues': pages_with_issues,
        'health_score': round(health_score, 1),
        'critical_count': critical_count,
        'warning_count': warning_count,
        'summary_data': {
            'duration_sec': round(time.time() - start_time, 2),
            'entry_urls': entry_urls,
            'allowed_domains': allowed_domains
        }
    }

    return {
        'audit_summary': audit_summary,
        'pages': pages_results,
        'recommendations': staged_recommendations
    }
