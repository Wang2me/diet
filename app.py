import os
import re
from datetime import datetime, timedelta
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

# !!! 把这里改成你在“查看可用模型”按钮里看到的模型名 !!!
# 例如：MODEL_NAME = "models/gemini-2.5-flash"
MODEL_NAME = "models/gemini-2.5-flash"

DATA_FILE = "data.csv"      # 每餐记录
BODY_FILE = "body.csv"      # 身体指标历史（体重/体脂/目标热量）


# ------------------ 工具函数 ------------------

def extract_total_calories(text: str) -> float | None:
    """（目前暂时不用）从文本里抓总热量数字"""
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


def add_body_record(weight: float, body_fat: float, target_cal: float):
    """把当前身体指标写入 body.csv（每天可写多次，我们取最近一条）"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    if os.path.exists(BODY_FILE):
        df = pd.read_csv(BODY_FILE)
    else:
        df = pd.DataFrame(columns=["date", "time", "weight", "body_fat", "target_cal"])

    new_row = {
        "date": date_str,
        "time": time_str,
        "weight": weight,
        "body_fat": body_fat,
        "target_cal": target_cal,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(BODY_FILE, index=False)


def load_latest_body():
    """从 body.csv 读取最近一次的身体指标，作为默认值"""
    if not os.path.exists(BODY_FILE):
        return 70.0, 20.0, 1800.0  # 默认值
    df = pd.read_csv(BODY_FILE)
    if df.empty:
        return 70.0, 20.0, 1800.0
    last = df.iloc[-1]
    return float(last["weight"]), float(last["body_fat"]), float(last["target_cal"])


def get_day_total_cal(date_str: str) -> float | None:
    """计算指定日期的总摄入千卡"""
    if not os.path.exists(DATA_FILE):
        return None
    df = pd.read_csv(DATA_FILE)
    day_df = df[df["date"] == date_str]
    if day_df.empty:
        return 0.0
    return float(day_df["calories"].sum())


def get_daily_totals():
    """返回一个 DataFrame：date, total_calories（每天总摄入）"""
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame(columns=["date", "total_calories"])
    df = pd.read_csv(DATA_FILE)
    grouped = df.groupby("date")["calories"].sum().reset_index()
    grouped = grouped.rename(columns={"calories": "total_calories"})
    return grouped


# 读取最近一次身体指标，作为初始默认值
default_weight, default_body_fat, default_target_cal = load_latest_body()


# ------------------ 侧边栏：身体状态 & 体脂秤识别 ------------------

with st.sidebar:
    st.header("👤 当前身体状态（会记住）")

    weight = st.number_input("体重 (kg)", min_value=30.0, max_value=200.0,
                             value=default_weight, step=0.1)
    body_fat = st.number_input("体脂率 (%)", min_value=5.0, max_value=60.0,
                               value=default_body_fat, step=0.1)
    target_cal = st.number_input(
        "今日目标摄入 (kcal)",
        min_value=1000.0,
        max_value=4000.0,
        value=float(default_target_cal),
        step=100.0,
    )

    st.markdown("---")
    # 昨日总摄入
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_total = get_day_total_cal(yesterday)
    st.subheader("📊 昨日摄入")
    if yesterday_total is not None:
        st.write(f"{yesterday} 约摄入：**{yesterday_total:.0f} kcal**")
    else:
        st.write("暂无昨日记录。")

    st.markdown("---")
    st.subheader("📷 体脂秤拍照识别（可选）")
    scale_img_file = st.file_uploader(
        "上传或拍一张体脂秤屏幕（要清晰显示体重和体脂率）",
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

    

# ------------------ 主界面：拍照 / 上传图片打卡 ------------------

st.title("🥗 我的减脂拍照助手（带记忆）")

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
                        st.warning("解析 JSON 失败，将不自动记录热量。")

                # ----- 记录本次用餐的逻辑（更严格） -----
                if meal_json is not None:
                    items = meal_json.get("items", [])
                    if (not items) or (total_cal is None) or (total_cal <= 0):
                        st.warning("模型未识别出有效食物或总热量为 0，本次不记录热量。")
                    else:
                        add_meal_record(total_cal, text)
                        st.success(f"已记录本次用餐：约 {total_cal:.0f} kcal")
                else:
                    st.warning("未能可靠提取结构化热量信息，本次不自动记录。")

            except Exception as e:
                st.error("分析出错，请查看日志。")
                st.exception(e)


# ------------------ 今日摄入总览 & 教练总结 ------------------

st.markdown("---")
st.header("📅 今日摄入总览")

if os.path.exists(DATA_FILE):
    df = pd.read_csv(DATA_FILE)
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_df = df[df["date"] == today_str]

    if not today_df.empty:
        total_today = today_df["calories"].sum()
        st.write(f"今天已经吃了大约 **{total_today:.0f} kcal**")
        st.dataframe(today_df[["time", "calories", "detail"]])

        if st.button("🧠 生成今日总结 & 明日饮食计划"):
            # 写入当前身体指标记录（相当于“打卡”）
            add_body_record(weight, body_fat, target_cal)

            # 计算昨日总摄入（方便模型做趋势判断）
            y_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            y_total = get_day_total_cal(y_str)
            if y_total is None:
                y_total_text = "昨日无记录"
            else:
                y_total_text = f"{y_str} 约 {y_total:.0f} kcal"

            summary_prompt = f"""
            你是一名严格但负责任的减脂教练，说话可以直接一点，但不要辱骂。

            用户当前数据：
            - 体重：{weight:.1f} kg
            - 体脂率：{body_fat:.1f} %
            - 今日目标摄入：{target_cal:.0f} kcal
            - 今日实际摄入约：{total_today:.0f} kcal
            - 昨日总摄入情况：{y_total_text}

            今日饮食记录（简化文本，仅供你参考）：
            {today_df.to_string(index=False)}

            请你用简洁的中文分点回答：
            1. 结合“昨日”和“今日”的热量，判断这两天总体是吃多了、差不多，还是偏少？要给出明确判断。
            2. 这两天在「碳水 / 蛋白质 / 脂肪」哪个维度最拉胯？请点名批评，但也给出改善方向。
            3. 明天的早餐 / 午餐 / 晚餐各给一个具体可执行的建议（例如：减少多少主食、增加多少克蛋白质）。
            4. 如果目前体脂率偏高，请提醒用户需要保持多久这样的控制节奏才能看到变化（粗略范围即可）。

            要求：
            - 控制在 200 字左右。
            - 语气可以略严厉，像一个真正盯着用户减脂的教练。
            - 不要复读表格内容，直接给结论和行动建议。
            """

            with st.spinner("教练正在回顾你这两天的表现..."):
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


# ------------------ 趋势分析：体重 & 每日总摄入 ------------------

st.markdown("---")
st.header("📈 趋势分析（体重 & 热量）")

cols = st.columns(2)

# 左侧：每日总摄入趋势
with cols[0]:
    st.subheader("每日总摄入 (kcal)")
    daily_totals = get_daily_totals()
    if not daily_totals.empty:
        daily_totals_sorted = daily_totals.sort_values("date")
        st.line_chart(
            daily_totals_sorted.set_index("date")["total_calories"],
            height=250,
        )
    else:
        st.write("暂无摄入记录。")

# 右侧：体重与体脂趋势
with cols[1]:
    st.subheader("体重 / 体脂率 变化")
    if os.path.exists(BODY_FILE):
        body_df = pd.read_csv(BODY_FILE)
        if not body_df.empty:
            body_df_sorted = body_df.sort_values(["date", "time"])
            body_last = body_df_sorted.tail(30)
            st.line_chart(
                body_last.set_index("date")[["weight", "body_fat"]],
                height=250,
            )
        else:
            st.write("暂无身体指标记录。")
    else:
        st.write("暂无身体指标记录。")


# ------------------ 身体成分 & 热量配合度分析 ------------------

st.markdown("---")
st.header("🧬 身体成分专业分析")

if os.path.exists(BODY_FILE):
    body_df = pd.read_csv(BODY_FILE)
    if not body_df.empty:
        body_df_sorted = body_df.sort_values(["date", "time"])
        body_last7 = body_df_sorted.tail(7)

        daily_totals = get_daily_totals().sort_values("date")
        daily_last7 = daily_totals.tail(7)

        if st.button("生成身体成分 & 热量配合度分析报告"):
            analysis_prompt = f"""
            你是一名专业的运动营养师和体成分分析师，现在要根据用户最近的身体数据和热量摄入情况，给出专业分析与建议。

            一、最近身体指标（按时间从早到晚排序，最近在最后）：
            {body_last7.to_string(index=False)}

            二、最近每日总热量摄入（单位：kcal）：
            {daily_last7.to_string(index=False)}

            请你用严谨、专业但通俗易懂的中文，分点回答以下问题：

            1. 从最近几次体重和体脂率变化来看，用户目前是：
               - 脂肪在下降、肌肉基本维持
               - 体重下降但体脂率不变或升高（可能掉的是肌肉）
               - 体脂和体重都在上升（热量明显超标）
               - 基本维持稳定（短期波动为主）
              请选择最符合的一种，并解释原因。

            2. 结合最近几天的总摄入热量，判断：
               - 用户目前的平均热量是否适合减脂（相对于体重和体脂水平，大致评估）。
               - 如果热量偏高或偏低，请给出一个建议的日均热量范围（例如：1600-1800 kcal）。

            3. 针对用户的体脂率，给出：
               - 当前体脂水平在健康范围中的大致档位（偏低/合理/偏高/肥胖）。
               - 未来 4-8 周内，合理的体脂下降速度（每周下降多少体脂百分比或体重）。

            4. 给出一个「综合行动方案」，包含：
               - 饮食：每日蛋白质大致目标（以克/天表示）以及主食和油脂的控制要点。
               - 运动：建议的每周运动频率和类型（例如：力量训练 + 有氧比例）。
               - 生活习惯：1-2 条最关键的作息/睡眠/压力管理建议。

            要求：
            - 回答结构清晰，有小标题或序号。
            - 避免空洞的鸡汤，要尽量结合给出的数据做具体分析。
            """

            with st.spinner("正在生成身体成分分析报告..."):
                try:
                    res = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=[analysis_prompt],
                    )
                    st.subheader("📋 身体成分 & 热量配合度分析报告")
                    st.write(res.text)
                except Exception as e:
                    st.error("生成身体分析报告时出错。")
                    st.exception(e)
    else:
        st.write("暂无身体指标记录，至少生成一次“今日总结”后再来。")
else:
    st.write("暂无身体指标记录，至少生成一次“今日总结”后再来。")
