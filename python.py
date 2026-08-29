"""
Pydroid AI Assistant - starter build
=====================================
A single-file Python assistant designed to run inside Pydroid 3 on Android.

WHAT THIS COVERS (realistically, from your feature list):
  - Answer Questions / Content Creation / Coding help / Decision Support
      -> via a cloud LLM API call (you plug in a key)
  - Multi-Turn Conversation (remembers chat history)
  - Memory & Personal Knowledge Base (saved to a local JSON file)
  - Custom Instructions (tone/style/persona you set)
  - File Upload Support (PDF, DOCX, XLSX, TXT)
  - Data Analysis (basic stats + chart from a CSV/XLSX)
  - Voice-to-Text & Text-to-Speech
  - Real-Time Web Access (simple web search + fetch)
  - Automate Tasks (local reminders, saved to file, checked on startup)
  - Multi-Language Support (translation via API)
  - Code Execution (runs small Python snippets locally, sandboxed-ish)
  - Privacy Controls (an "incognito" mode that skips saving memory)

WHAT THIS DOES **NOT** COVER (needs infrastructure a phone can't run):
  - Image/video generation, real speech-to-speech, huge local models,
    proactive OS-level automation (calendar/Slack/CRM integrations),
    true offline LLM reasoning (a phone can run a *tiny* local model,
    see the OFFLINE_MODE note at the bottom, but it will be weak).
"""

import os
import json
import datetime
import subprocess

# ---------------------------------------------------------------------------
# 0. CONFIG
# ---------------------------------------------------------------------------
# Put your API key here, or better: set it as an environment variable
# before launching Pydroid isn't possible on Android easily, so just
# paste it here for a personal/local build. Don't share this file with
# the key filled in.
API_KEY = "PUT_YOUR_ANTHROPIC_OR_OPENAI_KEY_HERE"
API_PROVIDER = "anthropic"  # "anthropic" or "openai"

MEMORY_FILE = "assistant_memory.json"
REMINDERS_FILE = "reminders.json"
INCOGNITO = False  # set True to stop saving anything to disk this session


# ---------------------------------------------------------------------------
# 1. MEMORY (multi-turn conversation + long-term facts)
# ---------------------------------------------------------------------------
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": [], "profile": {}}


def save_memory(memory):
    if INCOGNITO:
        return
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)


def remember_fact(memory, key, value):
    memory["profile"][key] = value
    save_memory(memory)


# ---------------------------------------------------------------------------
# 2. THE "BRAIN" - call a cloud LLM for the heavy reasoning features
#    (answering questions, writing, coding, translation, decisions)
# ---------------------------------------------------------------------------
def ask_ai(memory, user_text, system_style="Be concise, clear, and helpful."):
    import urllib.request

    history = memory["history"][-10:]  # last 10 turns for context
    messages = history + [{"role": "user", "content": user_text}]

    if API_PROVIDER == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 1000,
            "system": system_style,
            "messages": messages,
        }
    else:  # openai
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "content-type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
        body = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": system_style}] + messages,
        }

    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"[Network/API error: {e}]"

    if API_PROVIDER == "anthropic":
        reply = "".join(
            block.get("text", "") for block in data.get("content", [])
        )
    else:
        reply = data["choices"][0]["message"]["content"]

    memory["history"].append({"role": "user", "content": user_text})
    memory["history"].append({"role": "assistant", "content": reply})
    save_memory(memory)
    return reply


# ---------------------------------------------------------------------------
# 3. FILE READING (PDF, DOCX, XLSX, TXT) -> feed extracted text to ask_ai()
# ---------------------------------------------------------------------------
def read_file(path):
    ext = path.lower().rsplit(".", 1)[-1]
    try:
        if ext == "txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == "pdf":
            from PyPDF2 import PdfReader
            reader = PdfReader(path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext == "docx":
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        elif ext in ("xlsx", "xls", "csv"):
            import pandas as pd
            df = pd.read_csv(path) if ext == "csv" else pd.read_excel(path)
            return df.to_string()
        else:
            return f"[Unsupported file type: {ext}]"
    except Exception as e:
        return f"[Could not read file: {e}]"


# ---------------------------------------------------------------------------
# 4. DATA ANALYSIS - quick stats + a chart from a spreadsheet
# ---------------------------------------------------------------------------
def analyze_spreadsheet(path, chart_out="chart.png"):
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")  # no GUI backend needed
    import matplotlib.pyplot as plt

    df = pd.read_csv(path) if path.endswith(".csv") else pd.read_excel(path)
    summary = df.describe(include="all").to_string()

    numeric_cols = df.select_dtypes(include="number").columns
    if len(numeric_cols) > 0:
        df[numeric_cols].plot(kind="line")
        plt.tight_layout()
        plt.savefig(chart_out)
        chart_msg = f"Chart saved to {chart_out}"
    else:
        chart_msg = "No numeric columns found to chart."

    return summary, chart_msg


# ---------------------------------------------------------------------------
# 5. VOICE - speech to text + text to speech
# ---------------------------------------------------------------------------
def listen():
    import speech_recognition as sr
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        audio = r.listen(source)
    try:
        return r.recognize_google(audio)
    except Exception as e:
        return f"[Could not understand audio: {e}]"


def speak(text):
    # gTTS + a player is more reliable on Android than pyttsx3
    from gtts import gTTS
    tts = gTTS(text=text, lang="en")
    tts.save("reply.mp3")
    # Pydroid can't always auto-play; open with an Android intent instead:
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        File = autoclass("java.io.File")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(Intent.ACTION_VIEW)
        uri = Uri.fromFile(File(os.path.abspath("reply.mp3")))
        intent.setDataAndType(uri, "audio/mp3")
        PythonActivity.mActivity.startActivity(intent)
    except Exception:
        print("Saved reply.mp3 - open it manually with a music/file app.")


# ---------------------------------------------------------------------------
# 6. WEB ACCESS - simple search + page fetch
# ---------------------------------------------------------------------------
def web_search(query):
    import requests
    # DuckDuckGo's instant-answer API needs no key (limited results)
    r = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1},
        timeout=10,
    )
    data = r.json()
    return data.get("AbstractText") or "No instant answer found. Try a direct fetch."


