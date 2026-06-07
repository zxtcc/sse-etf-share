import unittest
from unittest.mock import Mock

from sse_client import SseEtfClient, validate_code, validate_date


class SseEtfClientTest(unittest.TestCase):
    def test_validate_code_requires_six_digits(self):
        self.assertEqual(validate_code("510050"), "510050")
        with self.assertRaises(ValueError):
            validate_code("5100")

    def test_validate_date_requires_standard_format(self):
        self.assertEqual(validate_date("2025-09-04"), "2025-09-04")
        with self.assertRaises(ValueError):
            validate_date("20250904")

    def test_fetch_share_matches_code_and_converts_unit(self):
        client = SseEtfClient()

        first = Mock()
        first.raise_for_status.return_value = None
        first.json.return_value = {
            "result": [
                {
                    "STAT_DATE": "2025-09-04",
                    "SEC_CODE": "510050",
                    "SEC_NAME": "50ETF",
                    "ETF_TYPE": "单市",
                    "TOT_VOL": "5833506.68",
                }
            ]
        }

        second = Mock()
        second.raise_for_status.return_value = None
        second.json.return_value = {"result": [["510050", "上证50ETF华夏"]]}

        client.session.get = Mock(side_effect=[first, second])

        result = client.fetch_share("510050", "2025-09-04")

        self.assertEqual(result.name, "上证50ETF华夏")
        self.assertEqual(result.total_volume_10k, "5833506.68")
        self.assertEqual(result.total_volume_shares, 58335066800)

    def test_fetch_share_returns_none_when_code_not_found(self):
        client = SseEtfClient()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"result": []}
        client.session.get = Mock(return_value=response)

        self.assertIsNone(client.fetch_share("510050", "2025-09-04"))

    def test_fetch_all_shares_reads_multiple_pages(self):
        client = SseEtfClient()

        first = Mock()
        first.raise_for_status.return_value = None
        first.json.return_value = {
            "pageHelp": {"pageCount": 2},
            "result": [
                {
                    "STAT_DATE": "2025-09-04",
                    "SEC_CODE": "510050",
                    "SEC_NAME": "50ETF",
                    "ETF_TYPE": "单市",
                    "TOT_VOL": "1",
                }
            ],
        }

        second = Mock()
        second.raise_for_status.return_value = None
        second.json.return_value = {
            "pageHelp": {"pageCount": 2},
            "result": [
                {
                    "STAT_DATE": "2025-09-04",
                    "SEC_CODE": "510300",
                    "SEC_NAME": "300ETF",
                    "ETF_TYPE": "跨市",
                    "TOT_VOL": "2.5",
                }
            ],
        }

        client.session.get = Mock(side_effect=[first, second])

        result = client.fetch_all_shares_for_date("2025-09-04")

        self.assertEqual([share.code for share in result], ["510050", "510300"])
        self.assertEqual(result[1].total_volume_shares, 25000)


if __name__ == "__main__":
    unittest.main()
