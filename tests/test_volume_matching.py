import sys
import types
import unittest


if "webview" not in sys.modules:
    webview = types.ModuleType("webview")
    webview.create_window = lambda *args, **kwargs: None
    webview.start = lambda *args, **kwargs: None
    webview.FOLDER_DIALOG = object()

    class _FileDialog:
        FOLDER = object()

    webview.FileDialog = _FileDialog
    sys.modules["webview"] = webview

if "playwright" not in sys.modules:
    playwright = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: None
    playwright.sync_api = sync_api
    sys.modules["playwright"] = playwright
    sys.modules["playwright.sync_api"] = sync_api

from app.main_webview import Api


class ChapterVolumeMatchingTest(unittest.TestCase):
    def setUp(self):
        self.remote_catalog = {
            "book_name": "测试书",
            "volume_items": [
                {"volume_id": "v1", "volume_name": "第一卷"},
                {"volume_id": "v2", "volume_name": "第二卷"},
            ],
            "chapters": [
                {
                    "item_id": "1",
                    "chapter_num": "1",
                    "chapter_title": "开篇",
                    "status": "已发布",
                    "volume_id": "v1",
                    "volume_name": "第一卷",
                }
            ],
        }
        self.local_chapters = [
            {
                "chapter_num": "1",
                "chapter_title": "开篇",
                "filename": "第001章_开篇.md",
            }
        ]

    def test_second_volume_does_not_match_first_volume_chapter(self):
        summary = Api._build_chapter_match_summary(
            "本地书",
            "测试书",
            self.local_chapters,
            self.remote_catalog,
            "第二卷",
        )
        rows = Api._build_chapter_diff_rows(self.local_chapters, self.remote_catalog, "第二卷")

        self.assertEqual(summary["remote_total"], 0)
        self.assertEqual(summary["matched_total"], 0)
        self.assertEqual(summary["pending_total"], 1)
        self.assertEqual(rows[0]["diff_status"], "uploadable")

    def test_first_volume_still_matches(self):
        summary = Api._build_chapter_match_summary(
            "本地书",
            "测试书",
            self.local_chapters,
            self.remote_catalog,
            "第一卷",
        )
        rows = Api._build_chapter_diff_rows(self.local_chapters, self.remote_catalog, "第一卷")

        self.assertEqual(summary["remote_total"], 1)
        self.assertEqual(summary["matched_total"], 1)
        self.assertEqual(summary["pending_total"], 0)
        self.assertEqual(rows[0]["diff_status"], "matched")
        self.assertEqual(rows[0]["remote_volume_name"], "第一卷")


if __name__ == "__main__":
    unittest.main()
