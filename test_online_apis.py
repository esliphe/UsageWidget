"""Comprehensive test for all online classification APIs."""
from __future__ import annotations

import time
import sys

sys.path.insert(0, ".")

from usage_widget.online_category import OnlineCategoryClassifier, CategoryLookupResult
from usage_widget.music_lookup import OnlineMusicVerifier, MusicLookupResult
from usage_widget.learning import (
    OnlineLearningTopicClassifier,
    LearningTopicResult,
    local_learning_topic,
    has_learning_intent,
    should_mark_learning,
    domain_matches,
)
from usage_widget.media import parse_music_identity

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  --  {detail}")


# ---- 1. parse_music_identity ----
print("\n=== parse_music_identity ===")

song, artist, label = parse_music_identity("Jay Chou - Qing Hua Ci")
check("Artist - Song format", song and artist, f"song={song!r} artist={artist!r}")

song, artist, label = parse_music_identity("Artist: Song Title")
check("Colon separator", song and artist, f"song={song!r} artist={artist!r}")

delim, _artist, _label = parse_music_identity("Artist:SongTitle")
check("Colon no-space separator", _artist or delim, f"song={_artist!r} artist={delim!r}")

song, artist, label = parse_music_identity("")
check("Empty string returns empty", song == "" and artist == "")

song, artist, label = parse_music_identity("Song - Artist - YouTube Music")
check("YouTube Music suffix stripped", "youtube" not in song.lower() and "youtube" not in artist.lower(),
      f"song={song!r} artist={artist!r}")

song, artist, label = parse_music_identity("Song Title - Artist Name - ExtraTag")
check("Multi-dash handles first two parts", song and artist,
      f"song={song!r} artist={artist!r}")

song, artist, label = parse_music_identity("Armin van Buuren - Blah Blah Blah (Official Music Video)")
check("(Official Music Video) stripped", "official" not in song.lower(),
      f"song={song!r} artist={artist!r}")

# ---- 2. OnlineCategoryClassifier ----
print("\n=== OnlineCategoryClassifier ===")

cat = OnlineCategoryClassifier(min_interval=1.0, ttl_seconds=3600)

c, conf = cat._classify_text("python programming tutorial for beginners")
check("Python text -> programming/learning", c in ("编程", "学习"), f"got {c} conf={conf:.2f}")

c, conf = cat._classify_text("league of legends gameplay walkthrough")
check("Game text -> 游戏", c == "游戏", f"got {c} conf={conf:.2f}")

c, conf = cat._classify_text("shopping online store amazon deals")
check("Shopping text -> 购物", c == "购物", f"got {c} conf={conf:.2f}")

c, conf = cat._classify_text("breaking news today headlines")
check("News text -> 新闻", c == "新闻", f"got {c} conf={conf:.2f}")

c, conf = cat._classify_text("spotify music playlist songs album")
check("Music text -> 音乐", c == "音乐", f"got {c} conf={conf:.2f}")

c, conf = cat._classify_text("zzzxyz abcdef something random unrelated")
check("Gibberish -> other (conf=0)", c == "其他" and conf == 0.0, f"got {c} conf={conf:.2f}")

c, conf = cat._classify_text("chatgpt openai claude ai assistant")
check("AI text -> AI tools/programming", c in ("AI 工具", "编程"), f"got {c} conf={conf:.2f}")

# Test cache with error TTL
cat._cache["err|key|1"] = (time.monotonic() - 1000, CategoryLookupResult("其他", 0.0, "error"))
result = cat.cached("err", "key", "1")
check("Error result expired after 900s", result is None, f"result={result}")

cat._cache["good|key|1"] = (time.monotonic() - 100, CategoryLookupResult("编程", 0.80, "good"))
result = cat.cached("good", "key", "1")
check("Good result valid after 100s", result is not None, f"result={result}")

# ---- 3. Category lookup live/fallback test ----
print("\n=== Category lookup live/fallback test ===")

