import html
import re
import base64

import streamlit as st
import streamlit.components.v1 as components


def _inline_format(text: str) -> str:
    text = html.escape(text, quote=True)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text


def markdown_to_html(md: str) -> str:
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    out: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    for raw in lines:
        line = raw.rstrip()

        if not line.strip():
            close_lists()
            continue

        if line.startswith("### "):
            close_lists()
            out.append(f"<h3>{_inline_format(line[4:].strip())}</h3>")
            continue

        if line.startswith("## "):
            close_lists()
            out.append(f"<h2>{_inline_format(line[3:].strip())}</h2>")
            continue

        if line.startswith("# "):
            close_lists()
            out.append(f"<h1>{_inline_format(line[2:].strip())}</h1>")
            continue

        m_ol = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if m_ol:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline_format(m_ol.group(2).strip())}</li>")
            continue

        m_ul = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if m_ul:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_format(m_ul.group(1).strip())}</li>")
            continue

        close_lists()
        out.append(f"<p>{_inline_format(line.strip())}</p>")

    close_lists()
    return "\n".join(out)


def build_export_html(
    *,
    base_css: str,
    orientation: str,
    sides: str,
    font_px: int,
    columns: int,
    content_html: str,
    filename: str,
) -> str:
    landscape = not orientation.startswith("纵向")
    page_w = "297mm" if landscape else "210mm"
    page_h = "210mm" if landscape else "297mm"

    # For PDF we render real A4 pages (not aspect-ratio scaling) and use JS to
    # sequentially fill page 1 then page 2 (if duplex).
    page_count = 1 if sides.startswith("单面") else 2
    page_blocks = []
    for i in range(1, page_count + 1):
        page_blocks.append(
            f"""
            <div class="a4-paper pdf-page" id="page{i}">
              <div class="a4-inner">
                <div class="content" id="page{i}Content" style="font-size: {font_px}px; column-count: {columns};"></div>
              </div>
              <div class="page-label">第 {i} 面</div>
            </div>
            """
        )

    # Hide on-screen-only banners and force print-friendly sizing.
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    {base_css}
    <style>
      body {{
        margin: 0;
        padding: 0;
        background: #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif;
      }}
      .canvas-wrap {{ background: #ffffff; padding: 0; min-height: auto; }}
      .page-label {{
        position: absolute;
        right: 14px;
        bottom: 12px;
        font-size: 11px;
        color: rgba(0,0,0,0.35);
        letter-spacing: 0.2px;
        user-select: none;
      }}
      .pdf-stack {{
        width: 100%;
        display: block;
        padding: 0;
        margin: 0;
      }}
      .pdf-page {{
        width: {page_w};
        height: {page_h};
        margin: 0;
        border-radius: 0;
        box-shadow: none;
        overflow: hidden;
        page-break-after: always;
      }}
      .pdf-page:last-child {{ page-break-after: auto; }}
      /* Keep export layout consistent with in-app preview */
      .a4-inner {{ padding: 28px 26px; }}
      @page {{
        size: A4 {"landscape" if landscape else "portrait"};
        margin: 0;
      }}
      @media print {{
        .pdf-page {{ box-shadow: none !important; }}
        #source {{ display: none !important; }}
      }}
      /* ensure we never split blocks across columns/pages */
      .content h1, .content h2, .content h3, .content p, .content li, .content ul, .content ol {{
        break-inside: avoid;
        page-break-inside: avoid;
        -webkit-column-break-inside: avoid;
      }}
      .content {{
        column-gap: 25px;
        column-rule: 1px solid #eaeaea;
        column-fill: auto;
        line-height: 1.35;
      }}
      html, body {{ overflow: hidden; }}
    </style>
  </head>
  <body>
    <div class="canvas-wrap">
      <div class="pdf-stack" id="stack">
        {''.join(page_blocks)}
      </div>
    </div>

    <div id="source" style="position: fixed; left: -200vw; top: -200vh; width: {page_w}; height: 0; overflow: hidden;">
      <div style="font-size: {font_px}px; column-count: {columns}; column-gap: 25px; column-rule: 1px solid #eaeaea; column-fill: auto; line-height: 1.35;">
        {content_html}
      </div>
    </div>

    <script>
      function clearEl(el) {{
        while (el.firstChild) el.removeChild(el.firstChild);
      }}
      function isOverflowing(el) {{
        return (el.scrollWidth > el.clientWidth + 2) || (el.scrollHeight > el.clientHeight + 2);
      }}
      function fillPageSequential(targetEl, blocks) {{
        clearEl(targetEl);
        const accepted = [];
        for (const node of blocks) {{
          const clone = node.cloneNode(true);
          targetEl.appendChild(clone);
          if (!isOverflowing(targetEl)) {{
            accepted.push(node);
          }} else {{
            targetEl.removeChild(clone);
            break;
          }}
        }}
        return accepted.length;
      }}
      function paginate() {{
        const source = document.querySelector('#source > div');
        const blocks = Array.from(source.children);
        let rest = blocks;
        for (let i = 1; i <= {page_count}; i++) {{
          const content = document.getElementById(`page${{i}}Content`);
          const n = fillPageSequential(content, rest);
          rest = rest.slice(n);
        }}
        const src = document.getElementById('source');
        if (src) src.remove();
      }}
    </script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <script>
      function exportPdf() {{
        const stack = document.getElementById('stack');
        if (!stack || !window.html2pdf) return;
        const opt = {{
          margin:       0,
          filename:     "{filename}",
          image:        {{ type: 'jpeg', quality: 0.98 }},
          html2canvas:  {{ scale: 2, useCORS: true }},
          jsPDF:        {{ unit: 'mm', format: 'a4', orientation: '{'landscape' if landscape else 'portrait'}' }}
        }};
        window.html2pdf().set(opt).from(stack).save();
      }}
      window.addEventListener('load', () => {{
        setTimeout(() => {{
          paginate();
          setTimeout(exportPdf, 200);
        }}, 60);
      }});
    </script>
  </body>
</html>
"""


DEFAULT_MD = """# CheatSheet Pro 一页纸速记模板

## 1. 核心概念速览（必背）

- **定义**：用一句话说明概念的本质
- **关键点**：列出 3-5 个最容易丢分的细节
- **常见陷阱**：写出最容易混淆的反例/边界条件

## 2. 公式与结论（可直接套用）

1. **结论 A**：适用条件 + 结果（别漏前提）
2. **结论 B**：推导思路（只写关键一步）
3. **结论 C**：极端情况/特例（考试爱考）

## 3. 题型套路（拿分最快）

- 看到题干关键词 → 先判断属于哪一类题型
- 先写结论再补过程：步骤清晰、得分点不遗漏
- 图表题：先读坐标轴/单位，再看趋势，再下结论

## 4. 长段落测试（排版与截断效果）

这是一段用于测试多栏排版的长文本：在期末开卷考试中，时间往往比知识更稀缺。把几十页笔记压缩到一张 A4 的关键不是“写得多”，而是“信息密度与可检索性”。请把最常考的定义、公式、条件、反例、步骤写成最短的可复用模块，并通过标题层级与列表结构让眼睛能在 1-2 秒内定位到答案所在位置。你可以把每个小节当作一张“知识卡片”：标题是问题，列表是要点，最后再用一句话写最容易失分的细节提醒。
"""


st.set_page_config(layout="wide", page_title="CheatSheet Pro")

BASE_CSS = """
<style>
/* Make the left dashboard compact */
section[data-testid="stSidebar"] { display: none; }
.block-container { padding-top: 2.0rem; padding-bottom: 1.2rem; }
div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="column"]) { gap: 0.9rem; }

