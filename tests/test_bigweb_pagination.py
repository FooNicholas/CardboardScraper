import httpx
import pytest

from scraperbot.connectors.bigweb import BigWebConnector


@pytest.mark.asyncio
async def test_bigweb_loads_all_pages_for_an_unknown_rarity() -> None:
    requested_pages: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(request.url.params.get("page"))
        page = request.url.params.get("page", "1")
        return httpx.Response(
            200,
            json={"success": True, "items": [{"id": page}], "pagenate": {"pageCount": 3}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = BigWebConnector(client)
        pages = await connector._product_pages({"game_id": 144, "cardsets": 1, "is_box": 0})

    assert [page["items"][0]["id"] for page in pages] == ["1", "2", "3"]
    assert requested_pages == [None, "2", "3"]
