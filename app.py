import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
import shutil
import signal
import subprocess
import sys
import tempfile
import os
import time
import wave
import json
import random
import math
import ctypes
import ctypes.util
import unicodedata
import urllib.error
import urllib.request


APP_TITLE = "Sesli Asistan — Linux"
SAMPLE_RATE = 16_000
RECORD_SECONDS = 5
PIPER_DEFAULT_VOICE = "tr_TR-dfki-medium"
PIPER_DATA_DIR = Path.home() / ".local" / "share" / "linux-voice-assistant" / "voices"
PIPER_CATALOG_PATH = PIPER_DATA_DIR / "voices.json"
PIPER_CATALOG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json?download=true"
CHAT_MODEL = "qwen3:1.7b"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
WAKE_WORDS = {
    "bilgisayar", "computer", "assistant", "asistente", "assistente", "ordinateur",
    "computadora", "ordenador", "computador", "assistent", "ассистент", "компьютер",
    "助手", "アシスタント", "컴퓨터", "مساعد", "كمبيوتر",
}
STOP_PHRASES = {
    "dur", "stop", "stop listening", "halt", "parar", "detener", "arrete",
    "arrête", "stopp", "остановись", "停止", "停止聆聽", "그만", "그만 들어",
}
YES_WORDS = {"evet", "yes", "oui", "sí", "si", "ja", "sim", "да", "是", "はい", "네", "نعم"}
NO_WORDS = {"hayır", "hayir", "no", "non", "nein", "não", "nao", "нет", "不", "いいえ", "아니요", "لا"}


def normalize(text: str) -> str:
    text = text.casefold().translate(str.maketrans({
        "ı": "i",
        "ç": "c",
        "ğ": "g",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    }))
    text = "".join(
        character for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in text).split())


