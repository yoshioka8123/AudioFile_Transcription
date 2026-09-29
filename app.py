import os
import tempfile
import wave
import streamlit as st
from openai import OpenAI

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
        status_box.info("ファイルを処理中...")
        
        try:
            # 1. アップロードファイルを一時保存
            file_ext = uploaded_file.name.split('.')[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_filepath = tmp_file.name

            target_filepath = tmp_filepath

            # WAVファイルかつ範囲指定がある場合は wave で切り出し
            if file_ext.lower() == "wav" and (start_sec > 0 or end_sec > 0):
                with wave.open(tmp_filepath, 'rb') as wav_in:
                    params = wav_in.getparams()
                    framerate = params.framerate
                    nframes = params.nframes
                    
                    start_frame = int(start_sec * framerate)
                    end_frame = int(end_sec * framerate) if (end_sec > 0 and end_sec > start_sec) else nframes
                    
                    wav_in.setpos(start_frame)
                    frames = wav_in.readframes(end_frame - start_frame)
                    
                    trimmed_filepath = tmp_filepath + "_trimmed.wav"
                    with wave.open(trimmed_filepath, 'wb') as wav_out:
                        wav_out.setparams(params)
                        wav_out.writeframes(frames)
                    target_filepath = trimmed_filepath

            status_box.info("OpenAI Whisper API で文字起こしを実行中...")

            # OpenAI Whisper API で文字起こし実行（OpenAI側で最大25MBまで直接受取）
            with open(target_filepath, "rb") as audio_file:
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
                abs_start = start_sec + segment.start
                
                if abs_start >= next_target_sec:
                    mins = int(abs_start // 60)
                    secs = int(abs_start % 60)
                    output_lines.append(f"\n--- [{mins:02d}:{secs:02d}] ---")
                    next_target_sec = ((int(abs_start) // interval_sec) + 1) * interval_sec

                output_lines.append(segment.text.strip())

            result_text = "\n".join(output_lines)

            # 後処理
            if os.path.exists(tmp_filepath):
                os.remove(tmp_filepath)
            if target_filepath != tmp_filepath and os.path.exists(target_filepath):
                os.remove(target_filepath)

            status_box.success("文字起こし処理が完了しました！")

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
