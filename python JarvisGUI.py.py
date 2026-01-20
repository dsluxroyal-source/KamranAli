# JarvisGUI.py
import threading
import queue
import tkinter as tk
from tkinter import scrolledtext, messagebox
import pyttsx3
import speech_recognition as sr
import datetime
import webbrowser
import time

from AI import get_response  # your second file

# ---------- Configuration ----------
SYSTEM_PROMPT = "You are Jarvis, a helpful, polite AI assistant. Keep replies concise and friendly."
VOICE_LANGUAGE = "en-PK"  # used by recognize_google (set according to your needs)
# -----------------------------------

class JarvisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Jarvis GUI - Simple Assistant")
        self.root.geometry("720x520")

        # Conversation memory
        self.chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Threading & queues
        self.audio_thread = None
        self.listening = False
        self.q = queue.Queue()  # queue for GUI updates / messages

        # TTS engine
        self.engine = pyttsx3.init()
        # Optional: change voice/rate if needed
        # voices = self.engine.getProperty('voices'); self.engine.setProperty('voice', voices[0].id)

        # Build UI
        self.build_ui()

        # Poll queue for results
        self.root.after(200, self._poll_queue)

    def build_ui(self):
        # Conversation display
        self.txt = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, state=tk.DISABLED)
        self.txt.pack(fill=tk.BOTH, padx=8, pady=8, expand=True)

        # Input frame
        inp_frame = tk.Frame(self.root)
        inp_frame.pack(fill=tk.X, padx=8, pady=(0,8))

        self.entry = tk.Entry(inp_frame)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,6))
        self.entry.bind("<Return>", lambda e: self.on_send_text())

        send_btn = tk.Button(inp_frame, text="Send", width=10, command=self.on_send_text)
        send_btn.pack(side=tk.LEFT)

        # Buttons frame
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0,8))

        self.listen_btn = tk.Button(btn_frame, text="Start Listening", width=16, command=self.toggle_listening)
        self.listen_btn.pack(side=tk.LEFT, padx=(0,6))

        stop_btn = tk.Button(btn_frame, text="Stop Listening", width=16, command=self.stop_listening)
        stop_btn.pack(side=tk.LEFT, padx=(0,6))

        reset_btn = tk.Button(btn_frame, text="Forget Conversation", width=16, command=self.reset_memory)
        reset_btn.pack(side=tk.LEFT, padx=(0,6))

        time_btn = tk.Button(btn_frame, text="Tell Time", width=12, command=self.tell_time)
        time_btn.pack(side=tk.LEFT, padx=(0,6))

        yt_btn = tk.Button(btn_frame, text="Open YouTube", width=12, command=lambda: webbrowser.open("https://www.youtube.com"))
        yt_btn.pack(side=tk.LEFT, padx=(0,6))

        # Status bar
        self.status = tk.Label(self.root, text="Ready", anchor=tk.W)
        self.status.pack(fill=tk.X, padx=8, pady=(0,8))

    # ---------- UI helpers ----------
    def append_text(self, role, text):
        """Append message to the conversation box and keep it in chat_history when role is user/assistant."""
        self.txt.configure(state=tk.NORMAL)
        prefix = "You: " if role == "user" else ("Jarvis: " if role == "assistant" else f"{role}: ")
        self.txt.insert(tk.END, f"{prefix}{text}\n\n")
        self.txt.see(tk.END)
        self.txt.configure(state=tk.DISABLED)

    def _poll_queue(self):
        """Poll queue for new messages to display (from worker threads)."""
        try:
            while True:
                item = self.q.get_nowait()
                if item["type"] == "append":
                    self.append_text(item["role"], item["text"])
                elif item["type"] == "status":
                    self.status.config(text=item["text"])
        except queue.Empty:
            pass
        finally:
            self.root.after(200, self._poll_queue)

    # ---------- Commands ----------
    def on_send_text(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)

        # show user text
        self.chat_history.append({"role": "user", "content": text})
        self.q.put({"type":"append","role":"user","text":text})
        self.q.put({"type":"status","text":"Waiting for AI..."})

        # call AI in background
        t = threading.Thread(target=self._call_ai_and_respond, args=(self.chat_history.copy(),))
        t.daemon = True
        t.start()

    def tell_time(self):
        now = datetime.datetime.now()
        ttext = f"Sir, the time is {now.hour} hours and {now.minute:02d} minutes."
        self.chat_history.append({"role":"user","content":"What time is it?"})
        self.q.put({"type":"append","role":"assistant","text":ttext})
        self.speak(ttext)

    def reset_memory(self):
        self.chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.q.put({"type":"append","role":"assistant","text":"Memory cleared. I have forgotten previous conversation."})
        self.q.put({"type":"status","text":"Memory reset"})

    # ---------- Voice listening ----------
    def toggle_listening(self):
        if self.listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self):
        if self.listening:
            return
        self.listening = True
        self.listen_btn.config(text="Listening...")
        self.q.put({"type":"status","text":"Listening..."})
        self.audio_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.audio_thread.start()

    def stop_listening(self):
        if not self.listening:
            return
        self.listening = False
        self.listen_btn.config(text="Start Listening")
        self.q.put({"type":"status","text":"Stopped listening"})

    def _listen_loop(self):
        r = sr.Recognizer()
        mic = sr.Microphone()
        with mic as source:
            r.adjust_for_ambient_noise(source, duration=1)
        while self.listening:
            try:
                with mic as source:
                    self.q.put({"type":"status","text":"Listening..."})
                    audio = r.listen(source, timeout=6, phrase_time_limit=8)
                # Recognize (may raise)
                try:
                    user_text = r.recognize_google(audio, language=VOICE_LANGUAGE)
                except sr.UnknownValueError:
                    self.q.put({"type":"status","text":"Could not understand audio"})
                    continue
                except sr.RequestError as e:
                    # Network issue
                    self.q.put({"type":"status","text":f"Speech API error: {e}"}); continue

                user_text = user_text.strip()
                if not user_text:
                    continue

                # Add to GUI & chat history
                self.chat_history.append({"role":"user","content":user_text})
                self.q.put({"type":"append","role":"user","text":user_text})
                self.q.put({"type":"status","text":"Sending to AI..."})

                # Call AI in background thread
                t = threading.Thread(target=self._call_ai_and_respond, args=(self.chat_history.copy(),))
                t.daemon = True
                t.start()

                # Small pause to avoid back-to-back immediate recordings
                time.sleep(0.5)

            except Exception as e:
                # Generic errors (microphone timeout, etc.)
                self.q.put({"type":"status","text":f"Listen loop error: {e}"})
                time.sleep(0.5)

    # ---------- AI calling ----------
    def _call_ai_and_respond(self, history_snapshot):
        """
        history_snapshot: copy of chat_history passed to worker to avoid concurrency issues.
        This worker calls AI, puts response into GUI queue, appends to the real chat_history.
        """
        try:
            ai_text = get_response(history_snapshot)
        except Exception as e:
            ai_text = f"[Error getting response: {e}]"

        # push response to GUI
        self.q.put({"type":"append","role":"assistant","text":ai_text})
        self.q.put({"type":"status","text":"Ready"})

        # append to the *main* chat_history for future context
        self.chat_history.append({"role":"assistant","content":ai_text})

        # speak it
        self.speak(ai_text)

    def speak(self, text):
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            # TTS error: still continue
            self.q.put({"type":"status","text":f"TTS error: {e}"})

# ---------- Run App ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = JarvisApp(root)
    root.mainloop()
