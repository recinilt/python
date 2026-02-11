# -*- coding: utf-8 -*-
"""
Instagram Grup Sohbet İndirici + HTML Görüntüleyici
====================================================
v2.1 — Reel/Feed/Story/IGTV medya indirme destekli
       challenge_required sorunu çözüldü: önce DM objesindeki URL denenir
Kullanım: python ig_chat_exporter.py
Gereksinimler: pip install instagrapi requests
"""

import os
import sys
import json
import time
import random
import re
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

try:
    from instagrapi import Client
    from instagrapi.types import DirectMessage, DirectThread
except ImportError:
    print("❌ instagrapi kurulu değil!")
    print("Kur: pip install instagrapi requests")
    sys.exit(1)

import requests

# ============================================================
# AYARLAR
# ============================================================
SESSION_FILE = "ig_session.json"
MESSAGES_PER_PAGE = 20
DELAY_MIN = 1.5
DELAY_MAX = 3.5
MAX_RETRIES = 3

# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def smart_delay():
    """Ban koruması: rastgele bekleme"""
    t = random.uniform(DELAY_MIN, DELAY_MAX)
    time.sleep(t)

def safe_filename(name):
    """Dosya adı için güvenli string"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:100] if name else 'unnamed'

def download_file(url, filepath, retries=MAX_RETRIES):
    """URL'den dosya indir"""
    for attempt in range(retries):
        try:
            headers = {
                'User-Agent': 'Instagram 275.0.0.27.98 Android'
            }
            r = requests.get(url, headers=headers, timeout=30, stream=True)
            if r.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                return True
            else:
                print(f"  ⚠️ HTTP {r.status_code} — deneme {attempt+1}/{retries}")
        except Exception as e:
            print(f"  ⚠️ İndirme hatası: {e} — deneme {attempt+1}/{retries}")
        time.sleep(2)
    return False

def ts_to_str(dt):
    if dt is None:
        return ""
    try:
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return str(dt)

def ts_to_date(dt):
    if dt is None:
        return ""
    try:
        return dt.strftime("%d.%m.%Y")
    except:
        return str(dt)

def get_color_for_user(username):
    colors = [
        "#E74C3C", "#3498DB", "#2ECC71", "#F39C12",
        "#9B59B6", "#1ABC9C", "#E67E22", "#EC407A",
        "#26A69A", "#AB47BC", "#42A5F5", "#FFA726",
        "#66BB6A", "#EF5350", "#7E57C2", "#29B6F6"
    ]
    h = int(hashlib.md5(username.encode()).hexdigest(), 16)
    return colors[h % len(colors)]

def ensure_aware(dt):
    """Naive datetime'ı UTC-aware'e çevir. Aware ise dokunma. None ise epoch başlangıcı döndür."""
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

# ============================================================
# DM OBJESİNDEN DOĞRUDAN MEDYA İNDİRME (media_info ÇAĞIRMADAN)
# ============================================================

def try_download_from_obj(media_obj, idx, photos_dir, videos_dir, prefix="media"):
    """
    DM mesajındaki clip/reel_share/media_share/felix_share objesinden
    doğrudan video_url veya video_versions ile indirme dener.
    media_info() çağırmadan çalışır — challenge_required riski yok.
    Returns: list of dict [{type, path, link}, ...] veya boş liste
    """
    results = []
    if media_obj is None:
        return results

    code = None
    ig_link = None

    # code ve link bilgisi
    if isinstance(media_obj, dict):
        code = media_obj.get('code', None)
        # Video URL dene
        vurl = media_obj.get('video_url', None)
        if not vurl:
            vvs = media_obj.get('video_versions', [])
            if vvs and isinstance(vvs, list) and len(vvs) > 0:
                if isinstance(vvs[0], dict):
                    vurl = vvs[0].get('url', '')
                else:
                    vurl = getattr(vvs[0], 'url', None) or str(vvs[0])
        # Foto URL dene
        purl = None
        if not vurl:
            ivs = media_obj.get('image_versions2', {})
            if isinstance(ivs, dict):
                candidates = ivs.get('candidates', [])
                if candidates and isinstance(candidates[0], dict):
                    purl = candidates[0].get('url', '')
            if not purl:
                purl = media_obj.get('thumbnail_url', None)
    else:
        code = getattr(media_obj, 'code', None)
        # Video URL dene
        vurl = getattr(media_obj, 'video_url', None)
        if not vurl:
            vvs = getattr(media_obj, 'video_versions', None)
            if vvs and isinstance(vvs, list) and len(vvs) > 0:
                vurl = getattr(vvs[0], 'url', None) if hasattr(vvs[0], 'url') else str(vvs[0])
        # Foto URL dene
        purl = None
        if not vurl:
            purl = getattr(media_obj, 'thumbnail_url', None)
            if not purl:
                ivs = getattr(media_obj, 'image_versions2', None)
                if ivs:
                    candidates = ivs.get('candidates', []) if isinstance(ivs, dict) else []
                    if candidates:
                        purl = candidates[0].get('url', '') if isinstance(candidates[0], dict) else ''

    if code:
        ig_link = f"https://www.instagram.com/p/{code}/"

    if vurl and str(vurl).startswith('http'):
        fname = f"{prefix}_{idx}.mp4"
        fpath = os.path.join(videos_dir, fname)
        if download_file(str(vurl), fpath):
            results.append({"type": "video", "path": f"media/videos/{fname}", "link": ig_link})
        smart_delay()
    elif purl and str(purl).startswith('http'):
        fname = f"{prefix}_{idx}.jpg"
        fpath = os.path.join(photos_dir, fname)
        if download_file(str(purl), fpath):
            results.append({"type": "photo", "path": f"media/photos/{fname}", "link": ig_link})
        smart_delay()

    return results

# ============================================================
# MEDYA İNDİRME — cl.media_info() ile gerçek medya çekme (FALLBACK)
# ============================================================

def download_media_by_pk(cl, media_pk, idx, photos_dir, videos_dir):
    """
    media_pk üzerinden cl.media_info() ile medya bilgisini al,
    video ise video olarak, foto ise foto olarak indir.
    Albüm ise tüm parçaları indir.
    challenge_required gelirse exponential backoff ile tekrar dener.
    Returns: list of dict [{type, path, link}, ...]
    """
    results = []
    info = None
    media_pk = int(media_pk)

    # Exponential backoff ile media_info dene
    for attempt in range(3):
        try:
            # media_info öncesi ekstra bekleme (ban koruması)
            wait_time = random.uniform(4, 8) * (attempt + 1)
            print(f"    ⏳ media_info öncesi {wait_time:.1f}s bekleniyor...")
            time.sleep(wait_time)
            info = cl.media_info(media_pk)
            break
        except Exception as e:
            err_str = str(e).lower()
            if 'challenge' in err_str:
                backoff = 30 * (attempt + 1) + random.uniform(5, 15)
                print(f"    ⚠️ challenge_required — {backoff:.0f}s bekleniyor (deneme {attempt+1}/3)...")
                time.sleep(backoff)
            elif 'login_required' in err_str:
                print(f"    ⚠️ login_required — session sorunlu olabilir, atlanıyor.")
                return results
            else:
                print(f"    ⚠️ media_info({media_pk}) başarısız: {e}")
                return results

    if info is None:
        print(f"    ❌ media_info({media_pk}) 3 denemede de başarısız oldu.")
        return results

    mtype = getattr(info, 'media_type', 0)
    code = getattr(info, 'code', None)
    ig_link = f"https://www.instagram.com/p/{code}/" if code else None

    if mtype == 8:
        # ALBÜM
        resources = getattr(info, 'resources', []) or []
        for ri, res in enumerate(resources):
            res_type = getattr(res, 'media_type', 1)
            if res_type == 2:
                vurl = getattr(res, 'video_url', None)
                if vurl:
                    fname = f"album_{idx}_{ri}.mp4"
                    fpath = os.path.join(videos_dir, fname)
                    if download_file(str(vurl), fpath):
                        results.append({"type": "video", "path": f"media/videos/{fname}", "link": ig_link})
            else:
                turl = getattr(res, 'thumbnail_url', None)
                if turl:
                    fname = f"album_{idx}_{ri}.jpg"
                    fpath = os.path.join(photos_dir, fname)
                    if download_file(str(turl), fpath):
                        results.append({"type": "photo", "path": f"media/photos/{fname}", "link": ig_link})
    elif mtype == 2:
        # VİDEO (feed video veya reel)
        vurl = getattr(info, 'video_url', None)
        if vurl:
            fname = f"media_{idx}.mp4"
            fpath = os.path.join(videos_dir, fname)
            if download_file(str(vurl), fpath):
                results.append({"type": "video", "path": f"media/videos/{fname}", "link": ig_link})
        else:
            turl = getattr(info, 'thumbnail_url', None)
            if turl:
                fname = f"media_{idx}.jpg"
                fpath = os.path.join(photos_dir, fname)
                if download_file(str(turl), fpath):
                    results.append({"type": "photo", "path": f"media/photos/{fname}", "link": ig_link})
    else:
        # FOTOĞRAF
        turl = getattr(info, 'thumbnail_url', None)
        if turl:
            fname = f"media_{idx}.jpg"
            fpath = os.path.join(photos_dir, fname)
            if download_file(str(turl), fpath):
                results.append({"type": "photo", "path": f"media/photos/{fname}", "link": ig_link})

    return results

