from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Codes.HousesRent.browser import is_challenge_page
from Codes.HousesRent.common import (
    CsvSink,
    OUTPUT_FIELDS,
    format_price_tl,
    is_explicitly_sale_listing,
    make_listing_row,
    normalize_price,
)
from Codes.HousesRent.Emlakjet.scraper import (
    build_page_url as build_emlakjet_page_url,
    discover_child_scope_urls,
    discover_province_urls,
    extract_result_count,
    parse_page as parse_emlakjet_page,
)


EMLAKJET_HTML = """
<html><body>
<div>41.279 ilan bulundu</div>
<article data-listing-id="19733335">
  <div>
    <h3 data-listing-title="true"><a href="/ilan/izmir-konak-kiralik-daire-19733335">Rental title with no advertiser field</a></h3>
    <p>İzmir, Konak</p>
    <p><span>3+1</span><span> · 98 m²</span><span> · 3. Kat</span><span> · 16.08.2026</span></p>
    <div class="price"><span>32.000 ₺</span></div>
  </div>
  <div class="agent">Agent name must not be exported</div>
</article>
<article data-listing-id="19733336">
  <div>
    <h3 data-listing-title="true"><a href="/ilan/ankara-cankaya-kiralik-daire-19733336">A second rental</a></h3>
    <p>Ankara, Çankaya</p>
    <p><span>2+0</span><span> · 75 m²</span><span> · 1. Kat</span><span> · 15.08.2026</span></p>
    <div class="price"><span>18.500 ₺</span></div>
  </div>
</article>
<article data-listing-id="19733337">
  <div>
    <h3 data-listing-title="true"><a href="/ilan/tokat-merkez-satilik-daire-19733337">Satılık listing must be rejected</a></h3>
    <p>Tokat, Merkez</p>
    <p><span>3+1</span><span> · 130 m²</span><span> · 2. Kat</span><span> · 15.08.2026</span></p>
    <div class="price"><span>3.875.000 ₺</span></div>
  </div>
</article>
<a href="/kiralik-konut?sayfa=2" aria-label="Sayfa 2">2</a>
<a href="/kiralik-konut?sayfa=50" aria-label="Sayfa 50">50</a>
</body></html>
"""


