import unittest

from app import app


class ExchangePagesTest(unittest.TestCase):
    def test_exchange_pages_have_one_header_and_distinct_content(self):
        client = app.test_client()
        pages = (
            ("/", "上海证券交易所", 'id="fundCatalogHeading"'),
            ("/szse/", "深圳证券交易所", '"/szse/api/backfill_stream"'),
        )
        for path, exchange, page_content in pages:
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertEqual(html.count("<h1>"), 1)
                self.assertEqual(html.count('<nav class="exchange-nav"'), 1)
                self.assertIn(exchange, html)
                self.assertIn(page_content, html)
                self.assertIn('href="/"', html)
                self.assertIn('href="/szse/"', html)
                self.assertIn(f'href="{path}" aria-current="page"', html)
                self.assertNotIn("<<<<<<<", html)

        css = client.get("/static/exchange-nav.css")
        self.addCleanup(css.close)
        self.assertEqual(css.status_code, 200)
        self.assertNotIn("<<<<<<<", css.get_data(as_text=True))
