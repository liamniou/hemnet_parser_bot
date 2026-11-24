from app.models import Listing
from app.services.matching import Criteria, matches


def _listing(**over) -> Listing:
    data = dict(
        id="1",
        slug="s",
        housing_form="APARTMENT",
        asking_price=4_000_000,
        rooms=2.0,
        living_area=55.0,
        fee=3500,
        sqm_price=72000,
        year_built=1935,
        has_balcony=True,
        has_elevator=None,
        labels=[],
        districts=["Vasastan", "Innerstaden"],
        area_name="Vasastan",
        location_description="Vasastan, Stockholms kommun",
        street_address="Odengatan 1",
        description="Charmig tvåa med kakelugn",
        new_construction=False,
        lat=59.343,
        lon=18.05,
    )
    data.update(over)
    return Listing(**data)


def test_ranges_strict_for_core_fields_and_lenient_for_optional():
    lst = _listing(fee=None, year_built=None)
    assert matches(Criteria(price_max=4_500_000, rooms_min=2, fee_max=3000), lst, [])
    assert not matches(Criteria(price_max=3_900_000), lst, [])
    assert not matches(Criteria(price_max=5_000_000), _listing(asking_price=None), [])
    assert matches(Criteria(year_built_min=1900), lst, [])


def test_regions_districts_and_forms():
    lst = _listing()
    assert matches(Criteria(region_ids=[1, 2]), lst, [2])
    assert not matches(Criteria(region_ids=[1]), lst, [2])
    assert matches(Criteria(districts=["Innerstaden"]), lst, [])
    assert not matches(Criteria(districts=["Södermalm"]), lst, [])
    assert not matches(Criteria(housing_forms=["HOUSE"]), lst, [])


def test_features_and_new_construction():
    assert not matches(Criteria(require_elevator=True), _listing(), [])
    assert matches(Criteria(require_elevator=True), _listing(labels=["ELEVATOR"]), [])
    assert not matches(
        Criteria(include_new_construction=False), _listing(new_construction=True), []
    )


def test_keywords_include_and_exclude():
    lst = _listing()
    assert matches(Criteria(keywords="kakelugn, eldstad"), lst, [])
    assert not matches(Criteria(keywords="eldstad"), lst, [])
    assert not matches(Criteria(keywords="-kakelugn"), lst, [])


def test_radius():
    lst = _listing()
    near = Criteria(center_lat=59.342, center_lon=18.049, radius_km=1)
    far = Criteria(center_lat=59.30, center_lon=18.10, radius_km=1)
    assert matches(near, lst, [])
    assert not matches(far, lst, [])
    assert not matches(near, _listing(lat=None, lon=None), [])


def test_water_distance_max_excludes_far_and_unknown():
    c = Criteria(water_distance_max=300)
    assert matches(c, _listing(water_distance=250), [])
    assert not matches(c, _listing(water_distance=800), [])
    assert not matches(c, _listing(water_distance=None), [])
    assert matches(Criteria(), _listing(water_distance=None), [])
