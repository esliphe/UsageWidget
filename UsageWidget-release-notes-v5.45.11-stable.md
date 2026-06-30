# UsageWidget v5.45.11-stable

## 修复与优化

- 修复桌面小组件可能同时显示收起条和详细面板的问题。根因是详细面板内排序下拉框的 Show/Hide 事件在收起过程中反向触发展开，导致视图状态交错。
- 展开/收起切换增加布局级高度保险：隐藏面板不仅设置不可见，也会被强制压到 0 高度，避免启动、托盘恢复和动画交错时出现双层界面。
- 优化启动体感：窗口先完成显示，再延迟启动监控与首轮采样，减少打开软件时首屏卡顿。
- 热力图格子尺寸改为同时按可用宽度和高度计算，并固定预留图例空间，避免底部“少/多”和色块在窄面板中挤压重叠。
- 默认忽略 `UsageWidget.exe` 自身，避免主列表把本程序显示成正在使用的软件。

## 验证

- `python -m compileall -q usage_widget run.py UsageWidget.spec` 通过。
- UI 离屏 smoke 覆盖折叠启动、展开、收起、动画后状态和热力图窄宽度截图。
- `python test_category_corrections.py` 通过。
- `python test_classification_regression.py` 通过。
- `python test_pipeline.py` 通过。
- `python test_monitor_storage_regression.py` 通过。
