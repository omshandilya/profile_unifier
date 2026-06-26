# Dev Profile Unifier (effiflo-dev-unifier)

A Python 3.11 FastAPI service to unify developer profiles across GitHub, StackOverflow, dev.to, and Hacker News using Gemini LLM enrichment and entity resolution.

## Getting Started

### Installation

1. Clone the repository and navigate into it:
   ```bash
   cd effiflo-dev-unifier
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # Windows
   # or source venv/bin/activate on Unix
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   copy .env.example .env
   ```

### Running the App

Run the development server:
```bash
uvicorn app.main:app --reload
```

### Running Tests

Run the test suite:
```bash
pytest
```
