import os
import tempfile
import math
import streamlit as st
from openai import OpenAI
from pydub import AudioSegment

# ページ基本設定
st.set_page_config(page_title="音声文字起こしツール", page_icon="🎙️", layout="centered")

st.title("🎙️ 音声文字起こしツール")
st.write("大容量（最大500MB）の音声ファイルに対応した文字起こしツールです。")

# APIキーの取得
api_key = st.secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("OpenAI APIキーが設定されていません。Streamlit の Advanced settings (Secrets) を確認してください。")
    st.stop()

client = OpenAI(api_key=api_key)

# アップロード枠
uploaded_file = st.file_uploader(
    "音声ファイルを選択してください (mp3, wav, m4a など)",
    type=["mp3", "wav", "m4a", "aac", "flac", "ogg"]
)

if uploaded_file is not None:
    st.audio(uploaded_file)
    
    st.subheader("⚙️ 設定オプション")
    
    col1, col2 = st.columns(2)
    with col1:
        start_sec = st.number_input("開始位置 (秒)", min_value=0, value=0, step=1)
    with col2:
        end_sec = st.number_input("終了位置 (秒 / 0で最後まで)", min_value=0, value=0, step=1)
        
    timestamp_interval = st.slider("タイムスタンプ挿入間隔 (分)", min_value=1, max_value=20, value=5, step=1)

    if st.button("指定範囲の文字起こしを開始する", type="primary"):
        status_box = st.empty()
        status_box.info("ファイルを準備中...")
        
        try:
            # 1. アップロードファイルを一時保存
            file_ext = uploaded_file.name.split('.')[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_filepath = tmp_file.name

            # 2. pydub で音声読み込みと範囲の切り出し
            status_box.info("音声を解析・カット中...")
            audio = AudioSegment.from_file(tmp_filepath)

            start_ms = start_sec * 1000
            end_ms = (end_sec * 1000) if (end_sec > 0 and end_sec > start_sec) else len(audio)
            target_audio = audio[start_ms:end_ms]

            # 3. 25MB制限を回避するため、10分（600,000ms）単位にチャンク分割
            chunk_length_ms = 10 * 60 * 1000  # 10分
            total_duration_ms = len(target_audio)
            total_chunks = math.ceil(total_duration_ms / chunk_length_ms)

            all_segments = []
            output_lines = []
            interval_sec = timestamp_interval * 60
            next_target_sec = 0.0

            # 4. 分割されたチャンクを順番に OpenAI Whisper API へ送信
            for i in range(total_chunks):
                status_box.info(f"文字起こし実行中... ({i + 1} / {total_chunks} ブロック目を処理中)")
                
                c_start_ms = i * chunk_length_ms
                c_end_ms = min((i + 1) * chunk_length_ms, total_duration_ms)
                chunk_audio = target_audio[c_start_ms:c_end_ms]

                # チャンク一時保存 (.mp3)
                chunk_path = tmp_filepath + f"_chunk_{i}.mp3"
                chunk_audio.export(chunk_path, format="mp3", bitrate="64k")

                try:
                    with open(chunk_path, "rb") as audio_file:
                        response = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="ja",
                            response_format="verbose_json",
                            timestamp_granularities=["segment"]
                        )

                    # チャンクごとのタイムスタンプを全体時間に補正
                    chunk_offset_sec = (c_start_ms / 1000.0) + start_sec
                    for segment in response.segments:
                        abs_start = chunk_offset_sec + segment.start
                        
                        if abs_start >= next_target_sec:
                            mins = int(abs_start // 60)
                            secs = int(abs_start % 60)
                            output_lines.append(f"\n--- [{mins:02d}:{secs:02d}] ---")
                            next_target_sec = ((int(abs_start) // interval_sec) + 1) * interval_sec

                        output_lines.append(segment.text.strip())

                finally:
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)

            result_text = "\n".join(output_lines)

            # 後処理
            if os.path.exists(tmp_filepath):
                os.remove(tmp_filepath)

            status_box.success("すべての文字起こし処理が完了しました！")

            # 結果表示エリア
            st.subheader("📝 変換結果")
            st.text_area("文字起こしテキスト", value=result_text, height=350)

            st.download_button(
                label="📄 .txt で保存",
                data=result_text,
                file_name="transcript.txt",
                mime="text/plain"
            )

        except Exception as e:
            status_box.error(f"エラーが発生しました: {e}")