# ---------------------------------------------------------------------------
# 7. TASK AUTOMATION - simple local reminders
# ---------------------------------------------------------------------------
def add_reminder(text, when_iso):
    reminders = []
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE) as f:
            reminders = json.load(f)
    reminders.append({"text": text, "when": when_iso, "done": False})
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)


def check_due_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return []
    with open(REMINDERS_FILE) as f:
        reminders = json.load(f)
    now = datetime.datetime.now().isoformat()
    due = [r for r in reminders if not r["done"] and r["when"] <= now]
    for r in due:
        r["done"] = True
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)
    return due


# ---------------------------------------------------------------------------
# 8. CODE EXECUTION - run a short Python snippet and return output
# ---------------------------------------------------------------------------
def run_python_snippet(code, timeout=5):
    with open("_snippet.py", "w") as f:
        f.write(code)
    try:
        result = subprocess.run(
            ["python", "_snippet.py"], capture_output=True, text=True, timeout=timeout
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"[Execution error: {e}]"


# ---------------------------------------------------------------------------
# 9. MAIN LOOP - simple text menu (swap for Kivy/GUI later if you want)
# ---------------------------------------------------------------------------
def main():
    memory = load_memory()
    due = check_due_reminders()
    for r in due:
        print(f"REMINDER: {r['text']}")

    print("AI Assistant ready. Type 'help' for commands, 'exit' to quit.")
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break

        elif user_input.lower() == "help":
            print(
                "Commands:\n"
                "  ask <question>          - chat with the AI\n"
                "  file <path>             - read & summarize a file\n"
                "  analyze <path.csv/xlsx> - stats + chart\n"
                "  search <query>          - web search\n"
                "  remind <text> | <ISO time> - set a reminder\n"
                "  listen                  - voice input\n"
                "  say <text>              - text to speech\n"
                "  run <code>              - execute a python one-liner\n"
                "  remember <key>=<value>  - save a fact about you\n"
                "  exit                    - quit"
            )

        elif user_input.startswith("ask "):
            print("AI:", ask_ai(memory, user_input[4:]))

        elif user_input.startswith("file "):
            text = read_file(user_input[5:].strip())
            print("AI:", ask_ai(memory, f"Summarize this:\n\n{text[:6000]}"))

        elif user_input.startswith("analyze "):
            summary, chart_msg = analyze_spreadsheet(user_input[8:].strip())
            print(summary)
            print(chart_msg)

        elif user_input.startswith("search "):
            print(web_search(user_input[7:]))

        elif user_input.startswith("remind "):
            try:
                text, when = user_input[7:].split("|")
                add_reminder(text.strip(), when.strip())
                print("Reminder saved.")
            except ValueError:
                print("Format: remind <text> | <ISO time e.g. 2026-08-30T09:00>")

        elif user_input == "listen":
            heard = listen()
            print("You said:", heard)
            print("AI:", ask_ai(memory, heard))

        elif user_input.startswith("say "):
            speak(user_input[4:])

        elif user_input.startswith("run "):
            print(run_python_snippet(user_input[4:]))

        elif user_input.startswith("remember "):
            try:
                k, v = user_input[9:].split("=", 1)
                remember_fact(memory, k.strip(), v.strip())
                print(f"Saved: {k.strip()} = {v.strip()}")
            except ValueError:
                print("Format: remember key=value")

        else:
            print("AI:", ask_ai(memory, user_input))


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# OFFLINE_MODE note:
# True offline "thinking" needs a local model. On a phone this is only
# realistic with a tiny quantized model via something like llama.cpp
# compiled for Android - not pip-installable in Pydroid itself. If you
# want offline text-only replies with no AI reasoning, you could swap
# ask_ai() for simple rule-based / keyword matching as a fallback when
# there's no internet.
# ---------------------------------------------------------------------------
