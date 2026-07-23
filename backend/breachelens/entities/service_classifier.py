"""Service classification: map root domains to known service names."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Default (service_name, domain_pattern) mappings
DEFAULT_MAPPINGS: List[Tuple[str, str]] = [
    ("Google", "google.com"),
    ("Google", "gmail.com"),
    ("Google", "youtube.com"),
    ("Google", "g.co"),
    ("Microsoft", "microsoft.com"),
    ("Microsoft", "microsoftonline.com"),
    ("Microsoft", "live.com"),
    ("Microsoft", "outlook.com"),
    ("Microsoft", "office.com"),
    ("Microsoft", "hotmail.com"),
    ("Microsoft", "msn.com"),
    ("Microsoft", "bing.com"),
    ("Apple", "apple.com"),
    ("Apple", "icloud.com"),
    ("Apple", "me.com"),
    ("Meta", "facebook.com"),
    ("Meta", "instagram.com"),
    ("Meta", "whatsapp.com"),
    ("Meta", "meta.com"),
    ("Meta", "messenger.com"),
    ("Twitter", "twitter.com"),
    ("Twitter", "x.com"),
    ("Discord", "discord.com"),
    ("Discord", "discordapp.com"),
    ("Reddit", "reddit.com"),
    ("Steam", "steampowered.com"),
    ("Steam", "steamcommunity.com"),
    ("Twitch", "twitch.tv"),
    ("Amazon", "amazon.com"),
    ("Amazon", "amazonaws.com"),
    ("Netflix", "netflix.com"),
    ("Spotify", "spotify.com"),
    ("Dropbox", "dropbox.com"),
    ("PayPal", "paypal.com"),
    ("Stripe", "stripe.com"),
    ("GitHub", "github.com"),
    ("GitHub", "githubusercontent.com"),
    ("GitLab", "gitlab.com"),
    ("Bitbucket", "bitbucket.org"),
    ("Atlassian", "atlassian.com"),
    ("Cloudflare", "cloudflare.com"),
    ("Vercel", "vercel.com"),
    ("Netlify", "netlify.com"),
    ("Coinbase", "coinbase.com"),
    ("Binance", "binance.com"),
    ("Kraken", "kraken.com"),
    ("LinkedIn", "linkedin.com"),
    ("TikTok", "tiktok.com"),
    ("Telegram", "telegram.org"),
    ("ProtonMail", "protonmail.com"),
    ("ProtonMail", "proton.me"),
    ("Yahoo", "yahoo.com"),
    ("Yandex", "yandex.com"),
    ("VK", "vk.com"),
    ("Tencent", "tencent.com"),
    ("Alibaba", "alibaba.com"),
]

# In-memory cache: root_domain -> service_name
_CACHE: Dict[str, str] = {}


def populate_cache(rules: List[Tuple[str, str]]) -> None:
    """Populate the in-memory cache from (domain_pattern, service_name) pairs."""
    _CACHE.clear()
    for domain, service in rules:
        _CACHE[domain.lower()] = service


def classify_service(root_domain: str) -> Optional[str]:
    """Classify a root domain into a known service name, or None if unknown."""
    return _CACHE.get(root_domain.lower())


def default_service_mappings() -> List[Tuple[str, str]]:
    """Return the default (service_name, domain_pattern) pairs."""
    return DEFAULT_MAPPINGS
