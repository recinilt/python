#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Video/Playlist Transkript Oluşturucu - İnteraktif Menü Versiyonu
GPU Destekli, Konuşmacı Ayrımı ve ZIP İndirme Özellikli - Faster Whisper Edition
"""

import os
import re
import time
import glob
import torch
from faster_whisper import WhisperModel
import base64
import subprocess
from pathlib import Path
from datetime import timedelta
import gc
import json
import zipfile
import shutil
import warnings
import sys
from typing import List, Dict, Optional, Tuple
import tkinter as tk
from tkinter import filedialog
import webbrowser

# Docker ortamı kontrolü
import os
IS_DOCKER = os.environ.get('CONTAINER_ENV') == 'docker'

if IS_DOCKER:
    # GUI fonksiyonlarını devre dışı bırak
    import sys
    sys.modules['tkinter'] = None

warnings.filterwarnings("ignore")

# Global değişken - tüm transkript dosyalarını takip etmek için
all_transcript_files = []

# Konuşmacı ayrımı için pipeline
diarization_pipeline = None

# Desteklenen dosya formatları
VIDEO_FORMATS = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
AUDIO_FORMATS = ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma']

# Renk kodları
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def clear_screen():
    """Ekranı temizler"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Program başlığını yazdırır"""
    clear_screen()
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKCYAN}YouTube Video/Playlist Transkript Oluşturucu{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Faster-Whisper • GPU Destekli • Konuşmacı Ayrımı • Toplu İşlem{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")


def get_user_choice(prompt: str, options: List[str], allow_custom: bool = False) -> str:
    """Kullanıcıdan seçim alır"""
    print(f"\n{Colors.BOLD}{prompt}{Colors.ENDC}")
    for i, option in enumerate(options, 1):
        print(f"{Colors.OKBLUE}{i}.{Colors.ENDC} {option}")
    
    if allow_custom:
        print(f"{Colors.OKBLUE}{len(options)+1}.{Colors.ENDC} Özel değer gir")
    
    while True:
        try:
            choice = input(f"\n{Colors.WARNING}Seçiminiz: {Colors.ENDC}")
            choice_int = int(choice)
            
            if 1 <= choice_int <= len(options):
                return options[choice_int - 1]
            elif allow_custom and choice_int == len(options) + 1:
                return input(f"{Colors.WARNING}Özel değer: {Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}Geçersiz seçim! Lütfen tekrar deneyin.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Lütfen bir sayı girin!{Colors.ENDC}")


def get_yes_no(prompt: str) -> bool:
    """Evet/Hayır sorusu sorar"""
    while True:
        response = input(f"\n{Colors.WARNING}{prompt} (E/H): {Colors.ENDC}").strip().upper()
        if response in ['E', 'EVET', 'Y', 'YES']:
            return True
        elif response in ['H', 'HAYIR', 'N', 'NO']:
            return False
        else:
            print(f"{Colors.FAIL}Lütfen E veya H girin!{Colors.ENDC}")


def select_files_or_folder_gui() -> Tuple[List[str], str]:
    """Dosya veya klasör seçmek için GUI penceresi açar"""
    root = tk.Tk()
    root.withdraw()
    
    # Önce seçim tipini sor
    print(f"\n{Colors.BOLD}Ne seçmek istersiniz?{Colors.ENDC}")
    print(f"{Colors.OKBLUE}1.{Colors.ENDC} Tek dosya")
    print(f"{Colors.OKBLUE}2.{Colors.ENDC} Birden fazla dosya")
    print(f"{Colors.OKBLUE}3.{Colors.ENDC} Klasör (içindeki tüm video/ses dosyaları)")
    
    choice = input(f"\n{Colors.WARNING}Seçiminiz: {Colors.ENDC}")
    
    output_dir = None
    
    if choice == "1":
        # Tek dosya seç
        file_path = filedialog.askopenfilename(
            title="Video veya Ses Dosyası Seçin",
            filetypes=[
                ("Video/Ses Dosyaları", " ".join(f"*{ext}" for ext in VIDEO_FORMATS + AUDIO_FORMATS)),
                ("Video Dosyaları", " ".join(f"*{ext}" for ext in VIDEO_FORMATS)),
                ("Ses Dosyaları", " ".join(f"*{ext}" for ext in AUDIO_FORMATS)),
                ("Tüm Dosyalar", "*.*")
            ]
        )
        root.destroy()
        
        if file_path:
            output_dir = os.path.dirname(file_path)
            return [file_path], output_dir
        else:
            return [], None
    
    elif choice == "2":
        # Birden fazla dosya seç
        file_paths = filedialog.askopenfilenames(
            title="Video veya Ses Dosyalarını Seçin (Ctrl ile çoklu seçim)",
            filetypes=[
                ("Video/Ses Dosyaları", " ".join(f"*{ext}" for ext in VIDEO_FORMATS + AUDIO_FORMATS)),
                ("Video Dosyaları", " ".join(f"*{ext}" for ext in VIDEO_FORMATS)),
                ("Ses Dosyaları", " ".join(f"*{ext}" for ext in AUDIO_FORMATS)),
                ("Tüm Dosyalar", "*.*")
            ]
        )
        root.destroy()
        
        if file_paths:
            output_dir = os.path.dirname(file_paths[0])
            return list(file_paths), output_dir
        else:
            return [], None
    
    elif choice == "3":
        # Klasör seç
        folder_path = filedialog.askdirectory(
            title="Video/Ses Dosyalarını İçeren Klasörü Seçin"
        )
        root.destroy()
        
        if folder_path:
            # Klasördeki tüm video/ses dosyalarını bul
            files = []
            for ext in VIDEO_FORMATS + AUDIO_FORMATS:
                files.extend(glob.glob(os.path.join(folder_path, f"*{ext}")))
                files.extend(glob.glob(os.path.join(folder_path, f"*{ext.upper()}")))
            
            if files:
                return files, folder_path
            else:
                print(f"{Colors.FAIL}Seçilen klasörde video/ses dosyası bulunamadı!{Colors.ENDC}")
                return [], None
        else:
            return [], None
    
    else:
        root.destroy()
        print(f"{Colors.FAIL}Geçersiz seçim!{Colors.ENDC}")
        return [], None


def check_dependencies():
    """Gerekli bağımlılıkları kontrol eder"""
    # FFmpeg kontrolü
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Colors.FAIL}❌ FFmpeg bulunamadı. Lütfen https://ffmpeg.org adresinden indirip PATH'e ekleyin.{Colors.ENDC}")
        return False
    
    # yt-dlp'yi Python modülü olarak kontrol et
    try:
        import yt_dlp
        print(f"{Colors.OKGREEN}✅ yt-dlp modülü bulundu{Colors.ENDC}")
    except ImportError:
        print(f"{Colors.FAIL}❌ yt-dlp modülü bulunamadı. pip install yt-dlp komutu ile yükleyin.{Colors.ENDC}")
        return False
    
    # faster-whisper kontrolü
    try:
        from faster_whisper import WhisperModel
        print(f"{Colors.OKGREEN}✅ faster-whisper modülü bulundu{Colors.ENDC}")
    except ImportError:
        print(f"{Colors.FAIL}❌ faster-whisper modülü bulunamadı. pip install faster-whisper komutu ile yükleyin.{Colors.ENDC}")
        return False
    
    return True


def gpu_baglanti_kontrol():
    """GPU bağlantısını kontrol et"""
    if torch.cuda.is_available():
        gpu_tipi = torch.cuda.get_device_name(0)
        print(f"{Colors.OKGREEN}✅ GPU bulundu: {gpu_tipi}{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.WARNING}⚠️ GPU bulunamadı. CPU kullanılacak (daha yavaş olabilir){Colors.ENDC}")
        return False


def clean_filename(filename):
    """Dosya adını Windows ve Linux için güvenli hale getirir"""
    forbidden_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in forbidden_chars:
        filename = filename.replace(char, '')

    if len(filename) > 100:
        filename = filename[:100] + "..."

    filename = filename.replace(' ', '_')
    filename = re.sub(r'_+', '_', filename)
    filename = filename.strip('_')

    return filename


def initialize_diarization_pipeline(huggingface_token: str, min_speakers: int = 2, max_speakers: int = 10):
    """Konuşmacı ayrımı pipeline'ını başlat"""
    global diarization_pipeline
    
    if not huggingface_token:
        print(f"{Colors.WARNING}⚠️ Konuşmacı ayrımı için HuggingFace token gerekli!")
        print(f"📌 Token almak için: https://huggingface.co/settings/tokens")
        print(f"📌 pyannote/speaker-diarization-3.1 modelini kabul etmeyi unutmayın!{Colors.ENDC}")
        return False
    
    try:
        from pyannote.audio import Pipeline
        print(f"{Colors.OKBLUE}🎤 Konuşmacı ayrımı modeli yükleniyor...{Colors.ENDC}")
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=huggingface_token
        )
        
        diarization_pipeline.to(device)
        
        print(f"{Colors.OKGREEN}✅ Konuşmacı ayrımı modeli yüklendi ({device}){Colors.ENDC}")
        return True
        
    except Exception as e:
        print(f"{Colors.FAIL}❌ Konuşmacı ayrımı modeli yüklenemedi: {str(e)}{Colors.ENDC}")
        diarization_pipeline = None
        return False


