import streamlit as st
from PIL import Image
import google.generativeai as genai
import os

st.set_page_config(page_title="减脂助手", page_icon="🥗")

# 1. 读取 API Key（从环境变量或 Secrets）
api_key = os.getenv("GOOGLE_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    st.error("没有找到 GOOGLE_API_KEY，请在 Streamlit 的 Secrets 里配置。")
    st.stop()

genai.configure(api_key=api_key)

# 2. 初始化模型 —— 注意：这里只用 **gemini-1.5-flash**，不要加 models/
try:
    model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    st.error(f"模型初始化失败，请检查 google-generativeai 版本和 API Key：{e}")
    st.stop()

st.title("🥗 我的减脂拍照助手")

st.header("📸 拍照分析一餐热量")
img_file = st.camera_input("对着食物拍一张")

if img_file:
    img = Image.open(img_file)
    st.image(img, caption="待分析的食物", use_container_width=True)

    analysis_prompt = """
    你是一个专业减脂营养师。请分析这张照片中的食物：
    1. 列出主要食物及估算克数。
    2. 估算每种食物的热量和这顿饭的总热量。
    3. 粗略给出碳水 / 蛋白质 / 脂肪的比例。
    4. 给出一句简短的减脂建议。

    输出要清晰、有条理。
    """

    with st.spinner("AI 正在分析这顿饭的热量..."):
        try:
            response = model.generate_content([analysis_prompt, img])
            st.success("分析完成")
            st.write(response.text)
        except Exception as e:
            st.error("分析出错，请看日志（Manage app -> Logs）。")
            st.exception(e)
