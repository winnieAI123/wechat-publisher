"""
微信公众号半自动发文脚本（自包含版）
功能：Markdown → 微信兼容HTML → 上传图片 → 创建草稿
凭证读取优先级：环境变量 > openclaw.json skills config > 命令行参数

用法：
  # 通过环境变量配置（推荐）
  set WECHAT_APP_ID=your_app_id
  set WECHAT_APP_SECRET=your_app_secret
  python wechat_draft_publisher.py --markdown article.md

  # 通过命令行参数
  python wechat_draft_publisher.py --markdown article.md --app-id xxx --app-secret xxx

  # 测试连接
  python wechat_draft_publisher.py --test
"""

import os
import re
import json
import time
import argparse
import requests
import markdown
from pathlib import Path
from datetime import datetime


# ============================================================
# 路径常量
# ============================================================

SCRIPT_DIR = Path(__file__).parent
DEFAULT_COVER_IMAGE = SCRIPT_DIR / "default_cover.png"
TOKEN_CACHE_FILE = SCRIPT_DIR / ".wechat_token_cache.json"

# 微信 API 端点
API_BASE = "https://api.weixin.qq.com/cgi-bin"
API_TOKEN = f"{API_BASE}/token"
API_UPLOAD_IMG = f"{API_BASE}/media/uploadimg"
API_ADD_MATERIAL = f"{API_BASE}/material/add_material"
API_ADD_DRAFT = f"{API_BASE}/draft/add"


# ============================================================
# 凭证管理
# ============================================================

def load_credentials(cli_app_id=None, cli_app_secret=None):
    """
    按优先级加载 AppID 和 AppSecret：
    1. 命令行参数
    2. 环境变量 WECHAT_APP_ID / WECHAT_APP_SECRET
    3. 凭证文件 ~/.openclaw/credentials/wechat-publisher.json
    """
    app_id = cli_app_id or os.environ.get("WECHAT_APP_ID")
    app_secret = cli_app_secret or os.environ.get("WECHAT_APP_SECRET")

    # 尝试从凭证文件读取
    if not app_id or not app_secret:
        cred_file = _find_credential_file()
        if cred_file:
            try:
                creds = json.loads(cred_file.read_text(encoding="utf-8"))
                app_id = app_id or creds.get("appId")
                app_secret = app_secret or creds.get("appSecret")
                if app_id:
                    print(f"  📋 从凭证文件加载: {cred_file.name}")
            except (json.JSONDecodeError, KeyError):
                pass

    if not app_id or not app_secret:
        raise RuntimeError(
            "❌ 未找到微信公众号凭证！请通过以下方式之一配置：\n"
            "  1. 凭证文件: ~/.openclaw/credentials/wechat-publisher.json\n"
            "     内容: {\"appId\": \"xxx\", \"appSecret\": \"xxx\"}\n"
            "  2. 环境变量: set WECHAT_APP_ID=xxx && set WECHAT_APP_SECRET=xxx\n"
            "  3. 命令行: --app-id xxx --app-secret xxx"
        )

    return app_id, app_secret


