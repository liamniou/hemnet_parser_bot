from fastapi.testclient import TestClient

from app.bot import handle_update
from app.db import session_scope
from app.models import Listing, ListingRegion, Region, User
from tests.conftest import make_card


def _client():
    from app.main import app

    return TestClient(app)


def _login(client, tg, tg_id: int, name: str = "User") -> dict:
    r = client.post("/api/auth/telegram")
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["url"] == f"https://t.me/hemnet_test_bot?start=login_{token}"
    assert client.get(f"/api/auth/telegram/{token}").json() == {"status": "pending"}

    tg_user = {"id": tg_id, "first_name": name, "username": name.lower()}
    handle_update(
        tg,
        {
            "message": {
                "chat": {"id": tg_id, "type": "private"},
                "from": tg_user,
                "text": f"/start login_{token}",
            }
        },
    )
    assert (
        tg.sent[-1][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"login:{token}"
    )
    handle_update(tg, {"callback_query": {"id": "cb", "from": tg_user, "data": f"login:{token}"}})

    r = client.get(f"/api/auth/telegram/{token}")
    assert r.json()["status"] == "ok"
    # Tokens are single-use.
    assert client.get(f"/api/auth/telegram/{token}").status_code == 410
    return r.json()["user"]


def test_telegram_login_first_user_is_admin(app_env, tg):
    c1, c2 = _client(), _client()
    assert c1.get("/api/me").status_code == 401
    admin = _login(c1, tg, 100, "Admin")
    user = _login(c2, tg, 200, "Regular")
    assert admin["is_admin"] is True and user["is_admin"] is False
    assert c1.get("/api/me").json()["telegram_id"] == 100
    assert c2.get("/api/admin/regions").status_code == 403
    assert c2.post("/api/auth/dev-login", params={"telegram_id": 1}).status_code == 404


def test_admin_regions_and_reseed_on_type_change(app_env, tg):
    c = _client()
    _login(c, tg, 100, "Admin")
    assert c.get("/api/admin/locations", params={"q": "Stock"}).json()[0]["id"] == "18031"
    r = c.post(
        "/api/admin/regions",
        json={"location_id": "18031", "name": "Stockholm", "item_types": ["bostadsratt"]},
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    assert (
        c.post("/api/admin/regions", json={"location_id": "18031", "name": "x"}).status_code == 409
    )
    assert (
        c.post(
            "/api/admin/regions", json={"location_id": "1", "name": "x", "item_types": ["castle"]}
        ).status_code
        == 400
    )
    with session_scope() as db:
        db.get(Region, rid).seeded = True
    r = c.patch(f"/api/admin/regions/{rid}", json={"item_types": ["villa", "bostadsratt"]})
    assert r.json()["seeded"] is False and r.json()["item_types"] == ["bostadsratt", "villa"]


def test_searches_listings_and_ownership(app_env, tg):
    from app.hemnet.parse import parse_card
    from app.models import utcnow
    from app.services.scanner import upsert_card

    with session_scope() as db:
        db.add(Region(id=1, location_id="18031", name="Stockholm", item_types=[]))
        db.flush()
        for lid, price in (("1", "3 000 000 kr"), ("2", "6 000 000 kr")):
            upsert_card(db, parse_card(make_card(lid, askingPrice=price)), 1, False, utcnow())

    alice, bob = _client(), _client()
    _login(alice, tg, 100, "Alice")
    _login(bob, tg, 200, "Bob")

    body = {"name": "Cheap", "price_max": 4_000_000, "region_ids": [1]}
    r = alice.post("/api/searches", json=body)
    assert r.status_code == 201 and r.json()["match_count"] == 1
    sid = r.json()["id"]
    assert bob.get(f"/api/searches/{sid}").status_code == 404
    assert bob.delete(f"/api/searches/{sid}").status_code == 404

    page = alice.post("/api/listings/query", json={"search_id": sid}).json()
    assert [x["id"] for x in page["items"]] == ["1"]
    page = alice.post("/api/listings/query", json={"sort": "price_desc"}).json()
    assert [x["id"] for x in page["items"]] == ["2", "1"]

    assert alice.put("/api/listings/2/state", json={"hidden": True}).status_code == 200
    page = alice.post("/api/listings/query", json={}).json()
    assert [x["id"] for x in page["items"]] == ["1"]
    assert len(bob.post("/api/listings/query", json={}).json()["items"]) == 2

    detail = alice.get("/api/listings/1").json()
    assert detail["regions"] == ["Stockholm"] and detail["gallery"][0]["url"].startswith("https://")

    facets = alice.get("/api/listings/facets", params={"region_ids": "1"}).json()
    assert {"name": "Södermalm", "count": 2} in facets["districts"]


def test_delete_region_purge_keeps_shared_listings(app_env, tg):
    c = _client()
    _login(c, tg, 100, "Admin")
    with session_scope() as db:
        db.add_all(
            [Region(id=1, location_id="a", name="A"), Region(id=2, location_id="b", name="B")]
        )
        db.flush()
        for lid in ("1", "2"):
            db.add(Listing(id=lid, slug=lid))
        db.flush()
        db.add_all(
            [
                ListingRegion(listing_id="1", region_id=1),
                ListingRegion(listing_id="2", region_id=1),
                ListingRegion(listing_id="2", region_id=2),
            ]
        )
    assert c.delete("/api/admin/regions/1", params={"purge": True}).status_code == 204
    with session_scope() as db:
        assert db.get(Listing, "1") is None and db.get(Listing, "2") is not None
        assert db.get(User, 1) is not None


def test_deleted_account_session_does_not_carry_over(app_env, tg):
    _login(_client(), tg, 100, "Admin")
    phone, laptop = _client(), _client()
    _login(laptop, tg, 200, "Old")
    phone.cookies.update(laptop.cookies)
    assert laptop.delete("/api/me").status_code == 200
    _login(_client(), tg, 300, "New")
    assert phone.get("/api/me").status_code == 401


def test_missing_secret_key_is_generated_and_persisted(app_env, monkeypatch):
    from app.config import Settings, get_settings

    monkeypatch.setenv("SECRET_KEY", "")
    s = Settings()
    s.ensure_secret_key()
    assert len(s.secret_key) >= 32
    again = Settings()
    again.ensure_secret_key()
    assert again.secret_key == s.secret_key
    assert (get_settings().data_dir / "secret_key").exists()
