from httpx import ASGITransport, AsyncClient

from src.main import app


async def get(path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


async def test_profile_matches_the_widget_contract():
    response = await get("/api/customers/ACC-DEMO01")

    assert response.status_code == 200
    assert response.json() == {
        "account_id": "ACC-DEMO01",
        "first_name": "Sarah",
        "last_name": "Whitfield",
        "region": "North",
        "services": ["electricity", "water"],
    }


async def test_unknown_account_is_404():
    response = await get("/api/customers/ACC-000000")

    assert response.status_code == 404
