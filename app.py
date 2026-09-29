import os
import tempfile
import math
import subprocess
import streamlit as st
from openai import OpenAI

# ページ基本設定
st.set_page_config(page_title="音声文字起こしツール", page_icon="🎙️", layout="centered")

st.title("🎙️ 音声文字起こしツール")
st.write("大容量の音声ファイルに対応した文字起こしツールです。")

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
    # 1. データをバイナリとして保持（再生エラー防止策）
    audio_bytes = uploaded_file.getvalue()
    st.audio(audio_bytes, format=f"audio/{uploaded_file.name.split('.')[-1]}")
    
    st.subheader("⚙️ 設定オプション")
    
    col1, col2 = st.columns(2)
    with col1:
        start_sec = st.number_input("開始位置 (秒)", min_value=0, value=0, step=1)
    with col2:
        end_sec = st.number_input("終了位置 (秒 / 0で最後まで)", min_value=0, value=0, step=1)
        
    timestamp_interval = st.slider("タイムスタンプ挿入間隔 (分)", min_value=1, max_value=20, value=5, step=1)

    if st.button("指定範囲の文字起こしを開始する", type="primary"):
        status_box = st.empty()
        status_box.info("ファイルを準備しています...")
        
        try:
            # 2. アップロードファイルを一時保存
            file_ext = uploaded_file.name.split('.')[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_filepath = tmp_file.name

            # 3. ffprobe で再生時間を取得
            def get_duration(filepath):
                cmd = [
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                return float(res.stdout.strip()) if res.returncode == 0 else 0.0

            total_sec = get_duration(tmp_filepath)
            
            # 開始・終了範囲の調整
            actual_start = start_sec
            actual_end = end_sec if (end_sec > 0 and end_sec > start_sec) else total_sec
            target_duration = actual_end - actual_start

            # 4. 20分（1200秒）ごとに分割処理
            chunk_sec = 20 * 60
            num_chunks = math.ceil(target_duration / chunk_sec)

            output_lines = []
            interval_sec = timestamp_interval * 60
            next_target_sec = 0.0
            last_text = ""  # ★重複（ループ）判定用変数

            # ★無音・幻覚ループを抑止するプロンプト
            system_prompt = "日本語の音声会話を文字起こしします。無音や雑音の区間は出力しないでください。"

            for i in range(num_chunks):
                c_start = actual_start + (i * chunk_sec)
                c_duration = min(chunk_sec, actual_end - c_start)
                
                status_box.info(f"文字起こし実行中... ({i + 1} / {num_chunks} ブロック目を処理中)")

                # ffmpeg で 20 分ごとに切り出し
                chunk_filepath = f"{tmp_filepath}_chunk_{i}.mp3"
                cmd_cut = [
                    "ffmpeg", "-y", "-ss", str(c_start), "-t", str(c_duration),
                    "-i", tmp_filepath, "-ac", "1", "-b:a", "64k", chunk_filepath
                ]
                subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                try:
                    with open(chunk_filepath, "rb") as audio_file:
                        response = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="ja",
                            prompt=system_prompt,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"]
                        )

                    # ★タイムスタンプ補正と重複カット処理
                    for segment in response.segments:
                        text = segment.text.strip()
                        if not text:
                            continue

                        # ★直前と同じ文章が連続した場合はスキップ（ループ対策）
                        if text == last_text:
                            continue
                        last_text = text

                        abs_start = c_start + segment.start
                        if abs_start >= next_target_sec:
                            mins = int(abs_start // 60)
                            secs = int(abs_start % 60)
                            output_lines.append(f"\n--- [{mins:02d}:{secs:02d}] ---")
                            next_target_sec = ((int(abs_start) // interval_sec) + 1) * interval_sec

                        output_lines.append(text)

                finally:
                    if os.path.exists(chunk_filepath):
                        os.remove(chunk_filepath)

            result_text = "\n".join(output_lines)

            # 一時ファイルの削除
            if os.path.exists(tmp_filepath):
                os.remove(tmp_filepath)

            status_box.success("すべての文字起こし処理が完了しました！")

            # 結果表示
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
