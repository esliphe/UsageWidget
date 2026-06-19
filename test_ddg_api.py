"""Verify DuckDuckGo online search for ambiguous app classification."""
import sys, time
sys.path.insert(0, ".")
from usage_widget.online_category import OnlineCategoryClassifier

cat = OnlineCategoryClassifier(min_interval=0.5)
passed = 0
failed = 0

# Test 1: Known apps with exe+title
print("=== Apps with exe + title ===")
tests = [
    ("yuanbao.exe", "", "AI Assistant"),
    ("doubao.exe", "", "AI Chatbot"),
    ("tongyi.exe", "", "AI Model"),
    ("wenxin.exe", "", "AI Platform"),
    ("keil.exe", "", "STM32F407 Project"),
    ("stm32cubemx.exe", "", "Pinout Configuration"),
    ("vivado.exe", "", "FPGA Project Manager"),
    ("matlab.exe", "", "Signal Processing Toolbox"),
    ("autocad.exe", "", "Drawing1.dwg"),
]

for exe, domain, title in tests:
    q = cat._query(exe, domain, title)
    print(f"  Q: {q[:70]}")
    try:
        r = cat._lookup(exe, domain, title)
        print(f"  -> category={r.category} conf={r.confidence:.2f} source={r.source}")
        if r.category != "其他":
            passed += 1
            print(f"  [PASS]")
        else:
            failed += 1
            print(f"  [WARN] got '其他'")
    except Exception as e:
        failed += 1
        print(f"  [FAIL] {type(e).__name__}: {e}")
    time.sleep(1.0)
    print()

# Test 2: Ambiguous exe-only queries (the key test!)
print("=== Ambiguous exe-only queries ===")
ambig = [
    "yuanbao.exe",
    "doubao.exe",
    "tongyi.exe",
    "wenxin.exe",
    "xinghuo.exe",
    "chatglm.exe",
    "zhipu.exe",
    "minimax.exe",
    "moonshot.exe",
    "baichuan.exe",
    "stepfun.exe",
]
for exe in ambig:
    q = cat._query(exe, "", "")
    print(f"  Q: {q!r}")
    try:
        r = cat._lookup(exe, "", "")
        print(f"  -> category={r.category} conf={r.confidence:.2f}")
        print(f"  -> summary: {r.summary[:120]}")
        if r.category != "其他":
            passed += 1
            print(f"  [PASS]")
        else:
            failed += 1
            print(f"  [WARN] got '其他' — may need better query")
    except Exception as e:
        failed += 1
        print(f"  [FAIL] {type(e).__name__}: {e}")
    time.sleep(1.0)
    print()

print(f"{'='*40}")
print(f"Results: {passed} passed, {failed} failed/warned, {passed+failed} total")
if failed > 0:
    sys.exit(1)
