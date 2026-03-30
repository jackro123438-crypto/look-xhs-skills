---
name: xiaohongshu
description: |
  小红书数据采集与发布技能。默认用于：搜索小红书内容、获取帖子详情（含互动数据与评论）、生成话题样本；当用户明确要求“发布”时再执行发布。
---

# 小红书 Skill（精简版）

## 默认用途（仅采集）
1. 搜索内容（`search_feeds`）
2. 获取帖子详情与评论（`get_feed_detail`）
3. 话题跟踪/样本收集（`track-topic.sh`）

> 默认不要执行点赞、收藏、评论、回复等互动操作。

## 采集执行策略（防超时，固定执行）
采用“两段式采集”：

### 阶段A：候选池
- 先按关键词+筛选条件执行搜索，拿候选池（建议 20-50 条）
- 先做基础过滤（如点赞阈值）

### 阶段B：详情补全
- 对候选逐条调用 `get_feed_detail` 补全详情
- 单条失败（如 noteDetailMap not found）直接跳过并换样本，不中断整批
- 分批处理（每批建议 5 条）并持续汇报进度

### 典型约束
- 例如“点赞>200、一年内、最多点赞、凑够10条”：
  - A阶段先筛点赞阈值
  - B阶段用详情时间字段二次过滤“一年内”
  - 不足10条继续补批直至凑够或候选耗尽

## 发布入口（仅在用户明确要求“发布”时）
- 使用 `publish_content` 或 `publish_with_video`
- 发布前必须二次确认：标题、正文、标签、图片清单

## 常用脚本
请从 skill 自带的 `scripts/` 目录运行；当前真实路径：
`/Users/look/openclaw/huanglei/workspace/skills/xiaohongshu/scripts`

```bash
cd /Users/look/openclaw/huanglei/workspace/skills/xiaohongshu/scripts
bash ./status.sh
bash ./search.sh "关键词"
bash ./post-detail.sh <feed_id> <xsec_token>
bash ./track-topic.sh "话题" --limit 10
```

发布（仅用户明确要求时）：
```bash
cd /Users/look/openclaw/huanglei/workspace/skills/xiaohongshu/scripts
bash ./mcp-call.sh publish_content '{"title":"...","content":"...","images":["..."]}'
```

## 说明
- 若登录失效，先重新登录再执行采集/发布。
- 采集中遇到单条详情失败时，自动换样本继续，不中断整批结果。
- 当前迁移后的脚本文件默认**没有可执行位**，因此应使用 `bash ./xxx.sh` 调用，而不是直接 `./xxx.sh`。