.cs-panel {
  background: #ffffff;
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 14px;
  padding: 20px 14px 12px 14px;
  box-shadow: 0 8px 26px rgba(0,0,0,0.06);
  position: relative;
  overflow: visible;
}
.cs-panel::before{
  content: "";
  position: absolute;
  left: 12px;
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 10px;
  background: linear-gradient(180deg, #4f8cff, #7c5cff);
  opacity: 0.95;
}
.cs-head{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-left: 10px;
  margin-bottom: 8px;
}
.cs-title {
  font-weight: 800;
  font-size: 16px;
  line-height: 1.45;
  margin: 0;
  letter-spacing: 0.1px;
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
}
.cs-badge{
  font-size: 11px;
  line-height: 1;
  padding: 6px 9px;
  border-radius: 999px;
  color: rgba(40, 48, 66, 0.85);
  background: rgba(79, 140, 255, 0.10);
  border: 1px solid rgba(79, 140, 255, 0.20);
  white-space: nowrap;
}
.cs-subtle {
  color: rgba(0,0,0,0.55);
  font-size: 12px;
  line-height: 1.35;
  padding-left: 10px;
  margin: 0 0 10px 0;
}

.cs-control-title{
  font-weight: 800;
  font-size: 13px;
  line-height: 1.7;
  padding: 8px 0 4px 0;
  margin: 0;
  color: rgba(0,0,0,0.88);
  overflow: visible;
}
div[data-testid="stMarkdownContainer"]{ overflow: visible; }

/* Preview canvas */
.canvas-wrap{
  background: #f0f2f6;
  border-radius: 18px;
  padding: 22px;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  min-height: calc(100vh - 140px);
}
.a4-paper{
  width: min(980px, 100%);
  background: #ffffff;
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.15);
  overflow: hidden; /* no internal scroll; content must be concise */
  position: relative;
}
.a4-inner{
  height: 100%;
  width: 100%;
  padding: 28px 26px;
  box-sizing: border-box;
}
.content{
  height: 100%;
  column-gap: 25px;
  column-rule: 1px solid #eaeaea;
  column-fill: auto;
  line-height: 1.35;
}
.content h1, .content h2, .content h3, .content p, .content li {
  break-inside: avoid;
  page-break-inside: avoid;
  -webkit-column-break-inside: avoid;
}
.content h1 { font-size: 1.55em; margin: 0 0 0.45em 0; }
.content h2 { font-size: 1.25em; margin: 0.65em 0 0.35em 0; }
.content h3 { font-size: 1.10em; margin: 0.55em 0 0.25em 0; }
.content p  { margin: 0 0 0.45em 0; }
.content ul, .content ol { margin: 0 0 0.55em 1.1em; padding: 0; }
.content li { margin: 0.12em 0; }
.content strong { font-weight: 700; }
@media print {
  /* 只打印右侧 A4 预览区域 */
  html, body {
    margin: 0;
    padding: 0;
    background: #ffffff !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  /* 隐藏 Streamlit 自己的框架和左侧控制区 */
  main, header, footer, section, [data-testid="stSidebar"], [data-testid="stHeader"] {
    visibility: hidden !important;
  }
  /* 仅让画布和纸张可见并参与打印 */
  .canvas-wrap, .canvas-wrap * {
    visibility: visible !important;
  }
  .canvas-wrap {
    position: fixed;
    inset: 0;
    margin: 0;
    padding: 0;
    border-radius: 0;
    background: #ffffff !important;
    box-shadow: none !important;
    display: flex;
    justify-content: center;
    align-items: flex-start;
  }
  .viewport {
    width: auto !important;
    height: auto !important;
  }
  .scaler {
    transform: none !important; /* 打印使用真实 A4 尺寸，不再缩放 */
  }
  .a4-paper {
    box-shadow: none !important;
    border-radius: 0;
  }
}
</style>
"""

st.markdown(BASE_CSS, unsafe_allow_html=True)


col_left, col_right = st.columns([3, 7], vertical_alignment="top")

with col_left:
    st.markdown(
        """
<div class="cs-panel">
  <div class="cs-head">
    <div class="cs-title">CheatSheet Pro</div>
    <div class="cs-badge">A4 排版预览</div>
  </div>
  <div class="cs-subtle">左侧输入，右侧实时 A4 分栏预览（超出即截断）</div>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.container():
        orientation = st.radio(
            "纸张方向",
            ["纵向 (Portrait)", "横向 (Landscape)"],
            horizontal=True,
            label_visibility="visible",
        )
        sides = st.radio(
            "纸张使用",
            ["单面 (1页)", "双面 (2页)"],
            horizontal=True,
            label_visibility="visible",
        )

        c1, c2 = st.columns(2)
        with c1:
            font_px = st.slider("全局字体大小(px)", min_value=8, max_value=16, value=11, step=1)
        with c2:
            columns = st.slider("分栏数量", min_value=1, max_value=4, value=3, step=1)

        md_text = st.text_area(
            "输入 Markdown 内容",
            value=DEFAULT_MD,
            height=520,
        )

        chars_with_ws = len(md_text or "")
        chars_no_ws = len(re.sub(r"\s+", "", md_text or ""))
        lines_count = (md_text or "").count("\n") + 1 if (md_text or "") else 0
        st.caption(f"字数统计：不含空格 {chars_no_ws} ｜ 含空格 {chars_with_ws} ｜ 行数 {lines_count}")

        st.markdown("")
        st.caption("导出将按当前：单/双面、横/竖版、字号、分栏生成 A4 PDF；云端推荐使用浏览器打印为 PDF。")
        export_now = st.button("导出 PDF（点击直接下载）", use_container_width=True)
        print_now = st.button("浏览器打印 / 导出 PDF（云端推荐）", use_container_width=True)


aspect_ratio = "1 / 1.414" if orientation.startswith("纵向") else "1.414 / 1"
content_html = markdown_to_html(md_text)
preview_height = 1800 if orientation.startswith("纵向") else 1200
is_landscape = not orientation.startswith("纵向")
paper_w = "297mm" if is_landscape else "210mm"
paper_h = "210mm" if is_landscape else "297mm"


@st.cache_data(show_spinner=False)
def _cached_pdf(
    md: str,
    orientation_value: str,
    sides_value: str,
    font_px_value: int,
    columns_value: int,
) -> bytes:
    # 仅保留签名以避免缓存失效错误；实际 PDF 由前端 html2pdf 生成
    return b""


if export_now:
    filename = "CheatSheet-Pro-双面.pdf" if sides.startswith("双面") else "CheatSheet-Pro-单面.pdf"
    with st.spinner("导出 PDF 生成中…"):
        try:
            components.html(
                build_export_html(
                    base_css=BASE_CSS,
                    orientation=orientation,
                    sides=sides,
                    font_px=font_px,
                    columns=columns,
                    content_html=content_html,
                    filename=filename,
                ),
                height=0,
                scrolling=False,
            )
            st.success("浏览器正在生成并下载 PDF（如果被拦截，请允许下载后重试）。")
        except Exception as e:
            st.error(str(e))
<!doctype html>
<html>
  <head><meta charset="utf-8" /></head>
  <body>
    <script>
      (function() {{
        const b64 = "{b64}";
        const binary = atob(b64);
        const len = binary.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], {{ type: "application/pdf" }});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "{filename}";
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {{
          URL.revokeObjectURL(url);
          a.remove();
        }}, 1500);
      }})();
    </script>
  </body>
