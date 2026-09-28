import logging
import socket
import urllib.parse
from typing import Sequence, Union

import validators

from neveai.config import ENABLE_RAG_LOCAL_WEB_FETCH, WEB_FETCH_FILTER_LIST
from neveai.constants import ERROR_MESSAGES
from neveai.utils.misc import is_string_allowed


log = logging.getLogger(__name__)


def resolve_hostname(hostname: str):
    addr_info = socket.getaddrinfo(hostname, None)
    ipv4_addresses = [info[4][0] for info in addr_info if info[0] == socket.AF_INET]
    ipv6_addresses = [info[4][0] for info in addr_info if info[0] == socket.AF_INET6]
    return ipv4_addresses, ipv6_addresses


def validate_url(url: Union[str, Sequence[str]]):
    if isinstance(url, str):
        if isinstance(validators.url(url), validators.ValidationError):
            raise ValueError(ERROR_MESSAGES.INVALID_URL)

        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme not in ["http", "https"]:
            log.warning("Blocked non-HTTP(S) protocol: %s in URL: %s", parsed_url.scheme, url)
            raise ValueError(ERROR_MESSAGES.INVALID_URL)

        if WEB_FETCH_FILTER_LIST and not is_string_allowed(url, WEB_FETCH_FILTER_LIST):
            log.warning("URL blocked by filter list: %s", url)
            raise ValueError(ERROR_MESSAGES.INVALID_URL)

        if not ENABLE_RAG_LOCAL_WEB_FETCH:
            ipv4_addresses, ipv6_addresses = resolve_hostname(parsed_url.hostname)
            for ip in ipv4_addresses:
                if validators.ipv4(ip, private=True):
                    raise ValueError(ERROR_MESSAGES.INVALID_URL)
            for ip in ipv6_addresses:
                if validators.ipv6(ip, private=True):
                    raise ValueError(ERROR_MESSAGES.INVALID_URL)
        return True

    if isinstance(url, Sequence):
        return all(validate_url(item) for item in url)

    return False


def safe_validate_urls(urls: Sequence[str]) -> Sequence[str]:
    valid_urls = []
    for url in urls:
        try:
            if validate_url(url):
                valid_urls.append(url)
        except Exception as exc:
            log.debug("Invalid URL %s: %s", url, exc)
    return valid_urls
