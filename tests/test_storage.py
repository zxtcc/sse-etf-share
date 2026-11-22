import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import storage
from sse_client import EtfShare


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_data_dir = storage.DATA_DIR
        self.old_status_file = storage.STATUS_FILE
        storage.DATA_DIR = Path(self.tmpdir.name)
        storage.STATUS_FILE = storage.DATA_DIR / "_update_status.json"

    def tearDown(self):
        storage.DATA_DIR = self.old_data_dir
        storage.STATUS_FILE = self.old_status_file
        self.tmpdir.cleanup()

    def test_save_and_load_share(self):
        share = EtfShare(
            stat_date="2025-09-04",
            code="510050",
            name="上证50ETF华夏",
            short_name="50ETF",
            etf_type="单市",
            total_volume_10k="5833506.68",
            total_volume_shares=58335066800,
        )

        storage.save_shares([share])
        loaded = storage.load_share("510050", "2025-09-04")

        self.assertEqual(loaded.code, "510050")
        self.assertEqual(loaded.total_volume_10k, "5833506.68")
        self.assertTrue((storage.DATA_DIR / "510050.xlsx").exists())

    def test_fund_catalog_uses_index_and_keeps_latest_name(self):
        share = EtfShare("2025-09-04", "510050", "50ETF", "50ETF", "单市", "1", 10000)
        storage.save_shares([share])
        storage.save_shares([replace(share, stat_date="2025-09-05", name="上证50ETF")])
        storage.save_shares([share])

        with patch.object(storage, "load_workbook", side_effect=AssertionError("opened Excel")):
            self.assertEqual(
                storage.local_funds(storage.local_codes()),
                [{"code": "510050", "name": "上证50ETF"}],
            )

    def test_mark_date_fully_updated(self):
        self.assertFalse(storage.is_date_fully_updated("2025-09-04"))
        storage.mark_date_fully_updated("2025-09-04", 715)
        self.assertTrue(storage.is_date_fully_updated("2025-09-04"))


if __name__ == "__main__":
    unittest.main()
