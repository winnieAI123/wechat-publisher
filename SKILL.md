---
name: wechat-publisher
description: 'Publish articles to WeChat Official Account (微信公众号) as drafts via API with professional Cyber-Zen minimalist formatting (赛博禅心风). Use this skill whenever the user asks to "发公众号", "推送到公众号", "发微信文章", "写一篇公众号文章", "写公众号", "公众号排版", "publish to WeChat", "公众号草稿", or mentions creating/writing/publishing content for their WeChat Official Account. This skill handles the FULL workflow — writing Markdown, generating cover image, converting to beautifully formatted WeChat HTML, uploading media, creating draft. ABSOLUTE RULE — you MUST use wechat_draft_publisher.py for ALL WeChat publishing. NEVER construct HTML manually or call WeChat API directly; the script contains inline styling that is REQUIRED for proper formatting. Without the script, articles will appear as ugly unstyled plain text.'
---

# WeChat Official Account Publisher (微信公众号发文)

Publishes Markdown articles to WeChat Official Accounts as drafts via the official API. The user taps "Publish" on their phone to complete the process.

## Skill Contents

```
wechat-publisher/
├── SKILL.md                              # This file
└── scripts/
    ├── wechat_draft_publisher.py         # Main publishing script
    └── default_cover.png                 # Default cover image
```

## Setup (First-Time Only)

### 1. Credentials

The script reads WeChat credentials from `openclaw.json`:

```json
{
  "skills": {
    "entries": {
      "wechat-publisher": {
        "appId": "your_wechat_app_id",
        "appSecret": "your_wechat_app_secret"
      }
    }
  }
}
```

Alternative: set environment variables `WECHAT_APP_ID` and `WECHAT_APP_SECRET`.

### 2. IP Whitelist

The server's public IP must be whitelisted in the WeChat Developer Platform. If you see "IP not in whitelist" errors, ask the user to update it at https://open.weixin.qq.com.

### 3. Dependencies

```bash
python -m pip install markdown requests
```

## When to Use

- User asks to write and publish a WeChat article
- User says "发公众号", "推到公众号", "写篇文章发公众号"
- User wants to share content on their WeChat Official Account

## Critical Rules

> ⚠️ **MUST use wechat_draft_publisher.py for ALL publishing!**
> The script contains赛博禅心极简风 inline CSS that is ESSENTIAL for formatting.
> If you construct HTML yourself or call the WeChat API directly, the article will have NO STYLING and look terrible.
> ALWAYS run: `python "<skill-path>/scripts/wechat_draft_publisher.py" --markdown "article.md" --cover "cover.png"`

> ⚠️ **NEVER use browser automation to interact with the WeChat backend (mp.weixin.qq.com)!**
> It triggers anti-bot detection and blocks the account. ALWAYS use this skill's API script.

> ⚠️ **Personal unverified accounts have restrictions:**
> - Do NOT pass `--author` — API rejects it
> - Do NOT manually set digest — let WeChat auto-extract
> - Cover image is mandatory — script auto-uses default if none specified

## Complete Workflow

### Step 1: Write the Article

Write the article in **Markdown format**:
- Use `# Title` as the first line — becomes the WeChat article title
- Use `##` and `###` for sections
- Use `**bold**` for emphasis (renders in red on WeChat)
- Support: blockquotes, tables, lists, code blocks, images

Save to: `D:\OpenClawResult\YYYY-MM-DD\article_name.md`

### Step 2: Generate Cover Image (MANDATORY — 每次必须新生成！)

**每篇文章必须用 nano-banana-pro 根据文章内容生成一张全新的封面图。** 禁止使用默认封面或复用旧图。

**封面风格要求（严格执行）：**
- **风格**: 简约学术手绘风（minimalist academic hand-drawn illustration）
- **配色**: 柔和素雅，偏米白/浅灰底色，线条用深灰/墨色
- **元素**: 与文章主题相关的简笔画式图标/符号/示意图
- **构图**: 留白充足，不要太满，学术论文插图的感觉
- **比例**: 2.35:1 横版（900×383）
- **禁止**: 花哨的渐变、3D效果、过于写实的照片风格
- **禁止**: 图上放文字（微信会自动叠加标题）

**Prompt 模板（给 nano-banana-pro）：**
```
Minimalist academic hand-drawn illustration about [文章核心主题].
Soft muted color palette on off-white background.
Simple ink-style line drawings of [相关视觉元素].
Clean composition with generous whitespace.
Academic paper illustration style. Aspect ratio 2.35:1. No text.
```

**示例：**
- AI Agent 文章 → 手绘的互联机器人 + 工作流箭头
- 投资分析文章 → 简笔画的上升趋势线 + 放大镜
- 芯片行业文章 → 手绘电路板 + 芯片示意图

将封面图保存到与文章同一目录。

### Step 3: Create Draft via API

The script is bundled with this skill. Run it using its **absolute path**:

```bash
# Find the script path (relative to this skill)
# It's at: <this-skill-directory>/scripts/wechat_draft_publisher.py

# With custom cover
python "<skill-path>/scripts/wechat_draft_publisher.py" --markdown "article.md" --cover "cover.png"

# Without cover (uses default)
python "<skill-path>/scripts/wechat_draft_publisher.py" --markdown "article.md"

# Test connection
python "<skill-path>/scripts/wechat_draft_publisher.py" --test
```

**Important**: Use the actual absolute path to the script. You can find it by looking at this skill's installation directory.

### Step 4: Notify the User

After success, tell the user:
- ✅ 草稿已创建成功
- 📱 请打开手机「订阅号助手」App → 草稿箱 → 点击发布

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `IP not in whitelist` | Server IP changed | User updates IP at WeChat Developer Platform |
| `access_token expired` | Cache stale | Delete `.wechat_token_cache.json` next to script |
| `author size out of limit` | Personal account restriction | Don't pass `--author` |
| Unicode escape codes in content | Wrong JSON encoding | Script already uses `ensure_ascii=False` |
