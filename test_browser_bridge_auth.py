from __future__ import annotations

import json
import urllib.error
import urllib.request

from usage_widget.browser_bridge import AUTH_HEADER, BrowserBridge


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def request(url: str, *, method: str = "GET", payload: dict | None = None, token: str = "", origin: str = "") -> tuple[int, dict]:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers[AUTH_HEADER] = token
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=2.0) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw.decode("utf-8") or "{}")


def main() -> None:
    bridge = BrowserBridge(port=0)
    bridge.start()
    try:
        base = f"http://127.0.0.1:{bridge.port}"
        status, _body = request(f"{base}/session")
        check("session requires extension origin", status == 403, str(status))

        status, session = request(f"{base}/session", origin="chrome-extension://test-extension")
        check("extension origin can get session", status == 200 and bool(session.get("token")), repr((status, session)))

        payload = {"title": "Example", "url": "https://example.com/page", "browser": "test"}
        status, _body = request(f"{base}/active-tab", method="POST", payload=payload, origin="chrome-extension://test-extension")
        check("missing token is rejected", status == 401, str(status))
        check("rejected request does not update latest tab", bridge.latest() is None)

        status, _body = request(
            f"{base}/active-tab",
            method="POST",
            payload=payload,
            token=str(session["token"]),
            origin="https://evil.example",
        )
        check("web origin is rejected", status == 401 or status == 403, str(status))

        status, _body = request(
            f"{base}/active-tab",
            method="POST",
            payload=payload,
            token=str(session["token"]),
            origin="chrome-extension://test-extension",
        )
        check("valid token accepts active tab", status == 200, str(status))
        latest = bridge.latest()
        check("accepted request updates latest tab", latest is not None and latest.domain == "example.com", repr(latest))
    finally:
        bridge.stop()

    print("all browser bridge auth tests passed")


if __name__ == "__main__":
    main()
