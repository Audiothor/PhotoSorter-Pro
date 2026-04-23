import os
import shutil
import piexif
import re
from datetime import datetime
from PIL import Image, ImageOps
import customtkinter as ctk
from tkinter import filedialog, messagebox
import speech_recognition as sr
import threading
import urllib.request
import webbrowser

# Configuration globale du design
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ModernPhotoSorter(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.version = "v1.9.7"

        self.title("PhotoSorter Pro - " + self.version)
        self.geometry("1250x850")
        self.after(10, lambda: self.state("zoomed"))
        
        try:
            from PIL import Image, ImageTk
            import os
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
            if os.path.exists(icon_path):
                self.iconphoto(False, ImageTk.PhotoImage(Image.open(icon_path)))
        except Exception:
            pass
        
        self.source_dir = ""
        self.dest_dir = ""
        self.photos = []
        self.idx = 0
        self.rotation = 0
        self.history = []

        # États pour la gestion du libellé
        self.awaiting_label = False
        self.temp_save_data = None

        # Variables Vocales
        self.is_listening = False
        self.recognizer = sr.Recognizer()

        self._setup_ui()
        self._bind_shortcuts()
        
        # Vérification des mises à jour en arrière-plan
        threading.Thread(target=self.check_for_updates, daemon=True).start()

    def _setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Panneau Latéral Gauche ---
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_rowconfigure(11, weight=1)

        # --- En-tête Sidebar (Style Illustration Finale - Compact) ---
        self.header_frame = ctk.CTkFrame(self.sidebar, fg_color="#1f3d6a", corner_radius=15, width=190, height=65)
        self.header_frame.grid(row=0, column=0, sticky="", padx=45, pady=20)
        self.header_frame.grid_propagate(False) # Empêche le cadre de s'agrandir
        
        try:
            from PIL import Image
            import os
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
            if os.path.exists(icon_path):
                self.title_icon = ctk.CTkImage(light_image=Image.open(icon_path), dark_image=Image.open(icon_path), size=(40, 40))
                self.lbl_title = ctk.CTkLabel(self.header_frame, text=" PhotoSorter Pro", image=self.title_icon, compound="left", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
            else:
                self.lbl_title = ctk.CTkLabel(self.header_frame, text="📸 PhotoSorter Pro", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
        except Exception:
            self.lbl_title = ctk.CTkLabel(self.header_frame, text="📸 PhotoSorter Pro", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
            
        self.lbl_title.pack(pady=(8, 0), padx=5, expand=True)
        self.lbl_subtitle = ctk.CTkLabel(self.header_frame, text=f"Version {self.version.lstrip('v')}", font=ctk.CTkFont(size=10), text_color="#a9cce3")
        self.lbl_subtitle.pack(pady=(0, 8), padx=5, expand=True)
        
        # Source
        self.btn_src = ctk.CTkButton(self.sidebar, text="📁 Choisir Source", command=self.load_source)
        self.btn_src.grid(row=1, column=0, padx=20, pady=(10, 0))
        self.lbl_src_path = ctk.CTkLabel(self.sidebar, text="Aucun dossier", text_color="gray", font=ctk.CTkFont(size=11), wraplength=220)
        self.lbl_src_path.grid(row=2, column=0, padx=10, pady=(2, 10))
        
        # Destination
        self.btn_dest = ctk.CTkButton(self.sidebar, text="🎯 Choisir Destination", command=self.load_dest)
        self.btn_dest.grid(row=3, column=0, padx=20, pady=(10, 0))
        self.lbl_dest_path = ctk.CTkLabel(self.sidebar, text="Aucun dossier", text_color="gray", font=ctk.CTkFont(size=11), wraplength=220)
        self.lbl_dest_path.grid(row=4, column=0, padx=10, pady=(2, 10))

        # --- NOUVEAU : Affichage du dossier en cours ---
        self.lbl_current_event = ctk.CTkLabel(self.sidebar, text="", text_color="#f1c40f", font=ctk.CTkFont(size=13, weight="bold"), wraplength=240)
        self.lbl_current_event.grid(row=5, column=0, padx=10, pady=(0, 10))

        # --- ZONE LIBELLÉ ---
        self.frame_label = ctk.CTkFrame(self.sidebar, fg_color="#3d1d1d", corner_radius=10)
        self.lbl_prompt = ctk.CTkLabel(self.frame_label, text="NOUVEAU DOSSIER !\nNommez l'événement :", text_color="#e74c3c", font=ctk.CTkFont(weight="bold"))
        self.lbl_prompt.pack(pady=(10, 2))
        self.entry_label = ctk.CTkEntry(self.frame_label, placeholder_text="Ex: Travaux Maison")
        self.entry_label.pack(pady=10, padx=10)
        self.entry_label.bind("<Return>", lambda e: self.confirm_label(self.entry_label.get()))

        # Stats & Progrès
        self.lbl_stats = ctk.CTkLabel(self.sidebar, text="0 / 0 photos")
        self.lbl_stats.grid(row=7, column=0, padx=20, pady=10)
        self.progress_bar = ctk.CTkProgressBar(self.sidebar)
        self.progress_bar.grid(row=8, column=0, padx=20, pady=5)
        self.progress_bar.set(0)

        # Annuler
        self.btn_undo = ctk.CTkButton(self.sidebar, text="↩ Annuler (Ctrl+Z)", fg_color="#e67e22", hover_color="#d35400", 
                                      text_color="white", text_color_disabled="#e0e0e0", command=self.undo_last, state="disabled")
        self.btn_undo.grid(row=9, column=0, padx=20, pady=10)

        # Micro
        self.btn_mic = ctk.CTkButton(self.sidebar, text="🎙 Activer la Voix", fg_color="#8e44ad", hover_color="#9b59b6", command=self.toggle_voice)
        self.btn_mic.grid(row=10, column=0, padx=20, pady=10)

        # Aide
        self.btn_help = ctk.CTkButton(self.sidebar, text="📖 Aide (README)", fg_color="#2980b9", hover_color="#3498db", command=lambda: webbrowser.open("https://github.com/Audiothor/PhotoSorter-Pro#readme"))
        self.btn_help.grid(row=11, column=0, padx=20, pady=10)

        # Quitter
        self.btn_exit = ctk.CTkButton(self.sidebar, text="❌ Quitter", fg_color="#34495e", hover_color="#c0392b", command=self.destroy)
        self.btn_exit.grid(row=12, column=0, padx=20, pady=(20, 5), sticky="s")

        # Label de version
        self.lbl_version = ctk.CTkLabel(self.sidebar, text=f"Version {self.version} (Vérification...)", font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_version.grid(row=13, column=0, padx=20, pady=(0, 10), sticky="s")

    def check_for_updates(self):
        try:
            url = f"https://raw.githubusercontent.com/Audiothor/PhotoSorter-Pro/main/PhotoSorter%20Pro.py?t={int(datetime.now().timestamp())}"
            req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=5) as response:
                content = response.read().decode('utf-8')
                
            match = re.search(r'self\.version\s*=\s*["\'](v[^"\']+)["\']', content)
            if match:
                remote_version = match.group(1)
                
                def parse_v(v): return tuple(map(int, v.strip('v').split('.')))
                
                if parse_v(remote_version) > parse_v(self.version):
                    def update_ui_available():
                        self.lbl_version.configure(text=f"🚀 Màj disponible : {remote_version} !", text_color="#2ecc71", cursor="hand2")
                        self.lbl_version.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/Audiothor/PhotoSorter-Pro"))
                    self.after(0, update_ui_available)
                else:
                    self.after(0, lambda: self.lbl_version.configure(
                        text=f"À jour ({self.version})", text_color="gray"
                    ))
            else:
                self.after(0, lambda: self.lbl_version.configure(text=f"Version {self.version}", text_color="gray"))
        except Exception:
            self.after(0, lambda: self.lbl_version.configure(text=f"Version {self.version} (Hors ligne)", text_color="gray"))

        # --- Zone Centrale ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.image_label = ctk.CTkLabel(self.main_frame, text="Veuillez charger un dossier")
        self.image_label.pack(expand=True)

        # Barre d'actions
        self.action_frame = ctk.CTkFrame(self, height=80, corner_radius=10)
        self.action_frame.grid(row=1, column=1, padx=20, pady=(0, 20), sticky="ew")
        self.action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_rotate = ctk.CTkButton(self.action_frame, text="⟲ Rotation (Espace)", command=self.do_rotate)
        self.btn_rotate.grid(row=0, column=0, padx=20, pady=20)
        self.btn_trash = ctk.CTkButton(self.action_frame, text="🗑 Corbeille (Suppr)", fg_color="#e74c3c", command=lambda: self.process_photo("trash"))
        self.btn_trash.grid(row=0, column=1, padx=20, pady=20)
        self.btn_save = ctk.CTkButton(self.action_frame, text="💾 Classer (→)", fg_color="#2ecc71", command=lambda: self.process_photo("save"))
        self.btn_save.grid(row=0, column=2, padx=20, pady=20)

    def _bind_shortcuts(self):
        self.bind("<Right>", lambda event: self.process_photo("save"))
        self.bind("<Delete>", lambda event: self.process_photo("trash"))
        self.bind("<space>", lambda event: self.do_rotate())
        self.bind("<Control-z>", lambda event: self.undo_last())

    def do_rotate(self):
        self.rotation = (self.rotation - 90) % 360
        self.show_current()

    def toggle_voice(self):
        self.is_listening = not self.is_listening
        if self.is_listening:
            self.btn_mic.configure(text="🔴 Écoute...", fg_color="#c0392b")
            threading.Thread(target=self._listen_loop, daemon=True).start()
        else:
            self.btn_mic.configure(text="🎙 Activer la Voix", fg_color="#8e44ad")

    def _listen_loop(self):
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            while self.is_listening:
                try:
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=3)
                    cmd = self.recognizer.recognize_google(audio, language="fr-FR").lower()
                    
                    if self.awaiting_label:
                        self.after(0, lambda c=cmd: self.confirm_label(c))
                    else:
                        # Ajout du mot exact "ok" ou "okay" grâce aux expressions régulières (Regex)
                        if "supprimer" in cmd or "corbeille" in cmd: 
                            self.after(0, lambda: self.process_photo("trash"))
                        elif "garder" in cmd or "sauvegarder" in cmd or re.search(r'\b(ok|okay)\b', cmd): 
                            self.after(0, lambda: self.process_photo("save"))
                        elif "rotation" in cmd or "tourner" in cmd: 
                            self.after(0, self.do_rotate)
                        elif "annuler" in cmd: 
                            self.after(0, self.undo_last)
                except: 
                    continue

    def get_safe_date(self, path):
        try:
            with Image.open(path) as img:
                exif = img._getexif()
                if exif and 36867 in exif: return datetime.strptime(exif[36867], '%Y:%m:%d %H:%M:%S')
        except: pass
        filename = os.path.basename(path)
        match = re.search(r'(20\d{2})(\d{2})(\d{2})', filename)
        if match:
            y, m, d = match.groups()
            try: return datetime(int(y), int(m), int(d))
            except: pass
        return datetime.fromtimestamp(os.path.getctime(path))

    def show_current(self):
        if self.idx < len(self.photos):
            self.update_ui_state()
            p = os.path.join(self.source_dir, self.photos[self.idx])
            with Image.open(p) as img:
                img = ImageOps.exif_transpose(img)
                if self.rotation != 0: img = img.rotate(self.rotation, expand=True)
                
                max_w, max_h = 800, 600
                img_w, img_h = img.size
                ratio = min(max_w / img_w, max_h / img_h)
                new_w = int(img_w * ratio)
                new_h = int(img_h * ratio)
                
                ci = ctk.CTkImage(img, size=(new_w, new_h))
                self.image_label.configure(image=ci, text="")
                self.image_label.image = ci
        else: 
            self.image_label.configure(image=None, text="Terminé !")

    def process_photo(self, action):
        if action == "save" and not self.dest_dir:
            return messagebox.showwarning("Erreur", "Définit la destination !")
        if self.idx >= len(self.photos): return

        src_path = os.path.join(self.source_dir, self.photos[self.idx])
        
        if action == "save":
            date_obj = self.get_safe_date(src_path)
            date_prefix = date_obj.strftime('%Y-%m-%d')
            year_folder = os.path.join(self.dest_dir, date_obj.strftime('%Y'))
            
            existing_folder = None
            if os.path.exists(year_folder):
                for d in os.listdir(year_folder):
                    if d.startswith(date_prefix):
                        existing_folder = os.path.join(year_folder, d)
                        break

            if not existing_folder:
                self.temp_save_data = (src_path, date_obj)
                self.show_label_prompt()
                return
            else:
                self.finalize_save(src_path, existing_folder)
        else:
            self.finalize_trash(src_path)

    def show_label_prompt(self):
        self.awaiting_label = True
        self.lbl_current_event.configure(text="En attente de libellé...", text_color="#e74c3c")
        self.frame_label.grid(row=6, column=0, padx=10, pady=10, sticky="ew")
        self.entry_label.delete(0, 'end')
        self.entry_label.focus()

    def confirm_label(self, label_text):
        if not self.awaiting_label: return
        self.awaiting_label = False
        self.frame_label.grid_forget()
        src_path, date_obj = self.temp_save_data
        
        folder_name = f"{date_obj.strftime('%Y-%m-%d')} {label_text}".strip()
        target_folder = os.path.join(self.dest_dir, date_obj.strftime('%Y'), folder_name)
        os.makedirs(target_folder, exist_ok=True)
        
        self.finalize_save(src_path, target_folder)

    def finalize_save(self, src_path, target_folder):
        # Affichage dynamique du dossier cible en vert/jaune
        self.lbl_current_event.configure(text=f"📁 Dossier : {os.path.basename(target_folder)}", text_color="#2ecc71")

        filename = os.path.basename(src_path)
        dest_path = os.path.join(target_folder, filename)
        counter = 1
        name, ext = os.path.splitext(filename)
        while os.path.exists(dest_path):
            dest_path = os.path.join(target_folder, f"{name}_{counter}{ext}")
            counter += 1

        with Image.open(src_path) as img:
            img = ImageOps.exif_transpose(img)
            if self.rotation != 0: img = img.rotate(self.rotation, expand=True)
            try:
                exif_bytes = piexif.dump(piexif.load(src_path))
                img.save(dest_path, quality=95, exif=exif_bytes)
            except: img.save(dest_path, quality=95)

        stat = os.stat(src_path)
        os.utime(dest_path, (stat.st_atime, stat.st_mtime))
        archive_dir = os.path.join(self.source_dir, "_archive_traitee")
        os.makedirs(archive_dir, exist_ok=True)
        arch_path = os.path.join(archive_dir, filename)
        shutil.move(src_path, arch_path)
        self.history.append({"action": "save", "src": src_path, "dest": dest_path, "arch": arch_path})
        self.next_photo()

    def finalize_trash(self, src_path):
        trash_dir = os.path.join(self.source_dir, "_corbeille_tri")
        os.makedirs(trash_dir, exist_ok=True)
        arch_path = os.path.join(trash_dir, os.path.basename(src_path))
        shutil.move(src_path, arch_path)
        self.history.append({"action": "trash", "src": src_path, "arch": arch_path})
        self.next_photo()

    def next_photo(self):
        self.idx += 1
        self.rotation = 0
        self.update_ui_state()
        self.show_current()

    def undo_last(self):
        if not self.history: return
        h = self.history.pop()
        shutil.move(h["arch"], h["src"])
        if h["action"] == "save": os.remove(h["dest"])
        self.idx -= 1
        self.update_ui_state()
        self.show_current()

    def load_source(self):
        p = filedialog.askdirectory()
        if p:
            self.source_dir = p
            self.lbl_src_path.configure(text=p)
            self.lbl_current_event.configure(text="") # On réinitialise l'affichage du dossier
            self.photos = [f for f in os.listdir(p) if f.lower().endswith(('.jpg','.jpeg','.png'))]
            self.idx = 0
            self.update_ui_state()
            self.show_current()

    def load_dest(self):
        p = filedialog.askdirectory()
        if p:
            self.dest_dir = p
            self.lbl_dest_path.configure(text=p)
            self.lbl_current_event.configure(text="") # On réinitialise l'affichage du dossier

    def update_ui_state(self):
        t = len(self.photos)
        self.lbl_stats.configure(text=f"{self.idx + 1} / {t}" if t > 0 else "0 / 0")
        self.progress_bar.set(self.idx / t if t > 0 else 0)
        self.btn_undo.configure(state="normal" if self.history else "disabled")

if __name__ == "__main__":
    app = ModernPhotoSorter()
    app.mainloop()