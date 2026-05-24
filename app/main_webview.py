import os
import glob
import time
import re
import threading
import sys
import json
from html import escape
from pathlib import Path
from email.utils import parsedate_to_datetime
import webview
from app.paths import CONFIG_FILE, DATA_DIR, STATE_FILE, WEB_DIR, configure_runtime_environment

configure_runtime_environment()

from playwright.sync_api import sync_playwright
BOOK_MANAGE_URL = "https://fanqienovel.com/main/writer/book-manage"

PAGE_CONTEXT_PUBLISH_JS = r"""
async ({ bookId, volumeId, volumeName, title, htmlContent }) => {
  const postForm = async (url, form) => {
    const resp = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
      },
      body: new URLSearchParams(form).toString(),
    });

    const text = await resp.text();
    let jsonData = null;
    try {
      jsonData = text ? JSON.parse(text) : null;
    } catch (e) {
      jsonData = null;
    }

    return {
      status: resp.status,
      text,
      json: jsonData,
      headers: Object.fromEntries(resp.headers.entries()),
    };
  };

  const newArticle = await postForm('/api/author/article/new_article/v0/', {
    aid: '2503',
    app_name: 'muye_novel',
    book_id: String(bookId),
    need_reuse: '1',
  });

  if (newArticle.status !== 200 || !newArticle.json || newArticle.json.code !== 0) {
    return { step: 'new_article', result: newArticle };
  }

  const itemId = newArticle.json.data.item_id;

  const preAudit = await postForm('/app/book/pre_audit_article/v0/', {
    aid: '2503',
    app_name: 'muye_novel',
    item_id: String(itemId),
    content: htmlContent,
    pre_audit_type: '1',
  });

  if (preAudit.status !== 200 || !preAudit.json || preAudit.json.code !== 0) {
    return {
      step: 'pre_audit_article',
      item_id: itemId,
      new_article: newArticle,
      result: preAudit,
    };
  }

  const publish = await postForm('/api/author/publish_article/v0/', {
    aid: '2503',
    app_name: 'muye_novel',
    item_id: String(itemId),
    book_id: String(bookId),
    content: htmlContent,
    timer_status: '0',
    need_pay: '0',
    volume_name: volumeName,
    volume_id: String(volumeId),
    title,
    timer_time: '',
    publish_status: '1',
    device_platform: 'pc',
    speak_type: '0',
    use_ai: '2',
    timer_chapter_preview: '[]',
    has_chapter_ad: 'false',
    chapter_ad_types: '',
  });

  return {
    step: 'done',
    item_id: itemId,
    new_article: newArticle,
    pre_audit: preAudit,
    publish,
  };
}
"""

