import truststore
truststore.inject_into_ssl()
import httpx
import os
import re
import asyncio
import threading
import hashlib
from bs4 import BeautifulSoup
from agent_framework import tool
from tools.core import with_quota
from tools.fs import _get_safe_path, _get_workspace_type, _get_workspace_dir, _IN_MEMORY_FS, session_dir_ctx

_ddgs_lock = threading.Lock()
_dedup_lock = threading.Lock()
_fetched_urls = {}
_fetched_hashes = {}


def _dedup_reset_to_current(run_key: str):
    """Reset dedup registry to only hold the current run's data.

    Removes all entries not matching run_key from both URL and hash registries.
    This guarantees the dicts only ever hold one run's data — no memory growth
    across runs.
    """
    with _dedup_lock:
        # Remove all keys that are not the current run_key
        for key in list(_fetched_urls.keys()):
            if key != run_key:
                del _fetched_urls[key]
        for key in list(_fetched_hashes.keys()):
            if key != run_key:
                del _fetched_hashes[key]

        # Ensure current run's entries exist (empty dict if new)
        if run_key not in _fetched_urls:
            _fetched_urls[run_key] = {}
        if run_key not in _fetched_hashes:
            _fetched_hashes[run_key] = {}


_ddgs_client = None
_consecutive_search_failures = 0
_backoff_lock = asyncio.Lock()


_MIN_CONTENT_CHARS = 200

# Hard wall-clock ceiling for the entire fetch operation (seconds)
# This caps total fetch time regardless of httpx's internal timeout behavior,
# preventing byte-trickle servers from causing unbounded wait times.
_FETCH_HARD_CEILING = 60


def _strip_image_markdown(text: str) -> tuple[str, int]:
    """Strip standalone image-markdown lines from text.

    Returns (cleaned_text, num_lines_removed).
    Only removes whole-line standalone images; inline images in text are untouched.
    Collapses 3+ consecutive blank lines to a single blank line.
    On any error, returns (original_text, 0).
    """
    try:
        lines = text.splitlines(keepends=True)
        original_count = len(lines)

        # Patterns for standalone image markdown
        # Format: ![[alt](url)] or ![alt](url) - one per line, possibly with leading/trailing whitespace
        image_pattern = re.compile(r'^\s*!\[[^\]]*\]\([^)]*\)\s*$')
        linked_image_pattern = re.compile(r'^\s*\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)\s*$')

        cleaned_lines = []
        removed_count = 0

        for line in lines:
            # Check if this is a standalone image line
            if image_pattern.match(line) or linked_image_pattern.match(line):
                removed_count += 1
            else:
                cleaned_lines.append(line)

        # Collapse 3+ consecutive blank lines to a single blank line
        result_lines = []
        blank_run_count = 0

        for line in cleaned_lines:
            if line.strip() == '':
                blank_run_count += 1
                if blank_run_count <= 1:
                    result_lines.append(line)
                # Skip additional blank lines in the run
            else:
                blank_run_count = 0
                result_lines.append(line)

        return (''.join(result_lines), removed_count)

    except Exception:
        # Fully defensive: on any error, return original text with 0 removed
        return (text, 0)


def get_ddgs_client():
    """Thread-safe lazy initialization of the DDGS client."""
    global _ddgs_client
    with _ddgs_lock:
        if _ddgs_client is None:
            from ddgs import DDGS
            _ddgs_client = DDGS(timeout=20)
            # Pre-warm the internal engine cache to prevent PyO3 deadlocks 
            # when multiple threads initialize primp.Client concurrently later.
            _ddgs_client._get_engines("text", "auto")
            _ddgs_client._get_engines("news", "auto")
    return _ddgs_client

