import os
import tempfile
import streamlit as st
from openai import OpenAI
from pydub import AudioSegment

# ページ基本設定
st.set_page_config(page_title="音声文字起こしツール", page_icon="🎙️", layout="centered")

st.title("🎙️ 音声文字起こしツール")
st.write("音声ファイルをアップロードして、指定した範囲やタイムスタンプ間隔で文字起こしを行います。")

# Secrets から OpenAI API キーを取得
api_key = st.secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")

if not api_key:
    st.error("OpenAI APIキーが設定されていません。Streamlit の Advanced settings (Secrets) を確認してください。")
    st.stop()

client = OpenAI(api_key=api_key)

# 音声ファイルアップロード
uploaded_file = st.file_uploader(
    "音声ファイルを選択してください (mp3, wav, m4a など)",
    type=["mp3", "wav", "m4a", "aac", "flac", "ogg"]
)

if uploaded_file is not None:
    # プレビュー表示
    st.audio(uploaded_file)
    
    # オプション設定領域
    st.subheader("⚙️ 設定オプション")
    
    col1, col2 = st.columns(2)
    with col1:
        start_sec = st.number_input("開始位置 (秒)", min_value=0, value=0, step=1)
    with col2:
        end_sec = st.number_input("終了位置 (秒 / 0で最後まで)", min_value=0, value=0, step=1)
        
    timestamp_interval = st.slider("タイムスタンプ挿入間隔 (分)", min_value=1, max_value=20, value=5, step=1)

    # 実行ボタン
    if st.button("指定範囲の文字起こしを開始する", type="primary"):
        with st.spinner("音声を処理中...（数分かかる場合があります）"):
            try:
                # 一時ファイルに保存
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_filepath = tmp_file.name

                # 音声の切り出し処理 (pydub を使用)
                audio = AudioSegment.from_file(tmp_filepath)
                total_duration_sec = len(audio) / 1000.0

                start_ms = start_sec * 1000
                end_ms = (end_sec * 1000) if (end_sec > 0 and end_sec > start_sec) else len(audio)

                trimmed_audio = audio[start_ms:end_ms]

                # 切り出した音声を一時保存 (.mp3)
                trimmed_filepath = tmp_filepath + "_trimmed.mp3"
                trimmed_audio.export(trimmed_filepath, format="mp3")

                # OpenAI Whisper API で文字起こし実行 (タイムスタンプ付き詳細レスポンス)
                with open(trimmed_filepath, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="ja",
                        response_format="verbose_json",
                        timestamp_granularities=["segment"]
                    )

                # テキストの整形・タイムスタンプ挿入処理
                output_lines = []
                interval_sec = timestamp_interval * 60
                next_target_sec = 0.0

                for segment in response.segments:
                    # 全体時間 offset 加算
                    abs_start = start_sec + segment.start
                    
                    # 指定間隔ごとにタイムスタンプ行を挿入
                    if abs_start >= next_target_sec:
                        mins = int(abs_start // 60)
                        secs = int(abs_start % 60)
                        output_lines.append(f"\n--- [{mins:02d}:{secs:02d}] ---")
                        next_target_sec = ((int(abs_start) // interval_sec) + 1) * interval_sec

                    output_lines.append(segment.text.strip())

                result_text = "\n".join(output_lines)

                # 後処理（一時ファイルの削除）
                os.remove(tmp_filepath)
                os.remove(trimmed_filepath)

                st.success("文字起こしが完了しました！")

                # 結果表示エリア
                st.subheader("📝 変換結果")
                st.text_area("文字起こしテキスト", value=result_text, height=350)

                # ダウンロードボタン
                st.download_button(
                    label="📄 .txt で保存",
                    data=result_text,
                    file_name="transcript.txt",
                    mime="text/plain"
                )

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
