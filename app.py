import os
import re
from datetime import datetime
import json

import streamlit as st
import pandas as pd
from PIL import Image

import google.genai as genai

# ------------------ 基础配置 ------------------

st.set_page_config(page_title="减脂拍照助手", page_icon="🥗")

# 从环境变量或 Streamlit Secrets 读取 API Key
api_key = os.getenv("GOOGLE_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    st.error("没有找到 GOOGLE_API_KEY，请在 Secrets 中配置。")
    st.stop()

# 初始化客户端
client = genai.Client(api_key=api_key)

# !!! 把这里改成你通过侧边栏“查看可用模型”按钮看到的可用模型名 !!!
# 例如：MODEL_NAME = "models/gemini-2.0-flash-exp"
MODEL_NAME = "models/gemini-2.0-flash-exp"

DATA_FILE = "data.csv"


# ------------------ 工具函数 ------------------

def extract_total_calories(text: str) -> float | None:
    """
    尝试从中文分析里抽出一个“总热量”数字（单位 kcal）。
    如：'大约 650 千卡' -> 650
    """
    m = re.search(r"(\d+)\s*(kcal|千卡|大卡)", text)
    if m:
        return float(m.group(1))
    return None


def add_meal_record(calories: float, raw_text: str):
    """把本次用餐记录追加到 data.csv 中"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
    else:
        df = pd.DataFrame(columns=["date", "time", "calories", "detail"])

    new_row = {
        "date": date_str,
        "time": time_str,
        "calories": calories,
        "detail": raw_text.replace("\n", " "),
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)


# ------------------ 侧边栏：身体状态 & 体脂秤识别 ------------------

with st.sidebar:
    st.header("👤 当前身体状态")

    weight = st.number_input("体重 (kg)", min_value=30.0, max_value=200.0,
                             value=70.0, step=0.1)
    body_fat = st.number_input("体脂率 (%)", min_value=5.0, max_value=60.0,
                               value=20.0, step=0.1)
    target_cal = st.number_input("今日目标摄入 (kcal)", min_value=1000,
                                 max_value=4000, value=1800, step=100)

    st.markdown("---")
    st.subheader("📷 体脂秤拍照识别（可选）")
    scale_img_file = st.file_uploader(
        "上传或拍一张体脂秤屏幕（图片中要清晰显示体重和体脂率）",
        type=["jpg", "jpeg", "png"]
    )

    if scale_img_file is not None and st.button("识别体脂秤数值"):
        scale_img = Image.open(scale_img_file)

        ocr_prompt = """
        这是一张体脂秤的屏幕照片，请你只做一件事：
        1. 从中精确识别：体重(kg) 和 体脂率(%)。
        2. 只用 JSON 返回，格式如下：
        {"weight": 67.3, "body_fat": 18.5}
        不要多写任何解释、注释或其它文字。
        """

        with st.spinner("AI 正在读取体脂秤数据..."):
            try:
                ocr_res = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[ocr_prompt, scale_img],
                    config={"response_mime_type": "application/json"},
                )
                data = json.loads(ocr_res.text)

                if "weight" in data:
                    weight = float(data["weight"])
                if "body_fat" in data:
                    body_fat = float(data["body_fat"])

                st.success(f"识别成功：体重 {weight:.1f} kg，体脂率 {body_fat:.1f}%")
            except Exception as e:
                st.error("识别失败，请检查图片清晰度或日志。")
                st.exception(e)

    st.markdown("---")
    st.subheader("🧪 调试工具")
    if st.button("查看可用模型"):
        try:
            models = client.models.list()
            names = [m.name for m in models]
            st.write("当前这把 API Key 可用的模型：")
            for n in names:
                st.write("-", n)
        except Exception as e:
            st.error("列出模型失败：")
            st.exception(e)


# ------------------ 主界面：拍照 / 上传图片打卡 ------------------

st.title("🥗 我的减脂拍照助手")

st.header("📸 选择一种方式记录这一餐")

tab1, tab2 = st.tabs(["📷 直接拍照", "🖼️ 上传已有图片"])

uploaded_img = None  # 统一放在这个变量里处理

with tab1:
    cam_file = st.camera_input("对着食物拍一张")
    if cam_file is not None:
        uploaded_img = Image.open(cam_file)

with tab2:
    file_img = st.file_uploader("上传一张食物照片", type=["jpg", "jpeg", "png"])
    if file_img is not None:
        uploaded_img = Image.open(file_img)

if uploaded_img is not None:
    st.image(uploaded_img, caption="待分析的食物", width="stretch")

    analysis_prompt = f"""
    你是一名专业的减脂营养师和食物识别专家。请分析这张照片中的一餐。

    当前用户身体情况（供参考）：
    - 体重：{weight:.1f} kg
    - 体脂率：{body_fat:.1f} %
    - 今日目标摄入：{target_cal:.0f} kcal

    需要你返回两部分内容：

    【第一部分：结构化 JSON】
    只返回一个 JSON 对象，格式如下（字段名必须用英文）：
    {{
      "items": [
        {{
          "name": "食物名称（中文）",
          "estimated_weight_g": 200,
          "calories": 320
        }}
      ],
      "total_calories": 650,
      "carbs_g": 80,
      "protein_g": 35,
      "fat_g": 20
    }}

    【第二部分：中文点评】
    在 JSON 后面换行，再用中文分点简要点评：
    - 这顿饭的整体热量评估
    - 碳水 / 蛋白 / 脂肪是否适合减脂
    - 接下来这一餐/今天剩余时间应该注意什么

    注意：
    1. JSON 部分必须是合法 JSON，不要加注释，不要多写字段。
    2. 热量单位用 kcal，重量单位用克。
    3. 点评要简洁、直接，语气可以稍微严格一点，像真正盯着用户减脂的教练。
    """

    if st.button("开始分析这一餐", type="primary"):
        with st.spinner("AI 正在分析这顿饭的热量..."):
            try:
                result = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[analysis_prompt, uploaded_img],
                )
                st.success("分析完成")
                text = result.text
                st.write(text)

                # ----- 从文本中抽取 JSON 部分 -----
                json_start = text.find("{")
                json_end = text.rfind("}")
                meal_json = None
                total_cal = None

                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_str = text[json_start:json_end + 1]
                    try:
                        meal_json = json.loads(json_str)
                        total_cal = float(meal_json.get("total_calories", 0))
                        st.subheader("🍽️ 结构化营养数据")
                        st.json(meal_json)
                    except Exception:
                        st.warning("解析 JSON 失败，仅使用文本进行热量提取。")

                # ----- 记录本次用餐 -----
                if total_cal and total_cal > 0:
                    add_meal_record(total_cal, text)
                    st.success(f"已记录本次用餐：约 {total_cal:.0f} kcal")
                else:
                    # 兜底，用正则从文本里提取
                    total_cal = extract_total_calories(text)
                    if total_cal:
                        add_meal_record(total_cal, text)
                        st.success(f"已记录本次用餐：约 {total_cal:.0f} kcal（从文本提取）")
                    else:
                        st.warning("未能可靠提取总热量，需要你自己估一下这顿饭的大致热量。")

            except Exception as e:
                st.error("分析出错，请查看日志。")
                st.exception(e)


# ------------------ 今日摄入总览 & 教练总结 ------------------

st.markdown("---")
st.header("📅 今日摄入总览")

if os.path.exists(DATA_FILE):
    df = pd.read_csv(DATA_FILE)
    today = datetime.now().strftime("%Y-%m-%d")
    today_df = df[df["date"] == today]

    if not today_df.empty:
        total_today = today_df["calories"].sum()
        st.write(f"今天已经吃了大约 **{total_today:.0f} kcal**")
        st.dataframe(today_df[["time", "calories", "detail"]])

        if st.button("🧠 生成今日总结 & 明日饮食计划"):
            summary_prompt = f"""
            你是一名严格但负责任的减脂教练，说话可以直接一点，但不要辱骂。

            用户当前数据：
            - 体重：{weight:.1f} kg
            - 体脂率：{body_fat:.1f} %
            - 今日目标摄入：{target_cal:.0f} kcal
            - 今日实际摄入约：{total_today:.0f} kcal

            今日饮食记录（简化文本，仅供你参考）：
            {today_df.to_string(index=False)}

            请你用简洁的中文分点回答：
            1. 今天总体是吃多了、差不多，还是偏少？要给出明确判断。
            2. 今天在「碳水 / 蛋白质 / 脂肪」哪个维度最拉胯？请点名批评，但也给出改善方向。
            3. 明天的早餐 / 午餐 / 晚餐各给一个具体可执行的建议（例如：减少主食、增加多少克蛋白质）。

            要求：
            - 控制在 200 字左右。
            - 语气可以略严厉，像一个真正盯着用户减脂的教练。
            - 不要复读表格内容，直接给结论和行动建议。
            """

            with st.spinner("教练正在回顾你今天的表现..."):
                try:
                    summary_res = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=[summary_prompt],
                    )
                    st.subheader("📋 今日总结 & 明日计划")
                    st.write(summary_res.text)
                except Exception as e:
                    st.error("生成总结时出错。")
                    st.exception(e)
    else:
        st.write("今天还没有记录任何一顿饭。")
else:
    st.write("暂无历史记录。")
