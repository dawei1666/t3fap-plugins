from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote, urljoin

from core.sdk import (
    BasePlugin,
    CatalogProvider,
    HealthReport,
    OfficialLink,
    ResourceAction,
    ResourceCapabilities,
    ResourceItem,
    ResourceLinks,
    ResourceListPage,
    ResourceQueryResponse,
    ResourceSection,
)
from core.services.resource_http import fetch_text


SITE_URL = "https://madou.club"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
CATEGORY_URLS = {
    "麻豆传媒": f"{SITE_URL}/category/%e9%ba%bb%e8%b1%86%e4%bc%a0%e5%aa%92",
    "麻豆番外篇": f"{SITE_URL}/category/%e9%ba%bb%e8%b1%86%e7%95%aa%e5%a4%96%e7%af%87",
    "麻豆花絮": f"{SITE_URL}/category/%e9%ba%bb%e8%b1%86%e8%8a%b1%e7%b5%ae",
}


class MadouCatalogPlugin(BasePlugin, CatalogProvider):
    plugin_id = "catalog.xpav"
    plugin_name = "麻豆社"
    plugin_version = "0.2.1"

    def health(self, ctx: dict[str, Any]) -> HealthReport:
        return HealthReport(status="ok", message="麻豆社 catalog plugin is ready.")

    def query(self, filters: dict[str, Any], cursor: str | None, limit: int) -> ResourceQueryResponse:
        page = self._page_from_cursor(cursor)
        keyword = str(filters.get("keyword") or filters.get("q") or "").strip()
        url = self._page_url(keyword=keyword, page=page)
        page_result = self._list_page(url, page=page, page_size=limit)
        return ResourceQueryResponse(
            filter_groups=[],
            items=page_result.items,
            next_cursor=str(page + 1) if page_result.has_more else None,
            total=page_result.total,
            notice=page_result.notice,
        )

    def list_sections(self) -> list[ResourceSection]:
        return [
            ResourceSection(key="latest", title="最新更新", media_type="movie"),
            ResourceSection(key="麻豆传媒", title="麻豆传媒", media_type="movie"),
            ResourceSection(key="麻豆番外篇", title="麻豆番外篇", media_type="movie"),
            ResourceSection(key="麻豆花絮", title="麻豆花絮", media_type="movie"),
        ]

    def list_items(self, section: str, query: dict[str, Any]) -> ResourceListPage:
        page = max(int(query.get("page", 1) or 1), 1)
        page_size = max(min(int(query.get("page_size", 12) or 12), 50), 1)
        keyword = str(query.get("keyword") or query.get("q") or "").strip()
        base_url = CATEGORY_URLS.get(section, SITE_URL)
        url = self._page_url(base_url=base_url, keyword=keyword, page=page)
        return self._list_page(url, page=page, page_size=page_size)

    def get_detail(self, resource_ref: dict[str, Any]) -> ResourceItem:
        detail_url = str(resource_ref.get("id") or resource_ref.get("url") or "").strip()
        if not detail_url.startswith("http"):
            raise ValueError("麻豆社资源缺少详情页地址")

        payload = fetch_text(detail_url, headers=HEADERS)
        title = self._first_text(payload, r"<h1[^>]*>(.*?)</h1>") or self._page_title(payload)
        title = title or detail_url
        play_url = self._resolve_play_url(payload, detail_url)
        links = [
            OfficialLink(platform="madou", label="麻豆社播放", url=play_url, kind="play")
        ] if play_url else [
            OfficialLink(platform="madou", label="麻豆社详情", url=detail_url, kind="detail")
        ]
        return ResourceItem(
            id=detail_url,
            source_plugin_id=self.plugin_id,
            source_type="catalog",
            source_name="麻豆社",
            title=title,
            subtitle="麻豆社",
            detail_url=detail_url,
            target_type="official",
            links=ResourceLinks(official=links),
            capabilities=ResourceCapabilities(
                searchable=True,
                official_searchable=True,
                downloadable=bool(play_url),
                strmable=bool(play_url),
            ),
            actions=self._task_actions() if play_url else [],
            meta={"resolved_play_url": bool(play_url), "site": SITE_URL},
        )

    def _list_page(self, url: str, *, page: int, page_size: int) -> ResourceListPage:
        payload = fetch_text(url, headers=HEADERS)
        items = self._parse_cards(payload, url)
        return ResourceListPage(
            items=items[:page_size],
            page=page,
            page_size=page_size,
            total=len(items),
            has_more=len(items) >= page_size,
        )

    def _parse_cards(self, payload: str, page_url: str) -> list[ResourceItem]:
        results: list[ResourceItem] = []
        articles = re.findall(r"<article\b[^>]*>(.*?)</article>", payload, re.IGNORECASE | re.DOTALL)
        for article in articles:
            href = self._first_attr(article, r"<a\b[^>]*href=[\"']([^\"']+)")
            if not href:
                continue
            detail_url = urljoin(page_url, html.unescape(href))
            title = self._first_text(article, r"<h2[^>]*>(.*?)</h2>")
            if not title:
                title = self._first_text(article, r"<h3[^>]*>(.*?)</h3>")
            title = title or detail_url
            cover = self._first_attr(article, r"<img\b[^>]*(?:data-src|src)=[\"']([^\"']+)")
            cover_url = urljoin(page_url, html.unescape(cover)) if cover else ""
            subtitle = self._first_text(article, r"class=[\"'][^\"']*post-view[^\"']*[\"'][^>]*>(.*?)</")
            results.append(
                ResourceItem(
                    id=detail_url,
                    source_plugin_id=self.plugin_id,
                    source_type="catalog",
                    source_name="麻豆社",
                    title=title,
                    subtitle=subtitle or "麻豆社",
                    cover_url=cover_url,
                    media_type="movie",
                    detail_url=detail_url,
                    target_type="official",
                    links=ResourceLinks(
                        official=[OfficialLink(platform="madou", label="麻豆社详情", url=detail_url, kind="detail")]
                    ),
                    capabilities=ResourceCapabilities(
                        searchable=True,
                        official_searchable=True,
                        downloadable=False,
                        strmable=False,
                    ),
                    meta={"site": SITE_URL},
                )
            )
        return results

    def _resolve_play_url(self, detail_html: str, detail_url: str) -> str:
        iframe = self._first_attr(detail_html, r"<iframe\b[^>]*src=[\"']?([^\"' >]+)")
        if not iframe:
            return ""
        iframe_url = urljoin(detail_url, html.unescape(iframe))
        player_html = fetch_text(iframe_url, headers={**HEADERS, "Referer": detail_url})
        token_match = re.search(r"var\s+token\s*=\s*[\"']([^\"']+)[\"']", player_html)
        m3u8_match = re.search(r"var\s+m3u8\s*=\s*[\"']([^\"']+)[\"']", player_html)
        if not token_match or not m3u8_match:
            return ""
        stream_url = urljoin(iframe_url, m3u8_match.group(1))
        return f"{stream_url}?token={quote(token_match.group(1), safe='._-~')}"

    @staticmethod
    def _page_url(base_url: str = SITE_URL, *, keyword: str = "", page: int = 1) -> str:
        if keyword:
            return f"{SITE_URL}/page/{page}?s={quote(keyword)}"
        if page <= 1:
            return base_url
        return base_url.rstrip("/") + f"/page/{page}"

    @staticmethod
    def _first_attr(payload: str, pattern: str) -> str:
        match = re.search(pattern, payload, re.IGNORECASE | re.DOTALL)
        return html.unescape(match.group(1)).strip() if match else ""

    @classmethod
    def _first_text(cls, payload: str, pattern: str) -> str:
        match = re.search(pattern, payload, re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return re.sub(r"<[^>]+>", " ", html.unescape(match.group(1))).strip()

    @classmethod
    def _page_title(cls, payload: str) -> str:
        return cls._first_text(payload, r"<title[^>]*>(.*?)</title>")

    @staticmethod
    def _page_from_cursor(cursor: str | None) -> int:
        try:
            return max(int(str(cursor or "1").strip()), 1)
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _task_actions() -> list[ResourceAction]:
        return [
            ResourceAction(
                key="task.video_download.create",
                label="影视下载",
                type="task",
                style="primary",
                target_plugin_id="task.video_download",
                payload={"template_key": "video_download"},
            ),
            ResourceAction(
                key="task.strm.create",
                label="生成STRM",
                type="task",
                target_plugin_id="task.strm",
                payload={"template_key": "strm_generate"},
            ),
        ]


plugin = MadouCatalogPlugin()

