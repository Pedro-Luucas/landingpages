"""Public-page Instagram/Facebook scrapers (M2). No login, no stealth, no private APIs.

Live Instagram and Facebook often return HTTP 401/403 or a login/challenge
page. That path is ``PLATFORM_BLOCKED``. Tests prove it with fixtures; they
never use the network.
"""

from studio_pipeline.scrapers.facebook import scrape_facebook
from studio_pipeline.scrapers.http import DEFAULT_TIMEOUT_SECONDS, HttpClient, HttpResponse
from studio_pipeline.scrapers.instagram import scrape_instagram
from studio_pipeline.scrapers.merge import merge_social
from studio_pipeline.scrapers.models import SocialScrape
from studio_pipeline.scrapers.public import DEFAULT_MAX_POSTS

__all__ = [
    "DEFAULT_MAX_POSTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "HttpClient",
    "HttpResponse",
    "SocialScrape",
    "merge_social",
    "scrape_facebook",
    "scrape_instagram",
]