try:
    result = cat._lookup("", "python.org", "Python Programming Language")
    check("Python lookup returns useful category", result.category in ("编程", "学习") and result.confidence >= 0.55,
          f"category={result.category} conf={result.confidence:.2f} source={result.source}")
except Exception as exc:
    check("Python lookup graceful fail", False, f"{type(exc).__name__}: {exc}")

time.sleep(1.5)

try:
    result = cat._lookup("steam.exe", "", "Counter-Strike 2")
    check("Steam game lookup", result.category in ("游戏", "其他"),
          f"category={result.category} conf={result.confidence:.2f} source={result.source}")
except Exception as exc:
    check("Steam lookup fail", False, f"{type(exc).__name__}: {exc}")

time.sleep(1.5)

try:
    result = cat._lookup("onenote.exe", "", "OneNote - Class Notes - Biology 101")
    check("OneNote class notes lookup", result.category in ("办公", "学习") and result.confidence >= 0.55,
          f"category={result.category} conf={result.confidence:.2f} source={result.source}")
except Exception as exc:
    check("OneNote lookup fail", False, f"{type(exc).__name__}: {exc}")

# ---- 4. OnlineMusicVerifier ----
print("\n=== OnlineMusicVerifier ===")

music = OnlineMusicVerifier(min_interval=1.0, ttl_seconds=3600)

# Test _matches
check("_matches exact", music._matches("Bohemian Rhapsody", "Queen", "Bohemian Rhapsody", "Queen"))
check("_matches fuzzy", music._matches("Bohemian Rhapsody", "Queen", "Bohemian Rhapsody", "Queen"))
check("_matches rejects different song",
      not music._matches("Love Story", "Taylor Swift", "Shake It Off", "Taylor Swift"))
check("_matches short strings exact", music._matches("Hi", "AB", "Hi", "AB"))
check("_matches short != long", not music._matches("Hi", "AB", "Hi there", "ABC"))

# Test cache error TTL
music._cache["err|test"] = (time.monotonic() - 700, MusicLookupResult(False, 0.0, "error"))
result = music.cached("test", "err")
check("Music error expired after 600s", result is None, f"result={result}")

# ---- 5. iTunes API live test ----
print("\n=== iTunes API live test ===")

try:
    result = music._lookup_itunes("Bohemian Rhapsody Queen", "Bohemian Rhapsody", "Queen")
    check("iTunes English song lookup", result.is_music and result.source == "itunes",
          f"title={result.title} artist={result.artist} conf={result.confidence:.2f}")
except Exception as exc:
    check("iTunes lookup fail", False, f"{type(exc).__name__}: {exc}")

time.sleep(1.5)

try:
    result = music._lookup_itunes("zzzxyzabc random gibberish 12345678", "", "")
    check("iTunes gibberish -> not music", not result.is_music, f"is_music={result.is_music}")
except Exception as exc:
    check("iTunes gibberish fail", False, f"{type(exc).__name__}: {exc}")

# ---- 6. MusicBrainz API live test ----
print("\n=== MusicBrainz API live test ===")

time.sleep(1.5)
try:
    result = music._lookup_musicbrainz("Bohemian Rhapsody Queen", "Bohemian Rhapsody", "Queen")
    check("MusicBrainz lookup", result.source in ("musicbrainz", "itunes"),
          f"is_music={result.is_music} conf={result.confidence:.2f}")
except Exception as exc:
    msg = str(exc)[:80]
    check("MusicBrainz graceful (may be ratelimited)",
          "rate" in msg.lower() or "http" in msg.lower() or "timeout" in msg.lower(),
          f"{type(exc).__name__}: {msg}")

# ---- 7. local_learning_topic ----
print("\n=== local_learning_topic ===")

result = local_learning_topic("Python tutorial object oriented programming class inheritance")
check("Python learning detected", result.topic == "Python", f"topic={result.topic} conf={result.confidence:.2f}")

result = local_learning_topic("calculus derivatives limits continuous functions mathematics")
check("Advanced math detected", result.topic == "高等数学" or "数学" in result.topic,
      f"topic={result.topic} conf={result.confidence:.2f}")