class Api:
    def __init__(self):
        self.window = None
        self.config = self.load_config()
        self.login_status = {"state": "idle", "message": ""}
        self.login_window = None

    @staticmethod
    def _chapter_patterns():
        return ("*.txt", "*.md")

    @classmethod
    def _list_chapter_files(cls, directory):
        chapter_files = []
        for pattern in cls._chapter_patterns():
            chapter_files.extend(glob.glob(os.path.join(directory, pattern)))
        return sorted(chapter_files, key=cls._chapter_file_sort_key)

    @classmethod
    def _count_book_chapter_files(cls, book_dir):
        direct_files = cls._list_chapter_files(book_dir)
        if direct_files:
            return len(direct_files)

        total = 0
        for name in sorted(os.listdir(book_dir)):
            sub_path = os.path.join(book_dir, name)
            if os.path.isdir(sub_path):
                total += len(cls._list_chapter_files(sub_path))
        return total

    def _resolve_local_book_dir(self, local_book_name):
        source_dir = self.config.get('source_dir')
        if not source_dir:
            raise RuntimeError("未设置草稿目录。")

        sub_path = os.path.join(source_dir, local_book_name)
        if os.path.isdir(sub_path):
            return sub_path
        return source_dir

    @staticmethod
    def _normalize_heading_line(line):
        if not line:
            return ""
        return re.sub(r'^\s*#+\s*', '', line).strip()

    @staticmethod
    def _normalize_chapter_num(value):
        text = str(value or "").strip()
        if not text:
            return ""
        digits_match = re.search(r'\d+', text)
        if digits_match:
            return str(int(digits_match.group(0)))
        return text

    @staticmethod
    def _select_latest_row_ids(rows, count):
        try:
            count = int(count)
        except Exception:
            return []

        if count <= 0:
            return []

        eligible = []
        for row in rows:
            diff_status = row.get("diff_status")
            if diff_status != "uploadable":
                continue
            chapter_num = Api._normalize_chapter_num(row.get("chapter_num", ""))
            if not chapter_num:
                continue
            eligible.append((int(chapter_num), row.get("row_id")))

        eligible.sort(key=lambda item: item[0])
        return [row_id for _, row_id in eligible[:count] if row_id]

    @staticmethod
    def _normalize_remote_books(book_names):
        normalized = []
        seen = set()
        for name in book_names:
            cleaned = (name or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append({"name": cleaned})
        return normalized

    @staticmethod
    def _normalize_remote_books_from_api(payload):
        result = []
        for book in payload.get("data", {}).get("book_list", []):
            name = str(book.get("book_name", "")).strip()
            book_id = str(book.get("book_id", "")).strip()
            if not name or not book_id:
                continue
            result.append({
                "name": name,
                "book_id": book_id,
                "chapter_count": int(book.get("chapter_number", 0) or 0),
                "last_chapter_title": str(book.get("last_chapter_title", "")).strip(),
            })
        return result

    @staticmethod
    def _normalize_remote_volumes_from_api(payload):
        result = []
        for volume in payload.get("data", {}).get("volume_list", []):
            volume_id = str(volume.get("volume_id", "")).strip()
            volume_name = str(volume.get("volume_name", "")).strip()
            if not volume_id or not volume_name:
                continue
            result.append({
                "volume_id": volume_id,
                "volume_name": volume_name,
                "item_count": int(volume.get("item_count", 0) or 0),
            })
        return result

    @staticmethod
    def _normalize_remote_chapters_from_api(payload):
        chapters = []
        for item in payload.get("data", {}).get("item_list", []):
            raw_title = str(item.get("title", "")).strip()
            match = re.search(r'第\s*(\d+)\s*章[\s：:·_-]*(.*)', raw_title)
            chapter_num = match.group(1).strip() if match else str(item.get("index", "")).strip()
            chapter_title = match.group(2).strip() if match else raw_title

            article_status = int(item.get("article_status", -1))
            if article_status == 1:
                status = "已发布"
            elif article_status == 0:
                status = "草稿"
            else:
                status = str(article_status)

            chapters.append({
                "item_id": str(item.get("item_id", "")).strip(),
                "chapter_num": chapter_num,
                "chapter_title": chapter_title,
                "status": status,
            })
        return chapters

    @staticmethod
    def _infer_local_book_name(source_dir):
        current_name = os.path.basename(os.path.normpath(source_dir))
        parent_dir = os.path.dirname(os.path.normpath(source_dir))
        parent_name = os.path.basename(parent_dir) if parent_dir else ""
        generic_names = {"正文", "chapters", "chapter", "drafts", "稿件", "章节"}
        if current_name in generic_names and parent_name:
            return parent_name
        return current_name

    @staticmethod
    def _dedupe_preserve_order(values):
        result = []
        seen = set()
        for value in values:
            cleaned = (value or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
        return result

    @staticmethod
    def _create_request_context(playwright):
        return playwright.request.new_context(storage_state=str(STATE_FILE))

    @staticmethod
    def _launch_browser(playwright, headless):
        try:
            return playwright.chromium.launch(headless=headless)
        except Exception as e:
            raise RuntimeError(
                "无法启动内置 Chromium。请确认已安装 Playwright Chromium，"
                "或重新使用打包脚本生成包含浏览器内核的应用。"
            ) from e

    @classmethod
    def _build_remote_catalog(cls, remote_book_name, volumes, chapters):
        normalized_chapters = []
        seen = set()
        for chapter in chapters:
            chapter_num = cls._normalize_chapter_num(chapter.get("chapter_num", ""))
            chapter_title = str(chapter.get("chapter_title", "")).strip()
            status = str(chapter.get("status", "")).strip()
            key = (chapter_num, chapter_title, status)
            if key in seen:
                continue
            seen.add(key)
            normalized_chapters.append({
                "chapter_num": chapter_num,
                "chapter_title": chapter_title,
                "status": status,
            })

        return {
            "book_name": (remote_book_name or "").strip(),
            "volumes": cls._dedupe_preserve_order(volumes),
            "chapters": normalized_chapters,
        }

    @classmethod
    def _scan_local_chapter_items(cls, chapter_dir):
        items = []
        for file_path in cls._list_chapter_files(chapter_dir):
            filename = os.path.basename(file_path)
            raw_title = os.path.splitext(filename)[0]
            chapter_num = ""
            chapter_title = ""

            match = re.search(r'第\s*(\d+)\s*章[\s_]*(.*)', raw_title)
            if match:
                chapter_num = match.group(1).strip()
                chapter_title = match.group(2).strip()

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    first_line = cls._normalize_heading_line(f.readline())
            except Exception:
                first_line = ""

            if not chapter_num and first_line:
                match_num = re.search(r'第\s*(\d+)\s*章', first_line)
                if match_num:
                    chapter_num = match_num.group(1).strip()

            if not chapter_title and first_line:
                match_title = re.search(r'第\s*\d+\s*章[\s：:]*(.*)', first_line)
                if match_title:
                    chapter_title = match_title.group(1).strip()

            items.append({
                "chapter_num": chapter_num,
                "chapter_title": chapter_title,
                "filename": filename,
            })
        return items

    @classmethod
    def _chapter_file_to_payload(cls, file_path):
        raw = Path(file_path).read_text(encoding="utf-8")
        lines = raw.splitlines()

        first_line = ""
        while lines and not first_line:
            first_line = cls._normalize_heading_line(lines[0].strip())
            if not first_line:
                lines.pop(0)

        match = re.search(r'第\s*(\d+)\s*章[\s：:·_-]*(.*)', first_line)
        if not match:
            raise RuntimeError(f"无法从第一行解析章节标题: {file_path}")

        chapter_num = cls._normalize_chapter_num(match.group(1))
        chapter_title = match.group(2).strip()

        body_lines = raw.splitlines()
        if body_lines:
            normalized_first = cls._normalize_heading_line(body_lines[0].strip())
            if re.search(r'第\s*\d+\s*章', normalized_first):
                body_lines = body_lines[1:]

        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]

        html_content = "".join(f"<p>{escape(line)}</p>" for line in body_lines if line.strip())
        if not html_content:
            raise RuntimeError(f"正文为空: {file_path}")

        return {
            "chapter_num": chapter_num,
            "title": f"第{chapter_num}章 {chapter_title}",
            "html_content": html_content,
        }

    @staticmethod
    def _build_chapter_match_summary(local_book_name, remote_book_name, local_chapters, remote_catalog):
        remote_by_num = {}
        for chapter in remote_catalog.get("chapters", []):
            chapter_num = Api._normalize_chapter_num(chapter.get("chapter_num", ""))
            if chapter_num and chapter_num not in remote_by_num:
                remote_by_num[chapter_num] = chapter

        matched_preview = []
        pending_preview = []
        title_conflicts = []
        matched_total = 0
        pending_total = 0

        for local in local_chapters:
            chapter_num = Api._normalize_chapter_num(local.get("chapter_num", ""))
            remote = remote_by_num.get(chapter_num)
            if remote:
                matched_total += 1
                if len(matched_preview) < 10:
                    matched_preview.append({
                        "chapter_num": chapter_num,
                        "local_title": local.get("chapter_title", ""),
                        "remote_title": remote.get("chapter_title", ""),
                        "remote_status": remote.get("status", ""),
                    })
                local_title = str(local.get("chapter_title", "")).strip()
                remote_title = str(remote.get("chapter_title", "")).strip()
                if local_title and remote_title and local_title != remote_title:
                    title_conflicts.append({
                        "chapter_num": chapter_num,
                        "local_title": local_title,
                        "remote_title": remote_title,
                        "remote_status": remote.get("status", ""),
                    })
            else:
                pending_total += 1
                if len(pending_preview) < 10:
                    pending_preview.append({
                        "chapter_num": chapter_num,
                        "local_title": local.get("chapter_title", ""),
                        "filename": local.get("filename", ""),
                    })

        return {
            "local_book_name": local_book_name,
            "remote_book_name": remote_book_name,
            "local_total": len(local_chapters),
            "remote_total": len(remote_catalog.get("chapters", [])),
            "matched_total": matched_total,
            "pending_total": pending_total,
            "matched_preview": matched_preview,
            "pending_preview": pending_preview,
            "title_conflicts": title_conflicts,
        }

    @staticmethod
    def _build_chapter_diff_rows(local_chapters, remote_catalog):
        remote_by_num = {}
        for chapter in remote_catalog.get("chapters", []):
            chapter_num = Api._normalize_chapter_num(chapter.get("chapter_num", ""))
            if chapter_num and chapter_num not in remote_by_num:
                remote_by_num[chapter_num] = chapter

        rows = []
        for local in local_chapters:
            chapter_num = Api._normalize_chapter_num(local.get("chapter_num", ""))
            local_title = str(local.get("chapter_title", "")).strip()
            remote = remote_by_num.get(chapter_num)
            remote_title = str(remote.get("chapter_title", "")).strip() if remote else ""
            remote_status = str(remote.get("status", "")).strip() if remote else ""

            if not remote:
                diff_status = "uploadable"
                default_selected = True
            elif local_title and remote_title and local_title != remote_title:
                diff_status = "title_conflict"
                default_selected = True
            else:
                diff_status = "matched"
                default_selected = False

            rows.append({
                "row_id": local.get("filename", chapter_num),
                "chapter_num": chapter_num,
                "local_title": local_title,
                "remote_title": remote_title,
                "remote_status": remote_status,
                "filename": local.get("filename", ""),
                "diff_status": diff_status,
                "default_selected": default_selected,
            })

        return rows

    def set_window(self, window):
        self.window = window

    def load_config(self):
        default_config = {}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with CONFIG_FILE.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception: pass
        return default_config

    def save_config(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with CONFIG_FILE.open('w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception: pass

    def get_config(self):
        return self.config

    def choose_dir(self, key='archive_dir'):
        print(f"[DEBUG] choose_dir called key={key!r} window_ready={self.window is not None}")
        if not self.window: return None
        dialog_type = getattr(webview, 'FileDialog', None)
        open_flag = dialog_type.FOLDER if dialog_type else webview.FOLDER_DIALOG
        try:
            print(f"[DEBUG] choose_dir open_flag={open_flag!r}")
            result = self.window.create_file_dialog(open_flag)
            print(f"[DEBUG] choose_dir result={result!r}")
            if isinstance(result, tuple) or isinstance(result, list):
                if result and result[0]:
                    self.config[key] = result[0]
                    self.save_config()
                    return result[0]
        except Exception as e:
            self.log(f"选择目录出错: {e}", "text-red-400")
        return None

    def log(self, msg, color="text-gray-300"):
        if self.window:
            safe_msg = msg.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            # Run evaluate_js in the UI thread context avoiding blocking
            try:
                self.window.evaluate_js(f'window.appendLog("{safe_msg}", "{color}");')
            except Exception as e:
                print("GUI Eval Error:", e)

    def _set_login_status(self, state, message=""):
        self.login_status = {"state": state, "message": message}

    def get_login_status(self):
        return self.login_status

    @staticmethod
    def _normalize_playwright_cookie(cookie):
        morsels = list(cookie.values())
        if not morsels:
            return None

        morsel = morsels[0]
        cookie_data = {
            "name": morsel.key,
            "value": morsel.value,
            "path": morsel["path"] or "/",
            "secure": bool(morsel["secure"]),
            "httpOnly": bool(morsel["httponly"]),
        }

        domain = morsel["domain"]
        if domain:
            cookie_data["domain"] = domain
        else:
            cookie_data["url"] = "https://fanqienovel.com"

        expires = morsel["expires"]
        if expires:
            try:
                cookie_data["expires"] = parsedate_to_datetime(expires).timestamp()
            except Exception:
                pass

        same_site = str(morsel["samesite"] or "").strip().lower()
        if same_site == "lax":
            cookie_data["sameSite"] = "Lax"
        elif same_site == "strict":
            cookie_data["sameSite"] = "Strict"
        elif same_site == "none":
            cookie_data["sameSite"] = "None"

        return cookie_data

    def _save_state_from_webview_cookies(self, cookies):
        playwright_cookies = []
        for cookie in cookies or []:
            normalized = self._normalize_playwright_cookie(cookie)
            if normalized:
                playwright_cookies.append(normalized)

        if not playwright_cookies:
            return False

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = self._launch_browser(p, headless=True)
            context = browser.new_context()
            context.add_cookies(playwright_cookies)

            page = context.new_page()
            page.goto("https://fanqienovel.com/main/writer/?enter_from=author_zone", timeout=60000)
            page.wait_for_timeout(2000)
            context.storage_state(path=str(STATE_FILE))

            request_context = self._create_request_context(p)
            try:
                response = request_context.get(
                    'https://fanqienovel.com/api/author/homepage/book_list/v0/?aid=2503&app_name=muye_novel&page_count=1&page_index=0&image_fmt_list=396x220'
                )
                if response.status != 200:
                    return False
                payload = response.json()
                return payload.get("code") == 0 and STATE_FILE.exists()
            finally:
                request_context.dispose()
                browser.close()

    def _update_progress(self, current, total):
        if self.window:
            try:
                self.window.evaluate_js(f"window.updateProgress({current}, {total});")
            except Exception:
                pass

    def check_login_state(self):
        """Check if login state file exists"""
        return STATE_FILE.exists()

    def _dismiss_platform_popups(self, target_page, wait_ms=200):
        """关闭平台提示弹窗，避免键盘快捷键作用到弹窗或整页。"""
        dismissed = False
        try:
            for dismiss_text in ["我知道了", "知道了", "关闭", "跳过", "完成"]:
                btn = target_page.get_by_text(dismiss_text, exact=True).first
                try:
                    btn.wait_for(state="visible", timeout=wait_ms)
                    if btn.is_visible():
                        btn.click(force=True)
                        target_page.wait_for_timeout(500)
                        dismissed = True
                except:
                    pass
        except:
            pass
        return dismissed

    @staticmethod
    def _chapter_file_sort_key(file_path):
        """按真实章节号排序，保证截取发布数量前的章节顺序正确。"""
        raw_title = os.path.splitext(os.path.basename(file_path))[0]
        # 文件名按字符串排序会把“第10章”排到“第5章”前面，这里先抽取章节数字做自然排序。
        match = re.search(r'第\s*(\d+)\s*章', raw_title)
        if not match:
            match = re.search(r'^\s*(\d+)', raw_title)
        if match:
            return (0, int(match.group(1)), raw_title.casefold())
        return (1, raw_title.casefold())

    @staticmethod
    def _volume_sort_key(name):
        match = re.search(r'第\s*(\d+)\s*卷', name)
        if match:
            return (0, int(match.group(1)), name.casefold())
        leading = re.search(r'^\s*(\d+)', name)
        if leading:
            return (0, int(leading.group(1)), name.casefold())
        return (1, name.casefold())

    def get_books(self):
        """Scan source_dir for books and chapter files."""
        books = []
        source_dir = self.config.get('source_dir')
        print(f"[DEBUG] get_books source_dir={source_dir!r}")
        if not source_dir or not os.path.isdir(source_dir):
            print("[DEBUG] get_books source_dir missing or not a directory")
            return books
        try:
            for name in sorted(os.listdir(source_dir)):
                sub_path = os.path.join(source_dir, name)
                if os.path.isdir(sub_path):
                    chapter_count = self._count_book_chapter_files(sub_path)
                    if chapter_count:
                        books.append({
                            "name": name,
                            "count": chapter_count,
                        })

            if books:
                print(f"[DEBUG] get_books found {len(books)} books")
                return books

            direct_chapter_files = self._list_chapter_files(source_dir)
            if direct_chapter_files:
                local_book_name = self._infer_local_book_name(source_dir)
                books.append({
                    "name": local_book_name,
                    "count": len(direct_chapter_files),
                })
        except Exception as e:
            print(f"[DEBUG] get_books crashed: {e}")
            raise

        print(f"[DEBUG] get_books found {len(books)} books")
        return books

    def get_local_volumes(self, local_book_name):
        book_dir = self._resolve_local_book_dir(local_book_name)

        child_dirs = []
        for name in sorted(os.listdir(book_dir), key=self._volume_sort_key):
            sub_path = os.path.join(book_dir, name)
            if os.path.isdir(sub_path) and self._list_chapter_files(sub_path):
                child_dirs.append({"name": name})

        if child_dirs:
            return child_dirs

        if self._list_chapter_files(book_dir):
            return [{"name": "默认卷"}]

        return []

    def fetch_remote_books(self):
        """Read current author's books from Fanqie writer backend."""
        if not STATE_FILE.exists():
            raise RuntimeError("未找到登录凭证，请先执行登录授权。")

        print("[DEBUG] fetch_remote_books starting")
        with sync_playwright() as p:
            request_context = self._create_request_context(p)
            try:
                response = request_context.get(
                    'https://fanqienovel.com/api/author/homepage/book_list/v0/?aid=2503&app_name=muye_novel&page_count=100&page_index=0&image_fmt_list=396x220'
                )
                if response.status != 200:
                    raise RuntimeError(f"后台书库接口失败: HTTP {response.status}")

                payload = response.json()
                normalized = self._normalize_remote_books_from_api(payload)
                self.config["remote_books"] = normalized
                self.save_config()
                return normalized
            finally:
                request_context.dispose()

    def fetch_remote_catalog(self, remote_book_name):
        """Read volumes and chapters for a specific remote book."""
        if not STATE_FILE.exists():
            raise RuntimeError("未找到登录凭证，请先执行登录授权。")

        if not remote_book_name:
            raise RuntimeError("缺少后台目标小说名。")

        print(f"[DEBUG] fetch_remote_catalog starting for {remote_book_name!r}")
        with sync_playwright() as p:
            request_context = self._create_request_context(p)
            try:
                remote_books = self.config.get("remote_books") or self.fetch_remote_books()
                target_book = next((book for book in remote_books if book.get("name") == remote_book_name), None)
                if not target_book:
                    raise RuntimeError(f"后台书库中找不到《{remote_book_name}》")

                book_id = str(target_book.get("book_id", "")).strip()
                if not book_id:
                    raise RuntimeError(f"《{remote_book_name}》缺少 book_id")

                volume_resp = request_context.get(
                    f'https://fanqienovel.com/api/author/volume/volume_list/v1?aid=2503&app_name=muye_novel&book_id={book_id}'
                )
                if volume_resp.status != 200:
                    raise RuntimeError(f"卷列表接口失败: HTTP {volume_resp.status}")
                volume_payload = volume_resp.json()
                normalized_volumes = self._normalize_remote_volumes_from_api(volume_payload)

                all_chapters = []
                for volume in normalized_volumes:
                    volume_id = volume["volume_id"]
                    chapter_resp = request_context.get(
                        f'https://fanqienovel.com/api/author/chapter/chapter_list/v1?aid=2503&app_name=muye_novel&book_id={book_id}&page_index=0&page_count=500&status=0&must_have_correction_feedback=0&need_correction_feedback_num=1&sort=&volume_id={volume_id}'
                    )
                    if chapter_resp.status != 200:
                        raise RuntimeError(f"章节列表接口失败: HTTP {chapter_resp.status}")
                    chapter_payload = chapter_resp.json()
                    all_chapters.extend(self._normalize_remote_chapters_from_api(chapter_payload))

                payload = {
                    "book_name": remote_book_name,
                    "volumes": [volume["volume_name"] for volume in normalized_volumes],
                    "chapters": all_chapters,
                    "book_id": book_id,
                    "volume_items": normalized_volumes,
                }
                self.config["remote_catalogs"] = self.config.get("remote_catalogs", {})
                self.config["remote_catalogs"][remote_book_name] = payload
                self.save_config()
                return payload
            finally:
                request_context.dispose()

    def _resolve_remote_book_and_volume(self, remote_book_name, remote_volume_name=None):
        remote_books = self.config.get("remote_books", [])
        target_book = next((book for book in remote_books if book.get("name") == remote_book_name), None)
        if not target_book:
            raise RuntimeError(f"后台书库中找不到《{remote_book_name}》")

        remote_book_id = str(target_book.get("book_id", "")).strip()
        if not remote_book_id:
            raise RuntimeError(f"《{remote_book_name}》缺少 book_id")

        remote_catalog = self.config.get("remote_catalogs", {}).get(remote_book_name, {})
        volume_items = remote_catalog.get("volume_items", []) if isinstance(remote_catalog, dict) else []

        if remote_volume_name:
            target_volume = next((vol for vol in volume_items if vol.get("volume_name") == remote_volume_name), None)
            if not target_volume:
                raise RuntimeError(f"《{remote_book_name}》中找不到分卷《{remote_volume_name}》")
        else:
            target_volume = volume_items[0] if volume_items else None

        if not target_volume:
            raise RuntimeError(f"《{remote_book_name}》缺少可用分卷信息，请先同步卷和章节")

        remote_volume_id = str(target_volume.get("volume_id", "")).strip()
        remote_volume_label = str(target_volume.get("volume_name", "")).strip()
        return remote_book_id, remote_volume_id, remote_volume_label

    def get_chapter_match_summary(self, local_book_name, remote_book_name, local_volume_name=None):
        book_dir = self._resolve_local_book_dir(local_book_name)
        chapter_dir = book_dir if not local_volume_name or local_volume_name == "默认卷" else os.path.join(book_dir, local_volume_name)
        local_chapters = self._scan_local_chapter_items(chapter_dir)

        catalogs = self.config.get("remote_catalogs", {})
        remote_catalog = catalogs.get(remote_book_name)
        if not remote_catalog:
            raise RuntimeError("后台卷和章节尚未同步，请先点击“同步卷和章节”。")

        return self._build_chapter_match_summary(
            local_book_name,
            remote_book_name,
            local_chapters,
            remote_catalog,
        )

    def get_chapter_diff_data(self, local_book_name, remote_book_name, local_volume_name=None):
        book_dir = self._resolve_local_book_dir(local_book_name)
        chapter_dir = book_dir if not local_volume_name or local_volume_name == "默认卷" else os.path.join(book_dir, local_volume_name)
        local_chapters = self._scan_local_chapter_items(chapter_dir)

        catalogs = self.config.get("remote_catalogs", {})
        remote_catalog = catalogs.get(remote_book_name)
        if not remote_catalog:
            raise RuntimeError("后台卷和章节尚未同步，请先点击“同步卷和章节”。")

        summary = self._build_chapter_match_summary(
            local_book_name,
            remote_book_name,
            local_chapters,
            remote_catalog,
        )
        rows = self._build_chapter_diff_rows(local_chapters, remote_catalog)

        return {
            "local_book_name": local_book_name,
            "local_volume_name": local_volume_name or "默认卷",
            "remote_book_name": remote_book_name,
            "remote_volumes": remote_catalog.get("volumes", []),
            "summary": summary,
            "rows": rows,
        }

    def do_login(self):
        """Launch login flow and return immediately; frontend polls status."""
        if self.login_status.get("state") == "in_progress":
            if self.login_window:
                try:
                    self.login_window.show()
                except Exception:
                    pass
            return True

        def _login_thread():
            self.log("开始登录授权流程...", "text-indigo-400 font-bold")
            self._set_login_status("in_progress", "登录浏览器已启动")
            try:
                self.login_window = webview.create_window(
                    '番茄登录',
                    'https://fanqienovel.com/main/writer/?enter_from=author_zone',
                    width=980,
                    height=760,
                    resizable=True,
                    text_select=True,
                    confirm_close=True,
                )
                self.log("【动作需求】请在内嵌登录窗口中完成扫码或密码登录！", "text-yellow-400 font-bold")

                deadline = time.time() + 600
                while time.time() < deadline:
                    if not self.login_window:
                        self._set_login_status("cancelled", "登录窗口已关闭")
                        self.log("❌ 登录流程已中止，凭证未保存。", "text-red-400")
                        return

                    try:
                        current_url = self.login_window.get_current_url() or ""
                    except Exception:
                        self._set_login_status("cancelled", "登录窗口已关闭")
                        self.log("❌ 登录流程已中止，凭证未保存。", "text-red-400")
                        self.login_window = None
                        return

                    if current_url.startswith("https://fanqienovel.com/main/writer"):
                        try:
                            cookies = self.login_window.get_cookies()
                            saved = self._save_state_from_webview_cookies(cookies)
                        except Exception as e:
                            saved = False
                            self.log(f"登录态桥接失败：{e}", "text-red-500")

                        if saved:
                            self._set_login_status("succeeded", "登录凭证已保存")
                            self.log("✅ 登录凭证已签发，写入成功！", "text-green-400 font-bold")
                            try:
                                self.login_window.destroy()
                            except Exception:
                                pass
                            self.login_window = None
                            return

                    time.sleep(1)

                self._set_login_status("failed", "登录等待超时")
                self.log("登录等待超时，请重试。", "text-red-500")
                if self.login_window:
                    try:
                        self.login_window.destroy()
                    except Exception:
                        pass
                    self.login_window = None
            except Exception as e:
                self.log(f"登录流程崩溃: {e}", "text-red-500")
                self._set_login_status("failed", str(e))
                if self.login_window:
                    try:
                        self.login_window.destroy()
                    except Exception:
                        pass
                    self.login_window = None

        self._set_login_status("in_progress", "准备启动登录浏览器")
        th = threading.Thread(target=_login_thread, daemon=True)
        th.start()
        return True


    def open_source_folder(self):
        """Open the source drafts folder in Windows File Explorer"""
        try:
            print("[DEBUG] open_source_folder called")
            target_dir = self.config.get('source_dir')
            if not target_dir:
                self.log("没有配置待发草稿目录！", "text-red-400")
                return
            os.makedirs(target_dir, exist_ok=True)
            print(f"[DEBUG] open_source_folder target_dir={target_dir!r}")
            if sys.platform == "win32":
                os.startfile(target_dir)
            elif sys.platform == "darwin":
                os.system(f'open "{target_dir}"')
            else:
                os.system(f'xdg-open "{target_dir}"')
            self.log(f"已为您打开本地草稿来源目录：{target_dir}", "text-green-300")
        except Exception as e:
            print(f"[DEBUG] open_source_folder failed: {e}")
            self.log(f"打开源码目录失败: {e}", "text-red-500")

    def start_publish(self, local_book_name, remote_book_name, publish_count, volume_num, remote_volume_name=None, selected_filenames=None, local_volume_name=None):
        """Start publish process in thread, wait to finish"""
        def _publish_thread():
            self.log(f"\n==================================================", "text-indigo-400")
            self.log(f"开始上传，本地稿件：{local_book_name}", "text-pink-400 font-bold")
            self.log(f"后台目标小说：{remote_book_name}", "text-cyan-400 font-bold")
            
            self.log(" -> 解析本地书籍目录...", "text-gray-400")
            chapter_dir = self._resolve_local_book_dir(local_book_name)
            if local_volume_name and local_volume_name != "默认卷":
                chapter_dir = os.path.join(chapter_dir, local_volume_name)
            self.log(f" -> 本地章节目录：{chapter_dir}", "text-gray-400")

            self.log(" -> 解析远端 book_id / volume_id ...", "text-gray-400")
            remote_book_id, remote_volume_id, remote_volume_label = self._resolve_remote_book_and_volume(
                remote_book_name, remote_volume_name
            )
            self.log(f" -> 远端解析成功：book_id={remote_book_id}, volume_id={remote_volume_id}", "text-gray-400")

            txts = self._list_chapter_files(chapter_dir)
            if selected_filenames:
                selected_set = {str(name) for name in selected_filenames}
                txts = [path for path in txts if os.path.basename(path) in selected_set]
            if publish_count is not None and publish_count > 0:
                txts = txts[:publish_count]
            queue_preview = " -> ".join(os.path.splitext(os.path.basename(path))[0] for path in txts[:10])
            if queue_preview:
                self.log(f"本次队列预览：{queue_preview}", "text-blue-300")
                
            self.log(f"本次爆更总发射目标数：{len(txts)} 章", "text-gray-300 font-bold")
            
            # Volume name
            volume_name = None
            if remote_volume_name:
                volume_name = remote_volume_name.strip()
                self.log(f"归档卷锚定于：【{volume_name}】", "text-blue-300")
            elif volume_num is not None and volume_num > 0:
                cn_digits = "一二三四五六七八九十"
                volume_name = f"第{cn_digits[volume_num - 1] if volume_num <= 10 else str(volume_num)}卷"
                self.log(f"归档卷锚定于：【{volume_name}】", "text-blue-300")
                
            self.log(f"==================================================\n", "text-indigo-400")
            
            try:
                with sync_playwright() as p:
                    self.log(" -> 启动静默浏览器上下文...", "text-gray-400")
                    browser = self._launch_browser(p, headless=True)
                    context = browser.new_context(storage_state=str(STATE_FILE))
                    page = context.new_page()
                    self.log(" -> 打开作者后台主页...", "text-gray-400")
                    page.goto(BOOK_MANAGE_URL, timeout=60000)
                    page.wait_for_timeout(3000)
                    
                    success_count = 0
                    total_target = len(txts)
                    self._update_progress(success_count, total_target)
                    
                    for i, file_path in enumerate(txts):
                        filename = os.path.basename(file_path)
                        payload = self._chapter_file_to_payload(file_path)
                        chapter_num = payload["chapter_num"]
                        chapter_title = payload["title"]
                        self.log(f"\n[{i+1}/{len(txts)}] 正在上膛: '{chapter_title}'", "text-yellow-200")
                        
                        try:
                            self.log(" -> 走页内上下文接口上传链路...", "text-sky-400")
                            result = page.evaluate(
                                PAGE_CONTEXT_PUBLISH_JS,
                                {
                                    "bookId": remote_book_id,
                                    "volumeId": remote_volume_id,
                                    "volumeName": remote_volume_label,
                                    "title": payload["title"],
                                    "htmlContent": payload["html_content"],
                                },
                            )

                            self.log(f" -> 页内接口返回 step={result.get('step')}", "text-gray-400")
                            if result.get("step") != "done":
                                raise RuntimeError(json.dumps(result, ensure_ascii=False))

                            self.log(f"  [成功] '{chapter_title}' 已上传", "text-green-400 font-bold")
                            success_count += 1
                            self._update_progress(success_count, total_target)
                                
                        except Exception as e:
                            self.log(f"!!! 处理 '第{chapter_num}章' 时发生毁灭性崩溃: {e}", "text-red-600 font-bold")
                            result = self.window.create_confirmation_dialog('上传异常', f'发生错误: {e}\n是否继续上传下一章？')
                            if not result:
                                break
                            
                        page.wait_for_timeout(1000)
                        
                    self.log(f"\n==========================================", "text-indigo-400 font-bold")
                    self.log(f"本次上传完成，共成功上传 {success_count} 章。", "text-green-400 font-bold text-lg")
                    self.log(f"==========================================\n", "text-indigo-400 font-bold")
                    browser.close()
            except Exception as e:
                self.log(f"执行主控程序彻底崩溃：{e}", "text-red-700 bg-red-100 p-2 rounded")

        # run in thread
        th = threading.Thread(target=_publish_thread, daemon=True)
        th.start()
        th.join() # blocks JS await until finished
        return True

def main():
    api = Api()

    html_path = WEB_DIR.joinpath('index.html').resolve().as_uri()

    window = webview.create_window(
        '番茄发文助手 PRO', 
        html_path, 
        js_api=api,
        width=1100, 
        height=770,
        min_size=(700, 500),
        frameless=False,      # Can be True for completely custom window bar
        text_select=True
    )
    api.set_window(window)
    webview.start()


if __name__ == '__main__':
    main()