def _find_credential_file():
    """查找微信凭证文件"""
    candidates = [
        Path.home() / ".openclaw" / "credentials" / "wechat-publisher.json",
        Path.home() / ".clawdbot" / "credentials" / "wechat-publisher.json",
        SCRIPT_DIR / "credentials.json",  # skill 目录内
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ============================================================
# 微信公众号排版 — 莫兰迪学术风内联样式
# ============================================================

# 莫兰迪配色 + 学术风设计
# 主色调：雾霾绿 #7B9E89 | 暖灰棕 #B8A08D | 赭石色 #B07D62
# 背景色：暖白 #F5F0EB | 亚麻色 #F0ECE6 | 浅灰 #F8F5F0

WRAPPER_STYLE = (
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif; "
    "font-size: 16px; line-height: 2; color: #3C3C3C; padding: 0 8px; "
    "letter-spacing: 0.5px;"
)

INLINE_STYLES = {
    "h1": (
        "font-size: 22px; font-weight: bold; color: #3D4F5F; "
        "margin: 30px 0 16px; padding-bottom: 10px; "
        "border-bottom: 2px solid #8BA098; letter-spacing: 1px;"
    ),
    "h2": (
        "font-size: 19px; font-weight: bold; color: #4A5A6A; "
        "margin: 26px 0 14px; padding: 4px 0 4px 14px; "
        "border-left: 4px solid #8BA098; letter-spacing: 0.5px;"
    ),
    "h3": (
        "font-size: 17px; font-weight: bold; color: #5A6A7A; "
        "margin: 22px 0 10px; letter-spacing: 0.5px;"
    ),
    "p": (
        "margin: 14px 0; text-align: justify; line-height: 2; "
        "color: #3C3C3C; letter-spacing: 0.5px;"
    ),
    "blockquote": (
        "margin: 20px 0; padding: 16px 20px; "
        "background: #F5F0EB; border-left: 4px solid #B8A08D; "
        "color: #6B6B6B; font-size: 15px; "
        "border-radius: 0 6px 6px 0; line-height: 1.9;"
    ),
    "code": (
        "background: #F0ECE6; padding: 2px 6px; border-radius: 3px; "
        "font-size: 14px; color: #8B6E4E;"
    ),
    "pre": (
        "background: #2D3436; color: #DFE6E9; padding: 18px; "
        "border-radius: 8px; overflow-x: auto; font-size: 13px; "
        "line-height: 1.6; margin: 16px 0;"
    ),
    "ul": "margin: 14px 0; padding-left: 24px; color: #3C3C3C;",
    "ol": "margin: 14px 0; padding-left: 24px; color: #3C3C3C;",
    "li": "margin: 8px 0; line-height: 1.9;",
    "img": "max-width: 100%; border-radius: 6px; margin: 16px 0;",
    "a": (
        "color: #7B9E89; text-decoration: none; "
        "border-bottom: 1px solid #7B9E89;"
    ),
    "strong": "color: #B07D62; font-weight: bold;",
    "em": "color: #6B8E7B; font-style: italic;",
    "table": (
        "width: 100%; border-collapse: collapse; margin: 20px 0; "
        "font-size: 14px;"
    ),
    "th": (
        "background: #7B9E89; color: white; padding: 10px 14px; "
        "text-align: left; font-weight: 600; letter-spacing: 0.5px;"
    ),
    "td": (
        "padding: 10px 14px; border-bottom: 1px solid #E8E4DF; "
        "color: #4A4A4A;"
    ),
    "hr": (
        "border: none; height: 1px; "
        "background: linear-gradient(to right, transparent, #B8A08D, transparent); "
        "margin: 28px 0;"
    ),
}

# pre > code 内的 code 标签需要覆盖默认 code 样式
PRE_CODE_STYLE = (
    "background: none; color: inherit; padding: 0; "
    "font-size: inherit; border-radius: 0;"
)


# ============================================================
# 核心功能
# ============================================================

def get_access_token(app_id, app_secret, force_refresh=False):
    """获取 access_token（带本地缓存，2小时有效期）"""

    if not force_refresh and TOKEN_CACHE_FILE.exists():
        try:
            cache = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
            if cache.get("app_id") == app_id and time.time() < cache.get("expires_at", 0):
                print(f"✅ 使用缓存 token（{int(cache['expires_at'] - time.time())}秒后过期）")
                return cache["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass

    print("🔄 正在获取新的 access_token...")
    resp = requests.get(API_TOKEN, params={
        "grant_type": "client_credential",
        "appid": app_id,
        "secret": app_secret
    })
    data = resp.json()

    if "access_token" not in data:
        raise RuntimeError(
            f"获取 token 失败！错误码: {data.get('errcode')}, 信息: {data.get('errmsg')}\n"
            f"常见原因：1) IP不在白名单 2) AppSecret错误 3) AppID错误"
        )

    cache = {
        "app_id": app_id,
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 7200) - 300
    }
    TOKEN_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    print(f"✅ 获取 token 成功（{data.get('expires_in', 7200)}秒有效）")
    return data["access_token"]


def upload_article_image(image_path, token):
    """上传文章内图片到微信CDN（返回 mmbiz URL）"""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    print(f"📤 上传文章内图片: {image_path.name}")
    with open(image_path, "rb") as f:
        resp = requests.post(
            API_UPLOAD_IMG,
            params={"access_token": token},
            files={"media": (image_path.name, f, _get_mime_type(image_path))}
        )

    data = resp.json()
    if "url" not in data:
        raise RuntimeError(f"上传图片失败: {data.get('errmsg', data)}")

    print(f"  ✅ URL: {data['url'][:60]}...")
    return data["url"]


def upload_cover_image(image_path, token):
    """上传封面图到微信永久素材（返回 media_id）"""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"封面图不存在: {image_path}")

    print(f"📤 上传封面图: {image_path.name}")
    with open(image_path, "rb") as f:
        resp = requests.post(
            API_ADD_MATERIAL,
            params={"access_token": token, "type": "image"},
            files={"media": (image_path.name, f, _get_mime_type(image_path))}
        )

    data = resp.json()
    if "media_id" not in data:
        raise RuntimeError(f"上传封面图失败: {data.get('errmsg', data)}")

    print(f"  ✅ media_id: {data['media_id'][:30]}...")
    return data["media_id"]


