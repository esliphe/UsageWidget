# UsageWidget v5.45.10-stable

## 修复与优化

- 回退 24 小时时间分布图到上一版分组柱视觉：前台、视频、音乐按小时并排显示，学习继续用绿色圆点标记。
- 修复桌面小组件启动时展开/折叠状态可能没有同步窗口尺寸和可见面板的问题。
- 桌面小组件顶部操作按钮改用 Qt 标准图标，避免特殊符号在部分字体环境中显示成方框。
- 保留详情页时间线按需加载优化，同时确认概览页 24 小时图继续使用聚合数据，不依赖时间线页签是否加载。

## 验证

- `python -m compileall -q usage_widget run.py UsageWidget.spec` 通过。
- UI 离屏 smoke 覆盖固定展开启动、悬浮折叠启动、展开态截图和详情页概览截图通过。
- `python test_category_corrections.py` 通过。
- `python test_classification_regression.py` 通过。
- `python test_pipeline.py` 通过。
