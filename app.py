import streamlit as st
import os

from PIL import Image
import google.generativeai as genai

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("请在 Streamlit Cloud 的 Secrets 中配置 GEMINI_API_KEY")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 建议使用 flash 模型，速度快，适合实时打卡
model = genai.GenerativeModel('gemini-1.5-flash')

# 设置页面标题
st.set_page_config(page_title="私人减脂助手", page_icon="🥗", layout="centered")
st.title("🥗 我的私人减脂助手")

# 2. 侧边栏：体脂数据输入
with st.sidebar:
    st.header("📈 当前身体数据")
    weight = st.number_input("体重 (kg)", min_value=30.0, max_value=200.0, value=70.0, step=0.1)
    fat_rate = st.number_input("体脂率 (%)", min_value=5.0, max_value=60.0, value=20.0, step=0.1)
    target_calorie = st.number_input("今日目标摄入 (kcal)", min_value=1000, max_value=4000, value=1800, step=100)
    
    st.markdown("---")
    st.info("💡 提示：准确的体脂数据能让 AI 给出更精准的建议。")

# 3. 主界面：拍照打卡核心区
st.header("📸 饮食拍照打卡")
# 移动端打开时，这里会自动调用手机摄像头
img_file = st.camera_input("对着食物拍一张，或点击上传")

if img_file is not None:
    # 读取图片
    img = Image.open(img_file)
    st.image(img, caption="待分析的食物", use_container_width=True)
    
    # 构建精准的 Prompt
    prompt = f"""
    你是一个严厉且专业的减脂教练。用户当前体重 {weight}kg，体脂率 {fat_rate}%，今日目标摄入热量 {target_calorie} kcal。
    请分析照片中的食物：
    1. 识别食物种类。
    2. 估算大致分量和总热量 (kcal)。
    3. 给出粗略的宏量营养素占比（碳水、蛋白质、脂肪）。
    4. 结合用户的身体数据和目标热量，给出严厉且直接的今日后续饮食建议。
    输出格式要求清晰易读。
    """
    
    # 调用 AI 进行分析
    with st.spinner('教练正在紧盯你的盘子，分析计算中...'):
        try:
            response = model.generate_content([prompt, img])
            st.success("分析完成！")
            st.markdown("### 📊 教练反馈")
            st.write(response.text)
        except Exception as e:
            st.error(f"分析出错啦，请检查网络或 API Key。错误信息：{e}")