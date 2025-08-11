import os
import json
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
import io
from pathlib import Path
import openpyxl
from datetime import datetime

# --- 初始化和配置 ---

# 直接在此处设置您的Gemini API密钥。
api_key = "AIzaSyCk3sz0VZ4-JHZBhAOjGS2KU7FkfzbyTOc"

if not api_key or api_key == "YOUR_API_KEY_HERE":
    raise ValueError("错误：请在代码中设置 GEMINI_API_KEY")

genai.configure(api_key=api_key)

# 初始化Flask应用
app = Flask(__name__)
# 允许来自任何源的跨域请求，方便本地调试
CORS(app)

# --- Excel 文件配置 ---
EXCEL_FILE_PATH = Path("food_log.xlsx")
EXCEL_HEADERS = [
    "Timestamp", "Product Name", "Manufacturer", "Ingredients", 
    "Calories", "Pros", "Cons", "Health Score"
]

def initialize_excel():
    """如果Excel文件不存在，则创建它并写入表头。"""
    if not EXCEL_FILE_PATH.exists():
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Food Analysis Log"
        sheet.append(EXCEL_HEADERS)
        workbook.save(EXCEL_FILE_PATH)
        print(f"'{EXCEL_FILE_PATH}' 已创建。")

def append_to_excel(data):
    """将一条新的分析记录追加到Excel文件中。"""
    try:
        workbook = openpyxl.load_workbook(EXCEL_FILE_PATH)
        sheet = workbook.active
        
        row_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get("productName", "N/A"),
            data.get("manufacturer", "N/A"),
            data.get("ingredients", "N/A"),
            data.get("calories", "N/A"),
            data.get("pros", "N/A"),
            data.get("cons", "N/A"),
            data.get("healthScore", "N/A")
        ]
        sheet.append(row_data)
        workbook.save(EXCEL_FILE_PATH)
    except Exception as e:
        print(f"写入Excel失败: {e}")


# --- AI模型和指令模板 ---

def get_vision_model():
    """动态查找一个支持 generateContent 的视觉模型。"""
    print("正在尝试寻找可用的视觉模型...")
    available_models = genai.list_models()
    vision_model_name = None
    
    # 优先尝试使用 gemini-1.0-pro-vision-latest
    try:
        model_info = genai.get_model('models/gemini-1.0-pro-vision-latest')
        if 'generateContent' in model_info.supported_generation_methods:
            vision_model_name = 'gemini-1.0-pro-vision-latest'
            print(f"找到并使用模型: {vision_model_name}")
            return genai.GenerativeModel(vision_model_name, safety_settings=safety_settings)
    except Exception:
        print("gemini-1.0-pro-vision-latest 不可用。正在寻找其他模型...")

    # 如果 gemini-1.0-pro-vision-latest 不可用，则遍历所有模型
    for model in available_models:
        # 视觉模型通常包含 'vision' 或 'image'
        if 'generateContent' in model.supported_generation_methods and ('vision' in model.name or 'image' in model.name):
            vision_model_name = model.name.replace('models/', '')
            print(f"找到并使用备用模型: {vision_model_name}")
            return genai.GenerativeModel(vision_model_name, safety_settings=safety_settings)
    
    raise ValueError("错误：未找到任何支持 generateContent 的视觉模型。请检查您的API配置或地区限制。")

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
model = get_vision_model()

# 这是给AI的核心指令 (Prompt)
prompt_template = """
Analyze the image of a food, beverage, or packaged food item. Based on the visual information, return a single JSON object with the following keys. Do not include any explanatory text, markdown formatting like ```json, or any characters outside of the JSON object itself.

- "productName": (string) The common name of the product (e.g., "Coca-Cola", "Scrambled eggs with tomato", "Fuji apple").
- "manufacturer": (string) The manufacturer or brand, if visible on packaging. If not applicable or not visible, return "N/A".
- "ingredients": (string) A brief analysis of the main components. For packaged food, list key ingredients. For dishes or natural foods, describe what it's made of (e.g., "Tomato, egg, oil, salt").
- "calories": (string) An estimated calorie count per 100g or per serving. Provide a reasonable estimate (e.g., "Approx. 450 kcal per 100g").
- "pros": (string) One or two main advantages from a health perspective.
- "cons": (string) One or two main disadvantages from a health perspective.
- "healthScore": (number) A health score from 1 to 10, where 1 is extremely unhealthy and 10 is very healthy.
"""

def clean_json_response(text):
    """一个更健壮的函数，用于从AI的响应中提取JSON。"""
    match = text.strip()
    if match.startswith("```json"):
        match = match[7:]
    if match.endswith("```"):
        match = match[:-3]
    return match.strip()


@app.route('/analyze', methods=['POST'])
def analyze_image():
    """接收图片，调用Gemini API进行分析，并返回JSON结果。"""
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files['image']
    
    try:
        img = Image.open(io.BytesIO(file.read()))
        # 在 img = Image.open(io.BytesIO(file.read())) 之后添加以下代码
        # 设置最大尺寸，例如限制为 1024 像素宽
        max_size = (1024, 1024)
        img.thumbnail(max_size, Image.LANCZOS)
        response = model.generate_content([prompt_template, img])
        cleaned_text = clean_json_response(response.text)
        data = json.loads(cleaned_text)

        # 成功解析后，将数据写入Excel
        append_to_excel(data)

        return jsonify(data)

    except json.JSONDecodeError:
        print(f"JSON解码失败，原始文本: '{response.text}'")
        return jsonify({"error": "AI response was not valid JSON."}), 500
    except Exception as e:
        print(f"发生未知错误: {e}")
        return jsonify({"error": "An unexpected error occurred during analysis."}), 500

if __name__ == '__main__':
    # 在启动服务前，确保Excel文件已初始化
    initialize_excel()
    # 在本地运行服务
    app.run(host='0.0.0.0', port=5000, debug=True)