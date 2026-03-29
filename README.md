# Interactcode Voice Agent

A desktop voice assistant app built with Python and Tkinter.

It supports:
- typed chat input
- microphone speech-to-text input
- text-to-speech output
- a local agent with simple intent handling (time, date, repeat, help)

## Features

- Clean Tkinter GUI chat window
- `Listen` button to capture microphone input
- `Speak Last` button to read the latest agent response
- Lightweight local agent logic with short conversation memory
- Status updates for calibration, listening, speaking, and errors

## Requirements

- Python 3.11+
- A working microphone
- Windows (recommended setup in this README)

Python packages:
- `SpeechRecognition`
- `PyAudio`
- `pyttsx3`

## Setup

### 1. Activate virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

If your virtual environment is already active:

```powershell
pip install SpeechRecognition PyAudio pyttsx3
```

Or install directly using the project environment Python:

```powershell
"d:/project/interactive coding/Interactcode/.venv/Scripts/python.exe" -m pip install SpeechRecognition PyAudio pyttsx3
```

## Run

From an activated environment:

```powershell
python main.py
```

Without activating the environment:

```powershell
"d:/project/interactive coding/Interactcode/.venv/Scripts/python.exe" main.py
```

## App Controls

- `Send`: send typed text to the agent
- `Listen`: capture speech from microphone and transcribe it
- `Speak Last`: speak the latest agent reply
- `Clear Chat`: clear conversation history shown in the GUI

## Customize Agent Logic

You can modify the local assistant behavior in:
- `LocalVoiceAgent.reply(...)` in `main.py`

This is the main place to add:
- custom commands
- API calls to external AI services
- domain-specific workflows

## Troubleshooting

- If microphone input fails, check Windows microphone permissions.
- If recognition says it cannot understand words, speak more clearly and reduce background noise.
- `recognize_google` needs internet; if unavailable, speech recognition may fail unless offline recognizers are configured.
- If text-to-speech fails, reinstall `pyttsx3` in the same virtual environment.

## Project Structure

- `main.py` - Voice-agent GUI application
- `README.md` - Project documentation
