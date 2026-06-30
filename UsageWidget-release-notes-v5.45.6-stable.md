# UsageWidget v5.45.6-stable

## 修复与优化

- 浏览器扩展与桌面端通信新增随机会话 token，上报请求必须带 `X-UsageWidget-Token`。
- 本地桥接服务新增 `/session` 握手，并限制 CORS/Origin，仅接受浏览器扩展来源。
- 联网分类、学习主题和音乐验证请求不再在 User-Agent 中暴露精确版本号。
- 音乐联网验证新增分 API 超时配置和瞬时失败重试，提升 iTunes / MusicBrainz / Last.fm 查询稳定性。
- 统计窗口新增快捷键：`Ctrl+F` 聚焦时间线搜索、`Ctrl+D` 回到今天、`Ctrl+Left/Right` 切换时间段、`Esc` 关闭。
- 主窗口新增快捷键：`Ctrl+,` 打开设置、`Ctrl+F` 打开统计搜索、`Ctrl+D` 打开今日统计。

## 验证

- `py_compile` 通过。
- `compileall` 通过。
- `test_browser_bridge_auth.py` 通过。
- `test_music_lookup_network.py` 通过。
- `test_security_and_ui_helpers.py` 通过。
- `test_online_category_mock.py` 通过。
