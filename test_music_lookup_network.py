from __future__ import annotations

import urllib.request

from usage_widget import music_lookup
from usage_widget.music_lookup import OnlineMusicVerifier


class FakeResponse:
    headers = {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return b'{"results":[]}'


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def main() -> None:
    verifier = OnlineMusicVerifier(min_interval=0.0)
    calls: list[float] = []
    original_urlopen = urllib.request.urlopen
    original_sleep = music_lookup.time.sleep

    def fake_urlopen(_request: urllib.request.Request, timeout: float) -> FakeResponse:
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError("simulated timeout")
        return FakeResponse()

    try:
        urllib.request.urlopen = fake_urlopen  # type: ignore[assignment]
        music_lookup.time.sleep = lambda _seconds: None  # type: ignore[assignment]
        result = verifier._fetch_json("https://example.test", {}, timeout=1.5, retries=1)
    finally:
        urllib.request.urlopen = original_urlopen  # type: ignore[assignment]
        music_lookup.time.sleep = original_sleep  # type: ignore[assignment]

    check("fetch json retries transient failure", result == {"results": []}, repr(result))
    check("fetch json uses caller timeout", calls == [1.5, 1.5], repr(calls))
    check("generic music user agent hides exact version", music_lookup.USER_AGENT == "UsageWidget", music_lookup.USER_AGENT)

    print("all music lookup network tests passed")


if __name__ == "__main__":
    main()
