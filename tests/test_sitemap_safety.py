import gzip
import unittest
from unittest.mock import patch

from training import crawl_web


class SitemapSafetyTests(unittest.TestCase):
    def test_parses_plain_sitemap_and_filters_cross_origin_locations(self):
        body = (
            b"<urlset><url><loc>https://docs.example.org/a</loc></url>"
            b"<url><loc>https://other.example.org/b</loc></url></urlset>"
        )
        pages, nested = crawl_web._sitemap_locations(
            body,
            "https://docs.example.org/sitemap.xml",
            "https://docs.example.org/sitemap.xml",
            10,
        )
        self.assertEqual(pages, ["https://docs.example.org/a"])
        self.assertEqual(nested, [])

    def test_parses_gzip_sitemap_with_same_bounded_path(self):
        body = gzip.compress(
            b"<urlset><url><loc>https://docs.example.org/a</loc></url></urlset>"
        )
        pages, nested = crawl_web._sitemap_locations(
            body,
            "https://docs.example.org/sitemap.xml.gz",
            "https://docs.example.org/sitemap.xml.gz",
            10,
        )
        self.assertEqual(pages, ["https://docs.example.org/a"])
        self.assertEqual(nested, [])

    def test_sitemap_index_separates_nested_maps(self):
        body = (
            b"<sitemapindex><sitemap>"
            b"<loc>https://docs.example.org/nested.xml</loc>"
            b"</sitemap></sitemapindex>"
        )
        pages, nested = crawl_web._sitemap_locations(
            body,
            "https://docs.example.org/sitemap.xml",
            "https://docs.example.org/sitemap.xml",
            10,
        )
        self.assertEqual(pages, [])
        self.assertEqual(nested, ["https://docs.example.org/nested.xml"])

    def test_gzip_expansion_is_bounded(self):
        body = gzip.compress(b"x" * 129)
        with patch.object(crawl_web, "MAX_SITEMAP_EXPANDED_BYTES", 128):
            with self.assertRaises(crawl_web.SitemapLimitError):
                crawl_web._read_sitemap_payload(
                    body, "https://docs.example.org/sitemap.xml.gz"
                )

    def test_gzip_compression_ratio_is_bounded(self):
        body = gzip.compress(b"x" * 2000)
        with (
            patch.object(crawl_web, "MAX_SITEMAP_EXPANDED_BYTES", 10_000),
            patch.object(crawl_web, "MAX_SITEMAP_COMPRESSION_RATIO", 2),
        ):
            with self.assertRaises(crawl_web.SitemapLimitError):
                crawl_web._read_sitemap_payload(
                    body, "https://docs.example.org/sitemap.xml.gz"
                )

    def test_xml_nesting_and_element_count_are_bounded(self):
        body = (
            b"<urlset><url><loc>https://docs.example.org/a</loc>"
            b"</url></urlset>"
        )
        with patch.object(crawl_web, "MAX_SITEMAP_DEPTH", 2):
            with self.assertRaises(crawl_web.SitemapLimitError):
                crawl_web._sitemap_locations(
                    body,
                    "https://docs.example.org/sitemap.xml",
                    "https://docs.example.org/sitemap.xml",
                    10,
                )
        with patch.object(crawl_web, "MAX_SITEMAP_ELEMENTS", 2):
            with self.assertRaises(crawl_web.SitemapLimitError):
                crawl_web._sitemap_locations(
                    body,
                    "https://docs.example.org/sitemap.xml",
                    "https://docs.example.org/sitemap.xml",
                    10,
                )


if __name__ == "__main__":
    unittest.main()