def _apply_inline_styles(html):
    """
    将内联样式注入 HTML 标签，确保微信兼容。
    微信编辑器会过滤 <style> 标签和 class 属性，
    因此必须使用内联 style="" 属性。
    """
    for tag, style in INLINE_STYLES.items():
        # 只匹配开标签，不匹配闭标签 </tag>
        # (?<!/) 确保 < 后面不是 /（排除闭标签）
        html = re.sub(
            rf'<(?!/){tag}(?=[\s>/])',
            f'<{tag} style="{style}"',
            html
        )
    # 特殊处理：<pre> 内的 <code> 需要覆盖默认 code 样式
    html = re.sub(
        r'(<pre[^>]*>)\s*<code[^>]*>',
        rf'\1<code style="{PRE_CODE_STYLE}">',
        html
    )
    # 表格偶数行交替背景色
    html = _apply_table_row_alternation(html)
    return html


def _strip_leading_h1(md):
    """剥掉正文最开头的 H1（微信顶栏已显示文章标题，正文再写一遍会重复）"""
    return re.sub(r'\A[ \t\r\n]*#[ \t]+[^\n]+\n*', '', md, count=1)


def _unwrap_misused_fenced_code(md):
    """自动 unwrap 误用的 fenced code block。

    AI 生成 markdown 时偶尔会把强调短语包成单行 ``` 代码块，例如：
        ```
        **Improvement Loop（改进循环）**。代码生成后让 Codex 自我评审。
        ```
    这种结构在微信渲染时会显示成深色代码框里塞一行中文，非常突兀。
    规则：单行 + 含 ** 或 __ markdown 强调标记 → 视为误用，unwrap 成普通段落。
    """
    pattern = re.compile(
        r'^```[^\n]*\n'   # 开 fence（允许跟语言名）
        r'([^\n]+)\n'     # 仅一行内容
        r'```[ \t]*$',    # 闭 fence
        re.MULTILINE
    )
    count = [0]
    def replace(m):
        line = m.group(1)
        if "**" in line or "__" in line:
            count[0] += 1
            return line
        return m.group(0)
    out = pattern.sub(replace, md)
    if count[0]:
        print(f"⚠️ 自动 unwrap 了 {count[0]} 处可疑的单行代码块（含强调标记）")
    return out


