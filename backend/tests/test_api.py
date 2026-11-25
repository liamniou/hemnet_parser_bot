from fastapi.testclient import TestClient

from app.db import session_scope
from app.models import Listing, ListingRegion, Region, User
from tests.conftest import make_card


def _client():
    from app.main import app

    return TestClient(app)


def _login(client, mail, email: str) -> dict:
    r = client.post("/api/auth/email", json={"email": email})
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/email/verify", json={"email": email, "code": mail.last_code(email)})
    assert r.status_code == 200, r.text
    return r.json()["user"]


def test_email_code_login_first_user_is_admin(app_env, mail):
    c1, c2 = _client(), _client()
    assert c1.get("/api/me").status_code == 401
    admin = _login(c1, mail, "Admin@X.se ")
    user = _login(c2, mail, "user@x.se")
    assert admin["email"] == "admin@x.se" and admin["is_admin"] is True
    assert user["is_admin"] is False
    assert c1.get("/api/me").json()["email"] == "admin@x.se"
    assert c2.get("/api/admin/regions").status_code == 403
    assert c2.post("/api/auth/dev-login", params={"email": "a@b.se"}).status_code == 404


def test_login_link_wrong_code_and_rate_limits(app_env, mail):
    c = _client()
    assert c.post("/api/auth/email", json={"email": "nope"}).status_code == 400
    assert c.post("/api/auth/email", json={"email": "u@x.se"}).status_code == 200
    # Resending within a minute is refused (no inbox spamming).
    assert c.post("/api/auth/email", json={"email": "u@x.se"}).status_code == 429
    assert len(mail.sent) == 1

    for _ in range(5):
        r = c.post("/api/auth/email/verify", json={"email": "u@x.se", "code": "000000"})
        assert r.status_code == 400
    # After too many wrong guesses even the right code is rejected.
    code = mail.last_code("u@x.se")
    r = c.post("/api/auth/email/verify", json={"email": "u@x.se", "code": code})
    assert r.status_code == 400 and "expired" in r.json()["detail"]

    # The emailed link still works (separate token), exactly once.
    token = mail.last_link_token("u@x.se")
    assert c.post("/api/auth/email/link", json={"token": token}).status_code == 200
    assert c.get("/api/me").json()["email"] == "u@x.se"
    assert _client().post("/api/auth/email/link", json={"token": token}).status_code == 400


def test_admin_emails_setting(app_env, mail, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("ADMIN_EMAILS", "boss@x.se")
    get_settings.cache_clear()
    assert _login(_client(), mail, "first@x.se")["is_admin"] is False
    assert _login(_client(), mail, "Boss@x.se")["is_admin"] is True


def test_admin_regions_and_reseed_on_type_change(app_env, mail):
    c = _client()
    _login(c, mail, "admin@x.se")
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


def test_searches_listings_and_ownership(app_env, mail):
    from app.hemnet.parse import parse_card
    from app.models import utcnow
    from app.services.scanner import upsert_card

    with session_scope() as db:
        db.add(Region(id=1, location_id="18031", name="Stockholm", item_types=[]))
        db.flush()
        for lid, price in (("1", "3 000 000 kr"), ("2", "6 000 000 kr")):
            upsert_card(db, parse_card(make_card(lid, askingPrice=price)), 1, False, utcnow())

    alice, bob = _client(), _client()
    _login(alice, mail, "alice@x.se")
    _login(bob, mail, "bob@x.se")

    body = {"name": "Cheap", "price_max": 4_000_000, "region_ids": [1]}
    r = alice.post("/api/searches", json=body)
    assert r.status_code == 201 and r.json()["match_count"] == 1
    sid = r.json()["id"]
    assert bob.get(f"/api/searches/{sid}").status_code == 404
    assert bob.delete(f"/api/searches/{sid}").status_code == 404

    page = alice.post("/api/listings/query", json={"search_id": sid}).json()
    assert [x["id"] for x in page["items"]] == ["1"]
    with session_scope() as db:
        db.get(Listing, "2").images = [{"file": "2/00.webp"}, {"file": "2/01.webp"}]
    page = alice.post("/api/listings/query", json={"sort": "price_desc"}).json()
    assert page["items"][0]["photos"] == ["/media/2/00.webp", "/media/2/01.webp"]
    assert page["items"][1]["photos"] == make_card("1")["thumbnails"]
    assert [x["id"] for x in page["items"]] == ["2", "1"]

    assert alice.put("/api/listings/2/state", json={"hidden": True}).status_code == 200
    page = alice.post("/api/listings/query", json={}).json()
    assert [x["id"] for x in page["items"]] == ["1"]
    r = alice.put("/api/listings/1/state", json={"subscribed": True})
    assert r.json()["subscribed"] is True
    page = alice.post("/api/listings/query", json={"subscribed_only": True}).json()
    assert [(x["id"], x["subscribed"]) for x in page["items"]] == [("1", True)]
    assert bob.post("/api/listings/query", json={"subscribed_only": True}).json()["items"] == []
    page = alice.post("/api/listings/query", json={"hidden_only": True}).json()
    assert [(x["id"], x["hidden"]) for x in page["items"]] == [("2", True)]
    assert len(alice.post("/api/listings/query", json={"show_hidden": True}).json()["items"]) == 2
    points = alice.post("/api/listings/map", json={}).json()
    assert [(p["id"], p["housing_form"]) for p in points] == [("1", "APARTMENT")]
    assert len(bob.post("/api/listings/query", json={}).json()["items"]) == 2

    detail = alice.get("/api/listings/1").json()
    assert detail["regions"] == ["Stockholm"] and detail["gallery"][0]["url"].startswith("https://")

    facets = alice.get("/api/listings/facets", params={"region_ids": "1"}).json()
    assert {"name": "Södermalm", "count": 2} in facets["districts"]


def test_delete_region_purge_keeps_shared_listings(app_env, mail):
    c = _client()
    _login(c, mail, "admin@x.se")
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


def test_deleted_account_session_does_not_carry_over(app_env, mail):
    _login(_client(), mail, "admin@x.se")
    phone, laptop = _client(), _client()
    _login(laptop, mail, "old@x.se")
    phone.cookies.update(laptop.cookies)
    assert laptop.delete("/api/me").status_code == 200
    _login(_client(), mail, "new@x.se")
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


def test_spa_index_is_revalidated_and_assets_are_immutable(app_env, tmp_path, monkeypatch):
    import importlib

    import app.main as main

    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "index-abc.js").write_text("x")
    monkeypatch.setenv("STATIC_DIR", str(static))
    main = importlib.reload(main)
    try:
        from fastapi.testclient import TestClient

        c = TestClient(main.app)
        r = c.get("/listings/123")
        assert r.text == "<html>app</html>" and r.headers["cache-control"] == "no-cache"
        r = c.get("/assets/index-abc.js")
        assert "immutable" in r.headers["cache-control"]
    finally:
        monkeypatch.delenv("STATIC_DIR")
        importlib.reload(main)
