"""End-to-end verification of learning video detection pipeline."""
import sys
sys.path.insert(0, ".")

from usage_widget.storage import Storage
from usage_widget.monitor import ProcessMonitor
from usage_widget.learning import (
    has_learning_intent, local_learning_topic, should_mark_learning,
    normalize_text, LEARNING_INTENT_HINTS,
)

s = Storage()
m = ProcessMonitor(s)
settings = s.load_settings()
errors = []

def check(name, actual, expected=None):
    ok = actual == expected if expected is not None else bool(actual)
    status = "OK" if ok else "FAIL"
    if not ok:
        errors.append((name, actual, expected))
    print(f"  [{status}] {name}")

print("=== 1. Learning intent on bare subject names ===")
subjects = [
    "大学物理", "高等数学", "线性代数", "微积分", "C语言",
    "Python", "数据结构", "单片机", "光学", "概率论",
]
for subj in subjects:
    check(f"has_learning_intent('{subj}')", has_learning_intent("", subj, "video_playback"))

print("\n=== 2. Learning intent on B站-style titles ===")
titles = [
    ("【完整版】《大学物理-光学》1.5小时快速突击|期末不挂科必备 蜂考", True),
    ("高等数学 同济七版 全程精讲", True),
    ("线性代数 2小时速成 猴博士", True),
    ("【原神】4.0新角色实况", False),
    ("搞笑合集 笑到肚子疼", False),
]
for title, expected in titles:
    check(f"'{title[:40]}...'", has_learning_intent("", normalize_text(title), "video_playback"), expected)

print("\n=== 3. local_learning_topic on video titles ===")
topic_tests = [
    ("大学物理-光学 蜂考", "物理"),
    ("高等数学 同济版 全程精讲", "高等数学"),
    ("C语言 谭浩强 从入门到精通", "C 语言"),
    ("Python教程 零基础入门", "Python"),
    ("原神 4.0版本 实况", ""),
]
for title, expected_topic in topic_tests:
    r = local_learning_topic(normalize_text(title))
    ok = (r.topic == expected_topic) or (expected_topic == "" and not r.topic)
    check(f"topic for '{title[:35]}' -> {r.topic}", ok)

print("\n=== 4. should_mark_learning for video_playback ===")
for title, topic, expected in [
    ("大学物理-光学", "物理", True),
    ("高等数学 精讲", "高等数学", True),
    ("原神 实况", "游戏", False),
    ("", "物理", True),  # video_playback + any topic not in {音乐,游戏} = True
]:
    r = should_mark_learning("视频", topic, "bilibili.com", normalize_text(title), "video_playback")
    check(f"should_mark('{title[:20]}', {topic})", r, expected)

print("\n=== 5. _category_for SMTC path (no domain, no extension) ===")
cat_tests = [
    ("大学物理-光学 蜂考 期末突击", "学习"),
    ("高等数学 同济版 全程精讲 猴博士", "学习"),
    ("【原神】新角色实况", "游戏"),
    ("搞笑视频合集", "娱乐"),
    ("手机开箱测评 好物推荐", "购物"),
    ("今日热点 新闻资讯", "新闻"),
]
for title, expected_cat in cat_tests:
    cat = m._category_for("browser", "", title, settings)
    check(f"category_for '{title[:30]}' -> {cat}", cat == expected_cat)

print("\n=== 6. Full pipeline simulation (SMTC video_playback) ===")
smtic_titles = [
    "大学物理-光学 蜂考",
    "高等数学 全程精讲 宋浩",
    "【原神】4.0新角色实况",
]
for title in smtic_titles:
    cat = m._category_for("browser", "", title, settings)
    topic = m._learning_topic_for(cat, "", title, "", "video_playback", settings)
    final_cat = m._learning_category_for(cat, topic, "", title, "video_playback")
    print(f"  '{title[:35]}': cat={cat} -> topic={topic!r} -> final_cat={final_cat}")

print("\n=== 7. Settings check ===")
check("track_media_sessions ON", settings.track_media_sessions)
check("track_window_titles ON", settings.track_window_titles)
check("private_title_mode OFF", not settings.private_title_mode)
check("pause_tracking OFF", not settings.pause_tracking)

s.close()
print(f"\n{'='*40}")
print(f"Results: {len(errors)} errors")
for name, actual, expected in errors:
    print(f"  - {name}: expected {expected!r}, got {actual!r}")
if errors:
    sys.exit(1)
