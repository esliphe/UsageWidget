# UsageWidget v5.45.14-stable

## 数据维护

- 修复「优化数据库」不回收空间的问题。此前只执行 `PRAGMA optimize` 与 `wal_checkpoint(PASSIVE)`，不做 `VACUUM`，因此清理旧时间线后数据库文件大小完全不变，界面却提示「优化完成」。
- 现在会重建数据库并回报压缩前后体积与实际回收量，例如 `722.0 MB → 68.4 MB`。
- WAL 检查点改为 `TRUNCATE`，失败时回退 `PASSIVE`，兼容读写并发场景。
- 首次启动写入 `PRAGMA user_version`，为后续迁移提供版本前置判断；检测到更高版本数据库时记入诊断日志而不是静默继续。

## 隐私

- 诊断日志不再记录前台窗口标题。慢采样、学习主题识别异常和历史内容联网分类失败三处日志统一改为记录进程名与 `title_len`，避免明文日志泄漏浏览内容。

## 可维护性

- 分类站点知识收敛为单一来源：打字站点常量移入 `classification.py`，`storage.py` 的默认规则与迁移清单由常量生成，`monitor.py` 的短状态判定复用同一份提示词。此前同一站点在三个文件、五处位置各写一遍。
- 默认分类规则表去掉历史遗留的 7 组完全重复项（444 → 428 条），保留首次出现顺序，不影响规则优先级与落库结果。
- 联网查询的 UA、请求体上限、编码回退与验证码识别抽为 `netlookup.py`，`learning.py` 与 `online_category.py` 不再各自维护一份 `_fetch_json` / `_fetch_text` / `_is_access_challenge`。
- 百度页面的编码处理统一走共享实现，GB18030 响应现在能正确解码；此前学习主题识别路径按 UTF-8 硬解，非 UTF-8 页面会退化为替换字符。
- 移除 Last.fm 音乐校验分支。该分支只有设置 `USAGEWIDGET_LASTFM_API_KEY` 才可用，实际恒返回 `lastfm-disabled`。iTunes / MusicBrainz 链路不变。

## 工程化

- 新增 `run_tests.py`：一条命令跑全部离线回归，汇总通过率并以退出码反映结果；`--online` 启用真实联网用例，`--verbose` 输出明细。
- 新增 `scripts/build_release.py`：构建前跑编译检查与回归，构建后校验 `UsageWidget.exe`、`_internal` 文件数与随包中文字体，再复制、生成 SHA256、打包并回验 zip 完整性。
- 打包脚本不再删除任何产物：旧构建整体移入 `build/previous-dist-<时间戳>/`。此前清理步骤会把刚复制的目录一并删掉，v5.45.6 / v5.45.8 / v5.45.10 / v5.45.12 四个版本因此发布了空包。
- 发布包生成 `SHA256SUMS-<version>.txt`，同时给出 zip 与 exe 的摘要。

## 验证

- `python -m compileall -q usage_widget run.py UsageWidget.spec` 通过。
- `python run_tests.py` 12/12 套通过（含新增的维护与规则归属回归）。
- 新增 `test_maintenance_and_rules.py`：验证删除行后文件不缩小、`optimize_database` 确实回收空间（844 KB → 381 KB）、架构版本号写入与重开保持、站点规则单一来源、联网实现共享。
- PySide6 离屏冒烟：主窗口、设置、统计、当前状态、运行诊断四个对话框全部构建成功，采样写入 3 轮正常，HTML 报告导出正常。

## 已知限制

- 采样线程与界面线程仍共用同一个 SQLite 连接（`check_same_thread=False`，无连接级锁）。写入方通过 `BEGIN/COMMIT` 保证原子性，WAL 保证读者看到已提交状态，但同连接内跨线程仍存在事务边界交错的窗口。彻底方案是写连接与读连接分离，属于数据层改造，本版未包含。
- 时间线仍按采样点逐条记录，未改为区间合并。数据库体积随使用时长增长的根因未变，本版只修复了「清理后不回收空间」这一环。