def perform_speaker_diarization(audio_path: str, min_speakers: int = 2, max_speakers: int = 10):
    """Ses dosyası için konuşmacı ayrımı yap"""
    global diarization_pipeline
    
    if not diarization_pipeline:
        return None
    
    try:
        print(f"{Colors.OKBLUE}🎤 Konuşmacılar tespit ediliyor...{Colors.ENDC}")
        
        diarization = diarization_pipeline(
            audio_path,
            min_speakers=min_speakers,
            max_speakers=max_speakers
        )
        
        speaker_segments = []
        speakers_found = set()
        
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speakers_found.add(speaker)
            speaker_segments.append({
                'start': turn.start,
                'end': turn.end,
                'speaker': speaker
            })
        
        print(f"{Colors.OKGREEN}✅ {len(speakers_found)} konuşmacı tespit edildi{Colors.ENDC}")
        return speaker_segments
        
    except Exception as e:
        print(f"{Colors.WARNING}⚠️ Konuşmacı ayrımı hatası: {str(e)}{Colors.ENDC}")
        return None


def assign_speakers_to_transcript(transcript_segments, speaker_segments):
    """Transkript segmentlerine konuşmacı bilgisi ekle"""
    if not speaker_segments:
        return transcript_segments
    
    enhanced_segments = []
    
    for segment in transcript_segments:
        seg_start = segment['start']
        seg_end = segment['end']
        seg_mid = (seg_start + seg_end) / 2
        
        best_speaker = "Bilinmeyen"
        best_overlap = 0
        
        for speaker_seg in speaker_segments:
            if speaker_seg['start'] <= seg_mid <= speaker_seg['end']:
                best_speaker = speaker_seg['speaker']
                break
            
            overlap_start = max(seg_start, speaker_seg['start'])
            overlap_end = min(seg_end, speaker_seg['end'])
            overlap = max(0, overlap_end - overlap_start)
            
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker_seg['speaker']
        
        segment['speaker'] = best_speaker
        enhanced_segments.append(segment)
    
    return enhanced_segments


def get_video_title_and_id(video_url: str) -> Tuple[str, str]:
    """Video URL'sinden başlık ve ID'yi alır"""
    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get('title', 'Video')
            video_id = info.get('id', '')
            
        return clean_filename(title), video_id
        
    except Exception as e:
        print(f"{Colors.WARNING}Video bilgileri alınamadı: {str(e)}{Colors.ENDC}")
        video_id = extract_youtube_id(video_url)
        return f"Video_{video_id}", video_id


def is_playlist_url(url: str) -> bool:
    """URL'nin playlist olup olmadığını kontrol eder"""
    playlist_patterns = [
        r'[?&]list=([^&]+)',
        r'youtube\.com/playlist\?list=([^&]+)',
    ]

    for pattern in playlist_patterns:
        if re.search(pattern, url):
            return True
    return False