@tool
@with_quota
async def fetch_url_to_workspace(url: str, filename: str, convert_to_md: bool = True) -> str:
    """Fetch external web content and save it directly to the workspace. If convert_to_md is True, parses to Markdown."""
    import config as app_config

    # Per-run dedup reset — prunes stale runs, keeps memory bounded
    run_key = session_dir_ctx.get()
    _dedup_reset_to_current(run_key)

    _blocked = app_config.cfg.get("settings", {}).get("blocked_fetch_domains", []) or []
    _host = re.sub(r"^https?://(www\.)?", "", url.lower()).split("/")[0]
    for _dom in _blocked:
        if _host == _dom.lower() or _host.endswith("." + _dom.lower()) or url.lower().find(_dom.lower()) != -1 and "/" in _dom:
            return (f"BLOCKED DOMAIN: {_dom} is on the known-hostile list (login walls / bot protection / "
                    f"no scrapable content). Nothing was fetched. Do NOT retry this website — find the same "
                    f"information from a different source.")

    # URL dedup check — early return if already fetched this run
    with _dedup_lock:
        if url in _fetched_urls.get(run_key, {}):
            existing = _fetched_urls[run_key][url]
            return (f"ALREADY FETCHED this run. SAVED_FILENAME={existing}\n"
                    f"This URL was already retrieved and saved as '{existing}'. Delegate that file to the Analyzer "
                    f"instead of re-fetching.")

    def _fetch():
        import time
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        _backoffs = [30, 60, 240]
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        for _wait in _backoffs:
            if resp.status_code != 429:
                break
            time.sleep(_wait)
            resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)

        if not convert_to_md:
            return resp.content  # Raw bytes

        content_type = resp.headers.get("content-type", "").lower()
        # Check actual bytes — a URL might say .pdf but serve HTML (JS-gated doc viewers)
        is_actual_pdf = resp.content[:4] == b"%PDF"
        is_pdf = is_actual_pdf or ("application/pdf" in content_type and is_actual_pdf)

        if is_pdf:
            # Save to temp file, then parse locally
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name
            try:
                # Try liteparse first (better spatial accuracy for PDFs)
                import shutil
                if shutil.which("liteparse"):
                    import subprocess
                    result = subprocess.run(
                        ["liteparse", tmp_path],
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout

                # Fallback to markitdown on local file
                try:
                    from utils.parsers import convert_to_markdown
                    md_content = convert_to_markdown(tmp_path)
                    if md_content:
                        return md_content
                except ImportError:
                    pass

                return f"[ERROR: PDF at {url} could not be parsed. Size: {len(resp.content)} bytes. Try a different source.]"
            finally:
                os.unlink(tmp_path)
        else:
            # HTML path: try markitdown on local temp file first, then BeautifulSoup fallback
            try:
                from utils.parsers import convert_to_markdown
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="wb") as tmp:
                    tmp.write(resp.content)
                    tmp_path = tmp.name
                try:
                    md_content = convert_to_markdown(tmp_path)
                    if md_content:
                        return md_content
                finally:
                    os.unlink(tmp_path)
            except ImportError:
                pass

            # BeautifulSoup fallback for HTML
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup(["script", "style", "nav", "footer"]): script.extract()
            return '\n'.join(line for line in (l.strip() for l in soup.get_text(separator='\n').splitlines()) if line)

        
    try:
        try:
            data = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=_FETCH_HARD_CEILING)
        except asyncio.TimeoutError:
            return f"FETCH TIMEOUT: {url} exceeded the {_FETCH_HARD_CEILING}s hard limit (likely a slow or trickling server). Nothing was saved. Try a different source."

        # Detect bot-challenge / block / error pages before saving junk to the workspace
        if isinstance(data, str) and len(data) < 20000:
            _block_markers = (
                "Just a moment", "Enable JavaScript and cookies", "Ray ID:",
                "Checking your browser", "Verifying you are human",
                "Complete the security check", "DDoS protection by",
                "Please enable Cookies and reload",
                "Access denied", "You do not have access to",
                "Error 403 Forbidden", "Error 1020",
                "Sorry, something went wrong.",
                "local_rate_limited", "local\\_rate\\_limited",
                "Click the button below to continue shopping",
                "We had to rate limit your IP", "Too Many Requests",
            )
            if any(m in data for m in _block_markers):
                return (f"BLOCKED: {url} returned a bot-challenge, access-denied, or error page instead of "
                        f"content. Nothing was saved. Do NOT retry this URL or this website — find the same "
                        f"information from a different source.")

        # Explicitly tag markdown files
        if convert_to_md and not filename.endswith('.md'):
            filename += '.md'
            
        path = _get_safe_path(filename)
        if not path: return f"Error: Invalid filename '{filename}'."
        
        if isinstance(data, str):
            # Strip standalone image-markdown lines and track removal count
            data, removed_count = _strip_image_markdown(data)

            # Reject too-short content BEFORE adding the provenance note, so the note's
            # characters don't inflate the length past the threshold (e.g. image-only pages).
            if len(data) < _MIN_CONTENT_CHARS:
                return (f"TOO SHORT: {url} returned only {len(data)} characters of content after cleaning — "
                        f"likely a stub, error, or image-only page with no usable text. Nothing was saved. "
                        f"Find the information from a different source.")

            # Content dedup check — return early if identical content already saved this run
            md5 = hashlib.md5(data.encode('utf-8', 'replace')).hexdigest()
            with _dedup_lock:
                if md5 in _fetched_hashes.get(run_key, {}):
                    existing = _fetched_hashes[run_key][md5]
                    return (f"DUPLICATE CONTENT. SAVED_FILENAME={existing}\n"
                            f"This page's content is byte-identical to '{existing}' already saved this run. "
                            f"Use that file; nothing new was saved.")

            # Prepend provenance marker only if images were actually stripped
            if removed_count > 0:
                provenance_note = (
                    f"_Note: {removed_count} inline image reference(s) were stripped from this page during fetch "
                    f"to reduce noise. The original page contained images not reproduced here._\n"
                )
                data = provenance_note + "\n" + data

            chunk = data[:5000000] # Allow larger sizes for markdown text (up to 5MB)
            mode = "w"
            encoding = "utf-8"
        else:
            chunk = data[:5000000] # Cap raw binary at 5MB
            mode = "wb"
            encoding = None
        
        # Record successful fetch in dedup registry
        with _dedup_lock:
            _fetched_urls[run_key][url] = filename
            # md5 only exists for string/markdown content; binary fetches skip hash dedup
            if isinstance(data, str):
                _fetched_hashes[run_key][md5] = filename

        if _get_workspace_type() == "disk":
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            if encoding:
                with open(path, mode, encoding=encoding) as f:
                    f.write(chunk)
            else:
                with open(path, mode) as f:
                    f.write(chunk)
            return (f"SUCCESS. SAVED_FILENAME={filename}\n"
                    f"When you delegate this file to the Analyzer you MUST pass exactly this filename: {filename}\n"
                    f"Do NOT invent, shorten, or rename it. Copy it character-for-character.")
        else:
            _IN_MEMORY_FS[path] = chunk
            return (f"SUCCESS. SAVED_FILENAME={filename}\n"
                    f"When you delegate this file to the Analyzer you MUST pass exactly this filename: {filename}\n"
                    f"Do NOT invent, shorten, or rename it. Copy it character-for-character.")
    except Exception as e:
        import traceback
        return f"Failed: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool
