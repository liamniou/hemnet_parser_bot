import json

import pytest

from app.hemnet import parse
from tests.conftest import make_card, rsc_html, search_html


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2 695 000 kr", 2695000),
        ("fr. 1\u00a0995\u00a0000 kr", 1995000),
        ("4 176 kr/mån", 4176),
        ("Pris saknas", None),
        (None, None),
    ],
)
def test_parse_money(text, expected):
    assert parse.parse_money(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [("46,5 m²", (46.5, None)), ("58+12 m²", (58.0, 12.0)), ("28-112 m²", (28.0, None))],
)
def test_parse_areas(text, expected):
    assert parse.parse_areas(text) == expected


def test_parse_rooms_ranges_and_decimals():
    assert parse.parse_number("2,5 rum") == 2.5
    assert parse.parse_number("1-5 rum") == 1.0


def test_parse_search_uses_result_cards_only():
    html = search_html([make_card("1"), make_card("2", askingPrice="fr. 2 000 000 kr")], total=140)
    page = parse.parse_search(html)
    assert page.total == 140
    assert [c.id for c in page.cards] == ["1", "2"]
    c = page.cards[0]
    assert (c.asking_price, c.fee, c.living_area, c.rooms) == (3495000, 3200, 46.0, 2.0)
    assert c.has_balcony is True and c.housing_form == "APARTMENT"
    assert c.published_at is not None and c.lat == 59.31


def test_parse_search_without_results_raises():
    with pytest.raises(parse.ParseError):
        parse.parse_search("<html>Cloudflare challenge</html>")


def _active(**over):
    obj = {
        "__typename": "ActivePropertyListing",
        "id": "42",
        "title": "Gatan 1",
        "area": "Årsta",
        "streetAddress": "Gatan 1",
        "coordinates": {"lat": 59.3, "long": 18.06},
        "municipality": {"id": "18031", "fullName": "Stockholms kommun"},
        "districts": [{"id": "1", "fullName": "Årsta"}, {"id": "2", "fullName": "Söderort"}],
        "askingPrice": {"amount": 2695000, "formatted": "2 695 000 kr"},
        "fee": {"amount": 4176, "formatted": "4 176 kr"},
        "squareMeterPrice": {"amount": 57957, "formatted": "57 957 kr/m²"},
        "numberOfRooms": 1,
        "livingArea": 46.5,
        "legacyConstructionYear": "1962",
        "formattedFloor": "1 av 3, hiss finns ej",
        "relevantAmenities": [
            {"kind": "BALCONY", "isAvailable": True},
            {"kind": "ELEVATOR", "isAvailable": False},
        ],
        "images": {
            "__typename": "ListingImageResults",
            "images": [
                {"__typename": "ListingImage", "filename": "48/55/a.jpg", "url": "x"},
                {"__typename": "ListingImage", "filename": "83/80/b.jpg", "url": "y"},
            ],
        },
        "floorPlanImages": [{"__typename": "ListingImage", "filename": "fp/1/c.jpg"}],
        "closestWaterDistanceMeters": 400,
        "coastlineDistanceMeters": 1100,
    }
    obj.update(over)
    return obj


def test_parse_detail_active_picks_richest_object():
    partial = {"__typename": "ActivePropertyListing", "id": "42", "isProject": False}
    detail = parse.parse_detail(rsc_html(partial, _active()), "42")
    assert detail.kind == "active"
    f = detail.fields
    assert f["year_built"] == 1962 and f["has_balcony"] is True and f["has_elevator"] is False
    assert f["districts"] == ["Årsta", "Söderort"] and f["fee"] == 4176
    assert (f["water_distance"], f["coastline_distance"]) == (400, 1100)
    assert detail.image_urls == [
        "https://bilder.hemnet.se/images/original/48/55/a.jpg",
        "https://bilder.hemnet.se/images/original/83/80/b.jpg",
        "https://bilder.hemnet.se/images/original/fp/1/c.jpg",
    ]


