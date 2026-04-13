import streamlit as st
import google.generativeai as genai
from PIL import Image
import json

# 配置（建議在 Secrets 中設置 GOOGLE_API_KEY）
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# 使用 1.5-flash 模型，它是圖像理解性價比最高的選擇
# 如果 404，請確保名稱完全匹配
model = genai.GenerativeModel('gemini-1.5-flash')

st.title("🥗 智能減脂視覺助手")

# 1. 身體數據（側邊欄）
with st.sidebar:
    st.header("👤 個人狀態")
    # 這裡可以加入文件上傳，自動識別體重
    uploaded_report = st.file_uploader("拍一下體脂秤或報告", type=['jpg','png'])
    if uploaded_report:
        # 圖像理解：提取體脂數據
        with st.spinner("正在讀取報告..."):
            res = model.generate_content(["提取圖中的體重和體脂率，以JSON格式返回: {'weight': float, 'fat': float}", Image.open(uploaded_report)])
            st.json(res.text)

# 2. 食物拍照分析（主介面）
img_file = st.camera_input("拍攝今日午餐")

if img_file:
    img = Image.open(img_file)
    st.image(img, use_container_width=True)
    
    # 圖像理解：精準分析
    # 重點：引導模型進行物理維度估算
    analysis_prompt = """
    作為專業營養師，請詳細分析此圖片：
    1. 識別盤中所有食物。
    2. 觀察食物與餐具（如筷子/盤子）的比例，精確估算重量。
    3. 計算總熱量和宏量營養素（碳水、蛋白、脂肪）。
    4. 輸出要求：先給出數據清單，再給出簡短的減脂建議。
    """
    
    with st.spinner("AI 正在掃描食物..."):
        response = model.generate_content([analysis_prompt, img])
        st.markdown("---")
        st.subheader("📊 營養分析報告")
        st.write(response.text)
