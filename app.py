import os
import json
import re
from typing import Literal
from flask import Flask, render_template, request, jsonify
from pydantic import BaseModel
from openai import OpenAI

app = Flask(__name__)

# Corrected base_url with the critical trailing slash
client = OpenAI(
    api_key=os.environ.get("ZHIPU_API_KEY", "your-api-key"),
    base_url="https://open.bigmodel.cn/api/paas/v4/" 
)

# --- Catholic Bible Metadata ---
CATHOLIC_BIBLE = {
    "Genesis": 50, "Exodus": 40, "Leviticus": 27, "Numbers": 36, "Deuteronomy": 34,
    "Joshua": 24, "Judges": 21, "Ruth": 4, "1 Samuel": 31, "2 Samuel": 24,
    "1 Kings": 22, "2 Kings": 25, "1 Chronicles": 29, "2 Chronicles": 36,
    "Ezra": 10, "Nehemiah": 13, "Tobit": 14, "Judith": 16, "Esther": 16,
    "1 Maccabees": 16, "2 Maccabees": 15, "Job": 42, "Psalms": 150, "Proverbs": 31,
    "Ecclesiastes": 12, "Song of Solomon": 8, "Wisdom": 19, "Sirach": 51,
    "Isaiah": 66, "Jeremiah": 52, "Lamentations": 5, "Baruch": 6, "Ezekiel": 48,
    "Daniel": 14, "Hosea": 14, "Joel": 3, "Amos": 9, "Obadiah": 1, "Jonah": 4,
    "Micah": 7, "Nahum": 3, "Habakkuk": 3, "Zephaniah": 3, "Haggai": 2,
    "Zechariah": 14, "Malachi": 4,
    "Matthew": 28, "Mark": 16, "Luke": 24, "John": 21, "Acts": 28, "Romans": 16,
    "1 Corinthians": 16, "2 Corinthians": 13, "Galatians": 6, "Ephesians": 6,
    "Philippians": 4, "Colossians": 4, "1 Thessalonians": 5, "2 Thessalonians": 3,
    "1 Timothy": 6, "2 Timothy": 4, "Titus": 3, "Philemon": 1, "Hebrews": 13,
    "James": 5, "1 Peter": 5, "2 Peter": 3, "1 John": 5, "2 John": 1, "3 John": 1,
    "Jude": 1, "Revelation": 22
}

CHINESE_ALIASES = {
    "創世紀": "Genesis", "出谷紀": "Exodus", "肋未紀": "Leviticus", "戶籍紀": "Numbers", "申命紀": "Deuteronomy",
    "若蘇厄書": "Joshua", "民長紀": "Judges", "盧德傳": "Ruth", "撒慕爾紀上": "1 Samuel", "撒慕爾紀下": "2 Samuel",
    "列王紀上": "1 Kings", "列王紀下": "2 Kings", "編年紀上": "1 Chronicles", "編年紀下": "2 Chronicles",
    "厄斯德拉上": "Ezra", "厄斯德拉下": "Nehemiah", "多俾亞傳": "Tobit", "友弟德傳": "Judith", "艾斯德爾傳": "Esther",
    "瑪加伯上": "1 Maccabees", "瑪加伯下": "2 Maccabees", "約伯傳": "Job", "聖詠集": "Psalms", "箴言": "Proverbs",
    "訓道篇": "Ecclesiastes", "雅歌": "Song of Solomon", "智慧篇": "Wisdom", "德訓篇": "Sirach",
    "依撒意亞": "Isaiah", "耶肋米亞": "Jeremiah", "哀歌": "Lamentations", "巴路克": "Baruch", "厄則克耳": "Ezekiel",
    "達尼爾": "Daniel", "欧瑟亚": "Hosea", "岳厄尔": "Joel", "亚毛斯": "Amos", "亚北底亚": "Obadiah", "约纳": "Jonah",
    "米该亚": "Micah", "纳鸿": "Nahum", "哈巴谷": "Habakkuk", "索福尼亚": "Zephaniah", "哈盖": "Haggai",
    "匝加利亚": "Zechariah", "玛拉基亚": "Malachi",
    "瑪竇福音": "Matthew", "馬爾谷福音": "Mark", "路加福音": "Luke", "若望福音": "John", "宗徒大事錄": "Acts",
    "羅馬書": "Romans", "格林多前書": "1 Corinthians", "格林多後書": "2 Corinthians", "迦拉達書": "Galatians",
    "厄弗所書": "Ephesians", "斐理伯書": "Philippians", "哥羅森書": "Colossians", "得撒洛尼前書": "1 Thessalonians",
    "得撒洛尼後書": "2 Thessalonians", "弟茂德前書": "1 Timothy", "弟茂德後書": "2 Timothy", "弟鐸書": "Titus",
    "費肋孟書": "Philemon", "希伯來書": "Hebrews", "雅各伯書": "James", "伯多祿前書": "1 Peter", "伯多祿後書": "2 Peter",
    "若望一書": "1 John", "若望二書": "2 John", "若望三書": "3 John", "猶達書": "Jude", "若望默示錄": "Revelation"
}

