# AI4S Bench 笔记

用浏览器打开 [首页](index.html) 即可预览。已生成的 HTML 可以直接发布到 GitHub Pages。

## 更新内容

- [Bench 指标](bench.html)：指标口径、案例分析、制作流程、任务模板与设计笔记在 `bench/` 中单独编辑。
- [每日出题实践](practice/index.html)：通过日期目录浏览记录，新增方式见下文。
- [论文更新](papers.html)：按日期倒序插入条目，填写日期、来源、摘要、设计笔记和原文链接。搜索会自动包含新条目。
- [Skills 与插件](skills.html)：把可分发的文件放到 `downloads/`，在 `skills.html` 里更新版本、下载链接与安装说明。

## 新增每日出题实践

1. 复制 [11 月 17 日的记录源文件](practice/entries/2026-11-17.json)，按新日期保存为 `practice/entries/YYYY-MM-DD.json`。填写当天标题、主题、记录类型、摘要和各段正文。可选的相关链接使用站内相对路径或 HTTP(S) 地址。
2. 在站点目录运行 `python3 scripts/build_practice.py`。脚本会为每个日期生成一个 `practice/YYYY-MM-DD.html`，并按日期倒序更新[实践目录](practice/index.html)。

日期页的内容由 JSON 决定。更新正文时编辑源文件后重跑脚本。[出题思路和提示词](practice/ideas.html)在独立页面编辑。

## GitHub Pages

将此目录的内容（包括 `.nojekyll` 和 `downloads/`）放到网站仓库的根目录。在仓库的 **Settings → Pages** 中选择 **Deploy from a branch**，将发布来源设为 **main → /(root)**。推送更新后，对应的 Pages 工作流会重新部署页面。
