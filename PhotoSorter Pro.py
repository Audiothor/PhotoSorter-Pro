import os
import shutil
import piexif
import re
import hashlib
import json
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from PIL import Image, ImageOps
import customtkinter as ctk
from tkinter import filedialog, messagebox
import speech_recognition as sr

# Configuration globale du design
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ModernPhotoSorter(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.version = "v1.11.1"

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
        self.current_target_folder = None
        self.is_renaming = False
        self.awaiting_label = False
        self.temp_save_data = None

        # Variables Vocales
        # Variables Vocales
        self.is_listening = False
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.5

        # Variables Doublons
        self.checksum_db = {} # md5 -> path
        self.index_file = ""
        self.scan_thread = None
        self.is_scanning = False

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

        # --- En-tête Sidebar ---
        self.header_frame = ctk.CTkFrame(self.sidebar, fg_color="#1f3d6a", corner_radius=15, width=190, height=65)
        self.header_frame.grid(row=0, column=0, sticky="", padx=45, pady=20)
        self.header_frame.grid_propagate(False)
        
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
            if os.path.exists(icon_path):
                self.title_icon = ctk.CTkImage(light_image=Image.open(icon_path), dark_image=Image.open(icon_path), size=(40, 40))
                self.lbl_title = ctk.CTkLabel(self.header_frame, text=" PhotoSorter Pro", image=self.title_icon, compound="left", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
            else:
                self.lbl_title = ctk.CTkLabel(self.header_frame, text="📸 PhotoSorter Pro", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
        except:
            self.lbl_title = ctk.CTkLabel(self.header_frame, text="📸 PhotoSorter Pro", font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
            
        self.lbl_title.pack(pady=(8, 0), padx=5, expand=True)
        self.lbl_subtitle = ctk.CTkLabel(self.header_frame, text=f"Version {self.version.lstrip('v')}", font=ctk.CTkFont(size=10), text_color="#a9cce3")
        self.lbl_subtitle.pack(pady=(0, 8), padx=5, expand=True)
        
        self.btn_src = ctk.CTkButton(self.sidebar, text="📁 Choisir Source", command=self.load_source)
        self.btn_src.grid(row=1, column=0, padx=20, pady=(10, 0))
        self.lbl_src_path = ctk.CTkLabel(self.sidebar, text="Aucun dossier", text_color="gray", font=ctk.CTkFont(size=11), wraplength=220)
        self.lbl_src_path.grid(row=2, column=0, padx=10, pady=(2, 10))
        
        self.btn_dest = ctk.CTkButton(self.sidebar, text="🎯 Choisir Destination", command=self.load_dest)
        self.btn_dest.grid(row=3, column=0, padx=20, pady=(10, 0))
        self.lbl_dest_path = ctk.CTkLabel(self.sidebar, text="Aucun dossier", text_color="gray", font=ctk.CTkFont(size=11), wraplength=220)
        self.lbl_dest_path.grid(row=4, column=0, padx=10, pady=(2, 10))

        self.lbl_current_event = ctk.CTkLabel(self.sidebar, text="", text_color="#f1c40f", font=ctk.CTkFont(size=13, weight="bold"), wraplength=240)
        self.lbl_current_event.grid(row=5, column=0, padx=10, pady=(0, 10))

        self.btn_rename = ctk.CTkButton(self.sidebar, text="✏️ Modifier le nom", font=ctk.CTkFont(size=11), fg_color="transparent", border_width=1, height=24, command=self.start_rename)

        self.frame_label = ctk.CTkFrame(self.sidebar, fg_color="#3d1d1d", corner_radius=10)
        self.lbl_prompt = ctk.CTkLabel(self.frame_label, text="NOUVEAU DOSSIER !\nNommez l'événement :", text_color="#e74c3c", font=ctk.CTkFont(weight="bold"))
        self.lbl_prompt.pack(pady=(10, 2))
        self.entry_label = ctk.CTkEntry(self.frame_label, placeholder_text="Ex: Travaux Maison")
        self.entry_label.pack(pady=10, padx=10)
        self.entry_label.bind("<Return>", lambda e: self.confirm_label(self.entry_label.get()))

        self.lbl_stats = ctk.CTkLabel(self.sidebar, text="0 / 0 photos")
        self.lbl_stats.grid(row=8, column=0, padx=20, pady=10)
        self.progress_bar = ctk.CTkProgressBar(self.sidebar)
        self.progress_bar.grid(row=9, column=0, padx=20, pady=5)
        self.progress_bar.set(0)

        self.btn_undo = ctk.CTkButton(self.sidebar, text="↩ Annuler (Ctrl+Z)", 
                                      fg_color="#e67e22", hover_color="#d35400", 
                                      text_color="white", 
                                      text_color_disabled="#2c3e50", # Gris très sombre pour le contraste sur orange
                                      font=ctk.CTkFont(weight="bold"),
                                      command=self.undo_last, state="disabled")
        self.btn_undo.grid(row=10, column=0, padx=20, pady=10)

        self.btn_mic = ctk.CTkButton(self.sidebar, text="🎙 Activer la Voix", fg_color="#8e44ad", hover_color="#9b59b6", command=self.toggle_voice)
        self.btn_mic.grid(row=11, column=0, padx=20, pady=10)

        self.btn_help = ctk.CTkButton(self.sidebar, text="📖 Aide (README)", fg_color="#2980b9", hover_color="#3498db", command=lambda: webbrowser.open("https://github.com/Audiothor/PhotoSorter-Pro#readme"))
        self.btn_help.grid(row=12, column=0, padx=20, pady=10)

        self.btn_keys = ctk.CTkButton(self.sidebar, text="⌨️ Commandes & Touches", fg_color="#16a085", hover_color="#1abc9c", command=self.show_shortcuts_help)
        self.btn_keys.grid(row=13, column=0, padx=20, pady=10)

        self.btn_exit = ctk.CTkButton(self.sidebar, text="❌ Quitter", fg_color="#34495e", hover_color="#c0392b", command=self.destroy)
        self.btn_exit.grid(row=14, column=0, padx=20, pady=(20, 5), sticky="s")

        self.lbl_version = ctk.CTkLabel(self.sidebar, text=f"Version {self.version}", font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_version.grid(row=15, column=0, padx=20, pady=(0, 10), sticky="s")

        # --- Zone Centrale ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.image_label = ctk.CTkLabel(self.main_frame, text="Veuillez charger un dossier")
        self.image_label.pack(expand=True)

        # Overlay Doublon
        self.lbl_dup_warning = ctk.CTkLabel(self.main_frame, text="⚠️ DOUBLON DÉTECTÉ !", fg_color="#c0392b", text_color="white", font=ctk.CTkFont(size=16, weight="bold"), corner_radius=10)

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

    def check_for_updates(self):
        def _check():
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
                        def update_ui():
                            self.lbl_version.configure(text=f"🚀 Màj disponible : {remote_version} !", text_color="#2ecc71", cursor="hand2")
                            self.lbl_version.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/Audiothor/PhotoSorter-Pro"))
                        self.after(0, update_ui)
                    else:
                        self.after(0, lambda: self.lbl_version.configure(text=f"À jour ({self.version})", text_color="gray"))
            except: pass
        threading.Thread(target=_check, daemon=True).start()

    def show_shortcuts_help(self):
        msg = (
            "⌨️ RACCOURCIS CLAVIER :\n"
            "----------------------------------\n"
            "➡ Flèche Droite / Entrée : Garder\n"
            "✖ Suppr : Mettre à la corbeille\n"
            "⏩ Échap : Passer à la suivante\n"
            "🔄 Espace : Rotation (90°)\n"
            "↩ Ctrl + Z : Annuler la dernière action\n\n"
            "🎙 COMMANDES VOCALES :\n"
            "----------------------------------\n"
            "✅ Garder, Sauvegarder, Ok, Oui, Ouais, Yes...\n"
            "🗑 Supprimer, Corbeille, Non, Nan, No...\n"
            "🔄 Rotation, Tourner\n"
            "↩ Annuler"
        )
        messagebox.showinfo("Aide : Commandes & Touches", msg)

    def _bind_shortcuts(self):
        self.bind("<Right>", lambda event: self._on_shortcut("save"))
        self.bind("<Return>", lambda event: self._on_shortcut("save"))
        self.bind("<Delete>", lambda event: self._on_shortcut("trash"))
        self.bind("<Escape>", lambda event: self._on_shortcut("skip"))
        self.bind("<space>", lambda event: self._on_shortcut("rotate"))
        self.bind("<Control-z>", lambda event: self._on_shortcut("undo"))

    def _on_shortcut(self, action):
        if self.awaiting_label: return # Ignorer si on tape un texte
        if action == "save": self.process_photo("save")
        elif action == "trash": self.process_photo("trash")
        elif action == "skip": self.next_photo()
        elif action == "rotate": self.do_rotate()
        elif action == "undo": self.undo_last()

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
                    time_limit = 6 if self.awaiting_label else 3
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=time_limit)
                    cmd = self.recognizer.recognize_google(audio, language="fr-FR").lower()
                    
                    if self.awaiting_label:
                        self.after(0, lambda c=cmd: self.confirm_label(c))
                    else:
                        # Ajout du mot exact "ok" ou "okay" grâce aux expressions régulières (Regex)
                        if "supprimer" in cmd or "corbeille" in cmd or re.search(r'\b(non|nan|no|nope|nom)\b', cmd): 
                            self.after(0, lambda: self.process_photo("trash"))
                        elif "garder" in cmd or "sauvegarder" in cmd or re.search(r'\b(ok|okay|oui|ouais|yes|yep|we)\b', cmd): 
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

    def calculate_md5(self, file_path):
        """Calcule l'empreinte MD5 d'un fichier."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except: return None

    def load_index(self):
        """Charge l'index des doublons."""
        self.index_file = os.path.join(self.dest_dir, ".photosorter_index.json")
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    self.checksum_db = json.load(f)
            except: self.checksum_db = {}
        else: self.checksum_db = {}

    def save_index(self):
        """Sauvegarde l'index des doublons."""
        if not self.dest_dir or not self.index_file: return
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.checksum_db, f, ensure_ascii=False, indent=2)
        except: pass

    def start_background_scan(self):
        """Lance le scan de la destination en arrière-plan."""
        if self.is_scanning: return
        self.is_scanning = True
        self.scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self.scan_thread.start()

    def _scan_worker(self):
        """Parcourt la destination pour indexer les fichiers existants."""
        extensions = ('.jpg', '.jpeg', '.png', '.mp4', '.mov')
        for root, dirs, files in os.walk(self.dest_dir):
            for file in files:
                if file.lower().endswith(extensions):
                    full_path = os.path.join(root, file)
                    try:
                        md5 = self.calculate_md5(full_path)
                        if md5: self.checksum_db[md5] = full_path
                    except: continue
            self.save_index()
            time.sleep(0.01)
        self.is_scanning = False
        self.save_index()

    def show_current(self):
        self.lbl_dup_warning.place_forget() # Reset warning
        if self.idx < len(self.photos):
            self.update_ui_state()
            p = os.path.join(self.source_dir, self.photos[self.idx])
            
            if not os.path.exists(p):
                self.image_label.configure(image=None, text=f"⚠ Fichier introuvable :\n{self.photos[self.idx]}\n(Déplacé ou supprimé ?)")
                return

            # Vérification de doublon par MD5
            current_md5 = self.calculate_md5(p)
            if current_md5 in self.checksum_db:
                found_path = self.checksum_db[current_md5]
                folder_hint = os.path.basename(os.path.dirname(found_path))
                self.lbl_dup_warning.configure(text=f"⚠️ DOUBLON DÉTECTÉ !\n(Déjà dans : {folder_hint})")
                self.lbl_dup_warning.place(relx=0.5, rely=0.1, anchor="center")

            try:
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
            except Exception as e:
                self.image_label.configure(image=None, text=f"⚠ Erreur de lecture :\n{self.photos[self.idx]}\n(Format non supporté ou fichier corrompu)")
        else: 
            self.image_label.configure(image=None, text="Terminé !")

    def process_photo(self, action):
        if self.idx >= len(self.photos): return
        
        filename = self.photos[self.idx]
        src_path = os.path.join(self.source_dir, filename)
        
        # Sécurité : Si le fichier a disparu entre temps
        if not os.path.exists(src_path):
            messagebox.showwarning("Fichier introuvable", f"Le fichier {filename} semble avoir été déplacé ou supprimé.\nPassage à la photo suivante.")
            self.next_photo()
            return

        if action == "save":
            if not self.dest_dir:
                return messagebox.showwarning("Erreur", "Définit le dossier de destination !")
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
        self.btn_rename.grid_forget()
        self.lbl_prompt.configure(text="NOUVEAU DOSSIER !\nNommez l'événement :")
        self.frame_label.grid(row=7, column=0, padx=10, pady=10, sticky="ew")
        self.entry_label.delete(0, 'end')
        self.entry_label.focus()

    def start_rename(self):
        if not self.current_target_folder: return
        self.is_renaming = True
        self.awaiting_label = True
        self.lbl_prompt.configure(text="RENOMMER DOSSIER :\nNouveau libellé :")
        self.frame_label.grid(row=7, column=0, padx=10, pady=10, sticky="ew")
        
        # Pré-remplir avec le libellé actuel (après YYYY-MM-DD )
        current_name = os.path.basename(self.current_target_folder)
        if len(current_name) >= 11:
            self.entry_label.delete(0, 'end')
            self.entry_label.insert(0, current_name[11:])
        self.entry_label.focus()

    def confirm_label(self, label_text):
        if not self.awaiting_label: return
        self.awaiting_label = False
        self.frame_label.grid_forget()
        
        if self.is_renaming:
            self.execute_rename(label_text)
            self.is_renaming = False
            return
            
        src_path, date_obj = self.temp_save_data
        
        folder_name = f"{date_obj.strftime('%Y-%m-%d')} {label_text}".strip()
        target_folder = os.path.join(self.dest_dir, date_obj.strftime('%Y'), folder_name)
        os.makedirs(target_folder, exist_ok=True)
        
        self.finalize_save(src_path, target_folder)

    def execute_rename(self, new_label):
        old_path = self.current_target_folder
        if not old_path or not os.path.exists(old_path): return
        
        parent = os.path.dirname(old_path)
        base = os.path.basename(old_path)
        prefix = base[:10] # YYYY-MM-DD
        
        new_name = f"{prefix} {new_label}".strip()
        new_path = os.path.join(parent, new_name)
        
        if old_path == new_path: return
        
        try:
            if os.path.exists(new_path):
                # Fusionner si le dossier existe déjà
                for f in os.listdir(old_path):
                    shutil.move(os.path.join(old_path, f), os.path.join(new_path, f))
                os.rmdir(old_path)
            else:
                os.rename(old_path, new_path)
                
            self.current_target_folder = new_path
            self.lbl_current_event.configure(text=f"📁 Dossier : {os.path.basename(new_path)}")
            
            # Mettre à jour l'historique pour éviter de casser l'Undo
            for h in self.history:
                if "dest" in h and h["dest"].startswith(old_path):
                    h["dest"] = h["dest"].replace(old_path, new_path)
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec du renommage : {e}")

    def finalize_save(self, src_path, target_folder):
        self.current_target_folder = target_folder
        self.btn_rename.grid(row=6, column=0, padx=10, pady=(0, 10))
        # Affichage dynamique du dossier cible en vert/jaune
        self.lbl_current_event.configure(text=f"📁 Dossier : {os.path.basename(target_folder)}", text_color="#2ecc71")

        filename = os.path.basename(src_path)
        dest_path = os.path.join(target_folder, filename)
        
        # Gestion des conflits de noms
        final_dest = dest_path
        counter = 1
        name, ext = os.path.splitext(filename)
        while os.path.exists(final_dest):
            final_dest = os.path.join(target_folder, f"{name}_{counter}{ext}")
            counter += 1
            
        try:
            with Image.open(src_path) as img:
                img = ImageOps.exif_transpose(img)
                if self.rotation != 0: img = img.rotate(self.rotation, expand=True)
                try:
                    exif_bytes = piexif.dump(piexif.load(src_path))
                    img.save(final_dest, quality=95, exif=exif_bytes)
                except: img.save(final_dest, quality=95)
        except:
            shutil.copy2(src_path, final_dest)

        stat = os.stat(src_path)
        os.utime(final_dest, (stat.st_atime, stat.st_mtime))
        
        # Mémoriser dans l'index
        md5 = self.calculate_md5(final_dest)
        if md5: 
            self.checksum_db[md5] = final_dest
            self.save_index()

        archive_dir = os.path.join(self.source_dir, "_archive_traitee")
        os.makedirs(archive_dir, exist_ok=True)
        arch_path = os.path.join(archive_dir, filename)
        shutil.move(src_path, arch_path)
        self.history.append({"action": "save", "src": src_path, "dest": final_dest, "arch": arch_path})
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
        try:
            if os.path.exists(h["arch"]):
                shutil.move(h["arch"], h["src"])
                if h["action"] == "save" and os.path.exists(h["dest"]):
                    os.remove(h["dest"])
                self.idx -= 1
                self.update_ui_state()
                self.show_current()
            else:
                messagebox.showerror("Erreur Annuler", "Impossible de retrouver le fichier dans l'archive/corbeille.")
        except Exception as e:
            messagebox.showerror("Erreur Annuler", f"Erreur lors de la restauration :\n{e}")

    def load_source(self):
        p = filedialog.askdirectory()
        if p:
            self.source_dir = p
            self.lbl_src_path.configure(text=p)
            self.lbl_current_event.configure(text="") # On réinitialise l'affichage du dossier
            self.btn_rename.grid_forget()
            self.current_target_folder = None
            self.photos = [f for f in os.listdir(p) if f.lower().endswith(('.jpg','.jpeg','.png'))]
            self.idx = 0
            self.update_ui_state()
            self.show_current()

    def load_dest(self):
        p = filedialog.askdirectory()
        if p:
            self.dest_dir = p
            self.lbl_dest_path.configure(text=p)
            self.lbl_current_event.configure(text="")
            self.btn_rename.grid_forget()
            self.current_target_folder = None
            self.load_index()
            self.start_background_scan()

    def update_ui_state(self):
        t = len(self.photos)
        self.lbl_stats.configure(text=f"{self.idx + 1} / {t}" if t > 0 else "0 / 0")
        self.progress_bar.set(self.idx / t if t > 0 else 0)
        self.btn_undo.configure(state="normal" if self.history else "disabled")

if __name__ == "__main__":
    app = ModernPhotoSorter()
    app.mainloop()