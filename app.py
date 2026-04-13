import streamlit as st
from PIL import Image
import google.genai as genai
from google.genai.types import Content, Part
import os

st.set_page_config(page_title="减脂助手", page_icon="🥗")

api_key = os.getenv("GOOGLE_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    st.error("没有找到 GOOGLE_API_KEY，请在 Secrets 中配置。")
    st.stop()

client = genai.Client(api_key=api_key)

st.title("🥗 我的减脂拍照助手")

st.header("📸 拍照分析一餐热量")
img_file = st.camera_input("对着食物拍一张")

if img_file:
    img = Image.open(img_file)
    st.image(img, caption="待分析的食物", width="stretch")

    analysis_prompt = """
    你是一个专业减脂营养师。请分析这张照片中的食物：
    1. 列出主要食物及估算克数。
    2. 估算每种食物的热量和这顿饭的总热量。
    3. 粗略给出碳水 / 蛋白质 / 脂肪的比例。
    4. 给出一句简短的、能督促我控制饮食的建议。
    """

    with st.spinner("AI 正在分析这顿饭的热量..."):
        try:
            result = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=[
                    Content(
                        parts=[
                            Part.from_text(analysis_prompt),
                            Part.from_image(img),
                        ]
                    )
                ],
            )
            st.success("分析完成")
            st.write(result.text)
        except Exception as e:
            st.error("分析出错，请查看日志。")
            st.exception(e)
