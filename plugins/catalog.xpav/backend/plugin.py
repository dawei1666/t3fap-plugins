from __future__ import annotations
from typing import Any

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
from core.services.resource_http import fetch_json

# ⚠️ 在这里填入你 XPAV.json 里的实际接口地址 ⚠️
XPAV_API_URL = "https://填写你的实际源地址/api.php/provide/vod/"

class XpavCatalogPlugin(BasePlugin, CatalogProvider):
    plugin_id = "catalog.xpav"
    plugin_name = "XPAV资源库"
    plugin_version = "0.1.0"

    def health(self, ctx: dict[str, Any]) -> HealthReport:
        return HealthReport(status="ok", message="XPAV plugin is ready.")

    def query(self, filters: dict[str, Any], cursor: str | None, limit: int) -> ResourceQueryResponse:
        page = int(cursor) if cursor else 1
        # 调用标准的 CMS API 接口
        payload = fetch_json(XPAV_API_URL, params={"ac": "detail", "pg": page, "limit": limit})
        
        items = self._parse_items(payload.get("list", []))
        total = payload.get("total", 0)
        has_more = payload.get("page", 1) * payload.get("limit", 20) < total
        
        return ResourceQueryResponse(
            filter_groups=[],
            items=items,
            next_cursor=str(page + 1) if has_more else None,
            total=total
        )

    def list_sections(self) -> list[ResourceSection]:
        # 可以在这里根据你的源分类自定义频道
        return [
            ResourceSection(key="latest", title="最新更新", media_type="movie")
        ]

    def list_items(self, section: str, query: dict[str, Any]) -> ResourceListPage:
        page = max(int(query.get("page", 1) or 1), 1)
        page_size = max(min(int(query.get("page_size", 20) or 20), 60), 1)

        payload = fetch_json(XPAV_API_URL, params={"ac": "detail", "pg": page, "limit": page_size})
        items = self._parse_items(payload.get("list", []))
        total = payload.get("total", 0)
        
        return ResourceListPage(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            has_more=page * page_size < total
        )

    def get_detail(self, resource_ref: dict[str, Any]) -> ResourceItem:
        vod_id = resource_ref.get("id")
        payload = fetch_json(XPAV_API_URL, params={"ac": "detail", "ids": vod_id})
        items = self._parse_items(payload.get("list", []))
        if items:
            return items[0]
        raise ValueError(f"XPAV 资源未找到: {vod_id}")

    def _parse_items(self, raw_items: list[dict[str, Any]]) -> list[ResourceItem]:
        results = []
        for item in raw_items:
            vod_id = str(item.get("vod_id", ""))
            if not vod_id:
                continue
            
            title = str(item.get("vod_name", "未知"))
            cover = str(item.get("vod_pic", ""))
            play_url = str(item.get("vod_play_url", ""))
            subtitle = str(item.get("vod_remarks", ""))
            
            results.append(
                ResourceItem(
                    id=vod_id,
                    source_plugin_id=self.plugin_id,
                    source_type="catalog",
                    source_name="XPAV",
                    title=title,
                    subtitle=subtitle,
                    cover_url=cover,
                    detail_url=play_url,
                    target_type="official",
                    links=ResourceLinks(
                        official=[OfficialLink(platform="xpav", label="播放源", url=play_url, kind="play")] if play_url else []
                    ),
                    capabilities=ResourceCapabilities(
                        searchable=True,
                        strmable=True,
                        downloadable=True
                    ),
                    actions=[
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
                )
            )
        return results

plugin = XpavCatalogPlugin()
