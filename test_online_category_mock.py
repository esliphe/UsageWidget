from __future__ import annotations

import sys

sys.path.insert(0, ".")

from usage_widget.online_category import OnlineCategoryClassifier


class FakeOnlineCategoryClassifier(OnlineCategoryClassifier):
    def __init__(self, mode: str) -> None:
        super().__init__(min_interval=0.0)
        self.mode = mode

    def _fetch_text(self, url: str) -> str:
        if self.mode == "site-meta":
            return """
            <html>
              <head>
                <title>在线打字练习 - 打字速度 WPM 测试</title>
                <meta name="description" content="键盘打字练习，测试 words per minute">
              </head>
            </html>
            """
        if self.mode == "baidu":
            return """
            <html>
              <title>未知专题 搜索结果</title>
              <div class="c-abstract">Python 编程 教程 SQLite 查询优化</div>
            </html>
            """
        raise OSError("network blocked for test")

    def _fetch_json(self, url: str) -> dict:
        if self.mode == "duckduckgo":
            return {
                "Heading": "Python tutorial",
                "AbstractText": "Python programming tutorial and documentation",
                "RelatedTopics": [],
            }
        raise OSError("network blocked for test")


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def main() -> None:
    site = FakeOnlineCategoryClassifier("site-meta")
    result = site.lookup_sync("browser", "dazidazi.example", "未知网页")
    check("site metadata classifies typing site", result.category == "工具", repr(result))
    check("site metadata source is visible", result.source == "site-meta", repr(result))

    ddg = FakeOnlineCategoryClassifier("duckduckgo")
    result = ddg.lookup_sync("browser", "", "unidentified alpha page")
    check("duckduckgo json summary can classify", result.category in {"编程", "学习"}, repr(result))

    baidu = FakeOnlineCategoryClassifier("baidu")
    result = baidu.lookup_sync("browser", "", "未知专题")
    check("baidu html summary can classify", result.category in {"编程", "学习"}, repr(result))

    blocked = FakeOnlineCategoryClassifier("blocked")
    result = blocked.lookup_sync("browser", "mystery.example", "zzzzzz")
    check("blocked network falls back to other", result.category == "其他" and result.source == "multi", repr(result))
    check("blocked provider errors are retained", bool(blocked.last_error or blocked.last_provider_errors), "missing provider error")

    print("all online category mock tests passed")


if __name__ == "__main__":
    main()
