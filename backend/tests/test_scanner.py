from datetime import timedelta

from sqlalchemy import select

from app.db import session_scope
from app.hemnet.parse import DetailData, SaleData
from app.models import Listing, Notification, Region, SavedSearch, User, UserListing, utcnow
from app.services import images, notifications, scanner
from tests.conftest import make_card


def _setup(region_types=("bostadsratt",)) -> int:
    with session_scope() as db:
        region = Region(
            location_id="18031", name="Stockholms kommun", item_types=list(region_types)
        )
        alice = User(email="alice@x.se", name="Alice")
        bob = User(email="bob@x.se", name="Bob")
        db.add_all([region, alice, bob])
        db.flush()
        db.add(SavedSearch(user_id=alice.id, name="Cheap", price_max=4_000_000))
        db.add(SavedSearch(user_id=bob.id, name="Big", living_area_min=100))
        return region.id


def _notifications():
    with session_scope() as db:
        return [
            (db.get(User, n.user_id).name, n.kind, n.listing_id)
            for n in db.scalars(select(Notification).order_by(Notification.id))
        ]


def test_seed_then_incremental_announces_only_new_matches(app_env, mail):
    rid = _setup()
    app_env.pages = [[make_card("1"), make_card("2")]]
    res = scanner.scan_region(rid)
    assert res.mode == "seed" and res.new == 2 and res.complete
    scanner.fetch_details()
    assert _notifications() == []

    app_env.since_pages = [[make_card("3"), make_card("1")]]
    res = scanner.scan_region(rid)
    assert res.mode == "incremental" and res.new == 1
    assert app_env.calls[-1][3] == "1d"

    scanner.fetch_details()
    with session_scope() as db:
        l3 = db.get(Listing, "3")
        assert l3.seed is False and l3.year_built == 1930 and l3.districts == ["Södermalm"]
    # Alice's price cap matches (3 495 000); Bob needs >= 100 m².
    assert _notifications() == [("Alice", "new", "3")]

    notifications.dispatch_pending()
    msg = mail.sent[-1]
    assert msg["to"] == "alice@x.se" and msg["subject"].startswith("New: Gatan 1")
    assert "Cheap" in msg["html"] and "/listings/3" in msg["text"]


def test_full_scan_price_drop_and_removal(app_env, mail):
    rid = _setup()
    app_env.pages = [[make_card("1"), make_card("2")]]
    scanner.scan_region(rid)
    with session_scope() as db:
        db.get(Listing, "1").seed = False
        db.add(UserListing(user_id=2, listing_id="1", favorite=True))

    app_env.pages = [[make_card("1", askingPrice="3 195 000 kr")]]
    with session_scope() as db:
        db.get(Region, rid).last_full_scan_at = utcnow() - timedelta(days=2)
    res = scanner.scan_region(rid)
    assert res.mode == "full" and res.price_changes == 1 and res.removed == 1
    with session_scope() as db:
        assert db.get(Listing, "2").status == "removed"
        l1 = db.get(Listing, "1")
        assert l1.asking_price == 3195000
        assert [(p.old_price, p.new_price) for p in l1.price_changes] == [(3495000, 3195000)]
    # Only the user who saved the listing hears about the drop.
    assert _notifications() == [("Bob", "price_drop", "1")]


def test_sold_scan_notifies_previously_notified_users(app_env, mail):
    rid = _setup()
    app_env.pages = [[make_card("1")]]
    scanner.scan_region(rid)
    app_env.since_pages = [[make_card("5")]]
    scanner.scan_region(rid)
    scanner.fetch_details()
    notifications.dispatch_pending()

    app_env.sales = [
        SaleData("s5", "5", "slug", 3_700_000, "3 700 000 kr", 3_495_000, utcnow(), "+6 %"),
        SaleData("s9", "9", "slug", 1, "1 kr", 1, utcnow(), None),
    ]
    assert scanner.scan_sold(rid) == 1
    with session_scope() as db:
        l5 = db.get(Listing, "5")
        assert (l5.status, l5.sold_price, l5.sold_price_change) == ("sold", 3_700_000, "+6 %")
    assert _notifications()[-1] == ("Alice", "sold", "5")

    notifications.dispatch_pending()
    msg = mail.sent[-1]
    assert msg["to"] == "alice@x.se" and "Sold for 3 700 000 kr" in msg["html"]


def test_check_removed_detects_sale(app_env):
    rid = _setup()
    app_env.pages = [[make_card("1")]]
    scanner.scan_region(rid)
    with session_scope() as db:
        db.get(Listing, "1").status = "removed"
    app_env.details["1"] = lambda: DetailData(
        "sold",
        "1",
        sale=SaleData("s1", "1", "x", 2_000_000, "2 000 000 kr", None, utcnow(), "-5 %"),
    )
    scanner.check_removed()
    with session_scope() as db:
        assert db.get(Listing, "1").status == "sold"


def test_failed_email_is_retried_then_given_up(app_env, mail):
    rid = _setup()
    app_env.pages = [[]]
    scanner.scan_region(rid)
    app_env.since_pages = [[make_card("7")]]
    scanner.scan_region(rid)
    scanner.fetch_details()
    mail.fail_with = OSError("SMTP down")
    notifications.dispatch_pending()
    with session_scope() as db:
        assert db.scalars(select(Notification.status)).all() == ["pending"]
    for _ in range(notifications.MAX_ATTEMPTS):
        notifications.dispatch_pending()
    with session_scope() as db:
        n = db.scalars(select(Notification)).one()
        assert (n.status, n.attempts, n.error) == (
            "failed",
            notifications.MAX_ATTEMPTS,
            "SMTP down",
        )


def test_archive_images_resizes_to_webp(app_env):
    rid = _setup()
    app_env.pages = [[make_card("1")]]
    scanner.scan_region(rid)
    app_env.details["1"] = lambda: DetailData(
        "active", "1", {}, ["https://bilder.hemnet.se/images/original/a.jpg"] * 2
    )
    scanner.fetch_details()
    assert images.archive_pending() == 1
    with session_scope() as db:
        listing = db.get(Listing, "1")
        assert listing.images_status == "done"
        assert [(i["w"], i["h"]) for i in listing.images] == [(1024, 683), (1024, 683)]
    from app.config import get_settings

    assert (get_settings().images_dir / "1" / "00.webp").exists()


def test_full_scan_beyond_hemnet_cap_does_not_mark_removed(app_env):
    rid = _setup()
    app_env.pages = [[make_card("1"), make_card("2")]]
    scanner.scan_region(rid)
    # Hemnet's 50-page cap: later pages come back empty while the total stays large.
    app_env.pages = [[make_card("1")]]
    app_env.total_override = 25_000
    res = scanner.scan_region(rid, "full")
    assert res.complete is False and res.removed == 0
    with session_scope() as db:
        assert db.get(Listing, "2").status == "active"


def test_failing_region_backs_off_instead_of_retrying_every_minute(app_env, monkeypatch):
    rid = _setup()
    app_env.pages = [[make_card("1")]]
    scanner.scan_region(rid)
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        raise RuntimeError("hemnet changed")

    monkeypatch.setattr(app_env, "search", boom)
    with session_scope() as db:
        db.get(Region, rid).last_scan_at = utcnow() - timedelta(days=1)
    scanner.run_due_scans()
    scanner.run_due_scans()
    assert len(calls) == 1
    with session_scope() as db:
        db.get(Region, rid).last_error_at = utcnow() - timedelta(minutes=31)
    scanner.run_due_scans()
    assert len(calls) == 2