# ============================================================
# GİRİŞ
# ============================================================

def get_challenge_code_from_user(username, choice):
    """Challenge resolver: kullanıcıdan doğrulama kodu iste"""
    print(f"\n📱 Instagram doğrulama kodu istiyor (yöntem: {choice})")
    print("   E-posta veya SMS ile gelen 6 haneli kodu gir.")
    code = input("   Doğrulama kodu: ").strip()
    return code

def login_by_sessionid_safe(cl, session_id):
    """login_by_sessionid'nin GraphQL 'data' KeyError hatası alması durumunda
    cookie'yi doğrudan set edip private (mobile) API ile doğrulama yapar."""
    # ÖNCELİK 1: Standart login_by_sessionid dene
    try:
        cl.login_by_sessionid(session_id)
        if cl.user_id:
            return True
    except Exception:
        pass

    # ÖNCELİK 2: Cookie'yi doğrudan set edip private API ile doğrula
    try:
        cl.settings["authorization_data"] = {"sessionid": session_id}
        # Private (mobile) API endpoint — GraphQL kullanmaz
        result = cl.private_request("accounts/current_user/?edit=true")
        user_data = result.get("user", {})
        user_pk = user_data.get("pk", None)
        username = user_data.get("username", "")
        if user_pk:
            cl._user_id = str(user_pk)
            cl.username = username
            return True
    except Exception:
        pass

    # ÖNCELİK 3: Daha basit doğrulama — direct_v2/inbox
    try:
        cl.settings["authorization_data"] = {"sessionid": session_id}
        result = cl.private_request("direct_v2/inbox/", params={"limit": "1"})
        if "inbox" in result:
            # user_id'yi session cookie'den parse et
            try:
                uid = session_id.split("%3A")[0] if "%3A" in session_id else session_id.split(":")[0]
                cl._user_id = str(int(uid))
            except (ValueError, IndexError):
                pass
            return True
    except Exception:
        pass

    return False


def login():
    cl = Client()
    cl.delay_range = [1, 3]
    # Challenge resolver tanımla — login sırasında challenge gelirse otomatik kod sorar
    cl.challenge_code_handler = get_challenge_code_from_user

    if os.path.exists(SESSION_FILE):
        print(f"📂 Kayıtlı session bulundu ({SESSION_FILE})")
        try:
            cl.load_settings(SESSION_FILE)
            sid = cl.settings.get('authorization_data', {}).get('sessionid', '')
            if sid and login_by_sessionid_safe(cl, sid):
                try:
                    cl.account_info()
                except Exception:
                    try:
                        cl.user_info(cl.user_id)
                    except Exception:
                        pass
                if cl.user_id:
                    print("✅ Session ile giriş başarılı!")
                    return cl
                else:
                    raise Exception("session geçersiz")
            else:
                raise Exception("session geçersiz")
        except Exception:
            print("⚠️ Session geçersiz, yeniden giriş yapılıyor...")

    print("\n🔐 Instagram Giriş")
    print("⚠️ Ana hesabını kullanma, test/yedek hesap önerilir!\n")
    print("Giriş yöntemi:")
    print("  1) Kullanıcı adı + Şifre")
    print("  2) Session ID ile giriş")
    method = input("Seçim [1/2]: ").strip()

    if method == "2":
        print("\n📋 Session ID nasıl alınır:")
        print("   1. Tarayıcıda Instagram'a giriş yap")
        print("   2. F12 → Application → Cookies → instagram.com")
        print("   3. 'sessionid' değerini kopyala\n")
        session_id = input("Session ID: ").strip()
        try:
            if not login_by_sessionid_safe(cl, session_id):
                raise Exception("Session ID geçersiz veya süresi dolmuş")
            # Session doğrulama — hafif bir çağrı ile kontrol
            try:
                cl.account_info()
            except Exception:
                try:
                    cl.user_info(cl.user_id)
                except Exception:
                    pass  # session geçerli olabilir, devam et
            if not cl.user_id:
                raise Exception("Session ID geçersiz veya süresi dolmuş")
            print(f"   👤 Giriş yapılan hesap: {cl.username or cl.user_id}")
        except Exception as e:
            print(f"❌ Session ID ile giriş başarısız: {e}")
            sys.exit(1)
    else:
        username = input("Kullanıcı adı: ").strip()
        password = input("Şifre: ").strip()

        has_2fa = input("2FA (iki adımlı doğrulama) açık mı? [e/h]: ").strip().lower()

        try:
            if has_2fa in ('e', 'evet', 'y', 'yes'):
                code = input("2FA kodunu gir (authenticator uygulamasından): ").strip()
                cl.login(username, password, verification_code=code)
            else:
                cl.login(username, password)
        except Exception as e:
            err_str = str(e).lower()
            if 'challenge' in err_str:
                print("\n⚠️ Instagram ek doğrulama istiyor, çözülmeye çalışılıyor...")
                try:
                    cl.challenge_resolve(cl.last_json)
                    # challenge çözüldükten sonra tekrar login dene
                    if has_2fa in ('e', 'evet', 'y', 'yes'):
                        code = input("Yeni 2FA kodunu gir: ").strip()
                        cl.login(username, password, verification_code=code)
                    else:
                        cl.login(username, password)
                except Exception as e2:
                    print(f"❌ Challenge çözülemedi: {e2}")
                    print("\n💡 Alternatif: Session ID ile giriş yapmayı dene (seçenek 2)")
                    print("   Tarayıcıdan Instagram'a giriş yap, sessionid cookie'sini kopyala.")
                    sys.exit(1)
            elif 'two_factor' in err_str or 'two-factor' in err_str or '2fa' in err_str:
                print("\n📱 2FA kodu gerekli (ilk seferde belirtmediniz).")
                code = input("2FA kodunu gir: ").strip()
                try:
                    cl.login(username, password, verification_code=code)
                except Exception as e2:
                    print(f"❌ Giriş başarısız: {e2}")
                    print("\n💡 Alternatif: Session ID ile giriş yapmayı dene (seçenek 2)")
                    sys.exit(1)
            else:
                print(f"❌ Giriş başarısız: {e}")
                sys.exit(1)

    cl.dump_settings(SESSION_FILE)
    print("✅ Giriş başarılı! Session kaydedildi.\n")
    return cl

# ============================================================
# SOHBET LİSTELE VE SEÇ
# ============================================================

def select_thread(cl):
    print("📋 Sohbetler yükleniyor...")
    threads = cl.direct_threads(amount=20)
    smart_delay()

    if not threads:
        print("❌ Hiç sohbet bulunamadı.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  {'#':<4} {'Tür':<4} {'İsim':<30} {'Kişi':<6}")
    print(f"{'='*60}")

    for i, t in enumerate(threads):
        user_count = len(t.users) + 1
        is_group = "👥" if user_count > 2 else "💬"
        name = t.thread_title or "İsimsiz"
        if not t.thread_title and t.users:
            name = ", ".join([u.username for u in t.users[:3]])
            if len(t.users) > 3:
                name += f" +{len(t.users)-3}"
        print(f"  {i+1:<4} {is_group:<4} {name:<30} {user_count:<6}")

    print(f"{'='*60}")

    while True:
        try:
            choice = int(input("\nHangi sohbeti indirmek istersin? [numara]: ")) - 1
            if 0 <= choice < len(threads):
                break
            print("❌ Geçersiz numara.")
        except ValueError:
            print("❌ Sayı gir.")

    thread = threads[choice]
    name = thread.thread_title or "grup_sohbet"
    print(f"\n✅ Seçilen: {name}")
    return thread

# ============================================================
# YARDIMCI: RAW API MESAJ PARSE
# ============================================================

def dict_to_namespace(d):
    """Dict'i SimpleNamespace'e recursive olarak çevir.
    process_messages getattr ile eriştiği için bu yapı uyumlu çalışır."""
    if d is None:
        return None
    if isinstance(d, dict):
        ns = SimpleNamespace(**{k: dict_to_namespace(v) for k, v in d.items()})
        return ns
    if isinstance(d, list):
        return [dict_to_namespace(i) for i in d]
    return d