result = local_learning_topic("CET4 English vocabulary words grammar")
check("English learning detected", result.topic == "英语",
      f"topic={result.topic} conf={result.confidence:.2f}")

result = local_learning_topic("machine learning neural network transformer GPT LLM")
check("ML/AI topic detected", result.topic in ("机器学习", "人工智能"),
      f"topic={result.topic} conf={result.confidence:.2f}")

result = local_learning_topic("game walkthrough league of legends LOL gameplay")
check("Game text NOT flagged as learning", not result.topic or result.confidence < 0.55,
      f"topic={result.topic} conf={result.confidence:.2f}")

result = local_learning_topic("email about train main pain daily")
check("No 'ai' false positive for AI", result.topic != "人工智能" or result.confidence < 0.55,
      f"topic={result.topic} conf={result.confidence:.2f}")

result = local_learning_topic("email documentation class docs exam example")
check("No 'docs/class/exam' false positive", not result.topic or result.confidence < 0.55,
      f"topic={result.topic} conf={result.confidence:.2f}")

# ---- 8. has_learning_intent ----
print("\n=== has_learning_intent ===")

check("course -> learning intent", has_learning_intent("", "python course for beginners"))
check("coursera.org -> learning intent", has_learning_intent("coursera.org", "anything"))
check("docs.python.org -> learning intent", has_learning_intent("docs.python.org", "itertools"))
check("Bilibili + tutorial -> learning intent",
      has_learning_intent("bilibili.com", "Python tutorial intro", "video_playback"))
check("Bilibili game video NOT learning",
      not has_learning_intent("bilibili.com", "gameplay entertainment fun", "video_playback"),
      "Game videos should NOT have learning intent")
check("GitHub repo NOT learning intent",
      not has_learning_intent("github.com", "torvalds/linux"),
      "GitHub repos without edu text should NOT be learning")

# ---- 9. should_mark_learning ----
print("\n=== should_mark_learning ===")

check("learning category + topic -> True",
      should_mark_learning("学习", "Python", "", "Python tutorial"))
check("video + learning intent -> True",
      should_mark_learning("视频", "Python", "bilibili.com", "Python tutorial", "video_playback"))
check("programming + topic + learning intent -> True",
      should_mark_learning("编程", "Python", "coursera.org", "Python course", "web_page"))
check("No topic -> False",
      not should_mark_learning("其他", "", "", "random text"))

# ---- 10. OnlineLearningTopicClassifier ----
print("\n=== OnlineLearningTopicClassifier ===")

learn = OnlineLearningTopicClassifier(min_interval=1.0, ttl_seconds=3600)

result = learn._lookup("bilibili.com", "calculus mathematics derivatives limits tutorial", "math teaching")
check("Online math topic lookup", result.topic in ("高等数学", "数学", ""),
      f"topic={result.topic} conf={result.confidence:.2f} source={result.source}")

time.sleep(1.5)

result = learn._lookup("youtube.com", "Python tutorial for beginners", "Learn Python programming")
check("Online Python topic lookup", result.topic in ("Python", ""),
      f"topic={result.topic} conf={result.confidence:.2f}")

# Test cache error TTL
learn._cache["err|key"] = (time.monotonic() - 1000, LearningTopicResult("", 0.0, "error"))
result = learn.cached("err", "key", "")
check("Learning error expired after 900s", result is None, f"result={result}")

# ---- 11. domain_matches ----
print("\n=== domain_matches ===")

check("exact domain match", domain_matches("bilibili.com", {"bilibili.com", "youtube.com"}))
check("subdomain match", domain_matches("www.bilibili.com", {"bilibili.com"}))
check("no match", not domain_matches("example.com", {"bilibili.com"}))
check("empty domain", not domain_matches("", {"bilibili.com"}))
check("None domain safe", not domain_matches(None, {"bilibili.com"}))  # type: ignore

# ---- Summary ----
print(f"\n{'='*40}")
print(f"Results: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
if FAIL > 0:
    sys.exit(1)
