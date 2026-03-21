from flask import Flask, render_template, request, jsonify, session
from groq import Groq
from dotenv import load_dotenv
import os, json, fitz  # fitz = PyMuPDF

load_dotenv()
app = Flask(__name__)
app.secret_key = "hackathon_winner_2024"

GROQ_API_KEY = os.getenv("GROQ_API_KEY") or "PASTE_YOUR_GROQ_KEY_HERE"
client = Groq(api_key=GROQ_API_KEY)

def ask_ai(system_prompt, user_message, max_tokens=1000):
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("Groq Error:", str(e))
        return "ERROR:" + str(e)


# ── PAGES ──────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/interview")
def interview():
    return render_template("interview.html")

@app.route("/chat")
def chat():
    return render_template("chat.html")

@app.route("/pdf")
def pdf_page():
    return render_template("pdf.html")
@app.route("/notes")
def notes_page():
    return render_template("notes.html")

@app.route("/summarize-notes", methods=["POST"])
def summarize_notes():
    data = request.json
    notes_text = data.get("notes", "")

    if not notes_text.strip():
        return jsonify({"error": "No notes provided"}), 400

    raw = ask_ai(
        """You are an expert study assistant.
Analyze the student's notes and return ONLY a valid JSON object like this:
{
  "title": "Topic title in 5 words",
  "summary": "Clear 3-4 sentence summary of the notes",
  "key_points": [
    "Key point 1",
    "Key point 2",
    "Key point 3",
    "Key point 4",
    "Key point 5"
  ],
  "important_terms": [
    {"term": "Term 1", "meaning": "Short definition"},
    {"term": "Term 2", "meaning": "Short definition"},
    {"term": "Term 3", "meaning": "Short definition"}
  ],
  "quiz": [
    {"question": "Question 1?", "answer": "Answer 1"},
    {"question": "Question 2?", "answer": "Answer 2"},
    {"question": "Question 3?", "answer": "Answer 3"}
  ],
  "study_tips": ["Tip 1", "Tip 2", "Tip 3"],
  "difficulty": "Beginner or Intermediate or Advanced"
}
Return ONLY JSON. No markdown. No extra text.""",
        f"Student Notes:\n{notes_text[:5000]}",
        max_tokens=1500
    )

    try:
        raw = raw.replace("```json","").replace("```","").strip()
        s = raw.find("{")
        e = raw.rfind("}") + 1
        result = json.loads(raw[s:e])
        session["pdf_text"] = notes_text
        session["pdf_title"] = result.get("title", "Notes")
        return jsonify(result)
    except Exception as ex:
        print("Notes parse error:", ex)
        return jsonify({"error": "AI parsing failed. Try again."}), 500


# ── TEST ───────────────────────────────────────────
@app.route("/test")
def test():
    result = ask_ai("You are helpful.", "Say hello in one word")
    return jsonify({"result": result})


# ── PDF SUMMARIZE ──────────────────────────────────
@app.route("/summarize", methods=["POST"])
def summarize():
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded"}), 400

    pdf_file = request.files["pdf"]
    if not pdf_file.filename.endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF file"}), 400

    try:
        # Extract text from PDF using PyMuPDF
        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        full_text = ""
        for page in doc:
            full_text += page.get_text()

        doc.close()

        # Limit text to avoid token overflow
        text_chunk = full_text[:6000]

        if not text_chunk.strip():
            return jsonify({"error": "PDF appears to be empty or image-based"}), 400

        # Ask AI to summarize
        summary_raw = ask_ai(
            """You are an expert document analyst.
Analyze the document and return ONLY a valid JSON object like this:
{
  "title": "Document title or topic in 5 words",
  "summary": "A clear 4-5 sentence summary of the entire document",
  "key_points": [
    "Key point 1 — important fact or concept",
    "Key point 2 — important fact or concept",
    "Key point 3 — important fact or concept",
    "Key point 4 — important fact or concept",
    "Key point 5 — important fact or concept",
    "Key point 6 — important fact or concept"
  ],
  "important_terms": [
    {"term": "Term 1", "meaning": "Short definition"},
    {"term": "Term 2", "meaning": "Short definition"},
    {"term": "Term 3", "meaning": "Short definition"},
    {"term": "Term 4", "meaning": "Short definition"}
  ],
  "difficulty": "Beginner or Intermediate or Advanced",
  "read_time": "estimated read time like 5 mins"
}
Return ONLY the JSON. No markdown. No explanation.""",
            f"Document content:\n{text_chunk}",
            max_tokens=1500
        )

        print("Summary raw:", summary_raw[:200])

        # Parse JSON
        summary_raw = summary_raw.replace("```json","").replace("```","").strip()
        s = summary_raw.find("{")
        e = summary_raw.rfind("}") + 1
        result = json.loads(summary_raw[s:e])

        # Save PDF text for chatbot context
        session["pdf_text"] = text_chunk
        session["pdf_title"] = result.get("title", "Document")

        return jsonify(result)

    except json.JSONDecodeError as e:
        print("JSON parse error:", e)
        return jsonify({"error": "AI response parsing failed. Try again."}), 500
    except Exception as e:
        print("PDF error:", str(e))
        return jsonify({"error": str(e)}), 500


