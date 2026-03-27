# AI Interview Analyzer

> Practice Smarter. Get Hired Faster.

An AI-powered mock interview platform that simulates real interviews with adaptive questioning, voice-based answering, real-time scoring, and instant feedback — all in a sleek, dark-themed web interface.

---

## Features

- Voice-Based Answering — Record answers directly in the browser  
- Adaptive AI Questions — Questions adjust based on previous performance  
- Multi-Dimensional Scoring — Relevance, Clarity, and Depth evaluation  
- Timed Responses — Simulates real interview pressure  
- AI Feedback — Structured feedback using LLaMA 3.1  
- Filler Word Detection — Detects "um", "uh", "like", etc.  
- Sentiment Analysis — Positive / Neutral / Negative tone detection  
- PDF & TXT Reports — Download full session reports  
- Performance Dashboard — Track progress over time  
- User Authentication — Secure login with SHA-256 hashing  

---

## Tech Stack

| Component | Technology |
|----------|-----------|
| UI Framework | Streamlit |
| AI / LLM | Groq (LLaMA 3.1-8b-instant) |
| Speech-to-Text | Google Speech Recognition |
| NLP / Sentiment | TextBlob |
| Database | SQLite |
| PDF Generation | FPDF |
| Authentication | SHA-256 (hashlib) |

---

## Project Structure

```
ai-interview-analyzer/
│
├── app2.py
├── users.db
├── image.png
├── image copy.png
├── requirements.txt
└── README.md
```

---

## Installation & Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-username/ai-interview-analyzer.git
cd ai-interview-analyzer
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Groq API Key

Option 1 — Directly in code:

```python
client = Groq(api_key="your_groq_api_key_here")
```

Option 2 — Using Streamlit secrets:

```toml
# .streamlit/secrets.toml
GROQ_API_KEY = "your_groq_api_key_here"
```

```python
client = Groq(api_key=st.secrets["GROQ_API_KEY"])
```

### 5. Run Application

```bash
streamlit run app2.py
```

Open: [http://localhost:8501](http://localhost:8501)

---

## Requirements

```
streamlit
speechrecognition
textblob
groq
fpdf
```

### Optional (Microphone Support)

- Windows:
  ```
  pip install pyaudio
  ```
- macOS:
  ```
  brew install portaudio && pip install pyaudio
  ```
- Linux:
  ```
  sudo apt-get install portaudio19-dev && pip install pyaudio
  ```

---

## Usage

### Step 1: Authentication

Sign up or log in using your credentials.

### Step 2: Dashboard

View performance stats including total interviews and average scores.

### Step 3: Configure Interview

- Select job role
- Choose interview mode
- Set number of questions
- Define time limit

### Step 4: Answer Questions

- Generate question
- Record response
- Automatic transcription and evaluation

### Step 5: Review Results

- Score breakdown
- Sentiment analysis
- Feedback
- Performance tracking

### Step 6: Download Reports

Export results as TXT or PDF.

---

## Adaptive Questioning Logic

| Question | Behavior            |
| -------- | ------------------- |
| Q1       | Introduction        |
| Q2       | Role-based question |
| Q3+      | Adaptive difficulty |

Rules:

- Score ≥ 75 → Increase difficulty
- Score < 50 → Simplify questions
- No repetition of similar questions

---

## Scoring Metrics

| Metric      | Description           |
| ----------- | --------------------- |
| Relevance   | Answer accuracy       |
| Clarity     | Communication quality |
| Depth       | Insight level         |
| Final Score | Overall performance   |

---

## Database Schema

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE interview_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    role TEXT NOT NULL,
    avg_score REAL NOT NULL,
    total_questions INTEGER NOT NULL,
    date TEXT NOT NULL
);
```

---

## Known Limitations

- Requires stable internet for speech recognition
- Microphone permissions needed
- Groq API rate limits on free tier
- Local images must be present

---

## Future Enhancements

- Custom job roles
- Video + body language analysis
- Multi-language support
- Interview scheduling
- Leaderboards
- LinkedIn integration
- Advanced analytics
- Theme toggle

---

## Contributing

1. Fork repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

---

## License

MIT License

---

## Author

Developed using Streamlit and Groq AI.

---

## Support

If you found this project useful, consider giving it a star on GitHub.
