# UsageWidget v5.45.9-stable

## 修复与优化

- 修复 DeepSeek、Codex 等 AI 工具在本地分类规则存在时仍可能被宽泛聊天规则覆盖的问题。
- 增加受保护的 AI 工具默认规则，并修复历史记录中已被误标为聊天/社交/网站/浏览器的 DeepSeek 数据。
- 调整分类规则命中权重：默认保护规则可压过联网学到的宽泛规则，但用户手动添加的更具体纠错仍可覆盖默认规则。
- 收紧网页视频分类审查：普通浏览 B 站、YouTube 等平台首页/搜索页/空间页时，不再仅凭域名归为“视频”。
- 收紧发声标签页播放类型判断：只有播放页 URL、video 元素或明确媒体播放状态足够强时才记为视频播放。
- 增加历史修复逻辑：已写入数据库的“网页浏览 + 视频”误标记录会回落为网站，除非 URL 或标题确实指向视频内容。

## 验证

- `python test_category_corrections.py` 通过。
- `python test_classification_regression.py` 通过。
- `python test_pipeline.py` 通过。
- `py_compile usage_widget/*.py` 通过。