# ── CHATBOT ────────────────────────────────────────
@app.route("/chatbot", methods=["POST"])
def chatbot():
    data = request.json
    user_message = data.get("message", "")
    history = data.get("history", [])
    pdf_context = session.get("pdf_text", "")
    pdf_title = session.get("pdf_title", "")

    system = """You are FutureQuadra — a friendly, witty AI assistant.
You help students with coding, career advice, interview tips, and questions.
Keep responses clear, helpful and conversational. Use emojis occasionally.
Always be encouraging and supportive."""

    if pdf_context:
        system += f"""

You also have access to a document the user uploaded titled: "{pdf_title}".
Document content: {pdf_context[:3000]}

If the user asks anything about this document, answer from it directly.
"""

    messages = [{"role": "system", "content": system}]
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=600,
            temperature=0.8
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        print("Chatbot error:", str(e))
        reply = f"Error: {str(e)}"

    return jsonify({"reply": reply})


# ── INTERVIEW ROUTES ───────────────────────────────
@app.route("/start", methods=["POST"])
def start():
    data = request.json
    job_description = data.get("job_description", "")

    raw = ask_ai(
        """You are an expert technical interviewer.
Generate exactly 5 interview questions based on the job description.
Mix technical and behavioral questions.
Return ONLY a valid JSON array. No explanation. No markdown.
Example: ["Question 1", "Question 2", "Question 3", "Question 4", "Question 5"]""",
        f"Job Description:\n{job_description}"
    )

    try:
        raw = raw.replace("```json","").replace("```","").strip()
        s = raw.find("["); e = raw.rfind("]") + 1
        questions = json.loads(raw[s:e])
        questions = [str(q) for q in questions[:5]]
    except:
        questions = [
            "Tell me about yourself.",
            "What are your strongest technical skills?",
            "Describe a challenging project.",
            "How do you handle pressure?",
            "Where do you see yourself in 5 years?"
        ]

    session["questions"] = questions
    session["current_q"] = 0
    session["answers"] = []
    session["job_description"] = job_description

    return jsonify({"question": questions[0], "q_number": 1, "total": len(questions)})


@app.route("/respond", methods=["POST"])
def respond():
    data = request.json
    user_answer = data.get("answer", "")
    questions = session.get("questions", [])
    current_q = session.get("current_q", 0)
    answers = session.get("answers", [])

    answers.append({"question": questions[current_q], "answer": user_answer})
    session["answers"] = answers
    session["current_q"] = current_q + 1

    feedback = ask_ai(
        """You are a warm encouraging interview coach.
Give exactly 2 sentences of feedback. Start with: Great answer!, Good point!, or Nice response!
No bullet points. Speak naturally.""",
        f'Question: "{questions[current_q]}"\nAnswer: "{user_answer}"'
    )

    if feedback.startswith("ERROR:"):
        feedback = "Good effort! Keep going."

    if current_q + 1 < len(questions):
        return jsonify({
            "feedback": feedback,
            "next_question": questions[current_q + 1],
            "q_number": current_q + 2,
            "total": len(questions),
            "done": False
        })

    qa_text = "\n\n".join([
        f"Q{i+1}: {a['question']}\nAnswer: {a['answer']}"
        for i, a in enumerate(answers)
    ])

    raw_score = ask_ai(
        """You are a professional interview evaluator.
Return ONLY raw JSON, no markdown:
{"score": 75, "rating": "Good", "summary": "2 sentence summary", "tips": ["tip 1", "tip 2", "tip 3"]}
Rating: Excellent, Good, Average, or Needs Improvement""",
        qa_text
    )

    try:
        raw_score = raw_score.replace("```json","").replace("```","").strip()
        s = raw_score.find("{"); e = raw_score.rfind("}") + 1
        score_data = json.loads(raw_score[s:e])
    except:
        score_data = {
            "score": 72, "rating": "Good",
            "summary": "You completed the interview well!",
            "tips": ["Use STAR method", "Give specific examples", "Stay confident"]
        }

    return jsonify({"feedback": feedback, "done": True, "score_data": score_data})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)