async def web_search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
) -> str:
    """Search the web for information on a given query.

    Returns search results with titles, URLs, and snippets.

    Args:
        query: Search query to execute
        max_results: Maximum number of results to return (default: 5)
        topic: Topic filter - 'general', 'news', or 'finance' (default: 'general')

    Returns:
        Formatted search results with titles, URLs, and snippets
    """
    from tools.core import check_quota
    quota_error = check_quota("web_search")
    if quota_error:
        return quota_error
        
    def _do_search():
        from ddgs import DDGS
        import config as app_config
        
        def _sanitize_snippet(text: str) -> str:
            """Strip CSS, SVG, and HTML artifacts from search snippets."""
            text = re.sub(r'<svg[\s\S]*?</svg>', '', text, flags=re.IGNORECASE)
            text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r"(?:[\w-]+=(?:'[^']*'|\"[^\"]*\")[\s]*){3,}", '', text)
            text = re.sub(r'%3[CEce][^%\s]{10,}', '', text)
            return re.sub(r'\s+', ' ', text).strip()

        provider = app_config.cfg.get("settings", {}).get("search_provider", "duckduckgo")
        result_texts = []

        if provider == "duckduckgo" or provider not in ("duckduckgo", "tavily"):
            # Default/fallback: DuckDuckGo (free, no API key required)
            client = get_ddgs_client()
            
            if topic == "news":
                search_results = client.news(query, max_results=max_results)
                for result in search_results:
                    url = result.get("url", "")
                    title = result.get("title", "")
                    snippet = _sanitize_snippet(result.get("body", "No snippet available"))
                    result_texts.append(f"## {title}\n**URL:** {url}\n**Snippet:** {snippet}\n")
            else:
                search_results = client.text(query, max_results=max_results)
                for result in search_results:
                    url = result.get("href", "")
                    title = result.get("title", "")
                    snippet = _sanitize_snippet(result.get("body", "No snippet available"))
                    result_texts.append(f"## {title}\n**URL:** {url}\n**Snippet:** {snippet}\n")
        elif provider == "tavily":
            pass # Removed Tavily placeholder to avoid undefined get_tavily_client() error in scaffold

        return f"🔍 Found {len(result_texts)} result(s) for '{query}':\n\n{chr(10).join(result_texts)}"
        
    global _consecutive_search_failures
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            result = await asyncio.wait_for(asyncio.to_thread(_do_search), timeout=45)
            _consecutive_search_failures = 0
            return result
        except asyncio.TimeoutError:
            return "Search failed: timed out after 45 seconds. Try again or rephrase the query."
        except Exception as e:
            _consecutive_search_failures += 1
            if _consecutive_search_failures >= 6:
                return ("SEARCH SERVICE UNAVAILABLE: the web search provider has returned errors "
                        "repeatedly despite waiting between attempts, and is likely rate-limiting "
                        "this machine for an extended period. Do NOT retry or reword this search. "
                        "Report to your caller that web search is currently unavailable and return "
                        "any findings you already have.")
            if attempt < max_attempts - 1:
                wait = 30 * (2 ** attempt)   # 30s, then 60s
                async with _backoff_lock:
                    await asyncio.sleep(wait)
            else:
                return f"Search failed: {str(e)}"