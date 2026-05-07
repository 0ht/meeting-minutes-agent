"""
Meeting Minutes Agent — Streamlit Frontend
==========================================
Communicates with the FastAPI backend (BACKEND_URL env var).
Within Container Apps the backend is on the private network (internal ingress).
"""
from __future__ import annotations

import io
import os
import re
import time
from datetime import datetime
from typing import Optional

import requests
import streamlit as st

# ── Configuration ─────────────────────────────────────────────────────────────
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "3"))
# Max wait time for the whole pipeline. Long audio + 3 LLM stages can easily
# exceed 5 minutes, so default to 60 minutes worth of polls.
MAX_WAIT_SECONDS = int(os.environ.get("MAX_WAIT_SECONDS", "3600"))
MAX_POLLS = max(1, MAX_WAIT_SECONDS // max(1, POLL_INTERVAL))

# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="会議議事録エージェント",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* Global font: 1 step smaller across the app */
html { font-size: 14px; }
.stApp, .stMarkdown, .stTextInput, .stTextArea, .stButton, .stTabs,
.stSelectbox, .stExpander, .stCaption, .stMetric { font-size: 0.92rem; }
h1 { font-size: 1.7rem !important; }
h2 { font-size: 1.35rem !important; }
h3 { font-size: 1.1rem !important; }
h4 { font-size: 1.0rem !important; }

/* Header */
.app-header {
    background: linear-gradient(135deg, #0078d4 0%, #004578 100%);
    color: white;
    padding: 20px 28px;
    border-radius: 12px;
    margin-bottom: 20px;
    text-align: center;
}
.app-header h1 { font-size: 1.7rem !important; margin: 0 0 6px; }
.app-header p  { font-size: 0.9rem; opacity: 0.85; margin: 0; }

/* Section headers */
.section-label {
    font-size: 0.92rem;
    font-weight: 600;
    color: #005a9e;
    margin-bottom: 4px;
}

/* Pipeline step cards */
.step-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid #e1dfdd;
    background: #f3f2f1;
    margin-bottom: 8px;
    font-size: 0.86rem;
}
.step-card.done    { border-color: #107c10; background: #dff6dd; }
.step-card.active  { border-color: #0078d4; background: #c7e0f4; }
.step-card.error   { border-color: #a4262c; background: #fde7e9; }
.step-card.pending { border-color: #e1dfdd; background: #f3f2f1; color: #a19f9d; }

/* Result markdown tweaks */
.minutes-box {
    background: #ffffff;
    border: 1px solid #e1dfdd;
    border-radius: 8px;
    padding: 18px 22px;
}
.stDownloadButton > button {
    background: #0078d4 !important;
    color: white !important;
}

/* Hide Streamlit branding */
#MainMenu, footer { visibility: hidden; }

/* Agent detail panel */
.detail-panel {
    border-left: 3px solid #0078d4;
    padding-left: 12px;
}
.detail-panel h4 { color: #0078d4; margin-bottom: 8px; }

/* Topic summary line in 議事 section */
.topic-summary {
    color: #424242;
    margin: 4px 0 6px 0;
    font-size: 0.92rem;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── Session state defaults ────────────────────────────────────────────────────
# Keys here are managed manually (not bound to a widget). The toggle's
# ``show_agent_detail`` key is intentionally NOT included — Streamlit forbids
# direct assignment to a key once a widget with that key has been instantiated,
# which used to crash the "新しい議事録" reset path.
_DEFAULTS: dict = {
    "page": "input",       # input | processing | result | error
    "audio_bytes": None,
    "audio_filename": None,
    "audio_mime": None,
    "transcript_text": None,
    "input_mode": "audio",   # audio | transcript
    "job_id": None,
    "job_result": None,
    "error_msg": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── API helpers ───────────────────────────────────────────────────────────────


def api_submit(audio_bytes: bytes, filename: str, mime: str) -> str:
    """Upload audio to backend and return job_id."""
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/audio/upload",
        files={"file": (filename, io.BytesIO(audio_bytes), mime)},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["job_id"]


def api_submit_transcript(transcript: str) -> str:
    """Submit a pre-existing transcript to backend and return job_id."""
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/audio/transcript",
        json={"transcript": transcript, "language": "ja"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["job_id"]


def api_list_history(limit: int = 100) -> list[dict]:
    """Return archived job entries (newest first)."""
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/v1/history",
            params={"limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except requests.RequestException as exc:
        st.warning(f"履歴の取得に失敗しました: {exc}")
        return []


def api_get_history(job_id: str) -> dict | None:
    """Return the archived meta+result for *job_id*."""
    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/history/{job_id}", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        st.error(f"議事録の読み込みに失敗しました: {exc}")
        return None


def api_get_history_input(job_id: str) -> tuple[bytes, str, str] | None:
    """Return ``(bytes, filename, mime)`` of the archived input for *job_id*."""
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/v1/history/{job_id}/input", timeout=120
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"入力ファイルの取得に失敗しました: {exc}")
        return None
    cd = resp.headers.get("content-disposition", "")
    filename = "input.bin"
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd)
    if m:
        try:
            filename = requests.utils.unquote(m.group(1))
        except Exception:
            pass
    return resp.content, filename, resp.headers.get("content-type", "application/octet-stream")


def api_delete_history(job_id: str) -> bool:
    try:
        resp = requests.delete(f"{BACKEND_URL}/api/v1/history/{job_id}", timeout=30)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        st.error(f"履歴の削除に失敗しました: {exc}")
        return False


# ── Transcript file parsers ───────────────────────────────────────────────────

_VTT_TIMESTAMP = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->")
_VTT_TAG = re.compile(r"<[^>]+>")


def parse_vtt(content: str) -> str:
    """Convert WebVTT/SRT content to plain text, preserving speaker labels.

    - Strips WEBVTT header, NOTE blocks, cue identifiers, and timestamp lines.
    - Extracts speaker name from <v Speaker>...</v> tags.
    - Removes other inline tags and collapses consecutive duplicates.
    """
    lines_out: list[str] = []
    last_line: str | None = None
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith("NOTE"):
            continue
        if _VTT_TIMESTAMP.search(line):
            continue
        if line.isdigit():  # SRT cue numbers
            continue
        speaker = None
        m = re.match(r"<v\s+([^>]+)>\s*(.*)", line)
        if m:
            speaker = m.group(1).strip()
            line = m.group(2)
        line = _VTT_TAG.sub("", line).strip()
        if not line:
            continue
        if speaker:
            line = f"{speaker}：{line}"
        if line == last_line:
            continue
        lines_out.append(line)
        last_line = line
    return "\n".join(lines_out)


def parse_docx(data: bytes) -> str:
    """Extract plain text from a .docx file (paragraphs + table cells)."""
    from docx import Document  # lazy import

    doc = Document(io.BytesIO(data))
    parts: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append("\t".join(cells))
    return "\n".join(parts)


def api_poll(job_id: str) -> dict:
    resp = requests.get(f"{BACKEND_URL}/api/v1/audio/jobs/{job_id}", timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Shared header ─────────────────────────────────────────────────────────────

def render_header() -> None:
    st.markdown(
        """
<div class="app-header">
  <h1>🎙️ 会議議事録エージェント</h1>
  <p>音声ファイルから AI が自動で議事録を生成します</p>
</div>
""",
        unsafe_allow_html=True,
    )


# ── Agent detail panel ─────────────────────────────────────────────────────────

def render_agent_detail(result: dict, input_mode: str = "audio") -> None:
    """Render agent input/output detail panel in the right column."""
    cu = result.get("content_analysis")
    script = result.get("script")
    minutes = result.get("minutes")
    final = result.get("final_minutes")

    st.markdown('<div class="detail-panel">', unsafe_allow_html=True)
    st.markdown("#### \U0001f50d エージェント入出力")

    # Make the panel itself independently scrollable so it doesn't push the
    # main column down. ``st.container(height=...)`` clips overflow and shows
    # a vertical scrollbar local to this panel only.
    with st.container(height=720, border=False):
        # Step 1: Speech Transcription — only shown when audio was provided.
        if input_mode != "transcript":
            with st.expander(
                "Step 1: 音声解析",
                expanded=cu is not None and script is None,
            ):
                st.markdown("**入力**")
                st.caption("音声ファイル（バイナリデータ）")
                st.divider()
                st.markdown("**出力**")
                if cu:
                    st.json(cu)
                else:
                    st.info("⏳ 処理待ち")

        # Step 2: Script generation
        with st.expander(
            "Step 2: スクリプト生成",
            expanded=script is not None and minutes is None,
        ):
            if input_mode == "transcript":
                st.markdown("**入力** — 文字起こしテキスト")
            else:
                st.markdown("**入力** — 音声解析結果")
            if cu:
                with st.container(height=200):
                    st.json(cu)
            else:
                st.info("⏳ 入力待ち" if input_mode == "transcript" else "⏳ Step 1 の完了待ち")
            st.divider()
            st.markdown("**出力**")
            if script:
                st.json(script)
            else:
                st.info("⏳ 処理待ち")

        # Step 3: Minutes creation
        with st.expander(
            "Step 3: 議事録作成",
            expanded=minutes is not None and final is None,
        ):
            st.markdown("**入力** — スクリプト")
            if script:
                with st.container(height=200):
                    st.json(script)
            else:
                st.info("⏳ Step 2 の完了待ち")
            st.divider()
            st.markdown("**出力**")
            if minutes:
                st.json(minutes)
            else:
                st.info("⏳ 処理待ち")

        # Step 4: Terminology enrichment
        with st.expander("Step 4: 用語補足", expanded=final is not None):
            st.markdown("**入力** — 議事録")
            if minutes:
                with st.container(height=200):
                    st.json(minutes)
            else:
                st.info("⏳ Step 3 の完了待ち")
            st.divider()
            st.markdown("**出力**")
            if final:
                st.json(final)
            else:
                st.info("⏳ 処理待ち")

    st.markdown('</div>', unsafe_allow_html=True)


# ── Pages ─────────────────────────────────────────────────────────────────────

def page_input() -> None:
    render_header()

    st.subheader("入力")
    tab_record, tab_upload, tab_text = st.tabs(
        ["🎤 録音", "📁 ファイルアップロード", "📝 文字起こしテキスト"]
    )

    audio_bytes: Optional[bytes] = None
    filename: Optional[str] = None
    mime: Optional[str] = None
    transcript_text: Optional[str] = None

    # ── Recording tab ─────────────────────────────────────────────────────────
    with tab_record:
        st.markdown(
            "ブラウザのマイクを使って録音します。**録音ボタン** を押して話しかけてください。"
        )
        try:
            recorded = st.audio_input("🎤 クリックして録音を開始")
            if recorded is not None:
                audio_bytes = recorded.read()
                filename = "recording.wav"
                mime = recorded.type or "audio/wav"
                st.audio(audio_bytes, format=mime)
                st.success(
                    f"録音完了：{len(audio_bytes)/1024:.1f} KB"
                    " — 下の「議事録を生成」ボタンを押してください。"
                )
        except AttributeError:
            st.warning(
                "この Streamlit バージョンは `audio_input` に対応していません。"
                "「ファイルアップロード」タブをお使いください。"
            )

    # ── Upload tab ────────────────────────────────────────────────────────────
    with tab_upload:
        st.markdown(
            "録音済みの音声ファイルをアップロードしてください。"
            "対応形式: **WAV, MP3, MP4, M4A, OGG, WebM, FLAC**（最大 100 MB）"
        )
        uploaded = st.file_uploader(
            "ファイルを選択またはドロップ",
            type=["wav", "mp3", "mp4", "m4a", "ogg", "webm", "flac"],
            accept_multiple_files=False,
        )
        if uploaded is not None:
            audio_bytes = uploaded.read()
            filename = uploaded.name
            mime = uploaded.type or "audio/wav"
            st.audio(audio_bytes, format=mime)
            st.info(f"選択中: **{filename}**（{len(audio_bytes)/1024:.1f} KB）")

    # ── Transcript text tab ────────────────────────────────────────────
    with tab_text:
        st.markdown(
            "すでに文字起こし済みのテキストがある場合は、こちらに貼り付けてください。"
            "話者を区別する場合は `話者：発言内容` の形式を推奨します。"
        )
        text_input = st.text_area(
            "文字起こしテキスト",
            height=300,
            placeholder="話者１：本日はお集まりいただきまして...",
        )
        uploaded_text = st.file_uploader(
            "またはテキストファイルをアップロード (.txt / .md / .vtt / .srt / .docx)",
            type=["txt", "md", "vtt", "srt", "docx"],
            accept_multiple_files=False,
            key="transcript_file",
        )
        if uploaded_text is not None:
            ext = uploaded_text.name.rsplit(".", 1)[-1].lower() if "." in uploaded_text.name else ""
            try:
                raw_bytes = uploaded_text.read()
                if ext == "docx":
                    text_input = parse_docx(raw_bytes)
                else:
                    decoded = raw_bytes.decode("utf-8", errors="replace")
                    if ext in ("vtt", "srt"):
                        text_input = parse_vtt(decoded)
                    else:
                        text_input = decoded
                st.success(
                    f"ファイルを読み込みました: **{uploaded_text.name}**（{len(text_input)} 文字）"
                )
                with st.expander("プレビュー"):
                    st.text(text_input[:1000] + ("..." if len(text_input) > 1000 else ""))
            except Exception as exc:  # noqa: BLE001
                st.error(f"ファイルの読み込みに失敗しました: {exc}")
        if text_input and text_input.strip():
            transcript_text = text_input.strip()
            st.caption(f"文字数: {len(transcript_text)}")

    # ── Submit ────────────────────────────────────────────────────────────────
    st.divider()
    has_input = (audio_bytes is not None) or (transcript_text is not None)
    col_left, col_btn, col_right = st.columns([3, 2, 3])
    with col_btn:
        if st.button(
            "✨ 議事録を生成",
            use_container_width=True,
            disabled=not has_input,
            type="primary",
        ):
            if transcript_text is not None:
                st.session_state.input_mode = "transcript"
                st.session_state.transcript_text = transcript_text
                st.session_state.audio_bytes = None
                st.session_state.audio_filename = None
                st.session_state.audio_mime = None
            else:
                st.session_state.input_mode = "audio"
                st.session_state.transcript_text = None
                st.session_state.audio_bytes = audio_bytes
                st.session_state.audio_filename = filename
                st.session_state.audio_mime = mime
            st.session_state.page = "processing"
            st.rerun()

    _render_history_section()


def _render_history_section() -> None:
    """Render the saved-history section with browse / download / open actions."""
    st.divider()
    with st.expander("📚 過去の議事録（履歴）", expanded=False):
        col_a, col_b = st.columns([1, 6])
        with col_a:
            if st.button("🔄 再読み込み", key="reload_history"):
                # Drop all cached entries + per-job md/input caches
                for k in list(st.session_state.keys()):
                    if k == "_history_items" or k.startswith("_md_") or k.startswith("_in_"):
                        st.session_state.pop(k, None)
                st.rerun()
        items = st.session_state.get("_history_items")
        if items is None:
            items = api_list_history()
            st.session_state["_history_items"] = items

        if not items:
            st.info("まだ履歴はありません。議事録を生成すると自動で保存されます。")
            return

        for it in items:
            jid = it.get("job_id", "")
            title = it.get("title") or "(無題)"
            created = it.get("created_at", "")
            try:
                created_disp = (
                    datetime.fromisoformat(created.replace("Z", "+00:00"))
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M")
                )
            except Exception:
                created_disp = created
            kind = it.get("input_kind", "")
            input_filename = it.get("input_filename", "")
            kind_label = "🎤 音声" if kind == "audio" else "📝 文字起こし"

            with st.container(border=True):
                st.markdown(
                    f"**{title}**  \n"
                    f"<span style='color:#605e5c;font-size:0.85rem;'>{created_disp} ・ "
                    f"{kind_label}（{input_filename}）・ <code>{jid[:8]}</code></span>",
                    unsafe_allow_html=True,
                )

                # Pre-fetch markdown + input lazily, cached per session.
                md_key = f"_md_{jid}"
                if md_key not in st.session_state:
                    meta = api_get_history(jid)
                    final = (meta or {}).get("result", {}).get("final_minutes") or {}
                    st.session_state[md_key] = final.get("markdown") or ""
                in_key = f"_in_{jid}"
                if in_key not in st.session_state:
                    payload = api_get_history_input(jid)
                    st.session_state[in_key] = payload  # tuple or None

                md_data = st.session_state.get(md_key) or ""
                in_payload = st.session_state.get(in_key)

                c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                with c1:
                    if st.button("📂 開く", key=f"open_{jid}", use_container_width=True):
                        meta = api_get_history(jid)
                        if meta:
                            result = meta.get("result", {})
                            st.session_state.job_result = result
                            st.session_state.job_id = jid
                            st.session_state.input_mode = (
                                "transcript" if kind == "transcript" else "audio"
                            )
                            st.session_state.page = "result"
                            st.rerun()
                with c2:
                    st.download_button(
                        "⬇️ 議事録をMarkdown形式でダウンロード",
                        data=md_data.encode("utf-8") if md_data else b"",
                        file_name=f"minutes_{jid[:8]}.md",
                        mime="text/markdown",
                        key=f"dl_md_{jid}",
                        use_container_width=True,
                        disabled=not md_data,
                    )
                with c3:
                    if in_payload:
                        data, fname, mime_ = in_payload
                        st.download_button(
                            "📥 入力ファイルをダウンロード",
                            data=data,
                            file_name=fname,
                            mime=mime_,
                            key=f"dl_in_{jid}",
                            use_container_width=True,
                        )
                    else:
                        st.button(
                            "📥 入力ファイルをダウンロード",
                            key=f"dl_in_disabled_{jid}",
                            use_container_width=True,
                            disabled=True,
                        )
                with c4:
                    confirm_key = f"_del_confirm_{jid}"
                    if st.session_state.get(confirm_key):
                        if st.button(
                            "❗ 本当に削除",
                            key=f"del_yes_{jid}",
                            use_container_width=True,
                            type="primary",
                        ):
                            if api_delete_history(jid):
                                # Purge caches and reload list.
                                for k in (md_key, in_key, confirm_key, "_history_items"):
                                    st.session_state.pop(k, None)
                                st.rerun()
                    else:
                        if st.button(
                            "🗑️ 削除",
                            key=f"del_{jid}",
                            use_container_width=True,
                        ):
                            st.session_state[confirm_key] = True
                            st.rerun()


def page_processing() -> None:
    render_header()
    st.subheader("処理状況")

    show_detail = st.toggle("🔍 エージェント詳細パネル", key="show_agent_detail")

    _ALL_STEPS = [
        ("cu",      "🔍", "音声解析（Speech Transcription）",
         "音声を文字起こしし、構造化データを抽出します"),
        ("script",  "📝", "スクリプト生成エージェント",
         "文字起こし結果を整理して読みやすいスクリプトにします"),
        ("minutes", "📋", "議事録作成エージェント",
         "スクリプトをもとに正式な議事録を作成します"),
        ("term",    "📚", "用語補足エージェント",
         "業界・社内用語を参照して議事録を補足します"),
    ]
    # Skip the audio-analysis step when the user submitted a pre-existing transcript.
    input_mode = st.session_state.get("input_mode", "audio")
    if input_mode == "transcript":
        _STEPS = [s for s in _ALL_STEPS if s[0] != "cu"]
    else:
        _STEPS = _ALL_STEPS

    if show_detail:
        col_main, col_detail = st.columns([3, 2])
    else:
        col_main = st.container()
        col_detail = None

    # Create placeholders for each step (inside main column)
    with col_main:
        step_phs: dict[str, st.empty] = {}
        for key, icon, title, desc in _STEPS:
            ph = st.empty()
            step_phs[key] = ph
            ph.markdown(
                f'<div class="step-card pending">'
                f'<span style="font-size:1.4rem">{icon}</span>'
                f'<div><strong>{title}</strong><br>'
                f'<span style="font-size:.83rem;color:#a19f9d">{desc}</span></div>'
                f'<span style="margin-left:auto;font-size:.83rem;color:#a19f9d">待機中</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
        msg_ph = st.empty()
        if input_mode == "transcript":
            msg_ph.info("文字起こしテキストを送信中...")
        else:
            msg_ph.info("音声ファイルを送信中...")

    # Detail panel placeholder
    detail_ph = None
    if col_detail is not None:
        with col_detail:
            detail_ph = st.empty()

    def render_step(key: str, icon: str, title: str, desc: str,
                    state: str, status_text: str, error_detail: str = "") -> None:
        css = {"done": "done", "active": "active", "error": "done"}.get(state, "pending")
        if state == "error":
            css = "error"
        icon_prefix = {
            "done": "✅", "active": "🔄", "error": "❌", "skipped": "⏭️",
        }.get(state, "⬜")
        color = {"pending": "#a19f9d", "skipped": "#a19f9d"}.get(state, "inherit")
        detail_html = ""
        if error_detail:
            detail_html = (
                f'<div style="font-size:.8rem;color:#a4262c;margin-top:2px;'
                f'word-break:break-word">{error_detail}</div>'
            )
        step_phs[key].markdown(
            f'<div class="step-card {css}">'
            f'<span style="font-size:1.4rem">{icon}</span>'
            f'<div><strong>{title}</strong><br>'
            f'<span style="font-size:.83rem">{desc}</span>{detail_html}</div>'
            f'<span style="margin-left:auto;font-size:.83rem;color:{color};white-space:nowrap">'
            f"{icon_prefix} {status_text}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Submit job ────────────────────────────────────────────────────────────
    job_id = st.session_state.job_id
    if job_id is None:
        try:
            if st.session_state.input_mode == "transcript":
                job_id = api_submit_transcript(st.session_state.transcript_text or "")
            else:
                job_id = api_submit(
                    st.session_state.audio_bytes,
                    st.session_state.audio_filename or "audio.wav",
                    st.session_state.audio_mime or "audio/wav",
                )
            st.session_state.job_id = job_id
        except Exception as exc:  # noqa: BLE001
            st.session_state.error_msg = f"送信エラー: {exc}"
            st.session_state.page = "error"
            st.rerun()
            return

    # ── Polling loop ──────────────────────────────────────────────────────────
    consecutive_errors = 0
    MAX_CONSEC_ERRORS = 5
    for _ in range(MAX_POLLS):
        try:
            result = api_poll(job_id)
            consecutive_errors = 0
        except Exception as exc:  # noqa: BLE001
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSEC_ERRORS:
                st.session_state.error_msg = (
                    f"ステータス取得エラーが連続しました: {exc}"
                )
                st.session_state.page = "error"
                st.rerun()
                return
            # Transient error: wait and retry without aborting the job.
            msg_ph.warning(
                f"⚠️ ステータス取得に失敗 ({consecutive_errors}/{MAX_CONSEC_ERRORS}回目) — 再試行します..."
            )
            time.sleep(POLL_INTERVAL)
            continue

        has_cu     = result.get("content_analysis") is not None
        has_script = result.get("script") is not None
        has_min    = result.get("minutes") is not None
        has_final  = result.get("final_minutes") is not None
        is_error   = result["status"] == "error"
        message    = result.get("message", "処理中...")

        # Determine which step failed (if any) based on partial results.
        # The step that was running when the error occurred is the first
        # incomplete step in the pipeline.
        failed_step: str | None = None
        if is_error:
            if input_mode == "transcript":
                if not has_script:
                    failed_step = "script"
                elif not has_min:
                    failed_step = "minutes"
                elif not has_final:
                    failed_step = "term"
            else:
                if not has_cu:
                    failed_step = "cu"
                elif not has_script:
                    failed_step = "script"
                elif not has_min:
                    failed_step = "minutes"
                elif not has_final:
                    failed_step = "term"

        # Extract a short error reason from the backend message.
        error_reason = ""
        if is_error and message:
            # Backend format: "エラーが発生しました: <detail>"
            if ":" in message:
                error_reason = message.split(":", 1)[1].strip()
            else:
                error_reason = message

        for key, icon, title, desc in _STEPS:
            if key == "cu":
                done, active = has_cu, not has_cu and not is_error
            elif key == "script":
                if input_mode == "transcript":
                    done, active = has_script, not has_script and not is_error
                else:
                    done, active = has_script, has_cu and not has_script and not is_error
            elif key == "minutes":
                done, active = has_min, has_script and not has_min and not is_error
            else:
                done, active = has_final, has_min and not has_final and not is_error

            if done:
                state, status_text, detail = "done", "完了", ""
            elif is_error and key == failed_step:
                state, status_text = "error", "エラー"
                detail = error_reason
            elif is_error:
                # Steps that were never reached (after the failed step).
                state, status_text, detail = "skipped", "未到達", ""
            elif active:
                state, status_text, detail = "active", "処理中...", ""
            else:
                state, status_text, detail = "pending", "待機中", ""

            render_step(key, icon, title, desc, state, status_text, detail)

        # Update detail panel if visible
        if detail_ph is not None:
            with detail_ph.container():
                render_agent_detail(result, input_mode=input_mode)

        if result["status"] == "done":
            msg_ph.success("✨ 議事録が生成されました！")
            st.session_state.job_result = result
            st.session_state.page = "result"
            time.sleep(0.8)
            st.rerun()
            return

        if is_error:
            msg_ph.error(f"❌ {message}")
            # Stay on this page so the user can see which step failed.
            # Show a button to go back to input.
            with col_main:
                st.divider()
                col_e1, col_e2, col_e3 = st.columns([3, 2, 3])
                with col_e2:
                    if st.button("🔄 やり直す", use_container_width=True, type="primary"):
                        for k, v in _DEFAULTS.items():
                            st.session_state[k] = v
                        st.rerun()
            return

        msg_ph.info(f"⏳ {message}")
        time.sleep(POLL_INTERVAL)

    st.session_state.error_msg = "タイムアウト: 処理が完了しませんでした。"
    st.session_state.page = "error"
    st.rerun()


def page_result() -> None:
    render_header()

    result = st.session_state.job_result or {}
    final  = result.get("final_minutes") or {}
    mins   = result.get("minutes") or {}
    script = result.get("script") or {}
    cu     = result.get("content_analysis") or {}

    markdown_text = final.get("markdown") or mins.get("raw_markdown", "")
    glossary      = final.get("glossary", [])

    show_detail = st.toggle("🔍 エージェント詳細パネル", key="show_agent_detail")

    if show_detail:
        col_main, col_detail = st.columns([3, 2])
    else:
        col_main = st.container()
        col_detail = None

    with col_main:
        # ── Action buttons ────────────────────────────────────────────────────
        col1, col2, col3 = st.columns([2, 2, 6])
        with col1:
            st.download_button(
                "⬇️ Markdown ダウンロード",
                data=markdown_text,
                file_name=f"minutes_{_today()}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col2:
            if st.button("🔄 新しい議事録", use_container_width=True):
                for k, v in _DEFAULTS.items():
                    st.session_state[k] = v
                st.rerun()

        st.divider()

        # ── Result tabs ───────────────────────────────────────────────────────
        t_min, t_script, t_transcript, t_glossary = st.tabs(
            ["📋 議事録", "📝 スクリプト", "🔤 文字起こし", "📚 用語集"]
        )

        with t_min:
            if mins:
                _render_structured_minutes(mins, glossary)
            elif markdown_text:
                with st.container(border=True):
                    st.markdown(markdown_text)
            else:
                st.info("議事録データがありません。")

        with t_script:
            s = script.get("script", "")
            if s:
                st.text_area("会議スクリプト", value=s, height=400, disabled=True)
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write("**参加者**")
                    for p in script.get("participants", []):
                        st.markdown(f"- {p}")
                with col_b:
                    st.write("**議題**")
                    for a in script.get("agenda_items", []):
                        st.markdown(f"- {a}")
            else:
                st.info("スクリプトデータがありません。")

        with t_transcript:
            tr = cu.get("raw_transcript", "")
            if tr:
                st.text_area("生の文字起こし", value=tr, height=400, disabled=True)
                meta_cols = st.columns(3)
                with meta_cols[0]:
                    st.metric("話者数", len(cu.get("speakers", [])))
                with meta_cols[1]:
                    dur = cu.get("duration_seconds")
                    st.metric("録音時間", f"{dur:.0f} 秒" if dur else "—")
                with meta_cols[2]:
                    st.metric("言語", cu.get("language") or "—")
                if cu.get("speakers"):
                    st.write("**話者:** " + "、".join(cu["speakers"]))
                if cu.get("topics"):
                    st.write("**主なトピック:** " + "、".join(cu["topics"]))
            else:
                st.info("文字起こしデータがありません。")

        with t_glossary:
            if glossary:
                import pandas as pd
                df = pd.DataFrame(glossary, columns=["term", "definition"])
                df.columns = ["用語", "定義"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("議事録中に専門用語は検出されませんでした。")

    if col_detail is not None:
        with col_detail:
            render_agent_detail(result, input_mode=st.session_state.get("input_mode", "audio"))


def page_error() -> None:
    render_header()
    st.error(f"⚠️ エラー: {st.session_state.error_msg}")
    if st.button("🔄 やり直す", type="primary"):
        for k, v in _DEFAULTS.items():
            st.session_state[k] = v
        st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _render_structured_minutes(mins: dict, glossary: list | None = None) -> None:
    """Render minutes in a Teams-style structure: 概要 / 議事 (collapsible topics) / フォローアップ タスク."""
    title = mins.get("title") or "会議議事録"
    date_str = mins.get("date") or ""
    participants = mins.get("participants") or []
    summary = (mins.get("summary") or "").strip()
    topics = mins.get("topics") or []
    follow_up = mins.get("follow_up_tasks") or mins.get("action_items") or []

    with st.container(border=True):
        st.markdown(f"### {title}")
        meta_parts = []
        if date_str:
            meta_parts.append(f"**日時：** {date_str}")
        if participants:
            meta_parts.append(f"**参加者：** {'、'.join(participants)}")
        if meta_parts:
            st.markdown("　".join(meta_parts))

        # ── 概要 ──
        st.markdown("#### 概要")
        if summary:
            st.markdown(summary)
        else:
            st.caption("概要は生成されませんでした。")

        st.markdown("---")

        # ── 議事 (collapsible topics) ──
        col_h, col_btn = st.columns([6, 1])
        with col_h:
            st.markdown("#### 議事")
        with col_btn:
            expand_all = st.toggle("すべて展開", key="topics_expand_all", value=False)

        if topics:
            for i, t in enumerate(topics, 1):
                t_title = t.get("title") or f"トピック {i}"
                t_summary = (t.get("summary") or "").strip()
                t_details = t.get("details") or []
                with st.expander(f"**{i}. {t_title}**", expanded=expand_all):
                    if t_summary:
                        st.markdown(
                            f"<div class='topic-summary'>{t_summary}</div>",
                            unsafe_allow_html=True,
                        )
                    for d in t_details:
                        st.markdown(f"- {d}")
        else:
            # Fallback: render the raw markdown body for legacy minutes without topics.
            raw = (mins.get("raw_markdown") or "").strip()
            if raw:
                st.markdown(raw)
            else:
                st.caption("議事は生成されませんでした。")

        st.markdown("---")

        # ── フォローアップ タスク ──
        st.markdown("#### フォローアップ タスク")
        if follow_up:
            for t in follow_up:
                task = t.get("task", "")
                owner = t.get("owner")
                due = t.get("due")
                meta = []
                if owner:
                    meta.append(f"担当: {owner}")
                if due:
                    meta.append(f"期限: {due}")
                meta_text = f"（{' / '.join(meta)}）" if meta else ""
                st.markdown(f"- **{task}** {meta_text}")
        else:
            st.caption("フォローアップ タスクはありません。")

        # ── 用語集（あれば） ──
        if glossary:
            st.markdown("---")
            st.markdown("#### 用語集")
            import pandas as pd
            df = pd.DataFrame(glossary, columns=["term", "definition"])
            df.columns = ["用語", "定義"]
            st.dataframe(df, use_container_width=True, hide_index=True)


# ── Router ────────────────────────────────────────────────────────────────────

def main() -> None:
    page = st.session_state.page
    if page == "input":
        page_input()
    elif page == "processing":
        page_processing()
    elif page == "result":
        page_result()
    elif page == "error":
        page_error()

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown(
        "<hr style='margin-top:40px'>"
        "<p style='text-align:center;color:#a19f9d;font-size:.82rem'>"
        "Meeting Minutes Agent — Azure AI Content Understanding × Azure OpenAI × Container Apps"
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
