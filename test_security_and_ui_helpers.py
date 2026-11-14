from __future__ import annotations

from pathlib import Path

from usage_widget.music_lookup import OnlineMusicVerifier
from usage_widget.ui_helpers import low_info_web_hint, online_feature_state, short_activity_hint


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def main() -> None:
    source = Path("usage_widget/music_lookup.py").read_text(encoding="utf-8")
    leaked_key_fragments = ("2c5389f9", "2935c2ef", "b944a3d3")
    check("No provider key is hardcoded", not any(fragment in source for fragment in leaked_key_fragments))
    check("Dead Last.fm branch removed", "lastfm" not in source.lower())
    check("Music verification needs no api key", "api_key" not in source)

    verifier = OnlineMusicVerifier(min_interval=0.0)
    check("Verifier constructs without external key", verifier.last_source == "")

    check("Unknown web page gets domain hint", low_info_web_hint("example.com", "zzz", "网站") == "网页 · example.com")
    check("Unknown title gets fallback hint", low_info_web_hint("", "Untitled random window", "其他").startswith("未识别网页"))
    check("Specific category suppresses generic web hint", low_info_web_hint("python.org", "Python", "编程") == "")
    check("Short activity helper still detects typing", short_activity_hint(domain="dazidazi.com", title="practice") == "打字")
    check("Private mode state text", "隐私模式" in online_feature_state(True, True))

    print("all security and ui helper tests passed")


if __name__ == "__main__":
    main()