def raw_item_to_message(item):
    """Raw JSON item'ını DirectMessage benzeri objeye çevir.
    Önce instagrapi'nin extractor'ını dener, başarısız olursa
    SimpleNamespace ile minimum uyumlu obje oluşturur."""
    # ÖNCELİK 1: instagrapi extractor
    # NOT: voice_media item'ları için extract_direct_message atlanır
    # çünkü DirectMessage Pydantic modeli voice_media alanını içermiyor,
    # veri sessizce kayboluyor. Doğrudan SimpleNamespace kullanılır.
    if item.get("item_type") != "voice_media":
        try:
            from instagrapi.extractors import extract_direct_message
            return extract_direct_message(item)
        except Exception:
            pass

    # ÖNCELİK 2: SimpleNamespace fallback
    try:
        ts = item.get("timestamp", None)
        dt = None
        if ts:
            ts_val = int(ts)
            # Instagram microsecond timestamp kullanır
            if ts_val > 1e15:
                ts_val = ts_val / 1_000_000
            dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)

        # clip nested yapıda geliyor: {"clip": {"clip": {...}}}
        clip_data = item.get("clip")
        clip_obj = None
        if clip_data and isinstance(clip_data, dict):
            clip_inner = clip_data.get("clip", clip_data)
            clip_obj = dict_to_namespace(clip_inner) if isinstance(clip_inner, dict) else None

        msg = SimpleNamespace(
            id=item.get("item_id", ""),
            user_id=item.get("user_id", None),
            timestamp=dt,
            item_type=item.get("item_type", "text"),
            text=item.get("text", ""),
            media=dict_to_namespace(item.get("media")) if item.get("media") else None,
            voice_media=dict_to_namespace(item.get("voice_media")) if item.get("voice_media") else None,
            visual_media=item.get("visual_media"),
            clip=clip_obj,
            reel_share=item.get("reel_share"),
            media_share=dict_to_namespace(item.get("media_share")) if item.get("media_share") else None,
            felix_share=item.get("felix_share"),
            story_share=item.get("story_share"),
            animated_media=dict_to_namespace(item.get("animated_media")) if item.get("animated_media") else None,
            link=dict_to_namespace(item.get("link")) if item.get("link") else None,
            action_log=dict_to_namespace(item.get("action_log")) if item.get("action_log") else None,
            xma_share=item.get("xma_share"),
            xma_media_share=item.get("xma_media_share"),
            placeholder=item.get("placeholder"),
        )
        return msg
    except Exception as e:
        print(f"  ⚠️ Mesaj parse hatası: {e}")
        return None


def fetch_messages_raw_api(cl, thread, start_cursor=None, stop_at_ids=None):
    """Raw API ile mesaj çek — Pydantic ValidationError'ı tamamen bypass eder.
    cl.private_request() ile doğrudan Instagram API endpoint'ini çağırır.
    stop_at_ids: bilinen mesaj ID'leri seti — bunlara rastlanınca durur."""
    all_messages = []
    cursor = start_cursor
    page = 0
    consecutive_errors = 0
    MAX_ERRORS = 5
    found_known = False

    print("\n🔄 Raw API ile eski mesajlar çekiliyor...")

    while True:
        page += 1
        params = {
            "visual_message_return_type": "unseen",
            "direction": "older",
            "seq_id": "0",
            "limit": "20",
        }
        if cursor:
            params["cursor"] = cursor

        try:
            result = cl.private_request(
                f"direct_v2/threads/{thread.id}/",
                params=params,
            )
        except Exception as e:
            consecutive_errors += 1
            err_str = str(e).lower()
            if consecutive_errors >= MAX_ERRORS:
                print(f"\n  ❌ Raw API {MAX_ERRORS} ardışık hata, durduruluyor.")
                break
            if 'challenge' in err_str or 'login_required' in err_str:
                wait = random.uniform(15, 30) * consecutive_errors
                print(f"\n  ⚠️ Raw API hatası: {e}")
                print(f"  ⏳ {wait:.0f}s bekleniyor (deneme {consecutive_errors}/{MAX_ERRORS})...")
                time.sleep(wait)
            else:
                wait = random.uniform(3, 6) * consecutive_errors
                print(f"\n  ⚠️ Raw API hatası: {e}")
                print(f"  ⏳ {wait:.1f}s bekleniyor (deneme {consecutive_errors}/{MAX_ERRORS})...")
                time.sleep(wait)
            continue

        consecutive_errors = 0
        thread_data = result.get("thread", {})
        items = thread_data.get("items", [])

        if not items:
            break

        parsed_count = 0
        for item in items:
            item_id = item.get("item_id", "")
            # Bilinen mesaja rastladık — dur
            if stop_at_ids and item_id in stop_at_ids:
                found_known = True
                break
            msg = raw_item_to_message(item)
            if msg:
                all_messages.append(msg)
                parsed_count += 1

        print(f"  📄 Raw sayfa {page}: +{parsed_count} mesaj (toplam raw: {len(all_messages)})", end='\r')

        if found_known:
            print(f"\n  🎯 Bilinen mesaja ulaşıldı, raw API durduruluyor.")
            break

        has_older = thread_data.get("has_older", False)
        new_cursor = thread_data.get("oldest_cursor")

        if not has_older or not new_cursor or new_cursor == cursor:
            break

        cursor = new_cursor
        smart_delay()

    print(f"\n  ✅ Raw API ile {len(all_messages)} ek mesaj çekildi.")
    return all_messages


# ============================================================
# MESAJLARI ÇEK
# ============================================================

def fetch_all_messages(cl, thread, stop_at_ids=None):
    """Mesajları çek. stop_at_ids verilmişse, bilinen ID'ye rastlayınca durur (incremental mod)."""
    all_messages = []
    cursor = None
    page = 0
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 3
    use_raw_api = True  # direct_messages_chunk voice_media verisini kaybediyor (Pydantic modelde yok)
    found_known = False

    if stop_at_ids:
        print(f"\n📥 Yeni mesajlar çekiliyor (incremental mod, {len(stop_at_ids)} bilinen mesaj)...")
    else:
        print("\n📥 Mesajlar çekiliyor...")

    while True:
        page += 1

        # ────────────────────────────────────────────
        # ÖNCELİK 1: instagrapi direct_messages_chunk
        # ────────────────────────────────────────────
        if not use_raw_api:
            try:
                if cursor:
                    msgs, new_cursor = cl.direct_messages_chunk(thread.id, amount=MESSAGES_PER_PAGE, cursor=cursor)
                else:
                    msgs, new_cursor = cl.direct_messages_chunk(thread.id, amount=MESSAGES_PER_PAGE)

                if not msgs:
                    break

                # stop_at_ids kontrolü: bilinen mesaja rastlayınca dur
                new_msgs = []
                for m in msgs:
                    m_id = getattr(m, 'id', None)
                    if stop_at_ids and str(m_id) in stop_at_ids:
                        found_known = True
                        break
                    new_msgs.append(m)

                all_messages.extend(new_msgs)
                consecutive_errors = 0
                print(f"  📄 Sayfa {page}: +{len(new_msgs)} mesaj (toplam: {len(all_messages)})", end='\r')

                if found_known:
                    print(f"\n  🎯 Bilinen mesaja ulaşıldı, çekme durduruluyor.")
                    break

                if not new_cursor or new_cursor == cursor:
                    break
                cursor = new_cursor
                smart_delay()
                continue

            except AttributeError:
                # direct_messages_chunk metodu yok — doğrudan raw API'ye geç
                print("\n  ⚠️ direct_messages_chunk bulunamadı, raw API'ye geçiliyor...")
                use_raw_api = True

            except Exception as e:
                consecutive_errors += 1
                print(f"\n  ⚠️ Sayfa {page} hatası ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}")

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"  🔄 {MAX_CONSECUTIVE_ERRORS} ardışık hata — raw API'ye geçiliyor...")
                    use_raw_api = True
                else:
                    # Retry with backoff
                    wait = random.uniform(3, 8) * consecutive_errors
                    print(f"  ⏳ {wait:.1f}s bekleniyor ve tekrar deneniyor...")
                    time.sleep(wait)
                    continue

        # ────────────────────────────────────────────
        # ÖNCELİK 2: Raw API fallback
        # ────────────────────────────────────────────
        if use_raw_api:
            existing_ids = {getattr(m, 'id', None) for m in all_messages}
            raw_msgs = fetch_messages_raw_api(cl, thread, start_cursor=cursor, stop_at_ids=stop_at_ids)
            # Tekrar eklemeyi önle
            for rm in raw_msgs:
                rm_id = getattr(rm, 'id', None)
                if rm_id not in existing_ids:
                    all_messages.append(rm)
                    existing_ids.add(rm_id)
            break

    all_messages.sort(key=lambda m: ensure_aware(m.timestamp))
    print(f"\n✅ Toplam {len(all_messages)} mesaj çekildi.\n")
    return all_messages

