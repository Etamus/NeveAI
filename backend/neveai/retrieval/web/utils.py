import asyncio
import logging
from typing import Any, AsyncIterator, Dict, Iterator, List, Sequence, Union

import aiohttp
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document

from neveai.config import WEB_LOADER_TIMEOUT
from neveai.constants import ERROR_MESSAGES
from neveai.utils.url import safe_validate_urls

log = logging.getLogger(__name__)


def extract_metadata(soup, url: str) -> dict:
    metadata = {"source": url}
    if title := soup.find("title"):
        metadata["title"] = title.get_text()
    if description := soup.find("meta", attrs={"name": "description"}):
        metadata["description"] = description.get("content", "")
    if html := soup.find("html"):
        metadata["language"] = html.get("lang", "")
    return metadata


class SafeWebBaseLoader(WebBaseLoader):
    """Local web loader with retries and the project's URL safety checks."""

    def __init__(self, trust_env: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trust_env = trust_env

    async def _fetch(
        self, url: str, retries: int = 3, cooldown: int = 2, backoff: float = 1.5
    ) -> str:
        async with aiohttp.ClientSession(trust_env=self.trust_env) as session:
            for attempt in range(retries):
                try:
                    kwargs: Dict = {
                        "headers": self.session.headers,
                        "cookies": self.session.cookies.get_dict(),
                    }
                    if not self.session.verify:
                        kwargs["ssl"] = False
                    async with session.get(
                        url,
                        **(self.requests_kwargs | kwargs),
                        allow_redirects=False,
                    ) as response:
                        if self.raise_for_status:
                            response.raise_for_status()
                        return await response.text()
                except aiohttp.ClientConnectionError:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(cooldown * backoff**attempt)
        raise ValueError("retry count exceeded")

    def _unpack_fetch_results(
        self, results: Any, urls: List[str], parser: Union[str, None] = None
    ) -> List[Any]:
        from bs4 import BeautifulSoup

        final_results = []
        for index, result in enumerate(results):
            current_parser = parser
            if current_parser is None:
                current_parser = (
                    "xml" if urls[index].endswith(".xml") else self.default_parser
                )
                self._check_parser(current_parser)
            final_results.append(
                BeautifulSoup(result, current_parser, **self.bs_kwargs)
            )
        return final_results

    async def ascrape_all(
        self, urls: List[str], parser: Union[str, None] = None
    ) -> List[Any]:
        return self._unpack_fetch_results(
            await self.fetch_all(urls), urls, parser=parser
        )

    def lazy_load(self) -> Iterator[Document]:
        for path in self.web_paths:
            try:
                soup = self._scrape(path, bs_kwargs=self.bs_kwargs)
                yield Document(
                    page_content=soup.get_text(**self.bs_get_text_kwargs),
                    metadata=extract_metadata(soup, path),
                )
            except Exception as error:
                log.warning("Unable to load %s: %s", path, error)

    async def alazy_load(self) -> AsyncIterator[Document]:
        results = await self.ascrape_all(self.web_paths)
        for path, soup in zip(self.web_paths, results):
            yield Document(
                page_content=soup.get_text(**self.bs_get_text_kwargs),
                metadata=extract_metadata(soup, path),
            )

    async def aload(self) -> list[Document]:
        return [document async for document in self.alazy_load()]


def get_web_loader(
    urls: Union[str, Sequence[str]],
    verify_ssl: bool = True,
    requests_per_second: int = 2,
    trust_env: bool = False,
):
    safe_urls = safe_validate_urls([urls] if isinstance(urls, str) else urls)
    if not safe_urls:
        raise ValueError(ERROR_MESSAGES.INVALID_URL)

    request_kwargs = {}
    if WEB_LOADER_TIMEOUT.value:
        try:
            timeout = float(WEB_LOADER_TIMEOUT.value)
        except (TypeError, ValueError):
            timeout = None
        if timeout:
            request_kwargs["timeout"] = timeout

    return SafeWebBaseLoader(
        web_paths=safe_urls,
        verify_ssl=verify_ssl,
        requests_per_second=requests_per_second,
        continue_on_failure=True,
        trust_env=trust_env,
        requests_kwargs=request_kwargs,
    )
