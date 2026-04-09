"""
Meeting Minutes Agent — Streamlit Frontend
==========================================
Communicates with the FastAPI backend (BACKEND_URL env var).
Within Container Apps the backend is on the private network (internal ingress).
"""
from __future__ import annotations

import io
import os
import time
from typing import Optional

import requests
import streamlit as st

# ── Configuration ─────────────────────────────────────────────────────────────
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
MAX_POLLS = 150  # ~5 minutes

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
/* Header */
.app-header {
    background: linear-gradient(135deg, #0078d4 0%, #004578 100%);
    color: white;
    padding: 24px 32px;
    border-radius: 12px;
    margin-bottom: 24px;
    text-align: center;
}
.app-header h1 { font-size: 2rem; margin: 0 0 6px; }
.app-header p  { font-size: 1rem; opacity: 0.85; margin: 0; }

/* Section headers */
.section-label {
    font-size: 1rem;
    font-weight: 600;
    color: #005a9e;
    margin-bottom: 4px;
}

/* Pipeline step cards */
.step-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-radius: 8px;
    border: 1px solid #e1dfdd;
    background: #f3f2f1;
    margin-bottom: 8px;
    font-size: .95rem;
}
.step-card.done    { border-color: #107c10; background: #dff6dd; }
.step-card.active  { border-color: #0078d4; background: #c7e0f4; }
.step-card.pending { border-color: #e1dfdd; background: #f3f2f1; color: #a19f9d; }

/* Result markdown tweaks */
.minutes-box {
    background: #ffffff;
    border: 1px solid #e1dfdd;
    border-radius: 8px;
    padding: 20px 24px;
}
.stDownloadButton > button {
    background: #0078d4 !important;
    color: white !important;
}

/* Hide Streamlit branding */
#MainMenu, footer { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Session state defaults ────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "page": "input",       # input | processing | result | error
    "audio_bytes": None,
    "audio_filename": None,
    "audio_mime": None,
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
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["job_id"]


def api_poll(job_id: str) -> dict:
    resp = requests.get(f"{BACKEND_URL}/api/v1/audio/jobs/{job_id}", timeout=15)
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


# ── Pages ─────────────────────────────────────────────────────────────────────

def page_input() -> None:
    render_header()

    st.subheader("音声入力")
    tab_record, tab_upload = st.tabs(["🎤 録音", "📁 ファイルアップロード"])

    audio_bytes: Optional[bytes] = None
    filename: Optional[str] = None
    mime: Optional[str] = None

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

    # ── Submit ────────────────────────────────────────────────────────────────
    st.divider()
    col_left, col_btn, col_right = st.columns([3, 2, 3])
    with col_btn:
        if st.button(
            "✨ 議事録を生成",
            use_container_width=True,
            disabled=audio_bytes is None,
            type="primary",
        ):
            st.session_state.audio_bytes = audio_bytes
            st.session_state.audio_filename = filename
            st.session_state.audio_mime = mime
            st.session_state.page = "processing"
            st.rerun()


def page_processing() -> None:
    render_header()
    st.subheader("処理状況")

    _STEPS = [
        ("cu",      "🔍", "音声解析（Content Understanding）",
         "音声を文字起こしし、構造化データを抽出します"),
        ("script",  "📝", "スクリプト生成エージェント",
         "文字起こし結果を整理して読みやすいスクリプトにします"),
        ("minutes", "📋", "議事録作成エージェント",
         "スクリプトをもとに正式な議事録を作成します"),
        ("term",    "📚", "用語補足エージェント",
         "業界・社内用語を参照して議事録を補足します"),
    ]

    # Create placeholders for each step
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
    msg_ph.info("音声ファイルを送信中...")

    def render_step(key: str, icon: str, title: str, desc: str,
                    state: str, status_text: str) -> None:
        css = {"done": "done", "active": "active"}.get(state, "pending")
        icon_prefix = {"done": "✅", "active": "🔄", "error": "❌"}.get(state, "⬜")
        color = {"pending": "#a19f9d"}.get(state, "inherit")
        step_phs[key].markdown(
            f'<div class="step-card {css}">'
            f'<span style="font-size:1.4rem">{icon}</span>'
            f'<div><strong>{title}</strong><br>'
            f'<span style="font-size:.83rem">{desc}</span></div>'
            f'<span style="margin-left:auto;font-size:.83rem;color:{color}">'
            f"{icon_prefix} {status_text}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Submit job ────────────────────────────────────────────────────────────
    job_id = st.session_state.job_id
    if job_id is None:
        try:
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
    for _ in range(MAX_POLLS):
        try:
            result = api_poll(job_id)
        except Exception as exc:  # noqa: BLE001
            st.session_state.error_msg = f"ステータス取得エラー: {exc}"
            st.session_state.page = "error"
            st.rerun()
            return

        has_cu     = result.get("content_analysis") is not None
        has_script = result.get("script") is not None
        has_min    = result.get("minutes") is not None
        has_final  = result.get("final_minutes") is not None
        is_error   = result["status"] == "error"
        message    = result.get("message", "処理中...")

        for key, icon, title, desc in _STEPS:
            if key == "cu":
                done, active = has_cu, not has_cu and not is_error
            elif key == "script":
                done, active = has_script, has_cu and not has_script and not is_error
            elif key == "minutes":
                done, active = has_min, has_script and not has_min and not is_error
            else:
                done, active = has_final, has_min and not has_final and not is_error

            state = "done" if done else ("active" if active else ("error" if is_error else "pending"))
            status_text = (
                "完了" if done
                else ("処理中..." if active else ("エラー" if is_error else "待機中"))
            )
            render_step(key, icon, title, desc, state, status_text)

        if result["status"] == "done":
            msg_ph.success("✨ 議事録が生成されました！")
            st.session_state.job_result = result
            st.session_state.page = "result"
            time.sleep(0.8)
            st.rerun()
            return

        if is_error:
            msg_ph.error(f"❌ {message}")
            st.session_state.error_msg = message
            st.session_state.page = "error"
            time.sleep(1)
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

    # ── Action buttons ────────────────────────────────────────────────────────
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

    # ── Result tabs ───────────────────────────────────────────────────────────
    t_min, t_script, t_transcript, t_glossary = st.tabs(
        ["📋 議事録", "📝 スクリプト", "🔤 文字起こし", "📚 用語集"]
    )

    with t_min:
        if markdown_text:
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
