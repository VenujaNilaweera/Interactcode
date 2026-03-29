"""Simple desktop GUI for a voice-enabled agent.

Features:
- Chat window with typed input
- Optional voice input using SpeechRecognition
- Optional voice output using pyttsx3

This app is intentionally lightweight so you can plug your own agent logic into
the `generate_agent_reply` function.
"""

from __future__ import annotations

from datetime import datetime
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None


class LocalVoiceAgent:
    """Small local agent with lightweight intent handling and short memory."""

    def __init__(self) -> None:
        self.memory: list[str] = []

    def reply(self, user_text: str) -> str:
        cleaned = " ".join(user_text.strip().split())
        if not cleaned:
            return "Please say or type something so I can help."

        self.memory.append(cleaned)
        if len(self.memory) > 10:
            self.memory.pop(0)

        lower = cleaned.lower()

        if any(word in lower for word in ("hello", "hi", "hey")):
            return "Hi, I can hear you. Tell me what you want to do."

        if "time" in lower:
            now = datetime.now().strftime("%I:%M %p")
            return f"Current time is {now}."

        if "date" in lower or "day" in lower:
            today = datetime.now().strftime("%A, %d %B %Y")
            return f"Today is {today}."

        if "repeat" in lower and len(self.memory) > 1:
            return f"Your last message was: {self.memory[-2]}"

        if "help" in lower:
            return (
                "You can ask me simple things like time, date, or repeat. "
                "You can also just talk and I will transcribe your speech."
            )

        return f"I heard: {cleaned}"


class VoiceAgentGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Voice Agent GUI")
        self.root.geometry("760x520")
        self.root.minsize(560, 420)

        self.engine = self._init_tts_engine()
        self.recognizer = sr.Recognizer() if sr else None
        self.agent = LocalVoiceAgent()

        self._build_ui()
        self._append_system("Ready. Type a message or click 'Listen'.")

        if sr is None:
            self._append_system("SpeechRecognition not available. Voice input disabled.")
        if pyttsx3 is None:
            self._append_system("pyttsx3 not available. Voice output disabled.")
        if self.recognizer is not None:
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            self.recognizer.non_speaking_duration = 0.5

    def _init_tts_engine(self):
        if pyttsx3 is None:
            return None
        try:
            return pyttsx3.init()
        except Exception:
            return None

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, padx=12, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        self.chat = scrolledtext.ScrolledText(
            container,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Segoe UI", 10),
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        input_row = tk.Frame(container, pady=8)
        input_row.pack(fill=tk.X)

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(input_row, textvariable=self.input_var, font=("Segoe UI", 10))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_entry.bind("<Return>", lambda _event: self.on_send())
        self.input_entry.focus_set()

        send_btn = tk.Button(input_row, text="Send", width=10, command=self.on_send)
        send_btn.pack(side=tk.LEFT, padx=(8, 0))

        control_row = tk.Frame(container)
        control_row.pack(fill=tk.X)

        self.listen_btn = tk.Button(control_row, text="Listen", width=12, command=self.on_listen)
        self.listen_btn.pack(side=tk.LEFT)

        self.speak_btn = tk.Button(control_row, text="Speak Last", width=12, command=self.on_speak_last)
        self.speak_btn.pack(side=tk.LEFT, padx=(8, 0))

        clear_btn = tk.Button(control_row, text="Clear Chat", width=12, command=self.on_clear)
        clear_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="Idle")
        status = tk.Label(container, textvariable=self.status_var, anchor="w", fg="#444")
        status.pack(fill=tk.X, pady=(8, 0))

        self.last_reply = ""

    def _append_line(self, role: str, message: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{role}: {message}\n")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _append_user(self, message: str) -> None:
        self._append_line("You", message)

    def _append_agent(self, message: str) -> None:
        self.last_reply = message
        self._append_line("Agent", message)

    def _append_system(self, message: str) -> None:
        self._append_line("System", message)

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def on_send(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            return

        self.input_var.set("")
        self._append_user(text)

        reply = self.agent.reply(text)
        self._append_agent(reply)

    def on_speak_last(self) -> None:
        if not self.last_reply:
            messagebox.showinfo("Speak", "No agent reply yet.")
            return
        self._speak_async(self.last_reply)

    def on_listen(self) -> None:
        if self.recognizer is None:
            messagebox.showwarning("Voice Input", "SpeechRecognition library is not available.")
            return

        self.listen_btn.configure(state=tk.DISABLED)
        self._set_status("Listening... Speak now")
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self) -> None:
        assert self.recognizer is not None

        try:
            with sr.Microphone() as source:
                self.root.after(0, lambda: self._set_status("Calibrating noise..."))
                self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
                self.root.after(0, lambda: self._set_status("Listening..."))
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)

            text = self._recognize_speech(audio)
            self.root.after(0, lambda: self._handle_listen_success(text))
        except sr.WaitTimeoutError:
            self.root.after(0, lambda: self._handle_listen_error("No speech detected before timeout."))
        except sr.UnknownValueError:
            self.root.after(0, lambda: self._handle_listen_error("I heard audio but could not understand words."))
        except sr.RequestError as exc:
            self.root.after(0, lambda: self._handle_listen_error(f"Speech service error: {exc}"))
        except Exception as exc:
            self.root.after(0, lambda: self._handle_listen_error(str(exc)))

    def _recognize_speech(self, audio):
        """Try online recognition first; use offline Sphinx if available."""
        assert self.recognizer is not None

        try:
            return self.recognizer.recognize_google(audio)
        except sr.RequestError:
            if hasattr(self.recognizer, "recognize_sphinx"):
                return self.recognizer.recognize_sphinx(audio)
            raise

    def _handle_listen_success(self, text: str) -> None:
        self._set_status("Heard input")
        self.listen_btn.configure(state=tk.NORMAL)
        self._append_user(text)
        reply = self.agent.reply(text)
        self._append_agent(reply)

    def _handle_listen_error(self, error_text: str) -> None:
        self._set_status("Listen failed")
        self.listen_btn.configure(state=tk.NORMAL)
        self._append_system(f"Could not capture voice input: {error_text}")

    def _speak_async(self, text: str) -> None:
        if self.engine is None:
            messagebox.showwarning("Voice Output", "pyttsx3 library is not available.")
            return

        self._set_status("Speaking...")
        threading.Thread(target=self._speak_worker, args=(text,), daemon=True).start()

    def _speak_worker(self, text: str) -> None:
        try:
            assert self.engine is not None
            self.engine.say(text)
            self.engine.runAndWait()
            self.root.after(0, lambda: self._set_status("Idle"))
        except Exception as exc:
            self.root.after(0, lambda: self._append_system(f"TTS error: {exc}"))
            self.root.after(0, lambda: self._set_status("Idle"))

    def on_clear(self) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)
        self.last_reply = ""
        self._append_system("Chat cleared.")


def main() -> None:
    root = tk.Tk()
    VoiceAgentGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()