def extract_youtube_id(url: str) -> Optional[str]:
    """YouTube URL'sinden video ID'sini çıkarır"""
    if '&' in url:
        url = url.split('&')[0]

    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([^\/\?\&]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([^\/\?\&]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([^\/\?\&]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([^\/\?\&]+)',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([^\/\?\&]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def get_playlist_videos(playlist_url: str, max_videos: int = 50) -> List[Dict]:
    """Playlist'teki videoları listeler"""
    print(f"{Colors.OKBLUE}Playlist bilgileri alınıyor...{Colors.ENDC}")

    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'playlistend': max_videos,
            'ignoreerrors': True
        }
        
        videos = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            
            if 'entries' in playlist_info:
                for entry in playlist_info['entries']:
                    if entry is None:
                        continue
                    
                    video_id = entry.get('id', '')
                    title = entry.get('title', 'Video')
                    duration = entry.get('duration', 0)
                    
                    if duration and duration != 0:
                        duration_str = str(timedelta(seconds=duration))
                    else:
                        duration_str = 'Bilinmiyor'
                    
                    videos.append({
                        'id': video_id,
                        'title': title,
                        'clean_title': clean_filename(title),
                        'duration': duration_str,
                        'url': f'https://www.youtube.com/watch?v={video_id}'
                    })

        return videos

    except Exception as e:
        print(f"{Colors.FAIL}Playlist bilgileri alınamadı: {str(e)}{Colors.ENDC}")
        return []


def download_youtube_audio_direct(youtube_url: str, output_path: Optional[str] = None) -> str:
    """YouTube videosunu direkt MP3 olarak indirir"""
    import yt_dlp
    
    video_id = extract_youtube_id(youtube_url)
    if not video_id:
        raise ValueError(f"Geçerli bir YouTube URL'si değil: {youtube_url}")

    print(f"{Colors.OKBLUE}YouTube video ID: {video_id}")
    print(f"Ses dosyası indiriliyor (direkt MP3)...{Colors.ENDC}")

    if output_path is None:
        timestamp = int(time.time())
        output_path = f"youtube_audio_{video_id}_{timestamp}.mp3"

    if not output_path.endswith('.mp3'):
        output_path = output_path.replace(os.path.splitext(output_path)[1], '.mp3')

    old_files = glob.glob(f"youtube_audio_{video_id}_*.mp3")
    for old_file in old_files:
        try:
            os.remove(old_file)
        except:
            pass

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'audioquality': 0,
        'outtmpl': output_path.replace('.mp3', '.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'retries': 5,
        'fragment_retries': 5,
        'socket_timeout': 30
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            
        expected_file = output_path
        if not os.path.exists(expected_file):
            directory = os.path.dirname(expected_file) if os.path.dirname(expected_file) else '.'
            mp3_files = glob.glob(os.path.join(directory, f"*{video_id}*.mp3"))
            if mp3_files:
                expected_file = max(mp3_files, key=os.path.getctime)
                if expected_file != output_path:
                    os.rename(expected_file, output_path)
                    expected_file = output_path

        if not os.path.exists(expected_file):
            raise Exception("İndirilen ses dosyası bulunamadı")

        try:
            duration_cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                expected_file
            ]

            duration = float(subprocess.check_output(duration_cmd, timeout=30).decode('utf-8').strip())
            print(f"{Colors.OKGREEN}Ses dosyası başarıyla indirildi: {expected_file}")
            print(f"Ses uzunluğu: {duration:.1f} saniye ({format_time_duration(duration)})")
            print(f"Dosya boyutu: {os.path.getsize(expected_file) / (1024*1024):.1f} MB{Colors.ENDC}")
        except:
            print(f"{Colors.OKGREEN}Ses dosyası başarıyla indirildi: {expected_file}{Colors.ENDC}")

        return expected_file

    except Exception as e:
        raise Exception(f"Ses indirme hatası: {str(e)}")


def format_time(seconds: float) -> str:
    """Saniye cinsinden zamanı SS:DD:SS formatına dönüştürür"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_time_duration(seconds: float) -> str:
    """Saniye cinsinden süreyi okunabilir formata dönüştürür"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours} saat {minutes} dakika {secs} saniye"
    elif minutes > 0:
        return f"{minutes} dakika {secs} saniye"
    else:
        return f"{secs} saniye"


def create_zip_archive(file_paths: List[str], zip_name: str = "transkriptler.zip") -> str:
    """Birden fazla dosyayı ZIP arşivi olarak oluşturur"""
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            if os.path.exists(file_path):
                arcname = os.path.basename(file_path)
                zipf.write(file_path, arcname)
    
    zip_size = os.path.getsize(zip_name) / (1024*1024)
    
    print(f"\n{Colors.OKGREEN}📦 ZIP arşivi oluşturuldu: {zip_name}")
    print(f"📁 Dosya sayısı: {len(file_paths)}")
    print(f"💾 ZIP boyutu: {zip_size:.2f} MB{Colors.ENDC}")
    
    return zip_name


def get_video_duration(input_file: str) -> float:
    """Video veya ses dosyasının süresini saniye cinsinden döndürür"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        input_file
    ]
    output = subprocess.check_output(cmd).decode('utf-8').strip()
    return float(output)


def is_audio_file(file_path: str) -> bool:
    """Dosyanın ses dosyası olup olmadığını kontrol eder"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in AUDIO_FORMATS


def is_video_file(file_path: str) -> bool:
    """Dosyanın video dosyası olup olmadığını kontrol eder"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_FORMATS


def check_file_type(file_path: str) -> str:
    """Dosya türünü kontrol eder ve uygun değeri döndürür"""
    if is_audio_file(file_path):
        return "audio"
    elif is_video_file(file_path):
        return "video"
    else:
        return "unknown"


def optimize_for_whisper(input_path: str) -> str:
    """Video veya ses dosyasını Whisper için optimize eder"""
    file_type = check_file_type(input_path)
    timestamp = int(time.time())
    audio_path = f"{Path(input_path).stem}_audio_{timestamp}.mp3"

    if file_type == "audio":
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:a', 'mp3',
            '-b:a', '192k',
            '-ar', '16000',
            '-ac', '1',
            '-af', 'highpass=f=200,lowpass=f=3000,volume=2',
            '-y',
            audio_path
        ]
    else:
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vn',
            '-c:a', 'mp3',
            '-b:a', '192k',
            '-ar', '16000',
            '-ac', '1',
            '-af', 'highpass=f=200,lowpass=f=3000,volume=2',
            '-y',
            audio_path
        ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return audio_path


def split_video_ffmpeg(input_file: str, segment_length: int = 15, output_dir: Optional[str] = None) -> List[str]:
    """Video veya ses dosyasını belirtilen dakikalık segmentlere böler"""
    if output_dir is None:
        output_dir = os.path.dirname(input_file)
        if output_dir == '':
            output_dir = '.'

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"{Colors.OKBLUE}Dosya inceleniyor: {input_file}{Colors.ENDC}")
    total_duration = get_video_duration(input_file)

    segment_length_sec = segment_length * 60
    num_segments = int(total_duration / segment_length_sec) + (1 if total_duration % segment_length_sec > 0 else 0)

    print(f"Toplam süre: {total_duration/60:.1f} dakika ({format_time_duration(total_duration)})")
    print(f"Dosya {num_segments} parçaya bölünecek ({segment_length} dakikalık dilimler)...")

    output_files = []

    file_ext = os.path.splitext(input_file)[1]
    if not file_ext:
        file_ext = ".mp3"

    for i in range(num_segments):
        start_time = i * segment_length_sec
        end_time = min((i + 1) * segment_length_sec, total_duration)

        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, f"{base_name}_part{i+1:02d}{file_ext}")

        print(f"Bölüm {i+1}/{num_segments} kesiliyor ({format_time(start_time)} - {format_time(end_time)})...")

        cmd = [
            'ffmpeg',
            '-i', input_file,
            '-ss', str(start_time),
            '-to', str(end_time),
            '-c', 'copy',
            '-y',
            output_file
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output_files.append(output_file)

    print(f"{Colors.OKGREEN}Bölme işlemi tamamlandı. {len(output_files)} parça oluşturuldu.{Colors.ENDC}")
    return output_files


def transcribe_segment(audio_path: str, model, language: str = "tr", 
                      high_quality: bool = True, timestamp_output: bool = True, 
                      speaker_diarization: Optional[List] = None) -> Dict:
    """Tek bir ses segmentinin transkriptini oluşturur - Faster Whisper ile"""
    segment_start_time = time.time()
    print(f"Segment işleniyor: {os.path.basename(audio_path)}")

    try:
        # Faster Whisper için transkript seçenekleri
        if high_quality:
            beam_size = 8
            best_of = 5
            temperature = [0.0, 0.2, 0.4, 0.6]
            condition_on_previous_text = True
        else:
            ###################################################################
            beam_size = 5
            best_of = 3
            temperature = [0.0, 0.2]
            condition_on_previous_text = False

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Faster Whisper transkript işlemi
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=beam_size,
            best_of=best_of,
            temperature=temperature,
            condition_on_previous_text=condition_on_previous_text,
            word_timestamps=timestamp_output,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        # Segmentleri listeye çevir
        transcript_segments = []
        transcript_text = ""
        
        for segment in segments:
            segment_dict = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            transcript_segments.append(segment_dict)
            transcript_text += segment.text.strip() + " "

        # Konuşmacı bilgilerini ekle
        if speaker_diarization is not None:
            transcript_segments = assign_speakers_to_transcript(transcript_segments, speaker_diarization)

        output_path = f"{Path(audio_path).stem}_transkript.txt"

        with open(output_path, "w", encoding="utf-8") as f:
            if not speaker_diarization:
                f.write(transcript_text.strip())
            else:
                f.write("## KONUŞMACI AYRIMLI TRANSKRİPT ##\n\n")
                current_speaker = None
                speaker_text = ""
                
                for segment in transcript_segments:
                    speaker = segment.get("speaker", "Bilinmeyen")
                    text = segment["text"].strip()
                    
                    if speaker != current_speaker:
                        if current_speaker is not None:
                            f.write(f"[{current_speaker}]: {speaker_text}\n\n")
                        current_speaker = speaker
                        speaker_text = text
                    else:
                        speaker_text += " " + text
                
                if current_speaker is not None:
                    f.write(f"[{current_speaker}]: {speaker_text}\n")

            if timestamp_output and transcript_segments:
                f.write("\n\n## ZAMANLI TRANSKRİPT ##\n\n")
                for segment in transcript_segments:
                    segment_start = segment["start"]
                    segment_end = segment["end"]
                    text = segment["text"]
                    timestamp = f"[{format_time(segment_start)} --> {format_time(segment_end)}]"
                    
                    if speaker_diarization:
                        speaker = segment.get("speaker", "Bilinmeyen")
                        f.write(f"{timestamp} [{speaker}]: {text}\n")
                    else:
                        f.write(f"{timestamp} {text}\n")

        segment_elapsed_time = time.time() - segment_start_time
        print(f"Segment tamamlandı: {os.path.basename(output_path)}")
        print(f"İşlem süresi: {segment_elapsed_time:.2f} saniye ({format_time_duration(segment_elapsed_time)})")

        return {
            "path": output_path,
            "text": transcript_text.strip(),
            "segments": transcript_segments
        }
    except Exception as e:
        print(f"{Colors.FAIL}❌ Segment işleme hatası: {str(e)}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return {
            "path": f"{Path(audio_path).stem}_hata.txt",
            "text": f"Transkript oluşturulamadı: {str(e)}",
            "segments": None
        }


def merge_transcripts(transcript_results: List[Dict], input_file: str, 
                     timestamp_output: bool = True, custom_filename: Optional[str] = None, 
                     has_speaker_diarization: bool = False, output_dir: Optional[str] = None) -> str:
    """Tüm transkript sonuçlarını birleştirir ve bir dosyaya kaydeder"""
    global all_transcript_files

    if custom_filename:
        full_transcript_path = custom_filename
    else:
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        full_transcript_path = f"{base_name}_tam_transkript.txt"
    
    # Çıktı dizini belirtilmişse kullan
    if output_dir:
        full_transcript_path = os.path.join(output_dir, os.path.basename(full_transcript_path))

    full_text = ""
    all_segments = []
    segment_time_offset = 0

    if has_speaker_diarization:
        full_text = "## KONUŞMACI AYRIMLI TAM TRANSKRİPT ##\n\n"
        speaker_texts = {}
        
        for i, result in enumerate(transcript_results):
            if result["segments"] is not None:
                for segment in result["segments"]:
                    speaker = segment.get("speaker", "Bilinmeyen")
                    if speaker not in speaker_texts:
                        speaker_texts[speaker] = []
                    speaker_texts[speaker].append(segment["text"].strip())
        
        for speaker, texts in sorted(speaker_texts.items()):
            full_text += f"\n[{speaker}]:\n"
            full_text += " ".join(texts) + "\n"
    else:
        for i, result in enumerate(transcript_results):
            full_text += f"\n\n--- BÖLÜM {i+1} ---\n\n"
            full_text += result["text"]

    if timestamp_output:
        for i, result in enumerate(transcript_results):
            if result["segments"] is not None:
                for segment in result["segments"]:
                    adjusted_segment = segment.copy()
                    adjusted_segment["start"] += segment_time_offset
                    adjusted_segment["end"] += segment_time_offset
                    all_segments.append(adjusted_segment)

                if result["segments"]:
                    last_segment = result["segments"][-1]
                    segment_time_offset += last_segment["end"]

    with open(full_transcript_path, "w", encoding="utf-8") as f:
        f.write(full_text)

        if timestamp_output and all_segments:
            f.write("\n\n## TAM ZAMANLI TRANSKRİPT ##\n\n")
            for segment in all_segments:
                start_time = segment["start"]
                end_time = segment["end"]
                text = segment["text"]
                timestamp = f"[{format_time(start_time)} --> {format_time(end_time)}]"
                
                if has_speaker_diarization and "speaker" in segment:
                    speaker = segment["speaker"]
                    f.write(f"{timestamp} [{speaker}]: {text}\n")
                else:
                    f.write(f"{timestamp} {text}\n")

    print(f"{Colors.OKGREEN}Tam transkript oluşturuldu: {full_transcript_path}{Colors.ENDC}")
    all_transcript_files.append(full_transcript_path)
    
    return full_transcript_path


def process_file(file_path: str, language: str = "tr", model_size: str = "large", 
                high_quality: bool = True, timestamp_output: bool = True, 
                segment_length_minutes: int = 15, delete_segments_after: bool = True, 
                custom_filename: Optional[str] = None, 
                enable_speaker_diarization: bool = False,
                min_speakers: int = 2, max_speakers: int = 10,
                output_dir: Optional[str] = None) -> Optional[str]:
    """Yerel veya indirilen dosyayı işleyip transkript oluşturur - Faster Whisper ile"""
    try:
        total_start_time = time.time()

        file_type = check_file_type(file_path)
        file_type_str = "Ses" if file_type == "audio" else "Video"

        print(f"\n{Colors.HEADER}--- 1. {file_type_str.upper()} OPTİMİZASYONU ---{Colors.ENDC}")
        audio_path = optimize_for_whisper(file_path)
        print(f"{file_type_str} dosyası optimize edildi: {audio_path}")

        speaker_diarization = None
        if enable_speaker_diarization and diarization_pipeline:
            print(f"\n{Colors.HEADER}--- KONUŞMACI AYRIMI ---{Colors.ENDC}")
            speaker_diarization = perform_speaker_diarization(audio_path, min_speakers, max_speakers)

        print(f"\n{Colors.HEADER}--- 2. SES BÖLME (FFmpeg ile Hızlı Kesim) ---{Colors.ENDC}")
        audio_segments = split_video_ffmpeg(audio_path, segment_length=segment_length_minutes)

        # Faster Whisper için cihaz seçimi
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "float32"
        
        if device == "cuda":
            print(f"\n{Colors.OKGREEN}GPU kullanılıyor: {torch.cuda.get_device_name(0)}{Colors.ENDC}")
        else:
            print(f"\n{Colors.WARNING}UYARI: GPU bulunamadı! CPU kullanılacak (çok yavaş olabilir){Colors.ENDC}")

        print(f"\n{Colors.HEADER}--- 3. FASTER WHISPER MODEL YÜKLEME ---{Colors.ENDC}")
        print(f"{model_size} boyutunda Faster Whisper modeli yükleniyor...")

        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()

        # Faster Whisper modeli oluştur
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print(f"{Colors.OKGREEN}Faster Whisper modeli yüklendi ({device}, {compute_type}){Colors.ENDC}")

        print(f"\n{Colors.HEADER}--- 4. TRANSKRİPT OLUŞTURMA ---{Colors.ENDC}")
        transcript_results = []

        for i, segment_path in enumerate(audio_segments):
            print(f"\n{Colors.OKCYAN}Ses parçası {i+1}/{len(audio_segments)} işleniyor...{Colors.ENDC}")

            segment_speaker_diarization = None
            if speaker_diarization:
                segment_duration = get_video_duration(segment_path)
                segment_start_offset = i * segment_length_minutes * 60
                
                segment_speaker_diarization = []
                for speaker_seg in speaker_diarization:
                    adjusted_start = max(0, speaker_seg['start'] - segment_start_offset)
                    adjusted_end = min(segment_duration, speaker_seg['end'] - segment_start_offset)
                    
                    if adjusted_start < segment_duration and adjusted_end > 0:
                        segment_speaker_diarization.append({
                            'start': adjusted_start,
                            'end': adjusted_end,
                            'speaker': speaker_seg['speaker']
                        })

            result = transcribe_segment(
                segment_path,
                model,
                language=language,
                high_quality=high_quality,
                timestamp_output=timestamp_output,
                speaker_diarization=segment_speaker_diarization
            )

            transcript_results.append(result)

            print("Bellek temizleniyor...")
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("Bellek temizlendi.")

        print(f"\n{Colors.HEADER}--- 5. TRANSKRİPTLERİ BİRLEŞTİRME ---{Colors.ENDC}")
        full_transcript_path = merge_transcripts(
            transcript_results,
            file_path,
            timestamp_output=timestamp_output,
            custom_filename=custom_filename,
            has_speaker_diarization=(speaker_diarization is not None),
            output_dir=output_dir
        )

        print(f"\n{Colors.OKGREEN}--- İŞLEM TAMAMLANDI ---{Colors.ENDC}")

        if delete_segments_after:
            print(f"\n{Colors.OKBLUE}Geçici dosyalar temizleniyor...{Colors.ENDC}")
            for segment_path in audio_segments:
                if os.path.exists(segment_path):
                    os.remove(segment_path)
                transcript_path = f"{Path(segment_path).stem}_transkript.txt"
                if os.path.exists(transcript_path):
                    os.remove(transcript_path)

            if os.path.exists(audio_path) and audio_path != file_path:
                os.remove(audio_path)

            print(f"{Colors.OKGREEN}Geçici dosyalar temizlendi{Colors.ENDC}")

        # Modeli bellek temizliği için sil
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        total_elapsed_time = time.time() - total_start_time
        print(f"\n{Colors.BOLD}Toplam işlem süresi: {total_elapsed_time:.2f} saniye ({format_time_duration(total_elapsed_time)}){Colors.ENDC}")

        print(f"\n{Colors.HEADER}TRANSKRİPT ÖN İZLEME (ilk 500 karakter):{Colors.ENDC}")
        print("=" * 80)
        with open(full_transcript_path, 'r', encoding='utf-8') as f:
            preview = f.read(500) + "..."
            print(preview)
        print("=" * 80)

        return full_transcript_path

    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Hata oluştu: {str(e)}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return None


def process_youtube_content(youtube_url: str, language: str = "tr", model_size: str = "medium", 
                           high_quality: bool = True, timestamp_output: bool = True, 
                           segment_length_minutes: int = 20, delete_segments_after: bool = True,
                           is_playlist_item: bool = False, playlist_index: Optional[int] = None,
                           enable_speaker_diarization: bool = False,
                           min_speakers: int = 2, max_speakers: int = 10,
                           output_dir: Optional[str] = None) -> Optional[str]:
    """YouTube içeriğini işler"""
    try:
        clean_title, video_id = get_video_title_and_id(youtube_url)

        if is_playlist_item and playlist_index is not None:
            custom_filename = f"[{playlist_index:02d}]-{clean_title}-{video_id}.txt"
        else:
            custom_filename = f"{clean_title}-{video_id}.txt"

        print(f"\n{Colors.OKBLUE}📝 Transkript dosya adı: {custom_filename}{Colors.ENDC}")

        print(f"\n{Colors.HEADER}--- YOUTUBE SES İNDİRME ---{Colors.ENDC}")
        audio_file_path = download_youtube_audio_direct(youtube_url)

        result = process_file(
            audio_file_path,
            language=language,
            model_size=model_size,
            high_quality=high_quality,
            timestamp_output=timestamp_output,
            segment_length_minutes=segment_length_minutes,
            delete_segments_after=delete_segments_after,
            custom_filename=custom_filename,
            enable_speaker_diarization=enable_speaker_diarization,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            output_dir=output_dir
        )

        if delete_segments_after and os.path.exists(audio_file_path):
            print("Orijinal ses dosyası temizleniyor...")
            os.remove(audio_file_path)
            print("Orijinal ses dosyası temizlendi")

        return result

    except Exception as e:
        print(f"{Colors.FAIL}❌ YouTube işleme hatası: {str(e)}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return None


def process_playlist(playlist_url: str, max_videos: int = 50, continue_on_error: bool = True, 
                    output_dir: Optional[str] = None, **kwargs) -> List[Dict]:
    """YouTube playlist'ini işler"""
    global all_transcript_files

    try:
        print(f"\n{Colors.HEADER}{'='*80}")
        print(f"🎬 YOUTUBE PLAYLIST İŞLEME BAŞLADI")
        print(f"{'='*80}{Colors.ENDC}")

        videos = get_playlist_videos(playlist_url, max_videos)

        if not videos:
            print(f"{Colors.FAIL}❌ Playlist'ten video bilgileri alınamadı!{Colors.ENDC}")
            return []

        print(f"\n{Colors.OKBLUE}📋 Playlist Bilgileri:")
        print(f"   • Bulunan video sayısı: {len(videos)}")
        print(f"   • İşlenecek maksimum video: {max_videos}")
        print(f"   • Hatada devam et: {'Evet' if continue_on_error else 'Hayır'}{Colors.ENDC}")

        all_results = []
        successful_count = 0
        failed_count = 0

        print(f"\n{Colors.HEADER}{'='*80}")
        print(f"🚀 VİDEO İŞLEME BAŞLIYOR")
        print(f"{'='*80}{Colors.ENDC}")

        for i, video in enumerate(videos, 1):
            video_start_time = time.time()

            print(f"\n{Colors.OKCYAN}{'-'*60}")
            print(f"📹 Video {i}/{len(videos)}")
            print(f"📌 ID: {video['id']}")
            print(f"📝 Başlık: {video['title']}")
            print(f"⏱️ Süre: {video['duration']}")
            print(f"🔗 URL: {video['url']}")
            print(f"{'-'*60}{Colors.ENDC}")

            try:
                result_path = process_youtube_content(
                    video['url'],
                    is_playlist_item=True,
                    playlist_index=i,
                    output_dir=output_dir,
                    **kwargs
                )

                if result_path:
                    video_elapsed_time = time.time() - video_start_time

                    all_results.append({
                        'video_info': video,
                        'transcript_path': result_path,
                        'status': 'success',
                        'processing_time': video_elapsed_time
                    })

                    successful_count += 1

                    print(f"\n{Colors.OKGREEN}✅ Video {i} başarıyla işlendi!")
                    print(f"⏱️ İşlem süresi: {format_time_duration(video_elapsed_time)}")
                    print(f"📁 Transkript dosyası: {result_path}{Colors.ENDC}")

                else:
                    failed_count += 1
                    all_results.append({
                        'video_info': video,
                        'transcript_path': None,
                        'status': 'failed',
                        'error': 'Transkript oluşturulamadı'
                    })
                    print(f"\n{Colors.FAIL}❌ Video {i} işlenemedi!{Colors.ENDC}")

                    if not continue_on_error:
                        print(f"{Colors.FAIL}❌ Hatada durma aktif - işlem durduruldu!{Colors.ENDC}")
                        break

            except Exception as e:
                failed_count += 1
                error_msg = str(e)

                all_results.append({
                    'video_info': video,
                    'transcript_path': None,
                    'status': 'failed',
                    'error': error_msg
                })

                print(f"\n{Colors.FAIL}❌ Video {i} işleme hatası: {error_msg}{Colors.ENDC}")

                if not continue_on_error:
                    print(f"{Colors.FAIL}❌ Hatada durma aktif - işlem durduruldu!{Colors.ENDC}")
                    break
                else:
                    print(f"{Colors.WARNING}⚠️ Hatada devam et aktif - bir sonraki videoya geçiliyor...{Colors.ENDC}")

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        create_playlist_summary(all_results, playlist_url, output_dir)

        return all_results

    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Playlist işleme genel hatası: {str(e)}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return []


def create_playlist_summary(results: List[Dict], playlist_url: str, output_dir: Optional[str] = None) -> None:
    """Playlist işleme özeti oluşturur"""
    global all_transcript_files

    print(f"\n{Colors.HEADER}{'='*80}")
    print(f"📊 PLAYLIST İŞLEME ÖZETİ")
    print(f"{'='*80}{Colors.ENDC}")

    successful_results = [r for r in results if r['status'] == 'success']
    failed_results = [r for r in results if r['status'] == 'failed']

    print(f"{Colors.OKBLUE}📋 Playlist URL: {playlist_url}")
    print(f"📊 Toplam video: {len(results)}")
    print(f"✅ Başarılı: {len(successful_results)}")
    print(f"❌ Başarısız: {len(failed_results)}{Colors.ENDC}")

    if successful_results:
        total_processing_time = sum(r.get('processing_time', 0) for r in successful_results)
        average_time = total_processing_time / len(successful_results)

        print(f"{Colors.OKGREEN}⏱️ Toplam işlem süresi: {format_time_duration(total_processing_time)}")
        print(f"⏱️ Ortalama video işlem süresi: {format_time_duration(average_time)}{Colors.ENDC}")

    summary_filename = f"playlist_ozet_{int(time.time())}.txt"
    if output_dir:
        summary_filename = os.path.join(output_dir, summary_filename)

    with open(summary_filename, 'w', encoding='utf-8') as f:
        f.write(f"YouTube Playlist Transkript Özeti\n")
        f.write(f"{'='*50}\n\n")
        f.write(f"Playlist URL: {playlist_url}\n")
        f.write(f"İşlem Tarihi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"📊 İstatistikler:\n")
        f.write(f"   • Toplam video: {len(results)}\n")
        f.write(f"   • Başarılı: {len(successful_results)}\n")
        f.write(f"   • Başarısız: {len(failed_results)}\n\n")

        if successful_results:
            f.write(f"✅ Başarıyla İşlenen Videolar:\n")
            f.write(f"{'-'*40}\n")
            for i, result in enumerate(successful_results, 1):
                video = result['video_info']
                f.write(f"{i}. {video['title']}\n")
                f.write(f"   • Video ID: {video['id']}\n")
                f.write(f"   • Süre: {video['duration']}\n")
                f.write(f"   • Transkript: {result['transcript_path']}\n")
                f.write(f"   • İşlem süresi: {format_time_duration(result.get('processing_time', 0))}\n\n")

        if failed_results:
            f.write(f"❌ İşlenemeden Videolar:\n")
            f.write(f"{'-'*40}\n")
            for i, result in enumerate(failed_results, 1):
                video = result['video_info']
                f.write(f"{i}. {video['title']}\n")
                f.write(f"   • Video ID: {video['id']}\n")
                f.write(f"   • URL: {video['url']}\n")
                f.write(f"   • Hata: {result.get('error', 'Bilinmeyen hata')}\n\n")

    print(f"\n{Colors.OKGREEN}📁 Özet dosyası oluşturuldu: {summary_filename}{Colors.ENDC}")
    all_transcript_files.append(summary_filename)


def get_transcript_settings():
    """Transkript ayarlarını kullanıcıdan alır"""
    settings = {}
    
    # Dil seçimi
    languages = {
        'Türkçe': 'tr',
        'İngilizce': 'en',
        'Almanca': 'de',
        'Fransızca': 'fr',
        'İspanyolca': 'es',
        'İtalyanca': 'it',
        'Rusça': 'ru',
        'Arapça': 'ar',
        'Çince': 'zh',
        'Japonca': 'ja',
        'Korece': 'ko',
        'Portekizce': 'pt'
    }
    
    lang_choice = get_user_choice("Transkript dili seçin:", list(languages.keys()))
    settings['language'] = languages[lang_choice]
    
    # Model boyutu - Faster Whisper modelleri
    if gpu_baglanti_kontrol():
        models = ['tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3']
        default_model = 'medium'
    else:
        models = ['tiny', 'base', 'small', 'medium']
        default_model = 'small'
        print(f"{Colors.WARNING}Not: GPU olmadığı için large modeller önerilmez{Colors.ENDC}")
    
    model_choice = get_user_choice(f"Model boyutu seçin (önerilen: {default_model}):", models)
    settings['model_size'] = model_choice
    
    # Kalite ayarı
    settings['high_quality'] = get_yes_no("Yüksek kalite modu kullanılsın mı? (daha yavaş ama daha doğru)")
    
    # Zaman damgası
    settings['timestamp_output'] = get_yes_no("Zaman damgaları eklensin mi?")
    
    # Segment uzunluğu
    segment_options = ['5', '10', '15', '20', '30', '60']
    segment_choice = get_user_choice("Segment uzunluğu (dakika):", segment_options, allow_custom=True)
    settings['segment_length_minutes'] = int(segment_choice)
    
    # Geçici dosyalar
    settings['delete_segments_after'] = get_yes_no("İşlem sonrası geçici dosyalar silinsin mi?")
    
    # Konuşmacı ayrımı
    settings['enable_speaker_diarization'] = get_yes_no("Konuşmacı ayrımı yapılsın mı?")
    
    if settings['enable_speaker_diarization']:
        settings['huggingface_token'] = input(f"{Colors.WARNING}HuggingFace token: {Colors.ENDC}")
        
        min_speakers = input(f"{Colors.WARNING}Minimum konuşmacı sayısı (varsayılan 2): {Colors.ENDC}")
        settings['min_speakers'] = int(min_speakers) if min_speakers else 2
        
        max_speakers = input(f"{Colors.WARNING}Maksimum konuşmacı sayısı (varsayılan 10): {Colors.ENDC}")
        settings['max_speakers'] = int(max_speakers) if max_speakers else 10
    
    return settings


def process_local_files():
    """Yerel dosyaları işle"""
    print(f"\n{Colors.BOLD}Yerel Dosya/Klasör İşleme{Colors.ENDC}")
    
    files, output_dir = select_files_or_folder_gui()
    
    if not files:
        print(f"{Colors.FAIL}Dosya seçimi iptal edildi veya dosya bulunamadı!{Colors.ENDC}")
        return
    
    print(f"\n{Colors.OKGREEN}Seçilen dosya sayısı: {len(files)}{Colors.ENDC}")
    for i, file in enumerate(files, 1):
        print(f"{Colors.OKBLUE}{i}. {os.path.basename(file)}{Colors.ENDC}")
    
    # Ayarları al
    settings = get_transcript_settings()
    
    # Konuşmacı ayrımı başlat
    if settings.get('enable_speaker_diarization') and settings.get('huggingface_token'):
        initialize_diarization_pipeline(
            settings['huggingface_token'],
            settings.get('min_speakers', 2),
            settings.get('max_speakers', 10)
        )
    
    # Her dosyayı işle
    all_results = []
    for i, file_path in enumerate(files, 1):
        print(f"\n{Colors.HEADER}{'='*60}")
        print(f"Dosya {i}/{len(files)}: {os.path.basename(file_path)}")
        print(f"{'='*60}{Colors.ENDC}")
        
        # Dosya adına göre transkript adı
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        #################################################################################################
        custom_filename = f"{base_name}_transkript.txt"
        
        result = process_file(
            file_path,
            language=settings.get('language', 'tr'),
            model_size=settings.get('model_size', 'medium'),
            high_quality=settings.get('high_quality', True),
            timestamp_output=settings.get('timestamp_output', True),
            segment_length_minutes=settings.get('segment_length_minutes', 20),
            delete_segments_after=settings.get('delete_segments_after', True),
            custom_filename=custom_filename,
            enable_speaker_diarization=settings.get('enable_speaker_diarization', False),
            min_speakers=settings.get('min_speakers', 2),
            max_speakers=settings.get('max_speakers', 10),
            output_dir=output_dir
        )
        
        if result:
            all_results.append(result)
            print(f"{Colors.OKGREEN}✅ Dosya başarıyla işlendi!{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}❌ Dosya işlenemedi!{Colors.ENDC}")
    
    # ZIP oluştur
    if len(all_results) > 1 and get_yes_no("Tüm transkriptleri ZIP dosyası olarak paketlensin mi?"):
        timestamp = int(time.time())
        zip_filename = f"toplu_transkriptler_{timestamp}.zip"
        if output_dir:
            zip_filename = os.path.join(output_dir, zip_filename)
        
        create_zip_archive(all_results, zip_filename)
        
        if get_yes_no("ZIP oluşturuldu. Tekil dosyalar silinsin mi?"):
            for file_path in all_results:
                if os.path.exists(file_path):
                    os.remove(file_path)
            print(f"{Colors.OKGREEN}✅ Tekil dosyalar silindi{Colors.ENDC}")


def process_youtube_videos():
    """YouTube video/playlist işle"""
    print(f"\n{Colors.BOLD}YouTube Video/Playlist İşleme{Colors.ENDC}")
    
    url = input(f"\n{Colors.WARNING}YouTube URL'si (video veya playlist): {Colors.ENDC}").strip()
    
    if not url:
        print(f"{Colors.FAIL}URL boş olamaz!{Colors.ENDC}")
        return
    
    # Playlist kontrolü
    if is_playlist_url(url):
        print(f"\n{Colors.OKGREEN}✅ Playlist URL'si tespit edildi!{Colors.ENDC}")
        
        max_videos = input(f"{Colors.WARNING}Maksimum video sayısı (varsayılan 50): {Colors.ENDC}")
        max_videos = int(max_videos) if max_videos else 50
        
        continue_on_error = get_yes_no("Hata durumunda devam edilsin mi?")
        
        # Çıktı dizini
        output_dir = None
        if get_yes_no("Transkriptler için özel bir klasör seçmek ister misiniz?"):
            root = tk.Tk()
            root.withdraw()
            output_dir = filedialog.askdirectory(title="Transkriptler için klasör seçin")
            root.destroy()
        
        # Ayarları al
        settings = get_transcript_settings()
        
        # Konuşmacı ayrımı başlat
        if settings.get('enable_speaker_diarization') and settings.get('huggingface_token'):
            initialize_diarization_pipeline(
                settings['huggingface_token'],
                settings.get('min_speakers', 2),
                settings.get('max_speakers', 10)
            )
        
        # Playlist'i işle
        process_playlist(
            url,
            max_videos=max_videos,
            continue_on_error=continue_on_error,
            output_dir=output_dir,
            **settings
        )
        
    else:
        print(f"\n{Colors.OKGREEN}✅ Tekil video URL'si tespit edildi!{Colors.ENDC}")
        
        # Çıktı dizini
        output_dir = None
        if get_yes_no("Transkript için özel bir klasör seçmek ister misiniz?"):
            root = tk.Tk()
            root.withdraw()
            output_dir = filedialog.askdirectory(title="Transkript için klasör seçin")
            root.destroy()
        
        # Ayarları al
        settings = get_transcript_settings()
        
        # Konuşmacı ayrımı başlat
        if settings.get('enable_speaker_diarization') and settings.get('huggingface_token'):
            initialize_diarization_pipeline(
                settings['huggingface_token'],
                settings.get('min_speakers', 2),
                settings.get('max_speakers', 10)
            )
        
        # Video'yu işle
        process_youtube_content(
            url,
            is_playlist_item=False,
            output_dir=output_dir,
            **settings
        )


def show_main_menu():
    """Ana menüyü göster"""
    while True:
        print_header()
        
        print(f"{Colors.BOLD}Ana Menü:{Colors.ENDC}")
        print(f"{Colors.OKBLUE}1.{Colors.ENDC} YouTube Video/Playlist İşle")
        print(f"{Colors.OKBLUE}2.{Colors.ENDC} Yerel Dosya/Klasör İşle")
        print(f"{Colors.OKBLUE}3.{Colors.ENDC} Hakkında")
        print(f"{Colors.OKBLUE}4.{Colors.ENDC} Çıkış")
        
        choice = input(f"\n{Colors.WARNING}Seçiminiz (1-4): {Colors.ENDC}")
        
        if choice == '1':
            process_youtube_videos()
            input(f"\n{Colors.WARNING}Devam etmek için Enter'a basın...{Colors.ENDC}")
            
        elif choice == '2':
            process_local_files()
            input(f"\n{Colors.WARNING}Devam etmek için Enter'a basın...{Colors.ENDC}")
            
        elif choice == '3':
            show_about()
            input(f"\n{Colors.WARNING}Devam etmek için Enter'a basın...{Colors.ENDC}")
            
        elif choice == '4':
            print(f"\n{Colors.OKGREEN}Program kapatılıyor...{Colors.ENDC}")
            break
            
        else:
            print(f"{Colors.FAIL}Geçersiz seçim! Lütfen 1-4 arası bir sayı girin.{Colors.ENDC}")
            time.sleep(1)


def show_about():
    """Hakkında bölümü"""
    clear_screen()
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKCYAN}YouTube Video/Playlist Transkript Oluşturucu{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Faster-Whisper Edition{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    
    print(f"\n{Colors.OKGREEN}📝 Özellikler:{Colors.ENDC}")
    print("  • YouTube video ve playlist desteği")
    print("  • Yerel video/ses dosyaları desteği")
    print("  • Toplu dosya işleme")
    print("  • GPU hızlandırma (Faster-Whisper)")
    print("  • Konuşmacı ayrımı")
    print("  • Çoklu dil desteği")
    print("  • Zaman damgalı transkript")
    print("  • ZIP arşivleme")
    
    print(f"\n{Colors.OKBLUE}🛠️ Teknolojiler:{Colors.ENDC}")
    print("  • Faster-Whisper (OpenAI Whisper optimized)")
    print("  • CTranslate2 backend")
    print("  • PyTorch")
    print("  • yt-dlp")
    print("  • FFmpeg")
    print("  • Pyannote (konuşmacı ayrımı)")
    
    print(f"\n{Colors.WARNING}⚙️ Sistem Gereksinimleri:{Colors.ENDC}")
    print("  • Python 3.8+")
    print("  • FFmpeg")
    print("  • 8GB+ RAM (önerilen)")
    print("  • NVIDIA GPU (opsiyonel, önerilen)")
    
    print(f"\n{Colors.OKCYAN}🚀 Faster-Whisper Avantajları:{Colors.ENDC}")
    print("  • 4x daha hızlı transkript")
    print("  • %50 daha az bellek kullanımı")
    print("  • Daha iyi GPU optimizasyonu")
    print("  • CTranslate2 quantization desteği")
    
    print(f"\n{Colors.OKCYAN}👨‍💻 Geliştirici: AI Assistant{Colors.ENDC}")
    print(f"{Colors.OKCYAN}📅 Versiyon: 2.1 (Faster-Whisper Edition){Colors.ENDC}")


def main():
    """Ana program fonksiyonu"""
    try:
        # Başlangıç kontrolları
        print_header()
        
        print(f"{Colors.OKBLUE}Sistem kontrolleri yapılıyor...{Colors.ENDC}")
        
        # Bağımlılık kontrolü
        if not check_dependencies():
            print(f"\n{Colors.FAIL}Gerekli bağımlılıklar eksik! Lütfen yukarıdaki hataları düzeltin.{Colors.ENDC}")
            input(f"\n{Colors.WARNING}Çıkmak için Enter'a basın...{Colors.ENDC}")
            sys.exit(1)
        
        # GPU kontrolü
        gpu_baglanti_kontrol()
        
        print(f"\n{Colors.OKGREEN}✅ Tüm kontroller başarılı!{Colors.ENDC}")
        time.sleep(1)
        
        # Ana menüyü göster
        show_main_menu()
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}⚠️ İşlem kullanıcı tarafından iptal edildi{Colors.ENDC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Beklenmeyen hata: {str(e)}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        input(f"\n{Colors.WARNING}Çıkmak için Enter'a basın...{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()