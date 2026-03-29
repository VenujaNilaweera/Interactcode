"""Continuous-listening voice agent with humanized TTS.

Features
--------
- Continuous listening loop — keeps listening until you click Stop
- "Repeat mode" — agent repeats back exactly what it hears
- Humanized TTS using pyttsx3 with best available voice selection
  (prefers neural/enhanced voices; falls back gracefully)
- Clean dark Tkinter GUI
- Background threads so the UI never freezes

Dependencies
------------
    pip install SpeechRecognition pyttsx3 pyaudio
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext

# ── optional imports ──────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

# ── colour palette ────────────────────────────────────────────────────────────
BG        = "#0d0f14"
SURFACE   = "#161921"
ACCENT    = "#4f8ef7"
ACCENT2   = "#a78bfa"
TEXT      = "#e8eaf0"
MUTED     = "#6b7280"
USER_CLR  = "#4f8ef7"
AGENT_CLR = "#a78bfa"
SYS_CLR   = "#4b5563"
DANGER    = "#ef4444"
SUCCESS   = "#22c55e"

FONT_MONO = ("Consolas", 10)
FONT_UI   = ("Segoe UI", 10)


# ── TTS helpers ───────────────────────────────────────────────────────────────

def _pick_best_voice(engine) -> None:
    """Select the most human-sounding voice available."""
    if engine is None:
        return

    voices = engine.getProperty("voices")
    if not voices:
        return

    priority = [
        "zira", "david", "hazel", "george",
        "ava", "samantha", "alex",
        "english",
    ]

    best = None
    best_score = -1
    for v in voices:
        name_lower = (v.name or "").lower()
        score = sum(1 for kw in priority if kw in name_lower)
        langs = getattr(v, "languages", []) or []
        lang_str = " ".join(str(l) for l in langs).lower()
        if "en" in lang_str or "english" in name_lower:
            score += 2
        if score > best_score:
            best_score = score
            best = v

    if best:
        engine.setProperty("voice", best.id)

    engine.setProperty("rate", 165)
    engine.setProperty("volume", 0.95)


# ── Dedicated TTS worker thread ───────────────────────────────────────────────
# pyttsx3 MUST be init'd and used on the SAME thread every time.
# We create one long-lived thread that owns the engine and processes a queue.

import queue as _queue

class TTSWorker:
    """Runs pyttsx3 on a single dedicated thread via a job queue."""

    _STOP = object()  # sentinel

    def __init__(self, on_status):
        self._q: _queue.Queue = _queue.Queue()
        self._on_status = on_status   # callable(msg, colour)
        self._engine = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def speak(self, text: str) -> None:
        self._q.put(text)

    def stop(self) -> None:
        self._q.put(self._STOP)

    def _run(self) -> None:
        if pyttsx3 is None:
            return
        try:
            self._engine = pyttsx3.init()
            _pick_best_voice(self._engine)
        except Exception:
            return

        while True:
            item = self._q.get()
            if item is self._STOP:
                break
            try:
                self._on_status("Speaking…", ACCENT2)
                self._engine.say(item)
                self._engine.runAndWait()
                self._on_status(None, None)   # None = restore previous status
            except Exception:
                # If the engine ever breaks, reinitialise it
                try:
                    self._engine = pyttsx3.init()
                    _pick_best_voice(self._engine)
                    self._engine.say(item)
                    self._engine.runAndWait()
                    self._on_status(None, None)
                except Exception:
                    pass


# ── Agent ─────────────────────────────────────────────────────────────────────

class Agent:
    """Simple agent: in repeat mode it echoes; otherwise basic intent handling."""

    def __init__(self) -> None:
        self.repeat_mode: bool = False
        self.history: list[str] = []

    def reply(self, text: str) -> str:
        text = " ".join(text.strip().split())
        if not text:
            return ""

        self.history.append(text)
        if len(self.history) > 20:
            self.history.pop(0)

        if self.repeat_mode:
            return text          # pure echo

        lower = text.lower()

        if any(w in lower for w in ("hello", "hi", "hey")):
            return "Hey there! I'm listening."
        if "time" in lower:
            return f"It is {datetime.now().strftime('%I:%M %p')}."
        if "date" in lower or "today" in lower:
            return f"Today is {datetime.now().strftime('%A, %d %B %Y')}."
        if "how are you" in lower:
            return "I'm doing great, thanks for asking!"
        if "your name" in lower:
            return "I'm your voice assistant. You can call me Aria."
        if "help" in lower:
            return (
                "You can ask me the time, date, or just talk. "
                "Enable Repeat Mode to have me echo everything you say."
            )
        return text   # default: echo anyway so speech is always heard


# ── GUI ───────────────────────────────────────────────────────────────────────

class VoiceAgentGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Voice Agent")
        self.root.geometry("820x580")
        self.root.minsize(600, 440)
        self.root.configure(bg=BG)

        self.agent       = Agent()
        self.recognizer  = sr.Recognizer() if sr else None
        self._tts        = TTSWorker(on_status=self._tts_status_cb) if pyttsx3 else None

        self._listening        = False   # continuous loop running?
        self._stop_event       = threading.Event()
        self._listen_thread: threading.Thread | None = None

        if self.recognizer:
            self.recognizer.dynamic_energy_threshold    = True
            self.recognizer.pause_threshold             = 0.6
            self.recognizer.non_speaking_duration       = 0.4
            self.recognizer.energy_threshold            = 300

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._sys("Ready. Click  ▶ Start Listening  to begin.")
        if sr is None:
            self._sys("⚠  SpeechRecognition not installed — voice input disabled.")
        if pyttsx3 is None:
            self._sys("⚠  pyttsx3 not installed — voice output disabled.")

    # ── TTS status callback ────────────────────────────────────────────────────

    def _tts_status_cb(self, msg, colour):
        def _do():
            if msg is None:
                if self._listening:
                    self._status("🎙 Listening…", SUCCESS)
                else:
                    self._status("Idle", MUTED)
            else:
                self._status(msg, colour)
        try:
            self.root.after(0, _do)
        except tk.TclError:
            pass

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── header bar ────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=SURFACE, pady=10, padx=16)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="● VOICE AGENT",
            font=("Consolas", 13, "bold"),
            fg=ACCENT, bg=SURFACE,
        ).pack(side=tk.LEFT)

        self.mode_lbl = tk.Label(
            header, text="MODE: SMART",
            font=("Consolas", 9),
            fg=MUTED, bg=SURFACE,
        )
        self.mode_lbl.pack(side=tk.RIGHT)

        # ── chat area ─────────────────────────────────────────────────────────
        chat_frame = tk.Frame(self.root, bg=BG, padx=14, pady=8)
        chat_frame.pack(fill=tk.BOTH, expand=True)

        self.chat = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=FONT_MONO,
            bg=SURFACE,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=ACCENT,
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=10,
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        # colour tags
        self.chat.tag_config("user",   foreground=USER_CLR)
        self.chat.tag_config("agent",  foreground=AGENT_CLR)
        self.chat.tag_config("system", foreground=SYS_CLR)

        # ── text input row ────────────────────────────────────────────────────
        inp_frame = tk.Frame(self.root, bg=BG, padx=14, pady=4)
        inp_frame.pack(fill=tk.X)

        self.input_var = tk.StringVar()
        self.entry = tk.Entry(
            inp_frame,
            textvariable=self.input_var,
            font=FONT_UI,
            bg=SURFACE, fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT, bd=0,
            highlightthickness=1,
            highlightbackground=MUTED,
            highlightcolor=ACCENT,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))
        self.entry.bind("<Return>", lambda _: self._on_type_send())

        tk.Button(
            inp_frame, text="Send",
            command=self._on_type_send,
            font=FONT_UI,
            bg=ACCENT, fg="white",
            activebackground=ACCENT2,
            relief=tk.FLAT, bd=0,
            padx=14, pady=5,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        # ── control row ───────────────────────────────────────────────────────
        ctrl = tk.Frame(self.root, bg=BG, padx=14, pady=8)
        ctrl.pack(fill=tk.X)

        self.listen_btn = self._btn(
            ctrl, "▶  Start Listening", SUCCESS, self._toggle_listen, side=tk.LEFT
        )

        self.repeat_btn = self._btn(
            ctrl, "◎  Repeat Mode: OFF", SURFACE, self._toggle_repeat,
            side=tk.LEFT, padx=(10, 0),
            border_color=ACCENT2, fg=ACCENT2,
        )

        self._btn(
            ctrl, "🔊  Speak Last", SURFACE, self._speak_last,
            side=tk.LEFT, padx=(10, 0),
            border_color=MUTED, fg=MUTED,
        )

        self._btn(
            ctrl, "✕  Clear", SURFACE, self._clear,
            side=tk.RIGHT,
            border_color=DANGER, fg=DANGER,
        )

        # ── status bar ────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Idle")
        status_bar = tk.Frame(self.root, bg="#0a0c10", pady=4)
        status_bar.pack(fill=tk.X)

        self.pulse_lbl = tk.Label(status_bar, text="●", fg=MUTED, bg="#0a0c10", font=("Consolas", 10))
        self.pulse_lbl.pack(side=tk.LEFT, padx=(14, 4))

        tk.Label(
            status_bar,
            textvariable=self.status_var,
            fg=MUTED, bg="#0a0c10",
            font=("Consolas", 9),
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X)

        self.last_reply: str = ""

    def _btn(
        self, parent, text, bg, cmd,
        side=tk.LEFT, padx=0,
        border_color=None, fg="white",
    ):
        f = tk.Frame(parent, bg=border_color or bg, padx=1 if border_color else 0, pady=1 if border_color else 0)
        f.pack(side=side, padx=padx)
        b = tk.Button(
            f, text=text, command=cmd,
            font=FONT_UI,
            bg=bg, fg=fg,
            activebackground=SURFACE,
            relief=tk.FLAT, bd=0,
            padx=12, pady=5,
            cursor="hand2",
        )
        b.pack()
        return b

    # ── append helpers ────────────────────────────────────────────────────────

    def _append(self, tag: str, label: str, msg: str) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{label}: ", tag)
        self.chat.insert(tk.END, f"{msg}\n")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _user(self, m):  self._append("user",   "You",    m)
    def _agent(self, m):
        self.last_reply = m
        self._append("agent", "Aria",   m)
    def _sys(self, m):   self._append("system", "System", m)

    def _status(self, m: str, dot_color: str = MUTED) -> None:
        self.status_var.set(m)
        self.pulse_lbl.configure(fg=dot_color)

    # ── typed input ───────────────────────────────────────────────────────────

    def _on_type_send(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            return
        self.input_var.set("")
        self._user(text)
        reply = self.agent.reply(text)
        if reply:
            self._agent(reply)
            self._speak_async(reply)

    # ── repeat mode toggle ────────────────────────────────────────────────────

    def _toggle_repeat(self) -> None:
        self.agent.repeat_mode = not self.agent.repeat_mode
        if self.agent.repeat_mode:
            self.repeat_btn.configure(text="◎  Repeat Mode: ON", fg=ACCENT2, bg="#1a1040")
            self.mode_lbl.configure(text="MODE: REPEAT", fg=ACCENT2)
            self._sys("Repeat mode ON — I will echo everything you say.")
        else:
            self.repeat_btn.configure(text="◎  Repeat Mode: OFF", fg=ACCENT2, bg=SURFACE)
            self.mode_lbl.configure(text="MODE: SMART", fg=MUTED)
            self._sys("Repeat mode OFF — back to smart responses.")

    # ── continuous listen loop ────────────────────────────────────────────────

    def _toggle_listen(self) -> None:
        if not self._listening:
            self._start_listening()
        else:
            self._stop_listening()

    def _start_listening(self) -> None:
        if self.recognizer is None:
            self._sys("SpeechRecognition not available.")
            return
        if self._listen_thread and self._listen_thread.is_alive():
            return
        self._listening = True
        self._stop_event.clear()
        self.listen_btn.configure(text="■  Stop Listening", bg=DANGER)
        self._status("Continuous listening active", SUCCESS)
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()

    def _stop_listening(self) -> None:
        self._listening = False
        self._stop_event.set()
        self.listen_btn.configure(text="▶  Start Listening", bg=SUCCESS)
        self._status("Idle", MUTED)
        self._sys("Stopped listening.")
        self._listen_thread = None

    def _listen_loop(self) -> None:
        """Background loop: listen → transcribe → reply → repeat."""
        assert self.recognizer is not None

        try:
            mic = sr.Microphone()
        except Exception as exc:
            self.root.after(0, lambda: self._sys(f"Microphone error: {exc}"))
            self.root.after(0, self._stop_listening)
            return

        with mic as source:
            self.root.after(0, lambda: self._status("Calibrating…", ACCENT))
            self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
            self.root.after(0, lambda: self._status("🎙 Listening…", SUCCESS))

            while not self._stop_event.is_set():
                try:
                    audio = self.recognizer.listen(
                        source,
                        timeout=None,          # wait indefinitely for speech start
                        phrase_time_limit=12,  # max phrase length
                    )
                except Exception:
                    continue

                if self._stop_event.is_set():
                    break

                # Transcribe in a thread so we don't block the mic
                threading.Thread(
                    target=self._transcribe_and_reply,
                    args=(audio,),
                    daemon=True,
                ).start()

    def _transcribe_and_reply(self, audio) -> None:
        try:
            text = self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return   # silence / unintelligible — just skip
        except sr.RequestError as exc:
            self.root.after(0, lambda: self._sys(f"Speech service error: {exc}"))
            return
        except Exception as exc:
            self.root.after(0, lambda: self._sys(str(exc)))
            return

        if not text.strip():
            return

        captured = text
        self.root.after(0, lambda: self._user(captured))

        reply = self.agent.reply(captured)
        if reply:
            self.root.after(0, lambda: self._agent(reply))
            self._speak_async(reply)

    # ── TTS ───────────────────────────────────────────────────────────────────

    def _speak_async(self, text: str) -> None:
        message = text.strip()
        if not message or self._tts is None:
            return
        self._tts.speak(message)

    def _speak_last(self) -> None:
        if self.last_reply:
            self._speak_async(self.last_reply)

    # ── clear ─────────────────────────────────────────────────────────────────

    def _clear(self) -> None:
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)
        self.last_reply = ""
        self._sys("Chat cleared.")

    def _on_close(self) -> None:
        self._stop_event.set()
        self._listening = False
        if self._tts is not None:
            try:
                self._tts.stop()
            except Exception:
                pass
        self.root.destroy()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    root = tk.Tk()
    VoiceAgentGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()