def test_parse_detail_sold_redirect():
    sold = {
        "__typename": "SoldPropertyListing",
        "id": "642",
        "listingId": "42",
        "hemnetUrl": "https://www.hemnet.se/salda/lagenhet-642",
        "soldAt": "1795514400.0",
        "sellingPrice": {"amount": 1950000, "formatted": "1 950 000 kr"},
        "askingPrice": {"amount": 1900000, "formatted": "1 900 000 kr"},
        "formattedPriceChangePercentageWithSign": "+3 %",
    }
    detail = parse.parse_detail(rsc_html(sold), "42")
    assert detail.kind == "sold"
    assert detail.sale.final_price == 1950000 and detail.sale.price_change == "+3 %"


def test_parse_detail_deactivated_and_unknown():
    deact = {"__typename": "DeactivatedPropertyListing", "id": "42"}
    assert parse.parse_detail(rsc_html(deact), "42").kind == "removed"
    with pytest.raises(parse.ParseError):
        parse.parse_detail(rsc_html({"foo": 1}), "42")


def test_parse_sold_search():
    sale = {
        "__typename": "SaleCard",
        "id": "642",
        "listingId": "42",
        "slug": "s",
        "soldAt": "1795514400.0",
        "askingPrice": "1 950 000 kr",
        "finalPrice": "2 100 000 kr",
        "priceChange": "+8 %",
    }
    res = {"__typename": "SoldListingResults", "total": 251590, "cards": [sale]}
    total, sales = parse.parse_sold_search(rsc_html({"r": res}))
    assert total == 251590
    assert sales[0].listing_id == "42" and sales[0].final_price == 2100000


def test_parse_detail_resolves_streamed_text_rows():
    desc = "Ljus trea med balkong mot söder.\r\n\r\nVälkommen!"
    html = rsc_html(_active(description="$64"))
    row = f"\n64:T{len(desc.encode()):x},{desc}"
    html = html.replace(
        "</body>", f"<script>self.__next_f.push({json.dumps([1, row])})</script></body>"
    )
    detail = parse.parse_detail(html, "42")
    assert detail.fields["description"] == desc


def test_parse_search_resolves_deduplicated_path_refs():
    top = make_card("5")
    # Next.js streams the top-listing ad first, then dedupes the same card in the results.
    element = ["$", "$L62", None, {"tracking": {"top": {"card": top}}}]
    tracking = f"3b:{json.dumps(['$L44', [], [], [], element])}\n"
    ref = "$3b:4:props:tracking:top:card"
    dup = {k: (f"{ref}:{k}" if isinstance(v, (dict, list)) else v) for k, v in top.items()}
    html = search_html([dup, make_card("6")])
    html = html.replace(
        "<script>", f"<script>self.__next_f.push({json.dumps([1, tracking])})</script><script>", 1
    )
    page = parse.parse_search(html)
    c = page.cards[0]
    assert [x.id for x in page.cards] == ["5", "6"]
    assert c.housing_form == "APARTMENT" and c.lat == 59.31 and c.has_balcony is True
    assert c.thumbnails == top["thumbnails"]


def test_parse_card_tolerates_unresolvable_refs():
    card = make_card("7", housingForm="$ff:1:x", labels="$ff:2", thumbnails="$ff:3")
    c = parse.parse_search(search_html([card])).cards[0]
    assert (c.housing_form, c.labels, c.thumbnails) == (None, [], [])


def test_parse_detail_project_unit():
    unit = _active(**{"__typename": "ProjectUnit", "closestWaterDistanceMeters": 250})
    detail = parse.parse_detail(rsc_html({"__typename": "Project", "id": "9"}, unit), "42")
    assert detail.kind == "active"
    assert detail.fields["water_distance"] == 250 and detail.fields["new_construction"] is True
    assert len(detail.image_urls) == 3