class VoiceAssistant:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("850x560")
        self.root.minsize(760, 500)
        self.root.configure(bg="#020804")
        self._setup_matrix_style()
        self.model = None
        self.last_detected_language = "tr"
        self.piper_voice_catalog: dict[str, dict] | None = None
        self.tts_voices: dict[str, object] = {}
        self.busy = False
        self.continuous_listening = threading.Event()
        self.chat_history: list[dict[str, str]] = []
        self.matrix_streams: list[dict[str, float | int]] = []
        self.countdown_remaining: int | None = None
        self.countdown_active = False
        self.elapsed_stage_started_at: float | None = None
        self.elapsed_active = False
        self.elapsed_phase = "DİNLEME"
        self.elapsed_durations = {"DİNLEME": 0.0, "DÜŞÜNME": 0.0, "CEVAP": 0.0}

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=0)

        self.matrix_canvas = tk.Canvas(
            root,
            width=175,
            bg="#020804",
            highlightthickness=1,
            highlightbackground="#0b4f22",
        )
        self.matrix_canvas.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        self.matrix_canvas.bind("<Configure>", self._reset_matrix_streams)

        outer = ttk.Frame(root, padding=18, style="Matrix.TFrame")
        outer.grid(row=0, column=0, sticky="nsew", padx=(12, 8), pady=12)

        ttk.Label(outer, text=APP_TITLE, font=("Sans", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Kulaklığa konuş. Metni kontrol et, sonra izin verdiğin basit eylemi çalıştır.",
            wraplength=590,
        ).pack(anchor="w", pady=(6, 14))

        self.microphone_name = tk.StringVar(value=self._default_microphone())
        ttk.Label(outer, text="Kullanılacak giriş (Linux varsayılanı):").pack(anchor="w")
        ttk.Label(outer, textvariable=self.microphone_name, wraplength=590).pack(anchor="w", pady=(3, 10))

        self.record_button = ttk.Button(outer, text=f"Konuş ve yazıya çevir ({RECORD_SECONDS} sn)", command=self.record)
        self.record_button.pack(anchor="w")
        self.continuous_button = ttk.Button(
            outer,
            text="Sürekli dinlemeyi başlat",
            command=self.toggle_continuous_listening,
        )
        self.continuous_button.pack(anchor="w", pady=(6, 0))

        ttk.Label(outer, text="Tanınan metin (gerekirse düzelt):").pack(anchor="w", pady=(16, 4))
        self.transcript = tk.Text(
            outer,
            height=6,
            wrap="word",
            font=("Sans", 12),
            bg="#020804",
            fg="#b8f5c4",
            insertbackground="#39ff67",
            selectbackground="#145527",
            selectforeground="#e4ffea",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#168b37",
            highlightcolor="#39ff67",
        )
        self.transcript.pack(fill="both", expand=True)

        button_row = ttk.Frame(outer)
        button_row.pack(anchor="w", pady=(12, 4))
        self.repeat_button = ttk.Button(button_row, text="Metni sesli tekrar et", command=self.repeat_transcript)
        self.repeat_button.pack(side="left", padx=(0, 8))
        self.run_button = ttk.Button(button_row, text="Eylemi çalıştır", command=self.run_action)
        self.run_button.pack(side="left")
        self.countdown_canvas = tk.Canvas(
            button_row,
            width=58,
            height=58,
            bg="#061109",
            highlightthickness=0,
        )
        self.countdown_canvas.pack(side="right", padx=6)
        self.countdown = tk.StringVar(value="DİNLEME SAYACI  —  HAZIR")
        ttk.Label(
            outer,
            textvariable=self.countdown,
            style="Matrix.Countdown.TLabel",
            font=("Monospace", 12, "bold"),
        ).pack(anchor="w", pady=(6, 2))
        self.elapsed_timer = tk.StringVar(value="DİNLEME 00:00  |  DÜŞÜNME 00:00  |  CEVAP 00:00")
        ttk.Label(
            outer,
            textvariable=self.elapsed_timer,
            style="Matrix.Elapsed.TLabel",
            font=("Monospace", 10, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.status = tk.StringVar(value="Komut için 'Bilgisayar' diye başlayabilirsin. Durdurmak için 'dur' de.")
        self.mini_status = tk.StringVar(value="Dinleme hazırlanıyor")
        self.mini_transcript = tk.StringVar(value="Henüz konuşma algılanmadı")
        ttk.Label(outer, textvariable=self.status, wraplength=590).pack(anchor="w", pady=(8, 0))
        self._create_mini_window()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_main_window)
        self.root.withdraw()
        self.root.after(120, self._animate_matrix)
        self.root.after(800, self._start_listening_on_launch)

    def _create_mini_window(self) -> None:
        self.mini_window = tk.Toplevel(self.root)
        self.mini_window.title("Sesli Asistan")
        self.mini_window.configure(bg="#020804")
        self.mini_window.resizable(False, False)

        # A wider circle keeps the transcript, timers, and controls readable.
        size = int(self.root.winfo_fpixels("8c"))
        x = max(0, self.root.winfo_screenwidth() - size - 12)
        self.mini_window.geometry(f"{size}x{size}+{x}+12")
        self.mini_window.attributes("-topmost", True)
        self.mini_window.overrideredirect(True)
        self.mini_window.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.mini_background = tk.Canvas(
            self.mini_window,
            width=size,
            height=size,
            bg="#020804",
            highlightthickness=0,
        )
        self.mini_background.place(x=0, y=0, relwidth=1, relheight=1)
        pad = 3
        self.mini_background.create_oval(
            pad, pad, size - pad, size - pad,
            fill="#061109",
            outline="#168b37",
            width=2,
        )
        content = tk.Frame(self.mini_window, bg="#061109")
        content.place(
            x=int(size * 0.13),
            y=int(size * 0.08),
            width=int(size * 0.74),
            height=int(size * 0.84),
        )
        content.grid_columnconfigure(0, weight=1)

        header = tk.Frame(content, bg="#061109")
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(
            header,
            text="SESLİ ASİSTAN",
            bg="#061109",
            fg="#39ff67",
            font=("Monospace", 8, "bold"),
        ).pack(side="left")
        ttk.Button(header, text="Büyüt", width=5, command=self._show_main_window).pack(side="right")
        self.mini_countdown_canvas = tk.Canvas(
            content,
            width=72,
            height=72,
            bg="#061109",
            highlightthickness=0,
        )
        self.mini_countdown_canvas.grid(row=1, column=0, pady=(1, 0))

        tk.Label(
            content,
            text="DUYULAN",
            bg="#061109",
            fg="#39ff67",
            anchor="center",
            font=("Monospace", 7, "bold"),
        ).grid(row=2, column=0, sticky="ew", pady=(0, 1))
        tk.Label(
            content,
            textvariable=self.mini_transcript,
            bg="#061109",
            fg="#e4ffea",
            justify="center",
            anchor="center",
            wraplength=int(size * 0.66),
            height=3,
            font=("Sans", 8),
        ).grid(row=3, column=0, sticky="ew")
        tk.Label(
            content,
            textvariable=self.mini_status,
            bg="#061109",
            fg="#b8f5c4",
            justify="center",
            anchor="center",
            wraplength=int(size * 0.66),
            font=("Sans", 7),
        ).grid(row=4, column=0, sticky="ew", pady=(0, 1))
        tk.Label(
            content,
            textvariable=self.countdown,
            bg="#061109",
            fg="#39ff67",
            anchor="center",
            font=("Monospace", 7, "bold"),
        ).grid(row=5, column=0, sticky="ew", pady=1)
        self.mini_elapsed_timer = tk.StringVar(value="DİN 00:00 | DÜŞ 00:00 | CEV 00:00")
        tk.Label(
            content,
            textvariable=self.mini_elapsed_timer,
            bg="#061109",
            fg="#8fdba0",
            anchor="w",
            font=("Monospace", 8),
        ).grid(row=6, column=0, sticky="ew", pady=1)

        controls = tk.Frame(content, bg="#061109")
        controls.grid(row=7, column=0, sticky="ew", pady=(2, 0))
        self.mini_toggle_button = ttk.Button(
            controls,
            text="Dinlemeyi durdur",
            width=15,
            command=self.toggle_continuous_listening,
        )
        self.mini_toggle_button.pack(side="left", padx=(0, 4))
        ttk.Button(controls, text="Çıkış", width=6, command=self.root.destroy).pack(side="left")

        for widget in (self.mini_window, self.mini_background, content, header):
            widget.bind("<ButtonPress-1>", self._start_mini_drag, add="+")
            widget.bind("<B1-Motion>", self._move_mini_window, add="+")
        self.mini_window.after(100, self._apply_circular_window_shape)
        self._draw_countdown_rings()
        self._refresh_mini_controls()

    def _start_mini_drag(self, event: tk.Event) -> None:
        self.mini_drag_x = event.x_root - self.mini_window.winfo_x()
        self.mini_drag_y = event.y_root - self.mini_window.winfo_y()

    def _move_mini_window(self, event: tk.Event) -> None:
        x = event.x_root - getattr(self, "mini_drag_x", 0)
        y = event.y_root - getattr(self, "mini_drag_y", 0)
        self.mini_window.geometry(f"+{x}+{y}")

    def _apply_circular_window_shape(self) -> None:
        """Clip the frameless Linux window to a circular X11 shape when available."""
        x11_name = ctypes.util.find_library("X11")
        xext_name = ctypes.util.find_library("Xext")
        if not x11_name or not xext_name:
            return
        try:
            x11 = ctypes.CDLL(x11_name)
            xext = ctypes.CDLL(xext_name)
            x11.XOpenDisplay.restype = ctypes.c_void_p
            display = x11.XOpenDisplay(None)
            if not display:
                return

            class XRectangle(ctypes.Structure):
                _fields_ = [
                    ("x", ctypes.c_short),
                    ("y", ctypes.c_short),
                    ("width", ctypes.c_ushort),
                    ("height", ctypes.c_ushort),
                ]

            size = self.mini_window.winfo_width()
            radius = size / 2 - 1
            rectangles = []
            for y in range(size):
                dy = y + 0.5 - size / 2
                half_width = math.sqrt(max(0, radius * radius - dy * dy))
                left = max(0, int(size / 2 - half_width))
                right = min(size, int(size / 2 + half_width))
                if right > left:
                    rectangles.append(XRectangle(left, y, right - left, 1))
            rect_array = (XRectangle * len(rectangles))(*rectangles)
            shape = xext.XShapeCombineRectangles
            shape.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.POINTER(XRectangle),
                ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ]
            shape(display, self.mini_window.winfo_id(), 0, 0, 0, rect_array, len(rectangles), 0, 0)
            x11.XFlush(display)
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay(display)
        except (OSError, AttributeError, TypeError, ValueError):
            # Keep the circular visual style even if this display lacks X11 shape support.
            return

    def _show_main_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_main_window(self) -> None:
        self.root.withdraw()

    def _refresh_mini_controls(self) -> None:
        if self.continuous_listening.is_set():
            self.mini_toggle_button.configure(text="Dinlemeyi durdur", state="normal")
        elif self.busy:
            label = "Durduruluyor…" if self.continuous_button.cget("text") == "Durduruluyor…" else "İşlem sürüyor"
            self.mini_toggle_button.configure(text=label, state="disabled")
        else:
            self.mini_toggle_button.configure(text="Dinlemeyi başlat", state="normal")

    def _reset_mini_matrix_streams(self, event: tk.Event) -> None:
        column_count = max(1, event.width // 12)
        self.mini_matrix_streams = [
            {
                "x": float(6 + column * 12),
                "y": float(random.randint(-event.height, event.height)),
                "speed": float(random.randint(7, 17)),
                "length": random.randint(4, 10),
            }
            for column in range(column_count)
        ]

    def _animate_mini_matrix(self) -> None:
        if not self.mini_window.winfo_exists():
            return
        canvas = self.mini_matrix_canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 2 or height < 2:
            self.mini_window.after(180, self._animate_mini_matrix)
            return
        if not self.mini_matrix_streams:
            self._reset_mini_matrix_streams(type("CanvasSize", (), {"width": width, "height": height})())
        canvas.delete("mini-rain")
        for stream in self.mini_matrix_streams:
            x, y = float(stream["x"]), float(stream["y"])
            length = int(stream["length"])
            for index in range(length):
                char_y = y - index * 12
                if 0 <= char_y <= height:
                    canvas.create_text(
                        x,
                        char_y,
                        text=random.choice("01{}[]<>/\\|*+-"),
                        fill="#39ff67" if index < 2 else "#087a2b",
                        font=("Monospace", 8, "bold" if index == 0 else "normal"),
                        tags="mini-rain",
                    )
            stream["y"] = y + float(stream["speed"])
            if y - length * 12 > height:
                stream["y"] = float(random.randint(-height, 0))
                stream["speed"] = float(random.randint(7, 17))
        self.mini_window.after(180, self._animate_mini_matrix)

    def _setup_matrix_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Matrix.TFrame", background="#061109")
        style.configure("TLabel", background="#061109", foreground="#b8f5c4")
        style.configure("Matrix.Countdown.TLabel", background="#061109", foreground="#39ff67")
        style.configure("Matrix.Elapsed.TLabel", background="#061109", foreground="#8fdba0")
        style.configure(
            "TButton",
            background="#0c3218",
            foreground="#c7ffd2",
            bordercolor="#168b37",
            lightcolor="#168b37",
            darkcolor="#061109",
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", "#145527"), ("disabled", "#101a12")],
            foreground=[("disabled", "#69836f")],
        )

    def _reset_matrix_streams(self, event: tk.Event) -> None:
        column_count = max(1, event.width // 14)
        self.matrix_streams = [
            {
                "x": float(7 + column * 14),
                "y": float(random.randint(-event.height, event.height)),
                "speed": float(random.randint(8, 20)),
                "length": random.randint(5, 12),
            }
            for column in range(column_count)
        ]

    def _animate_matrix(self) -> None:
        if not self.matrix_canvas.winfo_exists():
            return
        if self.root.state() == "withdrawn":
            self.root.after(500, self._animate_matrix)
            return
        canvas = self.matrix_canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 2 or height < 2:
            self.root.after(160, self._animate_matrix)
            return
        if not self.matrix_streams:
            self._reset_matrix_streams(type("CanvasSize", (), {"width": width, "height": height})())

        canvas.delete("matrix-rain")
        alphabet = "01{}[]<>/\\|*+-"
        for stream in self.matrix_streams:
            x = float(stream["x"])
            y = float(stream["y"])
            length = int(stream["length"])
            for index in range(length):
                char_y = y - index * 15
                if 0 <= char_y <= height:
                    shade = "#e4ffea" if index == 0 else ("#39ff67" if index < 3 else "#087a2b")
                    canvas.create_text(
                        x,
                        char_y,
                        text=random.choice(alphabet),
                        fill=shade,
                        font=("Monospace", 10, "bold" if index == 0 else "normal"),
                        tags="matrix-rain",
                    )
            stream["y"] = y + float(stream["speed"])
            if y - length * 15 > height:
                stream["y"] = float(random.randint(-height, 0))
                stream["speed"] = float(random.randint(8, 20))
                stream["length"] = random.randint(5, 12)
        canvas.create_text(
            width // 2,
            height - 14,
            text="LOCAL • READY",
            fill="#39ff67",
            font=("Monospace", 8, "bold"),
            tags="matrix-rain",
        )
        self.root.after(160, self._animate_matrix)

    def _start_listening_on_launch(self) -> None:
        if not self.continuous_listening.is_set() and not self.busy:
            self.toggle_continuous_listening()

    def set_status(self, text: str) -> None:
        self.status.set(text)
        compact = " ".join(text.split())
        if len(compact) > 30:
            compact = compact[:29].rstrip() + "…"
        self.mini_status.set(compact)

    def _default_microphone(self) -> str:
        try:
            result = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True, check=True)
            return result.stdout.strip() or "Sistem varsayılan mikrofonu"
        except (OSError, subprocess.CalledProcessError):
            return "Sistem varsayılan mikrofonu (pactl adı alınamadı)"

    def record(self) -> None:
        if self.busy or self.continuous_listening.is_set():
            return
        self.busy = True
        self.record_button.configure(state="disabled")
        self.set_status(f"Dinliyorum… {RECORD_SECONDS} saniye konuş.")
        threading.Thread(target=self._record_and_transcribe, daemon=True).start()

    def _record_and_transcribe(self) -> None:
        try:
            self._ensure_model()
            recording_path = self._capture_audio()
            try:
                self._post_status("Konuşma yazıya çevriliyor…")
                text = self._transcribe(recording_path)
            finally:
                self._delete_recording(recording_path)
            self.root.after(0, lambda t=text: self._show_transcript(t))
            if text:
                command = self._canonical_action(normalize(text))
                if command:
                    self._post_status("Komutu duydum. Eylem düğmesine basarak çalıştırabilirsin.")
                    if self.last_detected_language.startswith("en"):
                        self._speak_or_report(
                            f"I heard: {text}. I understood you want to {self._describe_action(command)}. "
                            "Press Run Action to continue."
                        )
                    else:
                        self._speak_or_report(f"Şunu duydum: {text}. Eylemi çalıştırmak için düğmeye bas.")
                else:
                    self._post_status("Yerel sohbet modeli cevap hazırlıyor…")
                    reply = self._chat_reply(text)
                    self._speak_or_report(reply)
                    self._post_status(f"Asistan: {reply}")
            else:
                self._post_status("Konuşma algılanmadı. Tekrar deneyebilirsin.")
        except Exception as exc:
            message = str(exc)
            self.root.after(0, lambda m=message: self._show_error(m))
        finally:
            self._stop_elapsed_timer()
            self.root.after(0, self._finish_recording)

    def _ensure_model(self) -> None:
        if self.model is None:
            self._post_status("Çok dilli konuşma modeli hazırlanıyor…")
            from faster_whisper import WhisperModel

            self.model = WhisperModel("base", device="cpu", compute_type="int8")

    def _capture_audio(self) -> str:
        recorder = shutil.which("pw-record")
        if not recorder:
            raise RuntimeError("pw-record bulunamadı. Terminalde 'sudo apt install pipewire-bin' komutuyla kur.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as recording:
            recording_path = recording.name
        try:
            recorder_process = subprocess.Popen(
                [recorder, f"--rate={SAMPLE_RATE}", "--channels=1", "--format=s16", recording_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._start_elapsed_timer()
            for remaining in range(RECORD_SECONDS, 0, -1):
                self._post_countdown(f"DİNLEME SAYACI  —  {remaining} sn", remaining, True)
                time.sleep(1)
            if recorder_process.poll() is None:
                recorder_process.send_signal(signal.SIGINT)
            stdout, stderr = recorder_process.communicate(timeout=10)
            self._post_countdown("DİNLEME TAMAMLANDI", 0, False)
            if recorder_process.returncode not in (0, -signal.SIGINT, 128 + signal.SIGINT):
                recorded_audio_exists = os.path.exists(recording_path) and os.path.getsize(recording_path) > 44
                if not recorded_audio_exists:
                    detail = stderr.strip() or stdout.strip()
                    raise RuntimeError(detail or f"pw-record {recorder_process.returncode} hata koduyla kapandı.")
            if os.path.getsize(recording_path) <= 44:
                raise RuntimeError("Ses kaydı boş geldi. Bluetooth mikrofonunu ve varsayılan giriş aygıtını kontrol et.")
            return recording_path
        except Exception:
            self._stop_elapsed_timer()
            self._delete_recording(recording_path)
            raise

    def _transcribe(self, recording_path: str, prompt: str | None = None) -> str:
        self._post_status("Konuşma yazıya çevriliyor…")
        self._set_elapsed_phase("DÜŞÜNME")
        try:
            options = {"beam_size": 3, "vad_filter": True}
            if prompt:
                options["initial_prompt"] = prompt
            segments, info = self.model.transcribe(recording_path, **options)
            self.last_detected_language = getattr(info, "language", None) or "unknown"
            return " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            self._set_elapsed_phase("DÜŞÜNME")

    @staticmethod
    def _delete_recording(recording_path: str) -> None:
        try:
            os.unlink(recording_path)
        except OSError:
            pass

    def _post_status(self, text: str) -> None:
        self.root.after(0, lambda t=text: self.set_status(t))

    def _post_countdown(self, text: str, remaining: int | None = None, active: bool | None = None) -> None:
        self.root.after(0, lambda: self._update_countdown(text, remaining, active))

    def _update_countdown(self, text: str, remaining: int | None, active: bool | None) -> None:
        self.countdown.set(text)
        if remaining is not None:
            self.countdown_remaining = remaining
        if active is not None:
            self.countdown_active = active
        self._draw_countdown_rings()

    def _draw_countdown_rings(self) -> None:
        for canvas in (self.countdown_canvas, self.mini_countdown_canvas):
            canvas.delete("countdown-ring")
            width = int(canvas.cget("width"))
            height = int(canvas.cget("height"))
            inset = 3
            x1, y1, x2, y2 = inset, inset, width - inset, height - inset
            canvas.create_arc(
                x1, y1, x2, y2,
                start=0,
                extent=359.9,
                style="arc",
                outline="#114d20",
                width=3,
                tags="countdown-ring",
            )
            if self.countdown_remaining is None:
                percent_text, seconds_text = "--%", "bekle"
            else:
                percent = round(100 * self.countdown_remaining / RECORD_SECONDS)
                percent_text = f"{percent}%"
                seconds_text = f"{self.countdown_remaining}s"
                extent = -360 * max(0, min(1, self.countdown_remaining / RECORD_SECONDS))
                if extent:
                    canvas.create_arc(
                        x1, y1, x2, y2,
                        start=90,
                        extent=extent,
                        style="arc",
                        outline="#39ff67" if self.countdown_active else "#168b37",
                        width=3,
                        tags="countdown-ring",
                    )
            center_x, center_y = width / 2, height / 2
            canvas.create_text(
                center_x,
                center_y - 4,
                text=percent_text,
                fill="#e4ffea",
                font=("Monospace", 8 if width < 50 else 9, "bold"),
                tags="countdown-ring",
            )
            canvas.create_text(
                center_x,
                center_y + 8,
                text=seconds_text,
                fill="#39ff67",
                font=("Monospace", 7 if width < 50 else 8),
                tags="countdown-ring",
            )

    def _start_elapsed_timer(self) -> None:
        self.elapsed_stage_started_at = time.monotonic()
        self.elapsed_active = True
        self.elapsed_phase = "DİNLEME"
        self.elapsed_durations = {"DİNLEME": 0.0, "DÜŞÜNME": 0.0, "CEVAP": 0.0}
        self.root.after(0, self._tick_elapsed_timer)

    def _set_elapsed_phase(self, phase: str) -> None:
        now = time.monotonic()
        if self.elapsed_active and self.elapsed_stage_started_at is not None:
            self.elapsed_durations[self.elapsed_phase] += now - self.elapsed_stage_started_at
            self.elapsed_stage_started_at = now
        self.elapsed_phase = phase

    def _tick_elapsed_timer(self) -> None:
        if not self.elapsed_active or self.elapsed_stage_started_at is None:
            return
        durations = dict(self.elapsed_durations)
        durations[self.elapsed_phase] += time.monotonic() - self.elapsed_stage_started_at
        display = "  |  ".join(
            f"{phase} {int(durations[phase]) // 60:02d}:{int(durations[phase]) % 60:02d}"
            for phase in ("DİNLEME", "DÜŞÜNME", "CEVAP")
        )
        self.elapsed_timer.set(display)
        self.mini_elapsed_timer.set(self._format_mini_elapsed(durations))
        self.root.after(200, self._tick_elapsed_timer)

    @staticmethod
    def _format_mini_elapsed(durations: dict[str, float]) -> str:
        return " | ".join(
            f"{short} {int(durations[phase]) // 60:02d}:{int(durations[phase]) % 60:02d}"
            for phase, short in (("DİNLEME", "DİN"), ("DÜŞÜNME", "DÜŞ"), ("CEVAP", "CEV"))
        )

    def _stop_elapsed_timer(self) -> None:
        if not self.elapsed_active or self.elapsed_stage_started_at is None:
            return
        self.elapsed_durations[self.elapsed_phase] += time.monotonic() - self.elapsed_stage_started_at
        self.elapsed_active = False
        self.elapsed_stage_started_at = None
        display = "SON TUR  |  " + "  |  ".join(
            f"{phase} {int(self.elapsed_durations[phase]) // 60:02d}:{int(self.elapsed_durations[phase]) % 60:02d}"
            for phase in ("DİNLEME", "DÜŞÜNME", "CEVAP")
        )
        self.root.after(0, lambda: self.elapsed_timer.set(display))
        mini_display = self._format_mini_elapsed(self.elapsed_durations)
        self.root.after(0, lambda: self.mini_elapsed_timer.set(mini_display))

    def toggle_continuous_listening(self) -> None:
        if self.continuous_listening.is_set():
            self.continuous_listening.clear()
            self.continuous_button.configure(text="Durduruluyor…", state="disabled")
            self._refresh_mini_controls()
            self._post_status("Dinlemeyi durduruyorum; bu kayıt bölümü tamamlanınca kapanacak.")
            return
        if self.busy:
            return
        try:
            import piper  # noqa: F401
        except ImportError:
            messagebox.showerror(
                "Doğal ses paketi eksik",
                "Terminalde './.venv/bin/python -m pip install -r requirements.txt' komutunu çalıştır.",
            )
            return
        self.continuous_listening.set()
        self.busy = True
        self.record_button.configure(state="disabled")
        self.continuous_button.configure(text="Dinlemeyi durdur")
        self.repeat_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self._refresh_mini_controls()
        threading.Thread(target=self._continuous_loop, daemon=True).start()

    def _continuous_loop(self) -> None:
        try:
            self._post_status("Konuşma modeli hazırlanıyor; hazır olunca sesli haber vereceğim…")
            self._ensure_model()
            try:
                self._speak("Merhaba, dinlemeye hazırım. Bana bilgisayar diye seslenebilirsin.")
            except Exception as exc:
                self._post_status(f"Dinleme başladı; sesli yanıt kullanılamıyor: {exc}")
            while self.continuous_listening.is_set():
                self._post_status(f"Sürekli dinliyorum ({RECORD_SECONDS} sn). Tanımlı komutları bekliyorum.")
                command_audio = self._capture_audio()
                try:
                    heard = self._transcribe(command_audio)
                finally:
                    self._delete_recording(command_audio)

                if not self.continuous_listening.is_set():
                    self._stop_elapsed_timer()
                    break

                normalized = normalize(heard)
                if not normalized:
                    self._stop_elapsed_timer()
                    continue
                if any(normalize(phrase) in normalized for phrase in STOP_PHRASES):
                    self.continuous_listening.clear()
                    self._speak_or_report(
                        "Listening stopped." if self.last_detected_language.startswith("en") else "Dinlemeyi durdurdum."
                    )
                    break

                self._post_status(f"Duydum: {heard}")
                words = normalized.split()
                wake_detected = any(word in WAKE_WORDS for word in words) or any(
                    wake_word in normalized for wake_word in WAKE_WORDS if not wake_word.isascii()
                )
                command_text = " ".join(word for word in words if word not in WAKE_WORDS)
                command = self._canonical_action(command_text)
                self.root.after(0, lambda t=heard: self._show_transcript(t))
                if command is None:
                    if wake_detected:
                        self._post_status("Yerel sohbet modeli cevap hazırlıyor…")
                        try:
                            reply = self._chat_reply(heard)
                        except Exception as exc:
                            self._speak_or_report(str(exc))
                            continue
                        self._post_status(f"Asistan: {reply}")
                        self._speak_or_report(reply)
                    else:
                        self._post_status(f"Seslenme bekleniyor: {heard}")
                    continue

                if self.last_detected_language.startswith("en"):
                    confirmation_prompt = (
                        f"I heard: {heard}. I understood you want to {self._describe_action(command)}. "
                        "Say yes to confirm or no to cancel."
                    )
                else:
                    confirmation_prompt = (
                        f"Şunu duydum: {heard}. {self._describe_action(command)} olarak anladım. "
                        "Onaylamak için evet, iptal etmek için hayır de."
                    )
                self._speak_or_report(confirmation_prompt)
                if not self.continuous_listening.is_set():
                    self._stop_elapsed_timer()
                    break
                self._post_status(f"Onay bekliyorum: {RECORD_SECONDS} saniye içinde evet veya hayır de.")
                confirmation_audio = self._capture_audio()
                try:
                    confirmation = normalize(self._transcribe(confirmation_audio))
                finally:
                    self._delete_recording(confirmation_audio)

                if not self.continuous_listening.is_set():
                    break
                if any(word in confirmation.split() for word in YES_WORDS):
                    result = self._execute_action(command)
                    self._post_status(result)
                    if self.last_detected_language.startswith("en"):
                        if result.startswith("Açıldı:"):
                            spoken_result = f"Opened: {self._describe_action(command)}."
                        elif result == "Hesap makinesi açıldı.":
                            spoken_result = "Calculator opened."
                        else:
                            spoken_result = "I could not complete that action."
                    else:
                        spoken_result = result
                    self._speak_or_report(spoken_result)
                elif any(word in confirmation.split() for word in NO_WORDS):
                    self._post_status("Komut iptal edildi.")
                    self._speak_or_report("I cancelled the request." if self.last_detected_language.startswith("en") else "Komutu iptal ettim.")
                else:
                    self._post_status("Onay alamadım; komutu çalıştırmadım.")
                    self._speak_or_report("Onay alamadım. Komutu çalıştırmadım.")
        except Exception as exc:
            message = str(exc)
            self.root.after(0, lambda m=message: self._show_error(m))
        finally:
            self._stop_elapsed_timer()
            self.continuous_listening.clear()
            self.root.after(0, self._finish_continuous_listening)

    def _speak_or_report(self, text: str) -> None:
        self._set_elapsed_phase("CEVAP")
        try:
            self._speak(text)
        except Exception as exc:
            self._post_status(f"Sesli yanıt verilemedi: {exc}")
        finally:
            self._stop_elapsed_timer()

    def _chat_reply(self, user_text: str) -> str:
        system_message = {
            "role": "system",
            "content": (
                "You are the user's local voice assistant on Linux Mint. "
                f"The latest speech was detected as language code '{self.last_detected_language}'. "
                "Reply naturally in the same language the user just spoke, and keep the reply concise for speech. "
                "Do not claim to have performed computer actions and do not execute commands. "
                "Desktop actions are restricted to the app's allowed choices and require user confirmation."
            ),
        }
        messages = [system_message, *self.chat_history, {"role": "user", "content": user_text}]
        request_body = json.dumps(
            {
                "model": CHAT_MODEL,
                "messages": messages,
                "stream": False,
                "think": False,
                "keep_alive": "5m",
                "options": {"num_ctx": 2048, "num_predict": 128, "temperature": 0.7},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            OLLAMA_CHAT_URL,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if "model" in detail.casefold() and ("not found" in detail.casefold() or "pull" in detail.casefold()):
                raise RuntimeError(f"Sohbet modeli kurulu değil. Terminalde `ollama pull {CHAT_MODEL}` komutunu çalıştır.") from exc
            raise RuntimeError(f"Yerel sohbet motoru hata verdi: {detail or exc}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Ollama çalışmıyor. Terminalde `ollama serve` komutunu başlatıp tekrar dene.") from exc

        reply = result.get("message", {}).get("content", "").strip()
        if not reply:
            raise RuntimeError("Yerel model boş yanıt verdi. Bir kez daha deneyebilirsin.")
        self.chat_history.extend(
            [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
        )
        self.chat_history = self.chat_history[-12:]
        return reply

    def _load_piper_catalog(self) -> dict[str, dict]:
        if self.piper_voice_catalog is not None:
            return self.piper_voice_catalog
        PIPER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        catalog: dict[str, dict] = {}
        if PIPER_CATALOG_PATH.exists() and time.time() - PIPER_CATALOG_PATH.stat().st_mtime < 30 * 86400:
            try:
                catalog = json.loads(PIPER_CATALOG_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                catalog = {}
        if not catalog:
            try:
                request = urllib.request.Request(PIPER_CATALOG_URL, headers={"User-Agent": APP_TITLE})
                with urllib.request.urlopen(request, timeout=15) as response:
                    catalog = json.loads(response.read().decode("utf-8"))
                PIPER_CATALOG_PATH.write_text(json.dumps(catalog), encoding="utf-8")
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                catalog = {}
        self.piper_voice_catalog = catalog
        return catalog

    def _piper_voice_for_language(self, language: str) -> str | None:
        catalog = self._load_piper_catalog()
        family = language.split("-")[0].split("_")[0].casefold()
        candidates = [
            voice_id for voice_id, details in catalog.items()
            if details.get("language", {}).get("family", "").casefold() == family
        ]
        if not candidates:
            if family == "tr":
                return PIPER_DEFAULT_VOICE
            return None
        if family == "tr" and PIPER_DEFAULT_VOICE in candidates:
            return PIPER_DEFAULT_VOICE
        quality_rank = {"medium": 0, "high": 1, "low": 2, "x_low": 3}
        candidates.sort(key=lambda voice_id: (
            quality_rank.get(catalog[voice_id].get("quality", ""), 9),
            "US" not in voice_id,
            voice_id,
        ))
        return candidates[0]

    def _load_piper_voice(self, voice_id: str):
        if voice_id in self.tts_voices:
            voice = self.tts_voices.pop(voice_id)
            self.tts_voices[voice_id] = voice
            return voice
        model_path = PIPER_DATA_DIR / f"{voice_id}.onnx"
        if not model_path.exists():
            self._post_status(f"{voice_id.split('-')[0]} için Piper sesi indiriliyor…")
            PIPER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            download = subprocess.run(
                [sys.executable, "-m", "piper.download_voices", "--download-dir", str(PIPER_DATA_DIR), voice_id],
                capture_output=True,
                text=True,
                check=False,
            )
            if download.returncode != 0 or not model_path.exists():
                detail = download.stderr.strip() or download.stdout.strip()
                raise RuntimeError(detail or f"Piper sesi indirilemedi: {voice_id}")
        from piper import PiperVoice

        voice = PiperVoice.load(str(model_path))
        while len(self.tts_voices) >= 2:
            self.tts_voices.pop(next(iter(self.tts_voices)))
        self.tts_voices[voice_id] = voice
        return voice

    @staticmethod
    def _espeak_voice(language: str) -> str | None:
        executable = shutil.which("espeak-ng")
        if not executable:
            return None
        aliases = {"jw": "jv", "zh": "zh", "yue": "yue", "no": "no"}
        requested = aliases.get(language, language)
        try:
            result = subprocess.run([executable, "--voices"], capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return None
        voices = [line.split()[1] for line in result.stdout.splitlines()[1:] if len(line.split()) > 1]
        matches = [voice for voice in voices if voice == requested or voice.startswith(requested + "-")]
        return matches[0] if matches else None

    def _speak(self, text: str) -> None:
        player = shutil.which("pw-play") or shutil.which("aplay")
        if not player:
            raise RuntimeError("Ses oynatıcı bulunamadı. 'pipewire-bin' paketinin kurulu olduğunu kontrol et.")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_path = audio_file.name
        try:
            language = self.last_detected_language
            voice_id = self._piper_voice_for_language(language)
            if voice_id:
                try:
                    voice = self._load_piper_voice(voice_id)
                    with wave.open(audio_path, "wb") as wav_file:
                        voice.synthesize_wav(text, wav_file)
                except Exception:
                    if language == "tr":
                        raise
                    voice_id = None
            if not voice_id:
                espeak = shutil.which("espeak-ng")
                voice = self._espeak_voice(language)
                if not espeak or not voice:
                    raise RuntimeError(
                        f"{language} için yerel ses bulunamadı. Piper'da veya espeak-ng'de o dilin sesini kur."
                    )
                subprocess.run([espeak, "-v", voice, "-w", audio_path, text], capture_output=True, text=True, check=True)
            subprocess.run([player, audio_path], capture_output=True, text=True, check=True)
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

    def _finish_continuous_listening(self) -> None:
        self.busy = False
        self._update_countdown("DİNLEME SAYACI  —  DURDU", None, False)
        self.record_button.configure(state="normal")
        self.continuous_button.configure(text="Sürekli dinlemeyi başlat", state="normal")
        self.repeat_button.configure(state="normal")
        self.run_button.configure(state="normal")
        if self.continuous_listening.is_set():
            self.continuous_button.configure(text="Dinlemeyi durdur")
        self._refresh_mini_controls()

    def _execute_action(self, text: str) -> str | None:
        actions = {
            "ev klasorunu ac": ("folder", Path.home()),
            "ana klasoru ac": ("folder", Path.home()),
            "indirilenleri ac": ("folder", Path.home() / "Downloads"),
            "indirilenler klasorunu ac": ("folder", Path.home() / "Downloads"),
            "hesap makinesini ac": ("calculator", None),
        }
        if text not in actions:
            return None
        kind, target = actions[text]
        if kind == "folder":
            if not target.exists():
                return f"Klasör bulunamadı: {target}"
            subprocess.Popen(["xdg-open", str(target)])
            return f"Açıldı: {target}"
        calculator = next(
            (shutil.which(name) for name in ("gnome-calculator", "mate-calc", "galculator") if shutil.which(name)),
            None,
        )
        if not calculator:
            return "Hesap makinesi bulunamadı."
        subprocess.Popen([calculator])
        return "Hesap makinesi açıldı."

    def _show_transcript(self, text: str) -> None:
        self.transcript.delete("1.0", "end")
        self.transcript.insert("1.0", text)
        compact = " ".join(text.split()) or "Henüz konuşma algılanmadı"
        if len(compact) > 78:
            compact = compact[:75].rstrip() + "…"
        self.mini_transcript.set(compact)
        self.set_status("Metni kontrol et. Eylem ancak düğmeye basınca çalışır.")

    def _show_error(self, error: str) -> None:
        self.set_status("Mikrofon veya model başlatılamadı.")
        messagebox.showerror("Ses tanıma hatası", error)

    def _finish_recording(self) -> None:
        self.busy = False
        self._update_countdown("DİNLEME SAYACI  —  HAZIR", None, False)
        self.record_button.configure(state="normal")
        self._refresh_mini_controls()

    def repeat_transcript(self) -> None:
        text = self.transcript.get("1.0", "end").strip()
        if not text:
            self.set_status("Önce konuşmayı yazıya çevir veya kutuya metin yaz.")
            return
        self.repeat_button.configure(state="disabled")
        self.set_status(f"Metni {self.last_detected_language} dilinde seslendiriyorum…")
        threading.Thread(target=self._speak_text, args=(text,), daemon=True).start()

    def _speak_text(self, text: str) -> None:
        try:
            self._speak(text)
        except Exception as exc:
            message = str(exc)
            self.root.after(0, lambda m=message: messagebox.showerror("Sesli okuma hatası", m))
        finally:
            self.root.after(0, lambda: self.repeat_button.configure(state="normal"))
            self.root.after(0, lambda: self.set_status("Metni dinleyip düzeltebilir, ardından eylemi çalıştırabilirsin."))

    def run_action(self) -> None:
        text = normalize(self.transcript.get("1.0", "end").strip())
        command = self._canonical_action(text)
        if command is None:
            self.set_status("Bu sürüm kurulu uygulamaları açabilir; metni düzenleyip tekrar dene.")
            return
        result = self._execute_action(command)
        self.set_status(result)
        if result.startswith("Açılamadı:"):
            messagebox.showerror("Eylem çalıştırılamadı", result)

    @staticmethod
    def _canonical_action(text: str) -> str | None:
        words = set(text.split())
        english_actions = {
            "open home folder": "ev klasorunu ac",
            "open the home folder": "ev klasorunu ac",
            "open home directory": "ev klasorunu ac",
            "open my home folder": "ev klasorunu ac",
            "open downloads": "indirilenleri ac",
            "open downloads folder": "indirilenleri ac",
            "open the downloads folder": "indirilenleri ac",
            "open calculator": "hesap makinesini ac",
            "open the calculator": "hesap makinesini ac",
        }
        if text in english_actions:
            return english_actions[text]
        if any(word.startswith("indir") for word in words):
            return "indirilenleri ac"
        if "hesap" in words and any(word.startswith("makine") for word in words):
            return "hesap makinesini ac"
        has_folder = any(word.startswith("klasor") for word in words)
        if "ev" in words and has_folder:
            return "ev klasorunu ac"
        if "ana" in words and has_folder:
            return "ana klasoru ac"
        if any(word in {"ac", "baslat", "calistir"} for word in words):
            filler_words = {
                "ac", "baslat", "calistir", "uygulama", "uygulamasini",
                "program", "programi", "programini", "u", "i", "yi", "nu", "ni",
            }
            target_words = [word for word in text.split() if word not in filler_words]
            if target_words:
                target = " ".join(target_words)
                if target in {"tarayici", "tarayiciyi", "internet", "web tarayicisi"}:
                    target = "tarayici"
                return f"uygulama:{target}"
        return None

    def _describe_action(self, command: str) -> str:
        if self.last_detected_language.startswith("en"):
            if command.startswith("uygulama:"):
                return f"open the {command.removeprefix('uygulama:').strip()} application"
            return {
                "ev klasorunu ac": "open the Home folder",
                "ana klasoru ac": "open the Home folder",
                "indirilenleri ac": "open the Downloads folder",
                "hesap makinesini ac": "open the calculator",
            }.get(command, command)
        if command.startswith("uygulama:"):
            return f"{command.removeprefix('uygulama:')} uygulamasını aç"
        return command

    @staticmethod
    def _execute_action(text: str) -> str:
        if text.startswith("uygulama:"):
            return VoiceAssistant._launch_installed_app(text.removeprefix("uygulama:").strip())

        home = Path.home()
        folders = {
            "ev klasorunu ac": home,
            "ana klasoru ac": home,
            "indirilenleri ac": home / "Downloads",
            "indirilenler klasorunu ac": home / "Downloads",
        }
        try:
            if text in folders:
                target = folders[text]
                if not target.exists():
                    return f"Açılamadı: {target} klasörü bulunamadı."
                subprocess.Popen(["xdg-open", str(target)])
                return f"Açıldı: {target}"

            calculator = next(
                (shutil.which(name) for name in ("gnome-calculator", "mate-calc", "galculator") if shutil.which(name)),
                None,
            )
            if calculator:
                subprocess.Popen([calculator])
                return "Hesap makinesi açıldı."
            return "Açılamadı: Hesap makinesi kurulu değil."
        except OSError as exc:
            return f"Açılamadı: {exc}"

    @staticmethod
    def _launch_installed_app(query: str) -> str:
        roots = (
            Path.home() / ".local" / "share" / "applications",
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
        )
        candidates: list[tuple[Path, str, str]] = []
        for root in roots:
            if not root.is_dir():
                continue
            for desktop_file in root.rglob("*.desktop"):
                try:
                    lines = desktop_file.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                in_entry = False
                fields: dict[str, str] = {}
                for line in lines:
                    if line.strip() == "[Desktop Entry]":
                        in_entry = True
                        continue
                    if in_entry and line.startswith("["):
                        break
                    if in_entry and "=" in line and not line.lstrip().startswith("#"):
                        key, value = line.split("=", 1)
                        fields[key.strip()] = value.strip()
                if fields.get("Hidden", "false").casefold() == "true":
                    continue
                if fields.get("NoDisplay", "false").casefold() == "true":
                    continue
                name = fields.get("Name[tr_TR]") or fields.get("Name[tr]") or fields.get("Name")
                if not name:
                    continue
                try_exec = fields.get("TryExec", "").strip()
                if try_exec and not Path(try_exec).exists() and not shutil.which(try_exec):
                    continue
                app_id = desktop_file.relative_to(root).as_posix().replace("/", "-").removesuffix(".desktop")
                candidates.append((desktop_file, app_id, name))

        normalized_query = normalize(query)
        preferred_names: tuple[str, ...] = ()
        if normalized_query in {"tarayici", "internet"}:
            preferred_names = ("firefox", "chromium", "chrome", "brave", "browser")

        chosen: tuple[Path, str, str] | None = None
        if preferred_names:
            for preferred in preferred_names:
                chosen = next(
                    (item for item in candidates if preferred in normalize(item[2]) or preferred in normalize(item[0].stem)),
                    None,
                )
                if chosen:
                    break
        if chosen is None:
            chosen = next(
                (
                    item for item in candidates
                    if normalized_query == normalize(item[2])
                    or normalized_query == normalize(item[0].stem)
                ),
                None,
            )
        if chosen is None:
            chosen = next(
                (
                    item for item in candidates
                    if normalized_query in normalize(item[2]) or normalized_query in normalize(item[0].stem)
                ),
                None,
            )
        if chosen is None:
            return f"Açılamadı: {query} adlı kurulu uygulama bulunamadı."

        desktop_file, app_id, name = chosen
        launcher = shutil.which("gtk-launch")
        try:
            if launcher:
                subprocess.Popen([launcher, app_id])
            else:
                gio = shutil.which("gio")
                if not gio:
                    return "Açılamadı: Uygulama başlatıcısı bulunamadı."
                subprocess.Popen([gio, "launch", str(desktop_file)])
        except OSError as exc:
            return f"Açılamadı: {exc}"
        return f"Açılıyor: {name}"


def main() -> None:
    root = tk.Tk()
    VoiceAssistant(root)
    root.mainloop()


if __name__ == "__main__":
    main()