def _apply_table_row_alternation(html):
    """为表格偶数行添加浅灰交替背景"""
    def process_table(table_match):
        table_html = table_match.group(0)
        row_idx = [0]
        def style_row(tr_match):
            row_idx[0] += 1
            if row_idx[0] % 2 == 0:
                return '<tr style="background: #FAFAFA;">'
            return tr_match.group(0)
        return re.sub(r'<tr[^>]*>', style_row, table_html)
    return re.sub(
        r'<table[^>]*>.*?</table>',
        process_table,
        html,
        flags=re.DOTALL
    )


def _auto_fix_tables(md_content):
    """
    自动修复缺少分隔行的 markdown 表格。
    markdown 表格必须有 |---|---| 分隔行才能被解析，
    但 agent 经常忘记写。本函数自动检测并补上。
    只在表格第一行（表头行）之后插入分隔行，不重复插入。
    """
    lines = md_content.split('\n')
    result = []
    in_fence = False
    in_table = False
    table_has_separator = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 跳过代码块
        if stripped.startswith('```'):
            in_fence = not in_fence
            in_table = False
            result.append(line)
            continue

        if in_fence:
            result.append(line)
            continue

        # 判断是否为分隔行
        is_separator = (
            stripped.startswith('|') and
            all(c in '-| :' for c in stripped)
            and '---' in stripped
        )

        # 判断是否为表格数据行
        is_table_row = (
            stripped.startswith('|') and
            stripped.count('|') >= 2 and
            not is_separator
        )

        if is_separator:
            in_table = True
            table_has_separator = True
            result.append(line)
        elif is_table_row:
            if not in_table:
                # 刚进入新表格，这是第一行（表头）
                in_table = True
                table_has_separator = False
                result.append(line)
                # 检查下一行是否已经是分隔行
                next_i = i + 1
                if next_i < len(lines):
                    next_s = lines[next_i].strip()
                    next_is_sep = (
                        next_s.startswith('|') and
                        all(c in '-| :' for c in next_s)
                        and '---' in next_s
                    )
                    if not next_is_sep:
                        # 缺少分隔行，自动生成
                        cols = stripped.count('|') - 1
                        if cols < 1:
                            cols = 1
                        separator = '|' + '|'.join([' --- '] * cols) + '|'
                        result.append(separator)
                        table_has_separator = True
            else:
                # 已在表格中，正常数据行
                result.append(line)
        else:
            # 非表格行，重置状态
            in_table = False
            table_has_separator = False
            result.append(line)

    return '\n'.join(result)


def _auto_fence_ascii_art(md_content):
    """
    自动检测 ASCII 框图/流程图并包裹成代码块，
    避免 markdown 库将其当普通段落处理导致空格丢失和 &nbsp; 泄漏。
    检测规则：连续行中包含 box-drawing Unicode 字符（┌│├└┐┤┘─═║ 等）
    """
    BOX_CHARS = set('┌┐└┘├┤┬┴┼─│═║╔╗╚╝╠╣╦╩╬▼▶◀▲↓↑←→')
    lines = md_content.split('\n')
    result = []
    in_art_block = False
    art_buffer = []
    in_existing_fence = False

    for line in lines:
        stripped = line.strip()

        # 跳过已有的代码块
        if stripped.startswith('```'):
            in_existing_fence = not in_existing_fence
            if in_art_block:
                result.append('```')
                result.extend(art_buffer)
                art_buffer = []
                in_art_block = False
            result.append(line)
            continue

        if in_existing_fence:
            result.append(line)
            continue

        # 判断该行是否包含 box-drawing 字符
        has_box = any(c in BOX_CHARS for c in line)

        if has_box and not in_art_block:
            # 开始 ASCII art 块
            in_art_block = True
            art_buffer = [line]
        elif has_box and in_art_block:
            # 继续 ASCII art 块
            art_buffer.append(line)
        elif not has_box and in_art_block:
            # ASCII art 块结束，包裹成代码块
            result.append('```')
            result.extend(art_buffer)
            result.append('```')
            art_buffer = []
            in_art_block = False
            result.append(line)
        else:
            result.append(line)

    # 处理文件末尾的 art 块
    if in_art_block and art_buffer:
        result.append('```')
        result.extend(art_buffer)
        result.append('```')

    return '\n'.join(result)


