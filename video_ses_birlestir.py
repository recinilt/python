# -*- coding: utf-8 -*-
"""
Video + Ses Birleştirici
- Tkinter ile dosya seçimi
- ffprobe ile süre tespiti
- ffmpeg ile birleştirme (-shortest: kısa olan baz alınır)
- Gereksinim: ffmpeg sisteme kurulu ve PATH'te olmalı
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import json
import os
import threading


def get_duration(filepath):
    """ffprobe ile dosya süresini saniye cinsinden döndürür."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_format", "-print_format", "json",
                filepath
            ],
            capture_output=True, text=True, encoding="utf-8"
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        return None


def format_duration(seconds):
    """Saniyeyi HH:MM:SS formatına çevirir."""
    if seconds is None:
        return "Bilinmiyor"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


class VideoSesBirlestirici:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 Video + Ses Birleştirici")
        self.root.geometry("620x420")
        self.root.resizable(False, False)

        self.video_path = ""
        self.audio_path = ""
        self.video_duration = None
        self.audio_duration = None

        # === Video Seçimi ===
        frame_video = tk.LabelFrame(root, text="📹 Video Dosyası", padx=10, pady=5)
        frame_video.pack(fill="x", padx=15, pady=(15, 5))

        self.lbl_video = tk.Label(frame_video, text="Seçilmedi", anchor="w", fg="gray")
        self.lbl_video.pack(side="left", fill="x", expand=True)

        btn_video = tk.Button(frame_video, text="Seç", width=8, command=self.select_video)
        btn_video.pack(side="right")

        # === Ses Seçimi ===
        frame_audio = tk.LabelFrame(root, text="🎵 Ses Dosyası", padx=10, pady=5)
        frame_audio.pack(fill="x", padx=15, pady=5)

        self.lbl_audio = tk.Label(frame_audio, text="Seçilmedi", anchor="w", fg="gray")
        self.lbl_audio.pack(side="left", fill="x", expand=True)

        btn_audio = tk.Button(frame_audio, text="Seç", width=8, command=self.select_audio)
        btn_audio.pack(side="right")

        # === Süre Bilgileri ===
        frame_info = tk.LabelFrame(root, text="📋 Süre Bilgileri", padx=10, pady=5)
        frame_info.pack(fill="x", padx=15, pady=5)

        self.lbl_video_dur = tk.Label(frame_info, text="Video süresi: -", anchor="w")
        self.lbl_video_dur.pack(fill="x")

        self.lbl_audio_dur = tk.Label(frame_info, text="Ses süresi: -", anchor="w")
        self.lbl_audio_dur.pack(fill="x")

        self.lbl_output_dur = tk.Label(frame_info, text="Çıktı süresi: -", anchor="w", fg="blue")
        self.lbl_output_dur.pack(fill="x")

        # === Birleştir Butonu ===
        self.btn_merge = tk.Button(
            root, text="🚀 Birleştir", font=("Arial", 12, "bold"),
            bg="#4CAF50", fg="white", height=2,
            command=self.start_merge, state="disabled"
        )
        self.btn_merge.pack(fill="x", padx=15, pady=15)

        # === Durum ===
        self.lbl_status = tk.Label(root, text="Video ve ses dosyası seçin.", anchor="w", fg="gray")
        self.lbl_status.pack(fill="x", padx=15, pady=(0, 10))

    def select_video(self):
        path = filedialog.askopenfilename(
            title="Video Dosyası Seç",
            filetypes=[
                ("Video dosyaları", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv"),
                ("Tüm dosyalar", "*.*")
            ]
        )
        if path:
            self.video_path = path
            self.lbl_video.config(text=os.path.basename(path), fg="black")
            self.video_duration = get_duration(path)
            self.lbl_video_dur.config(
                text=f"Video süresi: {format_duration(self.video_duration)}"
            )
            self.update_output_duration()
            self.check_ready()

    def select_audio(self):
        path = filedialog.askopenfilename(
            title="Ses Dosyası Seç",
            filetypes=[
                ("Ses dosyaları", "*.mp3 *.wav *.aac *.ogg *.flac *.m4a *.wma"),
                ("Tüm dosyalar", "*.*")
            ]
        )
        if path:
            self.audio_path = path
            self.lbl_audio.config(text=os.path.basename(path), fg="black")
            self.audio_duration = get_duration(path)
            self.lbl_audio_dur.config(
                text=f"Ses süresi: {format_duration(self.audio_duration)}"
            )
            self.update_output_duration()
            self.check_ready()

    def update_output_duration(self):
        if self.video_duration and self.audio_duration:
            shortest = min(self.video_duration, self.audio_duration)
            self.lbl_output_dur.config(
                text=f"Çıktı süresi (kısa olan): {format_duration(shortest)}"
            )

    def check_ready(self):
        if self.video_path and self.audio_path:
            self.btn_merge.config(state="normal")
            self.lbl_status.config(text="Hazır. Birleştir'e basın.", fg="green")

    def start_merge(self):
        output_path = filedialog.asksaveasfilename(
            title="Çıktı Dosyasını Kaydet",
            defaultextension=".mp4",
            filetypes=[("MP4 dosyası", "*.mp4")],
            initialfile="birlesik_video.mp4"
        )
        if not output_path:
            return

        self.btn_merge.config(state="disabled")
        self.lbl_status.config(text="⏳ Birleştiriliyor, lütfen bekleyin...", fg="orange")
        self.root.update()

        thread = threading.Thread(target=self.merge, args=(output_path,), daemon=True)
        thread.start()

    def merge(self, output_path):
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", self.video_path,
                "-i", self.audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                output_path
            ]

            process = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8"
            )

            if process.returncode == 0:
                self.root.after(0, lambda: self.on_success(output_path))
            else:
                error_msg = process.stderr[-500:] if process.stderr else "Bilinmeyen hata"
                self.root.after(0, lambda: self.on_error(error_msg))

        except FileNotFoundError:
            self.root.after(0, lambda: self.on_error(
                "ffmpeg bulunamadı!\n\nffmpeg'i indirip PATH'e ekleyin:\nhttps://ffmpeg.org/download.html"
            ))
        except Exception as e:
            self.root.after(0, lambda: self.on_error(str(e)))

    def on_success(self, output_path):
        self.lbl_status.config(text=f"✅ Tamamlandı: {os.path.basename(output_path)}", fg="green")
        self.btn_merge.config(state="normal")
        messagebox.showinfo("Başarılı", f"Dosya kaydedildi:\n{output_path}")

    def on_error(self, error_msg):
        self.lbl_status.config(text="❌ Hata oluştu!", fg="red")
        self.btn_merge.config(state="normal")
        messagebox.showerror("Hata", error_msg)


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoSesBirlestirici(root)
    root.mainloop()
