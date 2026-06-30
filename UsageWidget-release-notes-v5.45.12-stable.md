# UsageWidget v5.45.12-stable

## 修复与优化

- 优化网页、视频和音乐识别优先级：打字练习网页优先归为“打字”，普通网页不会再因为浏览器媒体会话被误判为视频或音乐播放。
- 媒体会话只在浏览器标签存在明确播放信号时才借用标签信息，减少“前台在打字，后台媒体抢分类”的情况。
- 折叠栏在“活动中”后新增短状态胶囊，支持显示打字、网页、音乐、视频等状态；前台网页和打字优先于后台音乐展示。
- 改进悬浮窗收回体验：离开后 260ms 触发收回，收回动画 95ms，展开动画 150ms；目标位置会按折叠后尺寸预先校准，减少边缘跳动和卡顿。
- 补充打字站点默认规则和配色，包括 dazidazi、monkeytype、10fastfingers、keybr、typing.com、typingclub 等。

## 验证

- `python -m compileall -q usage_widget run.py UsageWidget.spec` 通过。
- `python test_classification_regression.py` 通过。
- `python test_category_corrections.py` 通过。
- `python test_pipeline.py` 通过。
- `python test_monitor_storage_regression.py` 通过。
- UI 离屏 smoke 覆盖折叠状态胶囊、前台打字优先于后台音乐、网页胶囊分类、展开/收回动画时长和屏幕边缘位置校准。