class HousesRentScraperTests(unittest.TestCase):
    def test_normalize_turkish_prices(self) -> None:
        self.assertEqual(normalize_price("35.000 TL"), 35000)
        self.assertEqual(normalize_price("3.875.000 ₺"), 3875000)
        self.assertEqual(normalize_price("1.250,50 TL"), 1250.50)
        self.assertIsNone(normalize_price("Fiyat sorunuz"))

    def test_legacy_rental_output_contract_formats_first_columns(self) -> None:
        self.assertEqual(list(OUTPUT_FIELDS)[:3], ["District", "Rooms", "Price"])
        self.assertNotIn("Source", OUTPUT_FIELDS)
        self.assertEqual(format_price_tl(4500), "4.500 TL")
        self.assertEqual(format_price_tl(1250.5), "1.250,50 TL")
        row = make_listing_row(
            ilan_id="1",
            listing_url="https://example.test/ilan/1",
            province="Kayseri",
            district="Melikgazi",
            neighborhood="Kılıçaslan",
            property_type="Konut",
            rooms="3+1",
            area_m2=120,
            price=4500,
            listing_date="2026-08-17",
            collected_at="test",
        )
        self.assertEqual(row["District"], "Melikgazi / Kılıçaslan")
        self.assertEqual(row["Rooms"], "3+1")
        self.assertEqual(row["Price"], "4.500 TL")

    def test_challenge_detector_stops_instead_of_solving_protection(self) -> None:
        self.assertTrue(is_challenge_page("<title>Just a moment...</title>"))
        self.assertTrue(is_challenge_page("<div id='cf-turnstile'>verify you are human</div>"))
        self.assertFalse(is_challenge_page(EMLAKJET_HTML))

    def test_explicit_sale_detection_is_defensive(self) -> None:
        self.assertTrue(is_explicitly_sale_listing("Satılık daire", ""))
        self.assertTrue(is_explicitly_sale_listing("", "/ilan/satilik-daire-123"))
        self.assertFalse(is_explicitly_sale_listing("Kiralık daire", "/ilan/kiralik-daire-123"))

    def test_csv_sink_deduplicates_ids_within_and_across_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rentals.csv"
            sink = CsvSink(path)
            self.assertEqual(sink.write([{"ilanId": "1"}, {"ilanId": "1"}]), 1)
            self.assertEqual(sink.write([{"ilanId": "1"}, {"ilanId": "2"}]), 1)
            self.assertEqual(path.read_text(encoding="utf-8").count("\n"), 3)

    def test_emlakjet_parser_uses_listing_id_and_rejects_sale_cards(self) -> None:
        rows = parse_emlakjet_page(
            EMLAKJET_HTML,
            collected_at="2026-08-17T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ilanId"], "19733335")
        self.assertEqual(rows[0]["Province"], "İzmir")
        self.assertEqual(rows[0]["District"], "Konak")
        self.assertEqual(rows[0]["Rooms"], "3+1")
        self.assertEqual(rows[0]["AreaM2"], 98)
        self.assertEqual(rows[0]["Price"], "32.000 TL")
        self.assertNotIn("Source", rows[0])
        self.assertEqual(rows[0]["ListingDate"], "2026-08-16")
        self.assertEqual(set(rows[0]), set(OUTPUT_FIELDS))
        self.assertNotIn("Advertiser", rows[0])

    def test_emlakjet_count_and_allowed_page_url(self) -> None:
        self.assertEqual(extract_result_count(EMLAKJET_HTML), 41279)
        self.assertEqual(
            build_emlakjet_page_url("https://www.emlakjet.com/kiralik-konut", 2),
            "https://www.emlakjet.com/kiralik-konut?sayfa=2",
        )
        self.assertEqual(
            build_emlakjet_page_url("https://www.emlakjet.com/kiralik-konut?sayfa=2", 1),
            "https://www.emlakjet.com/kiralik-konut",
        )

    def test_emlakjet_discovers_provinces_and_child_scopes_without_detail_pages(self) -> None:
        province_html = """
        <a href="/kiralik-konut/istanbul">İstanbul Kiralık Ev</a>
        <a href="/kiralik-konut/ankara">Ankara Kiralık Ev</a>
        <a href="/kiralik-konut/tokat">Tokat</a>
        <a href="/kiralik-konut/emlakcidan">Emlak Ofisinden</a>
        <a href="/kiralik-konut/kiralik-daire">Daire</a>
        """
        self.assertEqual(
            discover_province_urls(province_html),
            {
                "https://www.emlakjet.com/kiralik-konut/ankara",
                "https://www.emlakjet.com/kiralik-konut/istanbul",
                "https://www.emlakjet.com/kiralik-konut/tokat",
            },
        )

        child_html = """
        <a href="/kiralik-konut/istanbul-kadikoy">İstanbul Kadıköy Kiralık Ev</a>
        <a href="/kiralik-konut/istanbul-kadikoy-bostanci-mahallesi">Bostancı Mahallesi kiralık ev</a>
        <a href="/kiralik-konut/istanbul-eyupsultan">Eyüpsultan</a>
        <a href="/kiralik-konut/ankara-cankaya">Ankara Çankaya Kiralık Ev</a>
        """
        self.assertEqual(
            discover_child_scope_urls(
                child_html,
                "https://www.emlakjet.com/kiralik-konut/istanbul",
            ),
            {
                "https://www.emlakjet.com/kiralik-konut/istanbul-kadikoy",
                "https://www.emlakjet.com/kiralik-konut/istanbul-kadikoy-bostanci-mahallesi",
                "https://www.emlakjet.com/kiralik-konut/istanbul-eyupsultan",
            },
        )


if __name__ == "__main__":
    unittest.main()
