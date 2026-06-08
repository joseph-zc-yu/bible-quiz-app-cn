import os
import json
import re
from typing import Literal
from flask import Flask, render_template, request, jsonify
from pydantic import BaseModel
from google import genai
from google.genai import types

app = Flask(__name__)

# Initialize the Gemini client
client = genai.Client()

# --- Catholic Bible Metadata for Validation ---
CATHOLIC_BIBLE = {
    # Old Testament
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
    # New Testament
    "Matthew": 28, "Mark": 16, "Luke": 24, "John": 21, "Acts": 28, "Romans": 16,
    "1 Corinthians": 16, "2 Corinthians": 13, "Galatians": 6, "Ephesians": 6,
    "Philippians": 4, "Colossians": 4, "1 Thessalonians": 5, "2 Thessalonians": 3,
    "1 Timothy": 6, "2 Timothy": 4, "Titus": 3, "Philemon": 1, "Hebrews": 13,
    "James": 5, "1 Peter": 5, "2 Peter": 3, "1 John": 5, "2 John": 1, "3 John": 1,
    "Jude": 1, "Revelation": 22
}

OT_BOOKS = list(CATHOLIC_BIBLE.keys())[:46]
NT_BOOKS = list(CATHOLIC_BIBLE.keys())[46:]

# --- Pydantic Schemas ---
class MCQ(BaseModel):
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: Literal["A", "B", "C", "D"] # Forces the AI to strictly output one of these letters

class QuizMCQOnly(BaseModel):
    mcqs: list[MCQ]

class QuizWithFRQ(BaseModel):
    mcqs: list[MCQ]
    frq_question: str

class FRQGrade(BaseModel):
    score: int
    feedback: str

# --- Helper Functions ---
def normalize(s):
    return " ".join(s.split()).lower()

def parse_citation(citation):
    """
    Locally validates Bible citations without using AI.
    Supports: Book, Chapter, Chapter Ranges, and Single-Chapter Verse Ranges.
    Rejects: Gibberish, cross-chapter verse ranges (ambiguity), and out-of-range chapters.
    """
    norm_cit = normalize(citation)
    found_book = None
    
    # Match the book name
    for book in sorted(CATHOLIC_BIBLE.keys(), key=len, reverse=True):
        norm_book = normalize(book)
        if norm_cit.startswith(norm_book):
            found_book = book
            remainder = norm_cit[len(norm_book):].strip()
            break
            
    if not found_book:
        return {"error": "Invalid book name. Please check your spelling."}
    
    # Case 1: Entire Book (e.g., "Genesis")
    if not remainder:
        return {"book": found_book, "type": "book"}
        
    max_chapters = CATHOLIC_BIBLE[found_book]
    
    # Case 2: Single Chapter (e.g., "Genesis 1")
    m_single_chapter = re.match(r'^(\d+)$', remainder)
    if m_single_chapter:
        ch = int(m_single_chapter.group(1))
        if ch < 1 or ch > max_chapters:
            return {"error": f"Invalid chapter. {found_book} only has {max_chapters} chapters."}
        return {"book": found_book, "chapter": ch, "type": "chapter"}
        
    # Case 3: Chapter Range (e.g., "Genesis 1-2")
    m_chapter_range = re.match(r'^(\d+)-(\d+)$', remainder)
    if m_chapter_range:
        ch_start = int(m_chapter_range.group(1))
        ch_end = int(m_chapter_range.group(2))
        if ch_start < 1 or ch_end < 1:
            return {"error": "Chapter numbers must be 1 or greater."}
        if ch_start > max_chapters or ch_end > max_chapters:
            return {"error": f"Invalid chapter range. {found_book} only has {max_chapters} chapters."}
        if ch_end < ch_start:
            return {"error": "Invalid chapter range. The end chapter cannot precede the start chapter."}
        return {"book": found_book, "chapter_start": ch_start, "chapter_end": ch_end, "type": "chapter_range"}
        
    # Case 4: Verse / Verse Range (e.g., "Genesis 1:1-5" or "Genesis 1:1")
    m_verse = re.match(r'^(\d+):(\d+)(?:-(\d+))?$', remainder)
    if m_verse:
        ch = int(m_verse.group(1))
        v_start = int(m_verse.group(2))
        v_end = int(m_verse.group(3)) if m_verse.group(3) else v_start
        
        if ch < 1 or ch > max_chapters:
            return {"error": f"Invalid chapter. {found_book} only has {max_chapters} chapters."}
        if v_start < 1 or v_end < 1:
            return {"error": "Verse numbers must be 1 or greater."}
        if v_end < v_start:
            return {"error": "Invalid verse range. The end verse cannot precede the start verse."}
            
        return {"book": found_book, "chapter": ch, "verse_start": v_start, "verse_end": v_end, "type": "verse"}
        
    # Default Fallback: Matches ambiguous inputs like "Genesis 1-2:1-5" or general gibberish
    return {"error": "Invalid format. Use formats like 'John 3', 'John 1-2', or 'John 3:16-21'. Avoid mixing ranges."}
    
def parse_llm_json(text):
    text = text.strip()
    if text.startswith("```json"): text = text[7:-3]
    elif text.startswith("```"): text = text[3:-3]
    return json.loads(text.strip())

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html', ot_books=OT_BOOKS, nt_books=NT_BOOKS)

@app.route('/validate', methods=['POST'])
def validate():
    citation = request.json.get('citation', '')
    parsed = parse_citation(citation)
    
    if 'error' in parsed:
        return jsonify({"status": "error", "message": parsed['error']})
    
    passage_str = parsed['book']
    if parsed['type'] == 'chapter':
        passage_str += f" {parsed['chapter']}"
    elif parsed['type'] == 'chapter_range':
        passage_str += f" {parsed['chapter_start']}-{parsed['chapter_end']}"
    elif parsed['type'] == 'verse':
        passage_str += f" {parsed['chapter']}:{parsed['verse_start']}"
        if parsed['verse_end'] > parsed['verse_start']:
            passage_str += f"-{parsed['verse_end']}"
            
    # Return exactly 5 questions
    return jsonify({"status": "ok", "passage": passage_str, "num_questions": 5})

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    data = request.json
    passage = data.get('passage')
    include_frq = data.get('include_frq', False)
    
    schema = QuizWithFRQ if include_frq else QuizMCQOnly
    frq_instruction = "2. Generate exactly 1 short free-response question (FRQ) that requires synthesis and consolidation of ideas from the passage." if include_frq else ""
    
    prompt = f"""
    You are an expert Catholic theology teacher. Generate a quiz strictly based on the Catholic Bible for: {passage}.
    1. Generate exactly 5 multiple-choice questions (MCQs). Each MCQ must have 4 options and one clear correct answer.
    {frq_instruction}
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return jsonify(parse_llm_json(response.text))
    except Exception as e:
        return jsonify({"error": f"AI Generation Failed: {str(e)}"}), 400

@app.route('/grade_frq', methods=['POST'])
def handle_grade_frq():
    data = request.json
    prompt = f"""
    You are a Catholic theology teacher grading a student's answer.
    Passage: {data.get('passage')}
    Question: {data.get('frq_question')}
    Student's Answer: {data.get('user_answer')}
    
    Grade the answer on an integer scale from 0 to 3 based on synthesis, consolidation of ideas, and theological accuracy according to the Catholic faith. Provide a short, constructive feedback paragraph.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FRQGrade,
            ),
        )
        return jsonify(parse_llm_json(response.text))
    except Exception as e:
         return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)