# ============================================================
# MESAJLARI İŞLE + MEDYA İNDİR
# ============================================================

def process_messages(cl, messages, thread, export_dir):
    photos_dir = os.path.join(export_dir, "media", "photos")
    videos_dir = os.path.join(export_dir, "media", "videos")
    audio_dir = os.path.join(export_dir, "media", "audio")
    os.makedirs(photos_dir, exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    my_pk = cl.user_id
    user_map = {str(my_pk): cl.username or "Ben"}
    for u in thread.users:
        user_map[str(u.pk)] = u.username

    processed = []
    total = len(messages)
    media_count = {"photo": 0, "video": 0, "audio": 0, "link": 0}

    print("🔄 Mesajlar işleniyor ve medyalar indiriliyor...\n")

    for idx, msg in enumerate(messages):
        pct = int((idx + 1) / total * 100)
        print(f"  ⏳ İşleniyor: {idx+1}/{total} ({pct}%)", end='\r')

        user_pk = str(msg.user_id) if msg.user_id else "system"
        username = user_map.get(user_pk, f"user_{user_pk}")
        is_me = (user_pk == str(my_pk))
        timestamp_str = ts_to_str(msg.timestamp)
        date_str = ts_to_date(msg.timestamp)

        entry = {
            "id": msg.id,
            "user": username,
            "user_pk": user_pk,
            "is_me": is_me,
            "timestamp": timestamp_str,
            "date": date_str,
            "type": "text",
            "text": "",
            "media_files": [],
            "link": None,
            "is_system": False
        }

        item_type = getattr(msg, 'item_type', 'text') or 'text'

        # ---- TEXT ----
        if item_type == 'text':
            entry["type"] = "text"
            entry["text"] = msg.text or ""

        # ---- MEDIA (doğrudan DM foto/video) ----
        elif item_type == 'media':
            media = getattr(msg, 'media', None)
            if media:
                video_url = None
                if hasattr(media, 'video_versions') and media.video_versions:
                    video_url = media.video_versions[0].url if hasattr(media.video_versions[0], 'url') else str(media.video_versions[0])

                if video_url:
                    fname = f"video_{idx}.mp4"
                    fpath = os.path.join(videos_dir, fname)
                    if download_file(video_url, fpath):
                        entry["type"] = "video"
                        entry["media_files"].append({"type": "video", "path": f"media/videos/{fname}"})
                        media_count["video"] += 1
                    smart_delay()
                else:
                    photo_url = None
                    if hasattr(media, 'image_versions2') and media.image_versions2:
                        candidates = media.image_versions2.get('candidates', []) if isinstance(media.image_versions2, dict) else []
                        if candidates:
                            photo_url = candidates[0].get('url', '')
                    if not photo_url and hasattr(media, 'thumbnail_url') and media.thumbnail_url:
                        photo_url = str(media.thumbnail_url)

                    if photo_url:
                        fname = f"photo_{idx}.jpg"
                        fpath = os.path.join(photos_dir, fname)
                        if download_file(photo_url, fpath):
                            entry["type"] = "photo"
                            entry["media_files"].append({"type": "photo", "path": f"media/photos/{fname}"})
                            media_count["photo"] += 1
                        smart_delay()

            if msg.text:
                entry["text"] = msg.text

        # ---- VOICE MEDIA ----
        elif item_type == 'voice_media':
            vm = getattr(msg, 'voice_media', None) or getattr(msg, 'visual_media', None)
            audio_url = None

            # --- Yöntem 1: Namespace yapıdan audio_src / video_versions ---
            if vm:
                if hasattr(vm, 'media') and vm.media:
                    m = vm.media
                    if hasattr(m, 'audio') and m.audio:
                        audio_url = getattr(m.audio, 'audio_src', None)
                    elif hasattr(m, 'video_versions') and m.video_versions:
                        audio_url = m.video_versions[0].url if hasattr(m.video_versions[0], 'url') else str(m.video_versions[0])
                elif hasattr(vm, 'audio') and vm.audio:
                    audio_url = getattr(vm.audio, 'audio_src', None)

            # --- Yöntem 2: vars() ile raw dict'ten ara ---
            if not audio_url:
                try:
                    raw = vars(msg) if hasattr(msg, '__dict__') else {}
                    vm_raw = raw.get('voice_media', {})
                    # voice_media namespace ise dict'e çevir
                    if hasattr(vm_raw, '__dict__'):
                        vm_raw = vars(vm_raw)
                    if isinstance(vm_raw, dict):
                        media_raw = vm_raw.get('media', {})
                        if hasattr(media_raw, '__dict__'):
                            media_raw = vars(media_raw)
                        if isinstance(media_raw, dict):
                            audio_raw = media_raw.get('audio', {})
                            if hasattr(audio_raw, '__dict__'):
                                audio_raw = vars(audio_raw)
                            if isinstance(audio_raw, dict):
                                audio_url = audio_raw.get('audio_src', None)
                            # video_versions fallback
                            if not audio_url:
                                vv = media_raw.get('video_versions', [])
                                if isinstance(vv, list) and vv:
                                    v0 = vv[0]
                                    if hasattr(v0, '__dict__'):
                                        v0 = vars(v0)
                                    if isinstance(v0, dict):
                                        audio_url = v0.get('url', None)
                                    elif hasattr(v0, 'url'):
                                        audio_url = v0.url
                except:
                    pass

            # --- Yöntem 3: voice_media kök seviyede doğrudan audio/video_versions ---
            if not audio_url and vm:
                try:
                    vm_dict = vars(vm) if hasattr(vm, '__dict__') else {}
                    # Doğrudan vm.audio (media katmanı olmadan)
                    audio_direct = vm_dict.get('audio', {})
                    if hasattr(audio_direct, '__dict__'):
                        audio_direct = vars(audio_direct)
                    if isinstance(audio_direct, dict) and audio_direct.get('audio_src'):
                        audio_url = audio_direct['audio_src']
                    # Doğrudan vm.video_versions
                    if not audio_url:
                        vv = vm_dict.get('video_versions', [])
                        if isinstance(vv, list) and vv:
                            v0 = vv[0]
                            if hasattr(v0, '__dict__'):
                                v0 = vars(v0)
                            if isinstance(v0, dict):
                                audio_url = v0.get('url', None)
                            elif hasattr(v0, 'url'):
                                audio_url = v0.url
                except:
                    pass

            # --- Debug log ---
            if not audio_url:
                try:
                    raw_debug = vars(msg) if hasattr(msg, '__dict__') else {}
                    vm_debug = raw_debug.get('voice_media', None)
                    if vm_debug and hasattr(vm_debug, '__dict__'):
                        vm_debug = vars(vm_debug)
                    print(f"\n  🔍 Ses mesajı #{idx} debug — voice_media: {str(vm_debug)[:300]}")
                except:
                    print(f"\n  🔍 Ses mesajı #{idx} debug — voice_media okunamadı")

            if audio_url:
                fname = f"audio_{idx}.mp4"
                fpath = os.path.join(audio_dir, fname)
                if download_file(audio_url, fpath):
                    entry["type"] = "audio"
                    entry["media_files"].append({"type": "audio", "path": f"media/audio/{fname}"})
                    media_count["audio"] += 1
                smart_delay()
            else:
                entry["type"] = "text"
                entry["text"] = "🎤 [Ses mesajı indirilemedi]"

        # ---- CLIP (Reel — Media nesnesi) ----
        elif item_type == 'clip':
            clip_obj = getattr(msg, 'clip', None)
            media_pk = None
            clip_link = None

            if clip_obj:
                media_pk = getattr(clip_obj, 'pk', None)
                code = getattr(clip_obj, 'code', None)
                if code:
                    clip_link = f"https://www.instagram.com/reel/{code}/"

            # ÖNCELİK 1: Clip objesindeki video_url ile doğrudan indir (API çağrısı yok)
            dl_results = []
            if clip_obj:
                print(f"\n    🎬 Clip/Reel objesinden doğrudan indiriliyor...")
                dl_results = try_download_from_obj(clip_obj, idx, photos_dir, videos_dir, prefix="clip")

            # ÖNCELİK 2: Başarısız olduysa media_info ile dene (fallback)
            if not dl_results and media_pk:
                print(f"\n    🎬 Clip/Reel media_info ile deneniyor (pk={media_pk})...")
                dl_results = download_media_by_pk(cl, media_pk, idx, photos_dir, videos_dir)

            if dl_results:
                entry["type"] = dl_results[0]["type"]
                for dr in dl_results:
                    entry["media_files"].append(dr)
                    if dr["type"] == "video":
                        media_count["video"] += 1
                    else:
                        media_count["photo"] += 1
            else:
                entry["type"] = "link"

            entry["link"] = clip_link
            entry["text"] = msg.text or "🎬 Reel paylaşımı"

        # ---- REEL SHARE (dict) ----
        elif item_type == 'reel_share':
            reel = getattr(msg, 'reel_share', None)
            reel_text = ""
            media_pk = None
            reel_link = None
            reel_media_obj = None

            if reel and isinstance(reel, dict):
                reel_text = reel.get('text', '')
                reel_media_obj = reel.get('media', {})
                if isinstance(reel_media_obj, dict):
                    media_pk = reel_media_obj.get('pk', None)
                    code = reel_media_obj.get('code', None)
                    if code:
                        reel_link = f"https://www.instagram.com/reel/{code}/"
            elif reel:
                reel_text = getattr(reel, 'text', '') or ''
                reel_media_obj = getattr(reel, 'media', None)
                if reel_media_obj:
                    media_pk = getattr(reel_media_obj, 'pk', None)
                    code = getattr(reel_media_obj, 'code', None)
                    if code:
                        reel_link = f"https://www.instagram.com/reel/{code}/"

            # ÖNCELİK 1: Reel objesindeki video_url ile doğrudan indir
            dl_results = []
            if reel_media_obj:
                print(f"\n    🎬 Reel objesinden doğrudan indiriliyor...")
                dl_results = try_download_from_obj(reel_media_obj, idx, photos_dir, videos_dir, prefix="reel")

            # ÖNCELİK 2: Başarısız olduysa media_info ile dene
            if not dl_results and media_pk:
                print(f"\n    🎬 Reel media_info ile deneniyor (pk={media_pk})...")
                dl_results = download_media_by_pk(cl, media_pk, idx, photos_dir, videos_dir)

            if dl_results:
                entry["type"] = dl_results[0]["type"]
                for dr in dl_results:
                    entry["media_files"].append(dr)
                    if dr["type"] == "video":
                        media_count["video"] += 1
                    else:
                        media_count["photo"] += 1
            else:
                entry["type"] = "link"

            entry["link"] = reel_link
            entry["text"] = reel_text or msg.text or "🎬 Reel paylaşımı"

        # ---- MEDIA SHARE (feed post — foto/video/albüm) ----
        elif item_type == 'media_share':
            ms = getattr(msg, 'media_share', None)
            media_pk = None
            post_link = None

            if ms:
                media_pk = getattr(ms, 'pk', None)
                code = getattr(ms, 'code', None)
                if code:
                    post_link = f"https://www.instagram.com/p/{code}/"

            # ÖNCELİK 1: Media share objesindeki URL ile doğrudan indir
            dl_results = []
            if ms:
                print(f"\n    📷 Feed post objesinden doğrudan indiriliyor...")
                dl_results = try_download_from_obj(ms, idx, photos_dir, videos_dir, prefix="shared")

            # ÖNCELİK 2: Başarısız olduysa media_info ile dene
            if not dl_results and media_pk:
                print(f"\n    📷 Feed post media_info ile deneniyor (pk={media_pk})...")
                dl_results = download_media_by_pk(cl, media_pk, idx, photos_dir, videos_dir)

            if dl_results:
                entry["type"] = dl_results[0]["type"]
                for dr in dl_results:
                    entry["media_files"].append(dr)
                    if dr["type"] == "video":
                        media_count["video"] += 1
                    else:
                        media_count["photo"] += 1
            else:
                # Son çare: thumbnail_url ile dene
                if ms:
                    turl = getattr(ms, 'thumbnail_url', None)
                    if turl:
                        fname = f"shared_{idx}.jpg"
                        fpath = os.path.join(photos_dir, fname)
                        if download_file(str(turl), fpath):
                            entry["type"] = "photo"
                            entry["media_files"].append({"type": "photo", "path": f"media/photos/{fname}"})
                            media_count["photo"] += 1
                        smart_delay()
                    else:
                        entry["type"] = "link"
                else:
                    entry["type"] = "link"

            entry["link"] = post_link
            entry["text"] = msg.text or "📎 Gönderi paylaşımı"

        # ---- FELIX SHARE (IGTV) ----
        elif item_type == 'felix_share':
            felix = getattr(msg, 'felix_share', None)
            media_pk = None
            felix_link = None
            felix_media_obj = None

            if felix and isinstance(felix, dict):
                felix_media_obj = felix.get('video', {}) or felix.get('media', {})
                if isinstance(felix_media_obj, dict):
                    media_pk = felix_media_obj.get('pk', None)
                    code = felix_media_obj.get('code', None)
                    if code:
                        felix_link = f"https://www.instagram.com/tv/{code}/"
            elif felix:
                felix_media_obj = getattr(felix, 'video', None) or getattr(felix, 'media', None)
                if felix_media_obj:
                    media_pk = getattr(felix_media_obj, 'pk', None)
                    code = getattr(felix_media_obj, 'code', None)
                    if code:
                        felix_link = f"https://www.instagram.com/tv/{code}/"

            # ÖNCELİK 1: Felix objesindeki URL ile doğrudan indir
            dl_results = []
            if felix_media_obj:
                print(f"\n    📺 IGTV objesinden doğrudan indiriliyor...")
                dl_results = try_download_from_obj(felix_media_obj, idx, photos_dir, videos_dir, prefix="igtv")

            # ÖNCELİK 2: Başarısız olduysa media_info ile dene
            if not dl_results and media_pk:
                print(f"\n    📺 IGTV media_info ile deneniyor (pk={media_pk})...")
                dl_results = download_media_by_pk(cl, media_pk, idx, photos_dir, videos_dir)

            if dl_results:
                entry["type"] = dl_results[0]["type"]
                for dr in dl_results:
                    entry["media_files"].append(dr)
                    if dr["type"] == "video":
                        media_count["video"] += 1
                    else:
                        media_count["photo"] += 1
            else:
                entry["type"] = "link"

            entry["link"] = felix_link
            entry["text"] = msg.text or "📺 IGTV paylaşımı"

        # ---- STORY SHARE ----
        elif item_type == 'story_share':
            story = getattr(msg, 'story_share', None)
            story_text = ""
            media_pk = None

            if story and isinstance(story, dict):
                story_text = story.get('title', '') or story.get('text', '') or story.get('message', '')
                story_media = story.get('media', {})
                if isinstance(story_media, dict):
                    media_pk = story_media.get('pk', None)
                    if not media_pk:
                        vvs = story_media.get('video_versions', [])
                        if vvs and isinstance(vvs, list) and len(vvs) > 0:
                            vurl = vvs[0].get('url', '') if isinstance(vvs[0], dict) else str(vvs[0])
                            if vurl:
                                fname = f"story_{idx}.mp4"
                                fpath = os.path.join(videos_dir, fname)
                                if download_file(vurl, fpath):
                                    entry["type"] = "video"
                                    entry["media_files"].append({"type": "video", "path": f"media/videos/{fname}"})
                                    media_count["video"] += 1
                                smart_delay()
                        else:
                            ivs = story_media.get('image_versions2', {})
                            candidates = ivs.get('candidates', []) if isinstance(ivs, dict) else []
                            if candidates:
                                purl = candidates[0].get('url', '') if isinstance(candidates[0], dict) else ''
                                if purl:
                                    fname = f"story_{idx}.jpg"
                                    fpath = os.path.join(photos_dir, fname)
                                    if download_file(purl, fpath):
                                        entry["type"] = "photo"
                                        entry["media_files"].append({"type": "photo", "path": f"media/photos/{fname}"})
                                        media_count["photo"] += 1
                                    smart_delay()
            elif story:
                story_text = getattr(story, 'title', '') or getattr(story, 'text', '') or ''
                story_media = getattr(story, 'media', None)
                if story_media:
                    media_pk = getattr(story_media, 'pk', None)

            if media_pk and not entry["media_files"]:
                print(f"\n    📖 Story indiriliyor (pk={media_pk})...")
                dl_results = download_media_by_pk(cl, media_pk, idx, photos_dir, videos_dir)
                if dl_results:
                    entry["type"] = dl_results[0]["type"]
                    for dr in dl_results:
                        entry["media_files"].append(dr)
                        if dr["type"] == "video":
                            media_count["video"] += 1
                        else:
                            media_count["photo"] += 1

            if not entry["media_files"]:
                entry["type"] = "text"
            entry["text"] = story_text or msg.text or "📖 Story paylaşımı"

        # ---- ANIMATED MEDIA (GIF) ----
        elif item_type == 'animated_media':
            anim = getattr(msg, 'animated_media', None)
            gif_url = None
            if anim:
                images = getattr(anim, 'images', None)
                if images:
                    fixed = getattr(images, 'fixed_height', None) or getattr(images, 'original', None)
                    if fixed:
                        gif_url = getattr(fixed, 'url', None)

            if not gif_url:
                try:
                    raw = vars(msg) if hasattr(msg, '__dict__') else {}
                    am = raw.get('animated_media', {})
                    if isinstance(am, dict):
                        imgs = am.get('images', {})
                        if isinstance(imgs, dict):
                            fh = imgs.get('fixed_height', {})
                            if isinstance(fh, dict):
                                gif_url = fh.get('url')
                except:
                    pass

            if gif_url:
                ext = ".gif" if ".gif" in gif_url else ".webp"
                fname = f"gif_{idx}{ext}"
                fpath = os.path.join(photos_dir, fname)
                if download_file(gif_url, fpath):
                    entry["type"] = "gif"
                    entry["media_files"].append({"type": "gif", "path": f"media/photos/{fname}"})
                    media_count["photo"] += 1
                smart_delay()
            else:
                entry["type"] = "text"
                entry["text"] = "🎞️ [GIF]"

        # ---- LINK ----
        elif item_type == 'link':
            link_obj = getattr(msg, 'link', None)
            entry["type"] = "link"
            if link_obj:
                url = getattr(link_obj, 'text', None) or getattr(link_obj, 'url', None)
                entry["link"] = str(url) if url else None
                title = getattr(link_obj, 'link_title', None) or getattr(link_obj, 'title', None)
                entry["text"] = title or msg.text or str(url) or "🔗 Link"
                media_count["link"] += 1
            else:
                entry["text"] = msg.text or "🔗 Link"
                urls = re.findall(r'https?://\S+', entry["text"])
                if urls:
                    entry["link"] = urls[0]
                    media_count["link"] += 1

        # ---- ACTION LOG ----
        elif item_type == 'action_log':
            entry["type"] = "system"
            entry["is_system"] = True
            al = getattr(msg, 'action_log', None)
            if al and hasattr(al, 'description'):
                entry["text"] = al.description or "ℹ️ Sistem mesajı"
            else:
                entry["text"] = msg.text or "ℹ️ Sistem mesajı"

        # ---- XMA MEDIA SHARE ----
        elif item_type in ('xma_media_share', 'xma_share'):
            entry["type"] = "text"
            entry["text"] = msg.text or "📎 Medya paylaşımı"
            xma = getattr(msg, 'xma_share', None) or getattr(msg, 'xma_media_share', None)
            if xma:
                preview = getattr(xma, 'preview_url', None)
                if preview:
                    fname = f"xma_{idx}.jpg"
                    fpath = os.path.join(photos_dir, fname)
                    if download_file(str(preview), fpath):
                        entry["type"] = "photo"
                        entry["media_files"].append({"type": "photo", "path": f"media/photos/{fname}"})
                        media_count["photo"] += 1
                    smart_delay()

        # ---- PLACEHOLDER ----
        elif item_type == 'placeholder':
            entry["type"] = "text"
            entry["text"] = "⚠️ [İçerik kullanılamıyor]"

        # ---- BİLİNMEYEN TÜR ----
        else:
            entry["type"] = "text"
            entry["text"] = msg.text or f"[{item_type}]"

        # Text fallback
        if not entry["text"] and not entry["media_files"] and not entry["link"]:
            entry["text"] = f"[{item_type}]"

        processed.append(entry)

    print(f"\n\n✅ İşlem tamamlandı!")
    print(f"   📷 Fotoğraf: {media_count['photo']}")
    print(f"   🎬 Video: {media_count['video']}")
    print(f"   🎤 Ses: {media_count['audio']}")
    print(f"   🔗 Link: {media_count['link']}")

    return processed, user_map, media_count

# ============================================================
# HTML OLUŞTUR
# ============================================================

def generate_html(processed, user_map, thread, export_dir, media_count):
    thread_name = thread.thread_title or "Grup Sohbeti"
    user_count = len(thread.users) + 1
    total_msgs = len(processed)

    user_colors = {}
    for pk, uname in user_map.items():
        user_colors[uname] = get_color_for_user(uname)

    html = f'''<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{thread_name} — Instagram Sohbet</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#000;--msg-me:#3797F0;--msg-other:#262626;--text:#FFF;--text-muted:#8E8E8E;--border:#363636;--system-bg:#1A1A1A;--search-bg:#262626}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.4;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
.header{{background:var(--bg);border-bottom:1px solid var(--border);padding:12px 16px;display:flex;align-items:center;gap:12px;flex-shrink:0;z-index:100}}
.header-avatar{{width:44px;height:44px;border-radius:50%;background:#363636;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}}
.header-info h1{{font-size:16px;font-weight:600}}
.header-info span{{font-size:12px;color:var(--text-muted)}}
.toolbar{{background:var(--bg);border-bottom:1px solid var(--border);padding:8px 16px;display:flex;gap:8px;align-items:center;flex-shrink:0}}
.search-box{{flex:1;background:var(--search-bg);border:none;border-radius:8px;padding:8px 12px;color:var(--text);font-size:14px;outline:none}}
.search-box::placeholder{{color:var(--text-muted)}}
.search-box:focus{{box-shadow:0 0 0 1px var(--msg-me)}}
.toolbar-btn{{background:var(--search-bg);border:none;border-radius:8px;padding:8px 12px;color:var(--text);cursor:pointer;font-size:13px;white-space:nowrap}}
.toolbar-btn:hover{{background:#363636}}
.search-nav{{display:none;align-items:center;gap:4px;color:var(--text-muted);font-size:12px}}
.search-nav.active{{display:flex}}
.search-nav button{{background:none;border:none;color:var(--text);cursor:pointer;font-size:16px;padding:2px 6px}}
.chat-container{{flex:1;overflow-y:auto;padding:8px 16px 16px;scroll-behavior:smooth}}
.date-sep{{text-align:center;margin:16px 0 8px}}
.date-sep span{{background:var(--system-bg);color:var(--text-muted);font-size:12px;padding:4px 12px;border-radius:12px}}
.msg-system{{text-align:center;margin:8px 0}}
.msg-system span{{background:var(--system-bg);color:var(--text-muted);font-size:12px;padding:4px 12px;border-radius:12px;display:inline-block}}
.msg-row{{display:flex;margin:2px 0;align-items:flex-end}}
.msg-row.me{{justify-content:flex-end}}
.msg-row.other{{justify-content:flex-start}}
.msg-avatar{{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0;margin-right:8px;margin-bottom:2px}}
.msg-row.me .msg-avatar{{display:none}}
.avatar-hidden{{visibility:hidden}}
.msg-bubble{{max-width:65%;padding:8px 12px;border-radius:18px;word-wrap:break-word;overflow-wrap:break-word;position:relative}}
.msg-row.me .msg-bubble{{background:var(--msg-me);border-bottom-right-radius:4px}}
.msg-row.other .msg-bubble{{background:var(--msg-other);border-bottom-left-radius:4px}}
.msg-username{{font-size:12px;font-weight:600;margin-bottom:2px;opacity:.9}}
.msg-text{{font-size:14px;line-height:1.4;white-space:pre-wrap}}
.msg-text a{{color:#E0F0FF;text-decoration:underline}}
.msg-row.other .msg-text a{{color:#90CAF9}}
.msg-time{{font-size:10px;color:rgba(255,255,255,.5);margin-top:2px;text-align:right}}
.msg-media img{{max-width:100%;max-height:300px;border-radius:12px;cursor:pointer;display:block;margin:4px 0}}
.msg-media video{{max-width:100%;max-height:300px;border-radius:12px;display:block;margin:4px 0}}
.msg-media audio{{width:100%;min-width:200px;margin:4px 0;height:36px}}
.msg-link-btn{{display:inline-block;margin-top:4px;padding:4px 10px;background:rgba(255,255,255,.15);border-radius:6px;color:#90CAF9;text-decoration:none;font-size:12px}}
.msg-link-btn:hover{{background:rgba(255,255,255,.25)}}
.lightbox{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.95);z-index:1000;align-items:center;justify-content:center;cursor:pointer}}
.lightbox.active{{display:flex}}
.lightbox img{{max-width:95%;max-height:95%;object-fit:contain}}
.lightbox-close{{position:absolute;top:16px;right:20px;color:#fff;font-size:32px;cursor:pointer;z-index:1001}}
.stats-bar{{background:var(--bg);border-top:1px solid var(--border);padding:8px 16px;display:flex;justify-content:center;gap:20px;font-size:12px;color:var(--text-muted);flex-shrink:0}}
.stats-bar span{{display:flex;align-items:center;gap:4px}}
.search-highlight{{background:#FFA000;color:#000;border-radius:2px;padding:0 1px}}
.search-highlight.current{{background:#FF6F00;outline:2px solid #FFCA28}}
.scroll-btn{{position:fixed;right:20px;width:40px;height:40px;border-radius:50%;background:var(--msg-me);border:none;color:#fff;font-size:18px;cursor:pointer;z-index:50;box-shadow:0 2px 8px rgba(0,0,0,.5);display:none}}
.scroll-btn:hover{{opacity:.8}}
#scrollTop{{bottom:100px}}
#scrollBottom{{bottom:52px}}
.date-modal{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);z-index:500;align-items:center;justify-content:center}}
.date-modal.active{{display:flex}}
.date-modal-content{{background:#262626;border-radius:16px;padding:24px;text-align:center}}
.date-modal-content input{{background:#363636;border:1px solid #555;border-radius:8px;color:#fff;padding:10px;font-size:16px;margin:12px 0}}
.date-modal-content button{{background:var(--msg-me);border:none;border-radius:8px;color:#fff;padding:10px 24px;font-size:14px;cursor:pointer;margin:4px}}
.date-modal-content button.cancel{{background:#555}}
@media(max-width:600px){{.msg-bubble{{max-width:80%}}.header{{padding:8px 12px}}.toolbar{{padding:6px 12px;flex-wrap:wrap}}}}
</style>
</head>
<body>
<div class="header">
    <div class="header-avatar">👥</div>
    <div class="header-info">
        <h1>{thread_name}</h1>
        <span>{user_count} kişi · {total_msgs} mesaj</span>
    </div>
</div>
<div class="toolbar">
    <input type="text" class="search-box" id="searchInput" placeholder="🔍 Mesajlarda ara..." />
    <div class="search-nav" id="searchNav">
        <span id="searchCount">0/0</span>
        <button onclick="searchPrev()">▲</button>
        <button onclick="searchNext()">▼</button>
        <button onclick="clearSearch()">✕</button>
    </div>
    <button class="toolbar-btn" onclick="openDatePicker()">📅 Tarihe Git</button>
</div>
<div class="chat-container" id="chatContainer">
'''

    last_date = ""
    last_user = ""

    for i, m in enumerate(processed):
        if m["date"] and m["date"] != last_date:
            last_date = m["date"]
            html += f'<div class="date-sep" data-date="{m["date"]}"><span>{m["date"]}</span></div>\n'

        if m["is_system"]:
            text_escaped = escape_html(m["text"])
            html += f'<div class="msg-system"><span>{text_escaped}</span></div>\n'
            last_user = ""
            continue

        side = "me" if m["is_me"] else "other"
        username = m["user"]
        color = user_colors.get(username, "#888")
        show_username = (not m["is_me"]) and (username != last_user)
        show_avatar = show_username
        initial = username[0].upper() if username else "?"
        last_user = username

        html += f'<div class="msg-row {side}" data-idx="{i}" data-user="{username}" data-date="{m["date"]}">\n'

        if not m["is_me"]:
            avatar_class = "" if show_avatar else "avatar-hidden"
            html += f'  <div class="msg-avatar {avatar_class}" style="background:{color}">{initial}</div>\n'

        html += f'  <div class="msg-bubble">\n'

        if show_username:
            html += f'    <div class="msg-username" style="color:{color}">{escape_html(username)}</div>\n'

        media_files = m.get("media_files", [])
        for mf in media_files:
            mf_type = mf.get("type", "")
            mf_path = mf.get("path", "")
            if mf_type in ("photo", "gif"):
                html += f'    <div class="msg-media"><img src="{mf_path}" alt="foto" onclick="openLightbox(this.src)" loading="lazy"></div>\n'
            elif mf_type == "video":
                html += f'    <div class="msg-media"><video controls preload="metadata"><source src="{mf_path}" type="video/mp4">Video oynatılamıyor.</video></div>\n'
            elif mf_type == "audio":
                html += f'    <div class="msg-media"><audio controls preload="metadata"><source src="{mf_path}" type="audio/mp4">Ses çalınamıyor.</audio></div>\n'

        text = m.get("text", "")
        if text:
            text_html = escape_html(text)
            text_html = re.sub(r'(https?://\S+)', r'<a href="\1" target="_blank" rel="noopener">\1</a>', text_html)
            html += f'    <div class="msg-text">{text_html}</div>\n'

        if m.get("link"):
            html += f'    <a class="msg-link-btn" href="{m["link"]}" target="_blank" rel="noopener">🔗 Instagram\'da aç</a>\n'

        if m["timestamp"]:
            time_only = m["timestamp"].split(" ")[-1] if " " in m["timestamp"] else m["timestamp"]
            html += f'    <div class="msg-time">{time_only}</div>\n'

        html += '  </div>\n</div>\n'

    html += f'''
</div>
<button class="scroll-btn" id="scrollTop" onclick="scrollToTop()">↑</button>
<button class="scroll-btn" id="scrollBottom" onclick="scrollToBottom()">↓</button>
<div class="stats-bar">
    <span>💬 {total_msgs} mesaj</span>
    <span>📷 {media_count["photo"]} foto</span>
    <span>🎬 {media_count["video"]} video</span>
    <span>🎤 {media_count["audio"]} ses</span>
    <span>🔗 {media_count["link"]} link</span>
</div>
<div class="lightbox" id="lightbox" onclick="closeLightbox()">
    <span class="lightbox-close">&times;</span>
    <img id="lightboxImg" src="" alt="">
</div>
<div class="date-modal" id="dateModal">
    <div class="date-modal-content">
        <div style="font-size:16px;margin-bottom:8px;">📅 Tarihe Git</div>
        <input type="date" id="dateInput" />
        <div>
            <button onclick="goToDate()">Git</button>
            <button class="cancel" onclick="closeDatePicker()">İptal</button>
        </div>
    </div>
</div>
<script>
const searchInput=document.getElementById('searchInput'),searchNav=document.getElementById('searchNav'),searchCount=document.getElementById('searchCount'),chatContainer=document.getElementById('chatContainer');
let searchResults=[],searchIdx=-1;
searchInput.addEventListener('input',debounce(doSearch,300));
searchInput.addEventListener('keydown',e=>{{if(e.key==='Enter'){{e.preventDefault();e.shiftKey?searchPrev():searchNext()}}if(e.key==='Escape')clearSearch()}});
function debounce(fn,ms){{let t;return(...a)=>{{clearTimeout(t);t=setTimeout(()=>fn(...a),ms)}}}}
function doSearch(){{clearHighlights();const q=searchInput.value.trim().toLowerCase();if(!q){{searchNav.classList.remove('active');return}}searchResults=[];const msgs=chatContainer.querySelectorAll('.msg-text');msgs.forEach(el=>{{const text=el.textContent.toLowerCase();if(text.includes(q)){{const regex=new RegExp('('+escapeRegex(q)+')','gi');const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);const textNodes=[];while(walker.nextNode())textNodes.push(walker.currentNode);textNodes.forEach(node=>{{if(node.textContent.toLowerCase().includes(q)){{const span=document.createElement('span');span.innerHTML=node.textContent.replace(regex,'<mark class="search-highlight">$1</mark>');node.parentNode.replaceChild(span,node)}}}});searchResults.push(el.closest('.msg-row')||el.closest('.msg-system'))}}}});if(searchResults.length>0){{searchIdx=0;searchNav.classList.add('active');updateSearchNav();scrollToResult()}}else{{searchNav.classList.add('active');searchCount.textContent='0/0'}}}}
function clearHighlights(){{document.querySelectorAll('.search-highlight').forEach(el=>{{const parent=el.parentNode;parent.replaceChild(document.createTextNode(el.textContent),el);parent.normalize()}});document.querySelectorAll('.msg-text span:not([class])').forEach(sp=>{{if(!sp.className&&sp.children.length===0){{sp.parentNode.replaceChild(document.createTextNode(sp.textContent),sp);if(sp.parentNode)sp.parentNode.normalize()}}}})}}
function searchNext(){{if(!searchResults.length)return;searchIdx=(searchIdx+1)%searchResults.length;updateSearchNav();scrollToResult()}}
function searchPrev(){{if(!searchResults.length)return;searchIdx=(searchIdx-1+searchResults.length)%searchResults.length;updateSearchNav();scrollToResult()}}
function clearSearch(){{searchInput.value='';clearHighlights();searchResults=[];searchIdx=-1;searchNav.classList.remove('active')}}
function updateSearchNav(){{searchCount.textContent=(searchIdx+1)+'/'+searchResults.length;document.querySelectorAll('.search-highlight.current').forEach(el=>el.classList.remove('current'));if(searchResults[searchIdx]){{const marks=searchResults[searchIdx].querySelectorAll('.search-highlight');if(marks[0])marks[0].classList.add('current')}}}}
function scrollToResult(){{if(searchResults[searchIdx])searchResults[searchIdx].scrollIntoView({{behavior:'smooth',block:'center'}})}}
function escapeRegex(s){{return s.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')}}
function openDatePicker(){{document.getElementById('dateModal').classList.add('active')}}
function closeDatePicker(){{document.getElementById('dateModal').classList.remove('active')}}
function goToDate(){{const input=document.getElementById('dateInput').value;if(!input)return;const parts=input.split('-');const target=parts[2]+'.'+parts[1]+'.'+parts[0];const sep=document.querySelector('.date-sep[data-date="'+target+'"]');if(sep){{sep.scrollIntoView({{behavior:'smooth',block:'start'}});closeDatePicker()}}else{{const seps=document.querySelectorAll('.date-sep');let closest=null,minDiff=Infinity;const targetDate=new Date(input);seps.forEach(s=>{{const d=s.getAttribute('data-date');const p=d.split('.');const dt=new Date(p[2]+'-'+p[1]+'-'+p[0]);const diff=Math.abs(dt-targetDate);if(diff<minDiff){{minDiff=diff;closest=s}}}});if(closest)closest.scrollIntoView({{behavior:'smooth',block:'start'}});else alert('Bu tarihte mesaj bulunamadı.');closeDatePicker()}}}}
function openLightbox(src){{document.getElementById('lightboxImg').src=src;document.getElementById('lightbox').classList.add('active')}}
function closeLightbox(){{document.getElementById('lightbox').classList.remove('active');document.getElementById('lightboxImg').src=''}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape'){{closeLightbox();closeDatePicker()}}}});
const scrollTopBtn=document.getElementById('scrollTop'),scrollBottomBtn=document.getElementById('scrollBottom');
chatContainer.addEventListener('scroll',()=>{{const st=chatContainer.scrollTop,sh=chatContainer.scrollHeight,ch=chatContainer.clientHeight;scrollTopBtn.style.display=st>300?'block':'none';scrollBottomBtn.style.display=(sh-st-ch>300)?'block':'none'}});
function scrollToTop(){{chatContainer.scrollTo({{top:0,behavior:'smooth'}})}}
function scrollToBottom(){{chatContainer.scrollTo({{top:chatContainer.scrollHeight,behavior:'smooth'}})}}
</script>
</body>
</html>'''

    html_path = os.path.join(export_dir, "index.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return html_path

def escape_html(text):
    if not text:
        return ""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text

# ============================================================
# YARDIMCI: ÖNCEKİ VERİYİ YÜKLE + MEDIA SAYACI
# ============================================================

def load_previous_data(export_dir):
    """Önceki data.json'ı yükle. Yoksa None döner."""
    data_path = os.path.join(export_dir, "data.json")
    if not os.path.exists(data_path):
        return None
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception as e:
        print(f"  ⚠️ data.json okunamadı: {e}")
    return None


def recount_media(processed):
    """Processed listesinden media_count yeniden hesapla."""
    media_count = {"photo": 0, "video": 0, "audio": 0, "link": 0}
    for entry in processed:
        for mf in entry.get("media_files", []):
            mf_type = mf.get("type", "")
            if mf_type in ("photo", "gif"):
                media_count["photo"] += 1
            elif mf_type == "video":
                media_count["video"] += 1
            elif mf_type == "audio":
                media_count["audio"] += 1
        if entry.get("link") and entry.get("type") == "link":
            media_count["link"] += 1
    return media_count


# ============================================================
# ANA AKIŞ
# ============================================================

def main():
    print("=" * 60)
    print("  📱 Instagram Grup Sohbet İndirici + HTML Görüntüleyici")
    print("  📦 v3.0 — Incremental güncelleme destekli")
    print("=" * 60)
    print()

    cl = login()
    thread = select_thread(cl)

    thread_name = safe_filename(thread.thread_title or "grup_sohbet")
    export_dir = os.path.join(os.getcwd(), f"chat_export_{thread_name}")
    os.makedirs(export_dir, exist_ok=True)
    print(f"\n📁 Çıktı klasörü: {export_dir}")

    # ────────────────────────────────────────────
    # ÖNCEKİ VERİ KONTROLÜ
    # ────────────────────────────────────────────
    old_data = load_previous_data(export_dir)
    incremental = False

    if old_data:
        old_count = len(old_data)
        # En eski ve en yeni tarihi bul
        dates = [d.get("date", "") for d in old_data if d.get("date")]
        date_range = ""
        if dates:
            date_range = f" ({dates[0]} — {dates[-1]})"
        print(f"\n📂 Önceki veri bulundu: {old_count} mesaj{date_range}")
        print(f"   1) 🔄 Sadece yeni mesajları çek (hızlı)")
        print(f"   2) 📥 Sıfırdan tümünü çek (yavaş)")

        while True:
            choice = input("\n   Seçim [1/2]: ").strip()
            if choice in ("1", "2"):
                break
            print("   ❌ 1 veya 2 gir.")

        incremental = (choice == "1")

    if incremental and old_data:
        # ────────────────────────────────────────────
        # INCREMENTAL MOD
        # ────────────────────────────────────────────
        print("\n🔄 Incremental mod: sadece yeni mesajlar çekiliyor...")

        # Bilinen mesaj ID'lerini topla
        known_ids = set()
        for entry in old_data:
            entry_id = entry.get("id", "")
            if entry_id:
                known_ids.add(str(entry_id))

        # Sadece yeni mesajları çek (bilinen ID'ye rastlayınca durur)
        new_messages = fetch_all_messages(cl, thread, stop_at_ids=known_ids)

        if not new_messages:
            print("\n✅ Yeni mesaj yok, her şey güncel!")
            # HTML'i yine de yeniden oluştur (kullanıcı istemiş olabilir)
            user_map = {}
            my_pk = str(cl.user_id)
            user_map[my_pk] = cl.username or "Ben"
            for u in thread.users:
                user_map[str(u.pk)] = u.username
            media_count = recount_media(old_data)
            html_path = generate_html(old_data, user_map, thread, export_dir, media_count)
            print(f"\n🌐 HTML oluşturuldu: {html_path}")
        else:
            print(f"\n🆕 {len(new_messages)} yeni mesaj bulundu, işleniyor...")

            # Yeni mesajları işle + medyaları indir
            new_processed, user_map, new_media_count = process_messages(cl, new_messages, thread, export_dir)

            # ────────────────────────────────────────────
            # MERGE: eski + yeni, ID bazlı tekrar önleme
            # ────────────────────────────────────────────
            merged = list(old_data)  # eski verinin kopyası
            existing_ids = {str(entry.get("id", "")) for entry in merged}

            added = 0
            for entry in new_processed:
                entry_id = str(entry.get("id", ""))
                if entry_id and entry_id not in existing_ids:
                    merged.append(entry)
                    existing_ids.add(entry_id)
                    added += 1

            # Tarihe göre sırala
            def sort_key(e):
                ts = e.get("timestamp", "")
                if ts:
                    try:
                        parts = ts.split(" ")
                        if len(parts) == 2:
                            d, t = parts
                            dd, mm, yyyy = d.split(".")
                            return f"{yyyy}{mm}{dd}{t}"
                    except:
                        pass
                return ""
            merged.sort(key=sort_key)

            print(f"\n📊 Merge sonucu: {len(old_data)} eski + {added} yeni = {len(merged)} toplam")

            # Kaydet
            data_path = os.path.join(export_dir, "data.json")
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            print(f"💾 Güncel veri kaydedildi: data.json")

            # HTML oluştur (tüm veriden)
            media_count = recount_media(merged)
            html_path = generate_html(merged, user_map, thread, export_dir, media_count)
            print(f"\n🌐 HTML oluşturuldu: {html_path}")

    else:
        # ────────────────────────────────────────────
        # TAM MOD (sıfırdan)
        # ────────────────────────────────────────────
        messages = fetch_all_messages(cl, thread)

        if not messages:
            print("❌ Mesaj bulunamadı.")
            sys.exit(1)

        processed, user_map, media_count = process_messages(cl, messages, thread, export_dir)

        data_path = os.path.join(export_dir, "data.json")
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Ham veri kaydedildi: data.json")

        html_path = generate_html(processed, user_map, thread, export_dir, media_count)
        print(f"\n🌐 HTML oluşturuldu: {html_path}")

    print(f"\n{'='*60}")
    print(f"  ✅ TAMAMLANDI!")
    print(f"  📁 Klasör: {export_dir}")
    print(f"  🌐 Aç: index.html")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()