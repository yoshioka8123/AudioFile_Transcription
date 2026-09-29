import os
import gc
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
    st.subheader("🎧 範囲指定・設定")
    
    col1, col2 = st.columns(2)
    with col1:
        start_min = st.number_input("開始位置 (分)", min_value=0, value=0, step=1, help="文字起こしを開始する位置を「分」で指定します")
    with col2:
        end_min = st.number_input("終了位置 (分 / 0で最後まで)", min_value=0, value=0, step=1, help="文字起こしを終了する位置を「分」で指定します（0の場合は最後まで）")
        
    timestamp_interval = st.slider("タイムスタンプ挿入間隔 (分)", min_value=1, max_value=20, value=5, step=1)

    # 試聴機能
    with st.expander("🔊 開始位置から30秒間だけプレビュー再生する（動作確認用）"):
        if st.button("プレビュー音声を生成"):
            with st.spinner("指定位置の音声を切り出しています..."):
                file_ext = uploaded_file.name.split('.')[-1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
                    uploaded_file.seek(0)
                    while chunk := uploaded_file.read(1024 * 1024 * 8):
                        tmp_file.write(chunk)
                    tmp_filepath = tmp_file.name

                preview_path = f"{tmp_filepath}_preview.mp3"
                p_start = start_min * 60
                cmd_preview = [
                    "ffmpeg", "-y", "-ss", str(p_start), "-t", "30",
                    "-i", tmp_filepath, "-ac", "1", "-b:a", "128k", preview_path
                ]
                subprocess.run(cmd_preview, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if os.path.exists(preview_path):
                    st.audio(preview_path)
                    os.remove(preview_path)
                if os.path.exists(tmp_filepath):
                    os.remove(tmp_filepath)
                
                gc.collect()

    st.markdown("---")

    if st.button("指定範囲の文字起こしを開始する", type="primary"):
        st.cache_data.clear()
        gc.collect()

        status_box = st.empty()
        status_box.info("ファイルを準備しています...")
        
        tmp_filepath = None
        try:
            start_sec = start_min * 60
            end_sec = end_min * 60

            file_ext = uploaded_file.name.split('.')[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
                uploaded_file.seek(0)
                while chunk := uploaded_file.read(1024 * 1024 * 8):
                    tmp_file.write(chunk)
                tmp_filepath = tmp_file.name

            def get_duration(filepath):
                cmd = [
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                return float(res.stdout.strip()) if res.returncode == 0 else 0.0

            total_sec = get_duration(tmp_filepath)
            
            actual_start = start_sec
            actual_end = end_sec if (end_sec > 0 and end_sec > start_sec) else total_sec
            target_duration = actual_end - actual_start

            chunk_sec = 20 * 60
            num_chunks = math.ceil(target_duration / chunk_sec)

            output_lines = []
            interval_sec = timestamp_interval * 60
            next_target_sec = 0.0
            
            # ハルシネーション対策用プロンプト（書き方のお手本を与えることで無音時の暴走を防ぐ）
            guide_prompt = "こんにちは。本日の会議・会話を文字起こしします。"

            for i in range(num_chunks):
                c_start = actual_start + (i * chunk_sec)
                c_duration = min(chunk_sec, actual_end - c_start)
                
                status_box.info(f"文字起こし実行中... ({i + 1} / {num_chunks} ブロック目を処理中)")

                chunk_filepath = f"{tmp_filepath}_chunk_{i}.mp3"
                cmd_cut = [
                    "ffmpeg", "-y", "-ss", str(c_start), "-t", str(c_duration),
                    "-i", tmp_filepath, "-ac", "1", "-b:a", "128k", chunk_filepath
                ]
                subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                try:
                    with open(chunk_filepath, "rb") as audio_file:
                        response = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="ja",
                            prompt=guide_prompt,
                            temperature=0.0,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"]
                        )

                    last_text = ""
                    repeat_count = 0

                    for segment in response.segments:
                        text = segment.text.strip()
                        if not text:
                            continue

                        # 同じ文字列が繰り返し出力された場合の連続生成ガード (2回まで許可)
                        if text == last_text:
                            repeat_count += 1
                            if repeat_count >= 2:
                                continue
                        else:
                            last_text = text
                            repeat_count = 0

                        # 代表的なハルシネーション単語のブラックリスト除外
                        if any(bad_word in text for bad_word in [
                            "お気に召し上がり", "E233系", "ご視聴ありがとうございました", 
                            "チャンネル登録", "高評価", "字幕:", "Subtitles by"
                        ]):
                            continue

                        # タイムスタンプの出力
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
                    gc.collect()

            st.session_state["transcript_result"] = "\n".join(output_lines)
            status_box.success("すべての文字起こし処理が完了しました！")

        except Exception as e:
            status_box.error(f"エラーが発生しました: {e}")
        finally:
            if tmp_filepath and os.path.exists(tmp_filepath):
                os.remove(tmp_filepath)
            gc.collect()

    # 結果表示
    if st.session_state.get("transcript_result"):
        st.subheader("📝 変換結果")
        st.text_area("文字起こしテキスト", value=st.session_state["transcript_result"], height=350)

        st.download_button(
            label="📄 .txt で保存",
            data=st.session_state["transcript_result"],
            file_name="transcript.txt",
            mime="text/plain"
        )
