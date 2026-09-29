from openai import OpenAI
import streamlit as st

st.set_page_config(page_title="音声文字起こしツール", layout="centered")

st.title("🎙️ 音声文字起こしツール")
st.write(
    "音声ファイルをアップロードすると、AIが自動でテキスト化します。"
)

# StreamlitのSecrets機能からOpenAI APIキーを取得
api_key = st.secrets.get("OPENAI_API_KEY")

if not api_key:
    st.error(
        "OpenAI APIキーが設定されていません。Streamlitの設定（Secrets）を確認してください。"
    )
    st.stop()

client = OpenAI(api_key=api_key)

# 音声ファイルのアップロード欄
uploaded_file = st.file_uploader(
    "音声ファイルを選択してください (mp3, wav, m4a など)",
    type=["mp3", "wav", "m4a", "mp4"],
)

if uploaded_file is not None:
    st.audio(uploaded_file, format="audio/mp3")

    if st.button("文字起こしを開始する", type="primary"):
        with st.spinner("文字起こし処理中...（少々お待ちください）"):
            try:
                # OpenAI Whisper API への送信
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=(uploaded_file.name, uploaded_file.getvalue()),
                    language="ja",
                    prompt="以下は日本語の音声会話です。自然な文脈で、句読点を正しく使用して文字起こしを行ってください。",
                )

                st.success("文字起こしが完了しました！")
                st.subheader("変換結果")
                st.text_area(
                    "文字起こしテキスト",
                    response.text,
                    height=300,
                )

                # ダウンロードボタン
                st.download_button(
                    label="テキストファイルとしてダウンロード",
                    data=response.text,
                    file_name=f"transcription_{uploaded_file.name}.txt",
                    mime="text/plain",
                )
            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")