def markdown_to_wechat_html(md_content, token=None, image_dir=None):
    """Markdown → 微信兼容 HTML（莫兰迪学术风内联样式 + 图片上传）

    预处理顺序：剥 H1 → 包 ASCII 框图为代码块 → 修表格分隔 → 转 HTML → 注入内联样式
    """

    # 处理本地图片引用
    if token and image_dir:
        image_dir = Path(image_dir)

        def replace_image(match):
            img_path = match.group(2)
            if img_path.startswith("http"):
                return match.group(0)
            full_path = image_dir / img_path
            if full_path.exists():
                try:
                    url = upload_article_image(full_path, token)
                    return f"![{match.group(1)}]({url})"
                except Exception as e:
                    print(f"  ⚠️ 图片上传失败 {img_path}: {e}")
            return match.group(0)

        md_content = re.sub(r'!\[(.*?)\]\((.*?)\)', replace_image, md_content)

    # 预处理：剥掉正文开头的 H1（微信顶栏已显示标题，避免重复）
    md_content = _strip_leading_h1(md_content)

    # 预处理：unwrap 误用的单行 fenced code（AI 经常把强调短语包成代码块）
    md_content = _unwrap_misused_fenced_code(md_content)

    # 预处理：自动检测 ASCII 框图并包裹成代码块
    md_content = _auto_fence_ascii_art(md_content)

    # 预处理：自动修复缺少分隔行的 markdown 表格
    md_content = _auto_fix_tables(md_content)

    # Markdown → HTML
    # 注意：禁用 indented code block（4 空格缩进），只保留 ``` fenced code，
    # 否则正文里被意外缩进的列表项/段落会被识别成代码块。
    md_parser = markdown.Markdown(
        extensions=[
            "markdown.extensions.tables",
            "markdown.extensions.fenced_code",
            "markdown.extensions.codehilite",
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
        ]
    )
    md_parser.parser.blockprocessors.deregister("code")
    html_body = md_parser.convert(md_content)

    # 清理 class/id 属性（markdown 扩展可能添加的）
    html_body = re.sub(r'\s+class="[^"]*"', '', html_body)
    html_body = re.sub(r'\s+id="[^"]*"', '', html_body)

    # 注入内联样式（微信兼容，不依赖 <style> 标签）
    html_body = _apply_inline_styles(html_body)

    # 用内联样式 div 包裹，不使用 class
    return f'<div style="{WRAPPER_STYLE}">\n{html_body}\n</div>'