</html>
""",
                height=0,
                scrolling=False,
            )
            st.success("已开始下载 PDF（如果浏览器拦截下载，请允许本地下载后重试）。")
        except Exception as e:
            st.error(str(e))

if print_now:
    components.html(
        """
<!doctype html>
<html>
  <head><meta charset="utf-8" /></head>
  <body>
    <script>
      window.addEventListener('load', function () {
        window.print();
      });
    </script>
  </body>
</html>
""",
        height=0,
        scrolling=False,
    )

with col_right:
    if sides.startswith("单面"):
        single_html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    {BASE_CSS}
    <style>
      body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif; }}
      .canvas-wrap {{ min-height: auto; }}
      :root {{ --paper-w: {paper_w}; --paper-h: {paper_h}; --scale: 1; }}
      .viewport {{ width: 100%; height: 100%; display: flex; justify-content: center; }}
      .scaler {{ width: var(--paper-w); height: var(--paper-h); transform: scale(var(--scale)); transform-origin: top center; }}
      .stage {{ width: var(--paper-w); height: var(--paper-h); position: relative; }}
      .a4-paper {{ width: 100%; height: 100%; position: absolute; inset: 0; }}
      .overflow-banner {{
        position: absolute;
        left: 14px;
        right: 14px;
        top: 14px;
        z-index: 10;
        display: none;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(255, 244, 214, 0.98);
        border: 1px solid rgba(232, 190, 106, 0.7);
        color: rgba(74, 52, 0, 0.92);
        font-size: 12px;
        line-height: 1.25;
        box-shadow: 0 10px 24px rgba(0,0,0,0.10);
      }}
      .show-overflow .overflow-banner {{ display: block; }}
      html, body {{ overflow-x: hidden; }}
    </style>
  </head>
  <body>
    <div class="canvas-wrap">
      <div class="viewport" id="viewport">
        <div class="scaler" id="scaler">
          <div class="stage" id="stage">
            <div class="a4-paper" id="page1">
              <div class="overflow-banner" id="banner">
                内容超出 A4 预览范围：请<strong>缩小字体</strong>或<strong>删减字数</strong>（超出部分将被截断）
              </div>
              <div class="a4-inner">
                <div class="content" id="page1Content" style="font-size: {font_px}px; column-count: {columns};"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div id="source" style="position: absolute; left: -99999px; top: -99999px; width: 980px;">
      <div style="font-size: {font_px}px; column-count: {columns}; column-gap: 25px; column-rule: 1px solid #eaeaea; column-fill: auto; line-height: 1.35;">
        {content_html}
      </div>
    </div>
    <script>
      function updateScale() {{
        const viewport = document.getElementById('viewport');
        const scaler = document.getElementById('scaler');
        if (!viewport || !scaler) return;
        const vw = viewport.clientWidth;
        const vh = viewport.clientHeight;
        const pw = scaler.offsetWidth;
        const ph = scaler.offsetHeight;
        if (!pw || !ph) return;
        const s = Math.min(vw / pw, vh / ph, 1);
        document.documentElement.style.setProperty('--scale', String(s));
      }}

      function clearEl(el) {{
        while (el.firstChild) el.removeChild(el.firstChild);
      }}

      function isOverflowing(el) {{
        // For multi-column layout, overflow often happens horizontally (more columns to the right)
        // For single-column, overflow happens vertically.
        return (el.scrollWidth > el.clientWidth + 2) || (el.scrollHeight > el.clientHeight + 2);
      }}

      function fillPageSequential(targetEl, blocks) {{
        clearEl(targetEl);
        const accepted = [];
        for (const node of blocks) {{
          const clone = node.cloneNode(true);
          targetEl.appendChild(clone);
          if (!isOverflowing(targetEl)) {{
            accepted.push(node);
          }} else {{
            targetEl.removeChild(clone);
            break;
          }}
        }}
        return accepted.length;
      }}

      function renderAndCheck() {{
        const stage = document.getElementById('stage');
        const page1 = document.getElementById('page1');
        const page1Content = document.getElementById('page1Content');
        if (!stage || !page1 || !page1Content) return;
        stage.classList.remove('show-overflow');

        const source = document.querySelector('#source > div');
        const blocks = Array.from(source.children);

        const n1 = fillPageSequential(page1Content, blocks);
        const rest = blocks.slice(n1);
        if (rest.length > 0) {{
          stage.classList.add('show-overflow');
        }}
      }}

      window.addEventListener('load', () => {{
        updateScale();
        setTimeout(() => {{
          updateScale();
          renderAndCheck();
        }}, 90);
      }});
      window.addEventListener('resize', () => {{
        clearTimeout(window.__csResizeT);
        window.__csResizeT = setTimeout(() => {{
          updateScale();
          renderAndCheck();
        }}, 160);
      }});
    </script>
  </body>
</html>
"""
        components.html(single_html, height=preview_height, scrolling=False)
    else:
        st.markdown('<div class="cs-control-title">预览页</div>', unsafe_allow_html=True)
        preview_page = st.radio(
            "预览页",
            ["第 1 面", "第 2 面"],
            horizontal=True,
            label_visibility="collapsed",
        )
        selected_page = 1 if preview_page.startswith("第 1") else 2

        duplex_html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    {BASE_CSS}
    <style>
      body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif; }}
      .canvas-wrap {{ min-height: auto; }}
      :root {{ --paper-w: {paper_w}; --paper-h: {paper_h}; --scale: 1; }}
      .viewport {{ width: 100%; height: 100%; display: flex; justify-content: center; }}
      .scaler {{ width: var(--paper-w); height: var(--paper-h); transform: scale(var(--scale)); transform-origin: top center; }}
      .stage {{ width: var(--paper-w); height: var(--paper-h); position: relative; background: transparent; }}
      .a4-paper {{ width: 100%; position: absolute; inset: 0; transition: opacity 120ms ease; }}
      .a4-paper.inactive {{ opacity: 0; pointer-events: none; }}
      .a4-paper.active {{ opacity: 1; pointer-events: auto; }}
      .page-label {{
        position: absolute;
        right: 14px;
        bottom: 12px;
        font-size: 11px;
        color: rgba(0,0,0,0.35);
        letter-spacing: 0.2px;
        user-select: none;
      }}
      .a4-paper.empty {{ opacity: 0; pointer-events: none; }}
      .empty-state {{
        position: absolute;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        color: rgba(0,0,0,0.45);
        font-size: 13px;
        text-align: center;
        padding: 24px;
        box-sizing: border-box;
      }}
      .show-empty .empty-state {{ display: flex; }}
      .overflow-banner {{
        position: absolute;
        left: 14px;
        right: 14px;
        top: 14px;
        z-index: 20;
        display: none;
        padding: 10px 12px;
        border-radius: 10px;
        background: rgba(255, 244, 214, 0.98);
        border: 1px solid rgba(232, 190, 106, 0.7);
        color: rgba(74, 52, 0, 0.92);
        font-size: 12px;
        line-height: 1.25;
        box-shadow: 0 10px 24px rgba(0,0,0,0.10);
      }}
      .show-overflow .overflow-banner {{ display: block; }}
      /* Inside iframe: disable any accidental scrollbars */
      html, body {{ overflow-x: hidden; }}
    </style>
  </head>
  <body>
    <div class="canvas-wrap">
      <div class="viewport" id="viewport">
        <div class="scaler" id="scaler">
          <div class="stage" id="stage">
            <div class="overflow-banner" id="overflowBanner">
              内容超出双面 A4 预览范围：请<strong>缩小字体</strong>或<strong>删减字数</strong>（超出部分将被截断）
            </div>
            <div class="a4-paper {'active' if selected_page == 1 else 'inactive'}" id="page1">
              <div class="a4-inner">
                <div class="content" id="page1Content" style="font-size: {font_px}px; column-count: {columns};"></div>
              </div>
              <div class="page-label">第 1 面</div>
            </div>
            <div class="a4-paper {'active' if selected_page == 2 else 'inactive'}" id="page2">
              <div class="a4-inner">
                <div class="content" id="page2Content" style="font-size: {font_px}px; column-count: {columns};"></div>
              </div>
              <div class="page-label">第 2 面</div>
            </div>
            <div class="empty-state" id="emptyState">第 2 面暂无内容（第 1 面还没写满）</div>
          </div>
        </div>
      </div>
    </div>

    <div id="source" style="position: absolute; left: -99999px; top: -99999px; width: 980px;">
      <div style="font-size: {font_px}px; column-count: {columns}; column-gap: 25px; column-rule: 1px solid #eaeaea; column-fill: auto; line-height: 1.35;">
        {content_html}
      </div>
    </div>

    <script>
      function updateScale() {{
        const viewport = document.getElementById('viewport');
        const scaler = document.getElementById('scaler');
        if (!viewport || !scaler) return;
        const vw = viewport.clientWidth;
        const vh = viewport.clientHeight;
        const pw = scaler.offsetWidth;
        const ph = scaler.offsetHeight;
        if (!pw || !ph) return;
        const s = Math.min(vw / pw, vh / ph, 1);
        document.documentElement.style.setProperty('--scale', String(s));
      }}

      function clearEl(el) {{
        while (el.firstChild) el.removeChild(el.firstChild);
      }}

      function isOverflowing(el) {{
        return (el.scrollWidth > el.clientWidth + 2) || (el.scrollHeight > el.clientHeight + 2);
      }}

      function fillPageSequential(targetEl, blocks) {{
        clearEl(targetEl);
        const accepted = [];

        for (const node of blocks) {{
          const clone = node.cloneNode(true);
          targetEl.appendChild(clone);
          if (!isOverflowing(targetEl)) {{
            accepted.push(node);
          }} else {{
            targetEl.removeChild(clone);
            break;
          }}
        }}

        return accepted.length;
      }}

      function paginateTwoPages() {{
        const stage = document.getElementById('stage');
        const page1 = document.getElementById('page1');
        const page2 = document.getElementById('page2');
        const page1Content = document.getElementById('page1Content');
        const page2Content = document.getElementById('page2Content');
        const emptyState = document.getElementById('emptyState');
        const overflowBanner = document.getElementById('overflowBanner');

        clearEl(page1Content);
        clearEl(page2Content);
        stage.classList.remove('show-empty');
        stage.classList.remove('show-overflow');

        // Build a block list from the source HTML (treat UL/OL as blocks to avoid splitting)
        const source = document.querySelector('#source > div');
        const blocks = Array.from(source.children);

        // Fill page 1 strictly first
        const n1 = fillPageSequential(page1Content, blocks);
        const rest = blocks.slice(n1);

        // Fill page 2 only after page 1 is full (or no more content)
        if (rest.length > 0) {{
          const n2 = fillPageSequential(page2Content, rest);
          page2.classList.remove('empty');
          const stillRest = rest.slice(n2);
          if (stillRest.length > 0) {{
            stage.classList.add('show-overflow');
          }}
        }} else {{
          page2.classList.add('empty');
          stage.classList.add('show-empty');
        }}
      }}

      // Run after layout settles
      window.addEventListener('load', () => {{
        updateScale();
        setTimeout(() => {{
          updateScale();
          paginateTwoPages();
        }}, 90);
      }});
      window.addEventListener('resize', () => {{
        clearTimeout(window.__csResizeT);
        window.__csResizeT = setTimeout(() => {{
          updateScale();
          paginateTwoPages();
        }}, 160);
      }});
    </script>
  </body>
</html>
"""
        components.html(duplex_html, height=preview_height, scrolling=False)

