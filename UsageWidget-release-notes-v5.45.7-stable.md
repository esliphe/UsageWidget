# UsageWidget v5.45.7-stable

## 修复与优化

- 修复采样 delta 被强制截断为 5 秒的问题；长时间睡眠/唤醒后会按安全上限记录，不再严重低估使用时长。
- 首次采样统一作为预热处理，`write=True` 也不会凭空写入默认 1.5 秒。
- 修复多实例进程的 `running_seconds` 被二次平方放大的问题。
- 为采样定时器增加重入保护，避免慢采样在事件队列中连续堆积执行。
- 浏览器桥读取增加异常保护，扩展/本地桥异常不会中断整个采样循环。
- 媒体会话采样新增短超时同步刷新，减少“新播放要等下一轮采样”的滞后；超时后自动回退异步刷新。
- 媒体会话连续错误达到 3 次才触发后台播放兜底，避免瞬时错误造成误记。
- 在线分类队列增加 pending 上限，防止短时间打开大量页面时堆积过多后台联网任务。
- 图标缓存增加容量上限，应用图标绘制增加缓存，降低长时间运行的内存增长。
- 延迟热力图渲染绑定接收对象并检查窗口状态，减少关闭统计窗口后的 Qt 对象访问风险。

## 验证

- `py_compile` 通过。
- `test_monitor_storage_regression.py` 通过。
- `test_media_provider_refresh.py` 通过。
- `test_pipeline.py` 通过。
- `test_classification_regression.py` 通过。
- `test_online_category_mock.py` 通过。
- `test_browser_bridge_auth.py` 通过。
- `test_security_and_ui_helpers.py` 通过。