def create_draft(title, content_html, thumb_media_id, token):
    """调用微信 Draft API 创建草稿"""

    article = {
        "title": title,
        "content": content_html,
        "content_source_url": "",
    }
    if thumb_media_id:
        article["thumb_media_id"] = thumb_media_id

    payload = {"articles": [article]}

    print(f"\n📝 创建草稿: 《{title}》")
    resp = requests.post(
        API_ADD_DRAFT,
        params={"access_token": token},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    data = resp.json()
    if "media_id" not in data:
        raise RuntimeError(f"创建草稿失败: {data.get('errmsg', data)}")

    print(f"✅ 草稿创建成功！media_id: {data['media_id'][:30]}...")
    return data["media_id"]


def extract_title_from_md(md_content):
    """从 Markdown 提取标题"""
    for line in md_content.strip().split("\n"):
        line = line.strip()
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return f"文章_{datetime.now().strftime('%Y%m%d_%H%M')}"


# ============================================================
# 主入口
# ============================================================

def publish_from_markdown(md_file, cover_image=None, app_id=None, app_secret=None):
    """
    一键入口：从 Markdown 文件创建微信公众号草稿

    参数：
        md_file: Markdown 文件路径
        cover_image: 封面图路径（可选）
        app_id: AppID（可选，默认从环境变量/配置读取）
        app_secret: AppSecret（可选，默认从环境变量/配置读取）
    """
    md_file = Path(md_file)
    if not md_file.exists():
        raise FileNotFoundError(f"Markdown 文件不存在: {md_file}")

    print("=" * 50)
    print(f"🚀 开始处理: {md_file.name}")
    print("=" * 50)

    # 1. 加载凭证
    app_id, app_secret = load_credentials(app_id, app_secret)

    # 2. 读取 Markdown
    md_content = md_file.read_text(encoding="utf-8")
    title = extract_title_from_md(md_content)
    print(f"📄 标题: {title}")

    # 3. 获取 token
    token = get_access_token(app_id, app_secret)

    # 4. 转换 HTML
    print("\n🔄 转换 Markdown → 微信 HTML...")
    html_content = markdown_to_wechat_html(md_content, token=token, image_dir=md_file.parent)
    print(f"  ✅ HTML 生成完毕（{len(html_content)} 字符）")

    # 5. 上传封面图
    thumb_media_id = ""
    if cover_image:
        cover_path = Path(cover_image)
        if cover_path.exists():
            thumb_media_id = upload_cover_image(cover_path, token)
        else:
            print(f"⚠️ 指定的封面图不存在: {cover_path}，使用默认封面")

    if not thumb_media_id:
        if DEFAULT_COVER_IMAGE.exists():
            print("🖼️ 使用默认封面图...")
            thumb_media_id = upload_cover_image(DEFAULT_COVER_IMAGE, token)
        else:
            raise FileNotFoundError(
                f"微信要求草稿必须有封面图！\n"
                f"请通过 --cover 指定封面，或将默认封面放到: {DEFAULT_COVER_IMAGE}"
            )

    # 6. 创建草稿
    media_id = create_draft(title, html_content, thumb_media_id, token)

    print("\n" + "=" * 50)
    print("🎉 全部完成！")
    print(f"  标题: 《{title}》")
    print(f"  草稿ID: {media_id[:30]}...")
    print("  📱 打开手机公众号App → 草稿箱 → 点发布！")
    print("=" * 50)

    return media_id


# ============================================================
# 工具函数
# ============================================================

def _get_mime_type(file_path):
    ext = Path(file_path).suffix.lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "application/octet-stream")


def test_connection(app_id=None, app_secret=None):
    """测试 API 连接"""
    print("🧪 测试 API 连接...")
    try:
        cred_id, cred_secret = load_credentials(app_id, app_secret)
        token = get_access_token(cred_id, cred_secret, force_refresh=True)
        print(f"✅ 连接成功！Token: {token[:20]}...")
        return True
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="微信公众号半自动发文 — Markdown → 草稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python wechat_draft_publisher.py --test
  python wechat_draft_publisher.py -m article.md
  python wechat_draft_publisher.py -m article.md -c cover.jpg
        """
    )

    parser.add_argument("--test", action="store_true", help="测试 API 连接")
    parser.add_argument("--markdown", "-m", type=str, help="Markdown 文件路径")
    parser.add_argument("--cover", "-c", type=str, help="封面图路径（推荐 900x383）")
    parser.add_argument("--app-id", type=str, help="微信 AppID（也可用环境变量 WECHAT_APP_ID）")
    parser.add_argument("--app-secret", type=str, help="微信 AppSecret（也可用环境变量 WECHAT_APP_SECRET）")

    args = parser.parse_args()

    if args.test:
        test_connection(args.app_id, args.app_secret)
        return

    if not args.markdown:
        parser.print_help()
        print("\n❌ 请指定 --markdown 参数！")
        return

    publish_from_markdown(
        md_file=args.markdown,
        cover_image=args.cover,
        app_id=args.app_id,
        app_secret=args.app_secret
    )


if __name__ == "__main__":
    main()
