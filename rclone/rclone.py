#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dual Pane RClone File Manager v4.0 - Windows VSCode
- tkinter GUI (Colab bağımlılığı yok)
- JSON ile durum kaydetme: program kapatılınca kaldığı yerden devam
- İnternet kesilince otomatik yeniden deneme
- Threading ile donmayan arayüz
"""

import os, subprocess, json, time, threading, re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime

# Windows'ta subprocess encoding'i UTF-8'e zorla
os.environ["PYTHONIOENCODING"] = "utf-8"
_SUBPROC_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

# ─── DURUM DOSYASI ───────────────────────────────────────────────────────────
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rclone_state.json")

def kaydet_durum(durum: dict):
    """Anlık durumu JSON'a yaz (program kapansa da korunur)."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(durum, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[UYARI] Durum kaydedilemedi: {e}")

def yukle_durum() -> dict:
    """Önceki oturumun durumunu yükle."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}

def temizle_durum():
    """İşlem bitince durum dosyasını sıfırla."""
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except:
        pass


# ─── ANA SINIF ────────────────────────────────────────────────────────────────
class RCloneManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🚀 Dual Pane RClone Manager v4.0")
        self.root.geometry("1000x700")
        self.root.configure(bg="#1e1e2e")

        # Değişkenler
        self.left_remote  = tk.StringVar()
        self.right_remote = tk.StringVar()
        self.left_path    = tk.StringVar(value="/")
        self.right_path   = tk.StringVar(value="/")
        self.test_mode       = tk.BooleanVar(value=False)
        self.ignore_existing = tk.BooleanVar(value=True)
        self.ignore_errors   = tk.BooleanVar(value=True)

        self.left_files  = []
        self.right_files = []
        self.transfer_running = False
        self.current_process  = None
        self.stop_requested   = False

        # Önceki oturumu yükle
        self._onceki_durumu_yukle()

        self._arayuz_olustur()
        self._rclone_kontrol()
        self.remote_listele()

    # ── Önceki Oturum ────────────────────────────────────────────────────────
    def _onceki_durumu_yukle(self):
        self.onceki_durum = yukle_durum()
        self.bekleyen_dosyalar = self.onceki_durum.get("bekleyen_dosyalar", [])
        self.onceki_islem      = self.onceki_durum.get("islem", None)
        self.onceki_kaynak     = self.onceki_durum.get("kaynak_remote", "")
        self.onceki_hedef      = self.onceki_durum.get("hedef_remote", "")
        self.onceki_hedef_yol  = self.onceki_durum.get("hedef_yol", "/")

    # ── RClone Kontrol ────────────────────────────────────────────────────────
    def _rclone_kontrol(self):
        try:
            subprocess.run(
                ["rclone", "version"],
                capture_output=True, check=True, timeout=10,
                encoding="utf-8", errors="replace", env=_SUBPROC_ENV
            )
        except FileNotFoundError:
            messagebox.showerror(
                "RClone Bulunamadı",
                "rclone.exe sisteminizde yok!\n\n"
                "1) https://rclone.org/downloads adresinden indirin\n"
                "2) ZIP'i açın, rclone.exe'yi C:\\Windows\\System32'ye kopyalayın\n"
                "3) CMD'de: rclone config  →  bağlantılarınızı ekleyin\n\n"
                "Sonra bu programı yeniden başlatın."
            )
            self.root.destroy()
        except Exception as e:
            self.log(f"⚠️ rclone kontrolünde hata: {e}")

    # ── Arayüz ────────────────────────────────────────────────────────────────
    def _arayuz_olustur(self):
        stil = ttk.Style()
        stil.theme_use("clam")

        # ── Üst Bar ──
        ust = tk.Frame(self.root, bg="#313244", pady=8)
        ust.pack(fill="x")
        tk.Label(ust, text="🚀 Dual Pane RClone Manager v4.0",
                 bg="#313244", fg="#cdd6f4",
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=12)

        # ── Seçenekler ──
        opt_frame = tk.Frame(self.root, bg="#1e1e2e", pady=4)
        opt_frame.pack(fill="x", padx=10)
        for text, var in [("🧪 Test", self.test_mode),
                          ("⏭️ Mevcut Atla", self.ignore_existing),
                          ("🔄 Hatada Devam", self.ignore_errors)]:
            tk.Checkbutton(opt_frame, text=text, variable=var,
                           bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244",
                           activebackground="#1e1e2e", activeforeground="#cdd6f4"
                           ).pack(side="left", padx=8)

        tk.Button(opt_frame, text="🔄 Bağlantıları Yenile",
                  command=self.remote_listele,
                  bg="#45475a", fg="#cdd6f4", relief="flat", padx=8
                  ).pack(side="right", padx=8)

        # ── Remote Seçiciler ──
        remote_frame = tk.Frame(self.root, bg="#1e1e2e")
        remote_frame.pack(fill="x", padx=10, pady=2)

        self.left_remote_cb  = ttk.Combobox(remote_frame, textvariable=self.left_remote,  width=20)
        self.right_remote_cb = ttk.Combobox(remote_frame, textvariable=self.right_remote, width=20)
        self.left_path_entry  = ttk.Entry(remote_frame, textvariable=self.left_path,  width=30)
        self.right_path_entry = ttk.Entry(remote_frame, textvariable=self.right_path, width=30)

        for w, lbl in [(tk.Label(remote_frame, text="📤 Sol:", bg="#1e1e2e", fg="#cdd6f4"), None),
                       (self.left_remote_cb, None),
                       (tk.Label(remote_frame, text="Yol:", bg="#1e1e2e", fg="#89b4fa"), None),
                       (self.left_path_entry, None),
                       (tk.Label(remote_frame, text="   📥 Sağ:", bg="#1e1e2e", fg="#cdd6f4"), None),
                       (self.right_remote_cb, None),
                       (tk.Label(remote_frame, text="Yol:", bg="#1e1e2e", fg="#89b4fa"), None),
                       (self.right_path_entry, None)]:
            w.pack(side="left", padx=3)

        self.left_remote_cb.bind("<<ComboboxSelected>>",  lambda e: self.dosyalari_listele())
        self.right_remote_cb.bind("<<ComboboxSelected>>", lambda e: self.dosyalari_listele())
        self.left_path_entry.bind("<Return>",  lambda e: self.dosyalari_listele())
        self.right_path_entry.bind("<Return>", lambda e: self.dosyalari_listele())

        # ── Dosya Panelleri ──
        panel_frame = tk.Frame(self.root, bg="#1e1e2e")
        panel_frame.pack(fill="both", expand=True, padx=10, pady=4)

        # Sol panel
        sol_cerceve = tk.LabelFrame(panel_frame, text="📤 Sol", bg="#1e1e2e",
                                     fg="#89b4fa", font=("Segoe UI", 9, "bold"))
        sol_cerceve.pack(side="left", fill="both", expand=True, padx=(0,4))
        self.sol_liste = tk.Listbox(sol_cerceve, bg="#313244", fg="#cdd6f4",
                                     selectbackground="#89b4fa", selectforeground="#1e1e2e",
                                     font=("Consolas", 9), activestyle="none")
        sol_scroll = ttk.Scrollbar(sol_cerceve, orient="vertical", command=self.sol_liste.yview)
        self.sol_liste.configure(yscrollcommand=sol_scroll.set)
        sol_scroll.pack(side="right", fill="y")
        self.sol_liste.pack(fill="both", expand=True)
        self.sol_liste.bind("<Double-Button-1>", lambda e: self._klasore_gir("sol"))

        # Sağ panel
        sag_cerceve = tk.LabelFrame(panel_frame, text="📥 Sağ", bg="#1e1e2e",
                                     fg="#a6e3a1", font=("Segoe UI", 9, "bold"))
        sag_cerceve.pack(side="right", fill="both", expand=True, padx=(4,0))
        self.sag_liste = tk.Listbox(sag_cerceve, bg="#313244", fg="#cdd6f4",
                                     selectbackground="#a6e3a1", selectforeground="#1e1e2e",
                                     font=("Consolas", 9), activestyle="none")
        sag_scroll = ttk.Scrollbar(sag_cerceve, orient="vertical", command=self.sag_liste.yview)
        self.sag_liste.configure(yscrollcommand=sag_scroll.set)
        sag_scroll.pack(side="right", fill="y")
        self.sag_liste.pack(fill="both", expand=True)
        self.sag_liste.bind("<Double-Button-1>", lambda e: self._klasore_gir("sag"))

        # ── İşlem Butonları ──
        buton_frame = tk.Frame(self.root, bg="#1e1e2e", pady=4)
        buton_frame.pack(fill="x", padx=10)
        for text, cmd, renk in [
            ("➡️ Kopyala Sol→Sağ", lambda: self.kopyala("lr"), "#89b4fa"),
            ("⬅️ Kopyala Sağ→Sol", lambda: self.kopyala("rl"), "#89b4fa"),
            ("🔄 Sync Sol→Sağ",    lambda: self.sync("lr"),    "#fab387"),
            ("🔄 Sync Sağ→Sol",    lambda: self.sync("rl"),    "#fab387"),
            ("⛔ Durdur",          self.durdur,                "#f38ba8"),
        ]:
            tk.Button(buton_frame, text=text, command=cmd,
                      bg=renk, fg="#1e1e2e", relief="flat",
                      font=("Segoe UI", 9, "bold"), padx=8, pady=4
                      ).pack(side="left", padx=4)

        # ── Progress ──
        progress_frame = tk.Frame(self.root, bg="#1e1e2e")
        progress_frame.pack(fill="x", padx=10)
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate", length=600)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.durum_label = tk.Label(progress_frame, text="Hazır",
                                     bg="#1e1e2e", fg="#a6e3a1",
                                     font=("Segoe UI", 9))
        self.durum_label.pack(side="right", padx=8)

        # ── Log Alanı ──
        self.log_alan = scrolledtext.ScrolledText(
            self.root, height=8, bg="#181825", fg="#cdd6f4",
            font=("Consolas", 8), state="disabled", wrap="word"
        )
        self.log_alan.pack(fill="x", padx=10, pady=(2,6))

        # Önceki oturum uyarısı
        if self.bekleyen_dosyalar:
            self._onceki_oturum_sor()

    # ── Önceki Oturum Sorusu ─────────────────────────────────────────────────
    def _onceki_oturum_sor(self):
        kalan = len(self.bekleyen_dosyalar)
        cevap = messagebox.askyesno(
            "Yarım Kalan İşlem",
            f"Önceki oturumda {kalan} dosya tamamlanamadı.\n\n"
            f"İşlem: {self.onceki_islem}\n"
            f"Kaynak: {self.onceki_kaynak}\n"
            f"Hedef:  {self.onceki_hedef}{self.onceki_hedef_yol}\n\n"
            "Kaldığı yerden devam edilsin mi?"
        )
        if cevap:
            self.log(f"↩️ {kalan} dosyayla kaldığı yerden devam ediliyor...")
            self.root.after(
                1000,
                lambda: self._transfer_baslat(
                    self.bekleyen_dosyalar,
                    self.onceki_kaynak,
                    self.onceki_hedef,
                    self.onceki_hedef_yol,
                    self.onceki_islem or "copy"
                )
            )
        else:
            temizle_durum()
            self.bekleyen_dosyalar = []

    # ── Remote Listele ────────────────────────────────────────────────────────
    def remote_listele(self):
        def _isle():
            try:
                result = subprocess.run(
                    ["rclone", "listremotes"],
                    capture_output=True, text=True, timeout=15,
                    encoding="utf-8", errors="replace", env=_SUBPROC_ENV
                )
                remotes = [r.strip() for r in result.stdout.strip().split("\n") if r.strip()]
                self.root.after(0, lambda: self._remote_guncelle(remotes))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ Remote listelenemedi: {e}"))
        threading.Thread(target=_isle, daemon=True).start()

    def _remote_guncelle(self, remotes):
        self.left_remote_cb["values"]  = remotes
        self.right_remote_cb["values"] = remotes
        self.log(f"✅ {len(remotes)} bağlantı: {', '.join(remotes)}")
        if remotes:
            if not self.left_remote.get():
                self.left_remote.set(remotes[0])
            if not self.right_remote.get() and len(remotes) > 1:
                self.right_remote.set(remotes[1])
        self.dosyalari_listele()

    # ── Dosya Listele ─────────────────────────────────────────────────────────
    def dosyalari_listele(self):
        def _isle():
            sol = self._listele(self.left_remote.get(),  self.left_path.get())
            sag = self._listele(self.right_remote.get(), self.right_path.get())
            self.left_files  = sol
            self.right_files = sag
            self.root.after(0, lambda: self._panelleri_guncelle(sol, sag))
        threading.Thread(target=_isle, daemon=True).start()

    def _listele(self, remote, path):
        dosyalar = []
        if path not in ("/", ""):
            ust = str(Path(path).parent).replace("\\", "/")
            if ust == ".": ust = "/"
            dosyalar.append({"name": "..", "path": ust, "is_dir": True, "size": ""})
        try:
            # Klasörler
            r = subprocess.run(
                ["rclone", "lsd", f"{remote}{path}", "--max-depth", "1"],
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace", env=_SUBPROC_ENV
            )
            if r.returncode == 0:
                for satir in r.stdout.strip().split("\n"):
                    if satir.strip():
                        parcalar = satir.strip().split()
                        if len(parcalar) >= 5:
                            ad = " ".join(parcalar[4:])
                            dosyalar.append({
                                "name": ad,
                                "path": (path.rstrip("/") + "/" + ad),
                                "is_dir": True, "size": ""
                            })
            # Dosyalar
            r = subprocess.run(
                ["rclone", "lsl", f"{remote}{path}", "--max-depth", "1"],
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace", env=_SUBPROC_ENV
            )
            if r.returncode == 0:
                for satir in r.stdout.strip().split("\n"):
                    if satir.strip():
                        parcalar = satir.strip().split()
                        if len(parcalar) >= 5:
                            ad   = " ".join(parcalar[4:])
                            boyut = int(parcalar[0])
                            if   boyut < 1024:      boyut_str = f"{boyut} B"
                            elif boyut < 1024**2:   boyut_str = f"{boyut//1024} KB"
                            elif boyut < 1024**3:   boyut_str = f"{boyut//1024**2} MB"
                            else:                   boyut_str = f"{boyut//1024**3} GB"
                            dosyalar.append({
                                "name": ad,
                                "path": (path.rstrip("/") + "/" + ad),
                                "is_dir": False, "size": boyut_str
                            })
        except:
            pass
        return dosyalar

    def _panelleri_guncelle(self, sol, sag):
        self.sol_liste.delete(0, "end")
        for f in sol:
            ikon = "📁" if f["is_dir"] else "📄"
            boyut = f"  [{f['size']}]" if f["size"] else ""
            self.sol_liste.insert("end", f"{ikon} {f['name']}{boyut}")

        self.sag_liste.delete(0, "end")
        for f in sag:
            ikon = "📁" if f["is_dir"] else "📄"
            boyut = f"  [{f['size']}]" if f["size"] else ""
            self.sag_liste.insert("end", f"{ikon} {f['name']}{boyut}")

    def _klasore_gir(self, taraf):
        if taraf == "sol":
            secim = self.sol_liste.curselection()
            if not secim: return
            dosya = self.left_files[secim[0]]
            if dosya["is_dir"]:
                self.left_path.set(dosya["path"])
                self.dosyalari_listele()
        else:
            secim = self.sag_liste.curselection()
            if not secim: return
            dosya = self.right_files[secim[0]]
            if dosya["is_dir"]:
                self.right_path.set(dosya["path"])
                self.dosyalari_listele()

    # ── Kopyala / Sync ────────────────────────────────────────────────────────
    def kopyala(self, yon):
        if yon == "lr":
            kaynak, hedef = self.left_remote.get(), self.right_remote.get()
            kaynak_yol, hedef_yol = self.left_path.get(), self.right_path.get()
            dosyalar = [f for f in self.left_files if f["name"] != ".."]
        else:
            kaynak, hedef = self.right_remote.get(), self.left_remote.get()
            kaynak_yol, hedef_yol = self.right_path.get(), self.left_path.get()
            dosyalar = [f for f in self.right_files if f["name"] != ".."]

        if not kaynak or not hedef:
            messagebox.showwarning("Uyarı", "Her iki panel de bağlı olmalı!")
            return
        if not dosyalar:
            messagebox.showwarning("Uyarı", "Kopyalanacak dosya yok!")
            return

        # Dosya yollarını kaynak remote ile zenginleştir
        for f in dosyalar:
            f["kaynak_remote"] = kaynak
        self._transfer_baslat(dosyalar, kaynak, hedef, hedef_yol, "copy")

    def sync(self, yon):
        if yon == "lr":
            kaynak, hedef = self.left_remote.get(), self.right_remote.get()
            kaynak_yol, hedef_yol = self.left_path.get(), self.right_path.get()
        else:
            kaynak, hedef = self.right_remote.get(), self.left_remote.get()
            kaynak_yol, hedef_yol = self.right_path.get(), self.left_path.get()

        if not kaynak or not hedef:
            messagebox.showwarning("Uyarı", "Her iki panel de bağlı olmalı!")
            return
        self._sync_baslat(kaynak, hedef, kaynak_yol, hedef_yol)

    def durdur(self):
        self.stop_requested = True
        if self.current_process:
            try:
                self.current_process.terminate()
            except:
                pass
        self.log("⛔ Durdurma isteği gönderildi...")

    # ── Transfer ──────────────────────────────────────────────────────────────
    def _transfer_baslat(self, dosyalar, kaynak, hedef, hedef_yol, islem):
        if self.transfer_running:
            messagebox.showwarning("Uyarı", "Zaten bir işlem devam ediyor!")
            return
        threading.Thread(
            target=self._transfer_thread,
            args=(dosyalar, kaynak, hedef, hedef_yol, islem),
            daemon=True
        ).start()

    def _transfer_thread(self, dosyalar, kaynak, hedef, hedef_yol, islem):
        self.transfer_running = True
        self.stop_requested   = False
        toplam = len(dosyalar)
        basari = hata = 0
        op_adi = "TEST" if self.test_mode.get() else islem.upper()

        self.root.after(0, lambda: self.log(f"🚀 {op_adi} başlıyor: {toplam} öğe"))

        for i, dosya in enumerate(dosyalar[:], 1):
            if self.stop_requested:
                break

            # ─ Durum kaydet (kaldığı yerden devam için) ─
            kalan = dosyalar[i-1:]
            kaydet_durum({
                "islem": islem,
                "kaynak_remote": kaynak,
                "hedef_remote": hedef,
                "hedef_yol": hedef_yol,
                "bekleyen_dosyalar": kalan,
                "zaman": datetime.now().isoformat()
            })

            ad = dosya["name"]
            dosya_kaynak = f"{kaynak}{dosya['path']}"
            dosya_hedef  = f"{hedef}{hedef_yol.rstrip('/')}/{ad}"

            progress_val = int((i / toplam) * 100)
            self.root.after(0, lambda p=progress_val, a=ad, idx=i:
                self._ui_guncelle(p, f"({idx}/{toplam}) 📁 {a}"))

            cmd = ["rclone", "copyfile" if not dosya["is_dir"] else "copy",
                   dosya_kaynak, dosya_hedef, "--verbose"]
            if self.ignore_existing.get(): cmd.append("--ignore-existing")
            if self.ignore_errors.get():   cmd.append("--ignore-errors")
            if self.test_mode.get():       cmd.append("--dry-run")

            # ─ Yeniden deneme döngüsü (internet kesintisi) ─
            deneme = 0
            MAX_DENEME = 5
            while deneme < MAX_DENEME:
                try:
                    self.current_process = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1, encoding="utf-8", errors="replace",
                        env=_SUBPROC_ENV
                    )
                    for line in self.current_process.stdout:
                        if self.stop_requested:
                            self.current_process.terminate()
                            break
                    self.current_process.wait()

                    if self.current_process.returncode == 0:
                        basari += 1
                        break
                    else:
                        deneme += 1
                        if deneme < MAX_DENEME:
                            bekleme = 2 ** deneme  # 2, 4, 8, 16, 32 sn
                            self.root.after(0, lambda d=deneme, b=bekleme, a=ad:
                                self.log(f"⚠️ {a} başarısız ({d}. deneme). {b}sn sonra tekrar..."))
                            time.sleep(bekleme)
                        else:
                            hata += 1
                            self.root.after(0, lambda a=ad:
                                self.log(f"❌ {a} {MAX_DENEME} denemede başarısız"))
                except Exception as e:
                    deneme += 1
                    if deneme >= MAX_DENEME:
                        hata += 1
                        self.root.after(0, lambda a=ad, err=str(e):
                            self.log(f"❌ {a}: {err}"))
                    else:
                        time.sleep(2 ** deneme)

        self.transfer_running = False
        if not self.stop_requested:
            temizle_durum()  # Başarıyla bitti, durum dosyasını sil

        ozet = f"🏁 {op_adi} bitti! ✅{basari} başarılı ❌{hata} hatalı"
        if self.stop_requested:
            ozet += f" ⛔ (durduruldu, {len(dosyalar)-i} dosya beklemede)"
        self.root.after(0, lambda: self.log(ozet))
        self.root.after(0, lambda: self._ui_guncelle(100, "Tamamlandı"))
        self.root.after(0, self.dosyalari_listele)

    # ── Sync Thread ───────────────────────────────────────────────────────────
    def _sync_baslat(self, kaynak, hedef, kaynak_yol, hedef_yol):
        if self.transfer_running:
            messagebox.showwarning("Uyarı", "Zaten bir işlem devam ediyor!")
            return

        def _isle():
            self.transfer_running = True
            self.stop_requested   = False
            op_adi = "TEST SYNC" if self.test_mode.get() else "SYNC"
            self.root.after(0, lambda: self.log(f"🔄 {op_adi} başlıyor..."))

            cmd = ["rclone", "sync",
                   f"{kaynak}{kaynak_yol}", f"{hedef}{hedef_yol}",
                   "--verbose", "--stats", "2s"]
            if self.ignore_errors.get(): cmd.append("--ignore-errors")
            if self.test_mode.get():     cmd.append("--dry-run")

            deneme = 0
            MAX_DENEME = 5
            while deneme < MAX_DENEME:
                try:
                    self.current_process = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1, encoding="utf-8", errors="replace",
                        env=_SUBPROC_ENV
                    )
                    for line in self.current_process.stdout:
                        if self.stop_requested:
                            self.current_process.terminate()
                            break
                        if line.strip():
                            self.root.after(0, lambda l=line.strip():
                                self._ui_guncelle(-1, l[:80]))
                    self.current_process.wait()

                    if self.current_process.returncode == 0 or self.stop_requested:
                        break
                    else:
                        deneme += 1
                        bekleme = 2 ** deneme
                        self.root.after(0, lambda b=bekleme:
                            self.log(f"⚠️ Sync başarısız. {b}sn sonra tekrar..."))
                        time.sleep(bekleme)
                except Exception as e:
                    deneme += 1
                    time.sleep(2 ** deneme)

            self.transfer_running = False
            durum = "✅ tamamlandı" if self.current_process and self.current_process.returncode == 0 else "❌ hata/durduruldu"
            self.root.after(0, lambda: self.log(f"🏁 {op_adi} {durum}"))
            self.root.after(0, lambda: self._ui_guncelle(100, "Tamamlandı"))
            self.root.after(0, self.dosyalari_listele)

        threading.Thread(target=_isle, daemon=True).start()

    # ── UI Yardımcıları ───────────────────────────────────────────────────────
    def _ui_guncelle(self, progress, durum_metni):
        if progress >= 0:
            self.progress_bar["value"] = progress
        self.durum_label.config(text=durum_metni[:90])

    def log(self, mesaj):
        zaman = datetime.now().strftime("%H:%M:%S")
        self.log_alan.config(state="normal")
        self.log_alan.insert("end", f"[{zaman}] {mesaj}\n")
        self.log_alan.see("end")
        self.log_alan.config(state="disabled")


# ─── BAŞLAT ───────────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    app  = RCloneManager(root)
    root.mainloop()

if __name__ == "__main__":
    main()