OT_BOOKS = list(CATHOLIC_BIBLE.keys())[:46]
NT_BOOKS = list(CATHOLIC_BIBLE.keys())[46:]

def parse_citation(citation):
    citation = citation.replace('：', ':').replace('－', '-')
    norm_cit = " ".join(citation.split()).lower()
    
    found_book = None
    remainder = ""
    
    for book in sorted(CATHOLIC_BIBLE.keys(), key=len, reverse=True):
        if norm_cit.startswith(book.lower()):
            found_book = book
            remainder = norm_cit[len(book):].strip()
            break
            
    if not found_book:
        cit_no_spaces = citation.replace(" ", "")
        for ch_book, en_book in sorted(CHINESE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if cit_no_spaces.startswith(ch_book):
                found_book = en_book
                remainder = cit_no_spaces[len(ch_book):]
                break

    if not found_book: return {"error_key": "err_invalid_book"}
    if not remainder: return {"book": found_book, "type": "book"}
        
    max_chapters = CATHOLIC_BIBLE[found_book]
    
    m_single = re.match(r'^(\d+)$', remainder)
    if m_single:
        ch = int(m_single.group(1))
        if ch < 1 or ch > max_chapters: return {"error_key": "err_invalid_chapter"}
        return {"book": found_book, "chapter": ch, "type": "chapter"}
        
    m_ch_range = re.match(r'^(\d+)-(\d+)$', remainder)
    if m_ch_range:
        ch_start, ch_end = int(m_ch_range.group(1)), int(m_ch_range.group(2))
        if ch_start < 1 or ch_end > max_chapters or ch_end < ch_start: return {"error_key": "err_invalid_range"}
        return {"book": found_book, "chapter_start": ch_start, "chapter_end": ch_end, "type": "chapter_range"}
        
    m_verse = re.match(r'^(\d+):(\d+)(?:-(\d+))?$', remainder)
    if m_verse:
        ch, v_start = int(m_verse.group(1)), int(m_verse.group(2))
        v_end = int(m_verse.group(3)) if m_verse.group(3) else v_start
        if ch < 1 or ch > max_chapters or v_start < 1 or v_end < v_start: return {"error_key": "err_invalid_range"}
        return {"book": found_book, "chapter": ch, "verse_start": v_start, "verse_end": v_end, "type": "verse"}
        
    return {"error_key": "err_invalid_format"}

def parse_llm_json(text):
    text = text.strip()
    if text.startswith("```json"): text = text[7:-3]
    elif text.startswith("```"): text = text[3:-3]
    return json.loads(text.strip())

@app.route('/')
def index():
    return render_template('index.html', ot_books=OT_BOOKS, nt_books=NT_BOOKS)

@app.route('/validate', methods=['POST'])
def validate():
    data = request.json or {}
    citation = data.get('citation', '')
    parsed = parse_citation(citation)
    
    if 'error_key' in parsed:
        return jsonify({"status": "error", "error_key": parsed['error_key']})
    
    passage_str = parsed['book']
    if parsed['type'] == 'chapter': passage_str += f" {parsed['chapter']}"
    elif parsed['type'] == 'chapter_range': passage_str += f" {parsed['chapter_start']}-{parsed['chapter_end']}"
    elif parsed['type'] == 'verse':
        passage_str += f" {parsed['chapter']}:{parsed['verse_start']}"
        if parsed['verse_end'] > parsed['verse_start']: passage_str += f"-{parsed['verse_end']}"
            
    return jsonify({"status": "ok", "passage": passage_str, "num_questions": 5})

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    data = request.json or {}
    passage = data.get('passage', 'Genesis 1')
    include_frq = data.get('include_frq', False)
    lang = data.get('language', 'en')
    
    if lang == 'zh':
        bible_version = "Catholic Chinese Sigao Bible (思高聖經)"
        lang_instruction = "The entire output MUST be in Traditional Chinese (繁體中文). You MUST use strict Catholic terminology (e.g., 天主 instead of 上帝, 聖神 instead of 聖靈)."
    else:
        bible_version = "New Revised Standard Version Catholic Edition (NRSV-CE)"
        lang_instruction = "The entire output MUST be in English."

    frq_instruction = "2. Generate exactly 1 short free-response question (FRQ) that requires synthesis and consolidation of ideas from the passage." if include_frq else ""
    
    json_structure = '{"mcqs": [{"question": "...", "option_a": "...", "option_b": "...", "option_c": "...", "option_d": "...", "correct_option": "A"}]'
    if include_frq:
        json_structure += ', "frq_question": "..."}'
    else:
        json_structure += '}'

    prompt = f"""
    You are an expert Catholic theology teacher. Generate a quiz based on the {bible_version} for: {passage}.
    {lang_instruction}
    1. Generate exactly 5 multiple-choice questions (MCQs). Each MCQ must have 4 options and one clear correct answer ('A', 'B', 'C', or 'D').
    {frq_instruction}
    
    You MUST output ONLY a valid JSON object matching this exact structure:
    {json_structure}
    
    Do not write any introductory or explanatory text. Your entire response must be the raw JSON object.
    """
    
    try:
        response = client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[
                {"role": "system", "content": "You are a helpful theology assistant that strictly outputs JSON."},
                {"role": "user", "content": prompt}
            ]
        )
        result_text = response.choices[0].message.content
        return jsonify(parse_llm_json(result_text))
    except Exception as e:
        return jsonify({"error": f"AI Generation Failed: {str(e)}"}), 400

@app.route('/grade_frq', methods=['POST'])
def handle_grade_frq():
    data = request.json or {}
    lang = data.get('language', 'en')
    
    lang_instruction = "Provide your grading and constructive feedback strictly in Traditional Chinese (繁體中文), using proper Catholic terminology." if lang == 'zh' else "Provide a short, constructive feedback paragraph in English."
    
    prompt = f"""
    You are a Catholic theology teacher grading a student's answer.
    Passage: {data.get('passage')}
    Question: {data.get('frq_question')}
    Student's Answer: {data.get('user_answer')}
    
    Grade the answer on an integer scale from 0 to 3 based on synthesis, consolidation of ideas, and theological accuracy according to the Catholic faith.
    {lang_instruction}
    
    You MUST output ONLY a valid JSON object matching this exact structure:
    {{"score": 2, "feedback": "..."}}
    
    Do not write any introductory or explanatory text. Your entire response must be the raw JSON object.
    """
    try:
        response = client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[
                {"role": "system", "content": "You are an expert Catholic grader that strictly outputs JSON."},
                {"role": "user", "content": prompt}
            ]
        )
        result_text = response.choices[0].message.content
        return jsonify(parse_llm_json(result_text))
    except Exception as e:
         return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)