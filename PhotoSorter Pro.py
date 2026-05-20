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
        self.version = "v1.14.7"

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
        self.previewed_folder = None # Dossier suggéré/affiché (v1.13.2)
        self.is_copying = False

        # Variables Vocales
        # Variables Vocales
        self.is_listening = False
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.5

        # Variables Doublons
        self.checksum_db = {} # md5 -> path
        self.filename_db = {} # name -> path (v1.13.0)
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
        self.sidebar.grid_propagate(False) # Garder la largeur fixe
        self.sidebar.grid_rowconfigure(17, weight=1)

        # --- En-tête Sidebar ---
        self.header_frame = ctk.CTkFrame(self.sidebar, fg_color="#1f3d6a", corner_radius=15, width=190, height=65)
        self.header_frame.grid(row=0, column=0, sticky="", padx=45, pady=(10, 15))
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
        
        self.frame_src = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.frame_src.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="ew")
        
        self.btn_src = ctk.CTkButton(self.frame_src, text="📁 Choisir Source", width=180, command=self.load_source)
        self.btn_src.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_open_src = ctk.CTkButton(self.frame_src, text="👁", width=35, height=28, font=("Segoe UI Emoji", 13), anchor="center", command=lambda: self.open_in_explorer(self.source_dir, "source"))
        self.btn_open_src.pack(side="right")

        self.lbl_src_path = ctk.CTkLabel(self.sidebar, text="Aucun dossier", text_color="gray", font=ctk.CTkFont(size=10), wraplength=240)
        self.lbl_src_path.grid(row=2, column=0, padx=10, pady=(2, 10))
        
        self.frame_dest = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.frame_dest.grid(row=3, column=0, padx=20, pady=(5, 0), sticky="ew")
        
        self.btn_dest = ctk.CTkButton(self.frame_dest, text="🎯 Choisir Destination", width=180, command=self.load_dest)
        self.btn_dest.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_open_dest = ctk.CTkButton(self.frame_dest, text="👁", width=35, height=28, font=("Segoe UI Emoji", 13), anchor="center", command=lambda: self.open_in_explorer(self.dest_dir, "destination"))
        self.btn_open_dest.pack(side="right")

        self.lbl_dest_path = ctk.CTkLabel(self.sidebar, text="Aucun dossier", text_color="gray", font=ctk.CTkFont(size=10), wraplength=240)
        self.lbl_dest_path.grid(row=4, column=0, padx=10, pady=(2, 5))

        # --- Section Dossier Cible (Preview + Actions) v1.13.6 ---
        self.frame_preview = ctk.CTkFrame(self.sidebar, fg_color="#34495e", corner_radius=8)
        self.frame_preview.grid(row=5, column=0, padx=10, pady=10, sticky="ew")
        
        self.lbl_preview_title = ctk.CTkLabel(self.frame_preview, text="PROCHAINE DESTINATION", font=("Segoe UI", 10, "bold"), text_color="#bdc3c7")
        self.lbl_preview_title.grid(row=0, column=0, pady=(5,0), sticky="ew")
        
        self.lbl_dest_preview = ctk.CTkLabel(self.frame_preview, text="", 
                                           font=("Segoe UI", 12, "bold"), wraplength=180, 
                                           text_color="white")
        self.lbl_dest_preview.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        
        self.frame_folder_actions = ctk.CTkFrame(self.frame_preview, fg_color="transparent")
        self.frame_folder_actions.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.frame_preview.columnconfigure(0, weight=1)

        self.btn_rename = ctk.CTkButton(self.frame_folder_actions, text="✏️ Renommer dossier", font=ctk.CTkFont(size=10), height=24, fg_color="#2c3e50", command=self.start_rename)
        self.btn_rename.pack(fill="x", pady=2)

        self.btn_new_event = ctk.CTkButton(self.frame_folder_actions, text="➕ Autre événement", font=ctk.CTkFont(size=10), height=24, fg_color="#2c3e50", command=self.start_new_event)
        self.btn_new_event.pack(fill="x", pady=2)
        
        self.frame_folder_actions.grid_forget() # Caché par défaut

        self.frame_label = ctk.CTkFrame(self.sidebar, fg_color="#3d1d1d", corner_radius=10)
        self.frame_label.grid(row=6, column=0, padx=10, pady=5, sticky="ew")
        self.lbl_prompt = ctk.CTkLabel(self.frame_label, text="NOUVEAU DOSSIER !\nNommez l'événement :", text_color="#e74c3c", font=ctk.CTkFont(weight="bold"))
        self.lbl_prompt.pack(pady=(10, 2))
        self.entry_label = ctk.CTkEntry(self.frame_label, placeholder_text="Ex: Travaux Maison")
        self.entry_label.pack(pady=10, padx=10)
        self.entry_label.bind("<Return>", lambda e: self.confirm_label(self.entry_label.get()))
        self.frame_label.grid_forget()

        self.lbl_stats = ctk.CTkLabel(self.sidebar, text="0 / 0 médias", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_stats.grid(row=7, column=0, padx=20, pady=(5, 0))
        
        self.lbl_filename = ctk.CTkLabel(self.sidebar, text="", font=ctk.CTkFont(size=11, weight="bold"), wraplength=200)
        self.lbl_filename.grid(row=8, column=0, padx=10, pady=(10, 0))

        self.lbl_src_subdir = ctk.CTkLabel(self.sidebar, text="", font=ctk.CTkFont(size=9), text_color="gray")
        self.lbl_src_subdir.grid(row=9, column=0, padx=10, pady=0)

        self.lbl_file_date = ctk.CTkLabel(self.sidebar, text="", font=ctk.CTkFont(size=11), text_color="#3498db")
        self.lbl_file_date.grid(row=10, column=0, padx=10, pady=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(self.sidebar)
        self.progress_bar.grid(row=11, column=0, padx=20, pady=5)
        self.progress_bar.set(0)

        self.lbl_video_info = ctk.CTkLabel(self.sidebar, text="", font=ctk.CTkFont(size=10), text_color="#e67e22")
        self.lbl_video_info.grid(row=12, column=0, padx=20, pady=0)

        self.lbl_other_files_info = ctk.CTkLabel(self.sidebar, text="", font=ctk.CTkFont(size=10), text_color="#95a5a6")
        self.lbl_other_files_info.grid(row=13, column=0, padx=20, pady=0)

        self.lbl_scan_status = ctk.CTkLabel(self.sidebar, text="", font=ctk.CTkFont(size=10), text_color="#3498db")
        self.lbl_scan_status.grid(row=14, column=0, padx=20, pady=0)
        
        self.btn_reset_index = ctk.CTkButton(self.sidebar, text="🗑 Réinit. Index", font=ctk.CTkFont(size=9), 
                                             fg_color="transparent", border_width=1, height=18, width=80,
                                             command=self.reset_duplicate_index)
        self.btn_reset_index.grid(row=15, column=0, padx=10, pady=(20, 0), sticky="e")

        self.btn_undo = ctk.CTkButton(self.sidebar, text="↩ Annuler (Ctrl+Z)", fg_color="#d35400", width=220, command=self.undo_last, text_color_disabled="#2c3e50")
        self.btn_undo.grid(row=16, column=0, padx=10, pady=5)

        self.btn_mic = ctk.CTkButton(self.sidebar, text="🎙 Activer la Voix", fg_color="#8e44ad", width=220, command=self.toggle_voice)
        self.btn_mic.grid(row=17, column=0, padx=10, pady=5)

        # --- Aide & Quitter (v1.13.28 Compact) ---
        self.sidebar.grid_rowconfigure(18, weight=1) # Espace flexible pour stabiliser le bas

        self.btn_help_keys = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.btn_help_keys.grid(row=19, column=0, pady=(5, 0))
        
        self.btn_help = ctk.CTkButton(self.btn_help_keys, text="📖 Aide", width=88, height=24, font=ctk.CTkFont(size=10), command=self.show_readme)
        self.btn_help.grid(row=0, column=0, padx=2)
        self.btn_keys = ctk.CTkButton(self.btn_help_keys, text="⌨️ Touches", width=88, height=24, font=ctk.CTkFont(size=10), command=self.show_shortcuts_help)
        self.btn_keys.grid(row=0, column=1, padx=2)

        self.lbl_version = ctk.CTkLabel(self.sidebar, text=f"À jour ({self.version})", font=("Inter", 10), text_color="#95a5a6")
        self.lbl_version.grid(row=20, column=0, pady=(5, 0))

        self.btn_quit = ctk.CTkButton(self.sidebar, text="❌ Quitter l'application", 
                                    command=self.quit_app, fg_color="#c0392b", hover_color="#a93226",
                                    height=38, font=("Inter", 12, "bold"))
        self.btn_quit.grid(row=21, column=0, padx=20, pady=(5, 20), sticky="ew")



        # --- Zone Centrale ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.image_label = ctk.CTkLabel(self.main_frame, text="Veuillez charger un dossier")
        self.image_label.pack(expand=True)
        self.image_label.bind("<Button-1>", self.on_image_click)

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

    def show_readme(self):
        webbrowser.open("https://github.com/Audiothor/PhotoSorter-Pro#readme")

    def quit_app(self):
        try:
            if hasattr(self, 'index_file') and os.path.exists(self.index_file):
                os.remove(self.index_file)
        except: pass
        self.destroy()

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
            "🗑 Supprimer, Corbeille, PASSER, Non, No...\n"
            "🔄 Rotation, Tourner\n"
            "↩ Annuler"
        )
        messagebox.showinfo("Aide : Commandes & Touches", msg)

    def open_in_explorer(self, path, folder_type):
        if not path or not os.path.exists(path):
            messagebox.showwarning("Dossier introuvable", f"Veuillez d'abord sélectionner un dossier de {folder_type} valide.")
            return
        try:
            import platform
            path_norm = os.path.normpath(path)
            if platform.system() == "Windows":
                os.startfile(path_norm)
            elif platform.system() == "Darwin": # macOS
                import subprocess
                subprocess.Popen(["open", path_norm])
            else: # Linux/other
                import subprocess
                subprocess.Popen(["xdg-open", path_norm])
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le dossier :\n{e}")

    def play_media(self, path):
        try:
            import platform
            path_norm = os.path.normpath(path)
            if platform.system() == "Windows":
                os.startfile(path_norm)
            elif platform.system() == "Darwin": # macOS
                import subprocess
                subprocess.Popen(["open", path_norm])
            else: # Linux/other
                import subprocess
                subprocess.Popen(["xdg-open", path_norm])
        except Exception as e:
            messagebox.showerror("Erreur de lecture", f"Impossible de lancer la vidéo :\n{e}")

    def on_image_click(self, event):
        if self.idx < len(self.photos):
            filename = self.photos[self.idx]
            p = os.path.join(self.source_dir, filename)
            is_video = os.path.splitext(p)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
            if is_video and os.path.exists(p):
                self.play_media(p)

    def _bind_shortcuts(self):
        self.bind("<Right>", lambda event: self._on_shortcut("save"))
        self.bind("<Return>", lambda event: self._on_shortcut("save"))
        self.bind("<Delete>", lambda event: self._on_shortcut("trash"))
        self.bind("<Escape>", lambda event: self._on_shortcut("skip"))
        self.bind("<space>", lambda event: self._on_shortcut("rotate"))
        self.bind("<Control-z>", lambda event: self._on_shortcut("undo"))

    def _on_shortcut(self, action):
        if self.is_copying: return
        # SECURITÉ (v1.12.6) : Ignorer les raccourcis si on tape dans un champ de texte
        # focus_get() peut retourner un widget interne de CustomTkinter, on vérifie donc le type
        focused = self.focus_get()
        if focused and (isinstance(focused, (ctk.CTkEntry, ctk.CTkTextbox)) or 'entry' in str(focused).lower()):
            return
            
        if self.awaiting_label: return # Ignorer si on attend un libellé
        if action == "save": self.process_photo("save")
        elif action == "trash": self.process_photo("trash")
        elif action == "skip": self.next_photo()
        elif action == "rotate":
            if self.idx < len(self.photos):
                filename = self.photos[self.idx]
                is_video = os.path.splitext(filename)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
                if is_video: return
            self.do_rotate()
        elif action == "undo": self.undo_last()

    def do_rotate(self):
        if self.is_copying: return
        if self.idx < len(self.photos):
            filename = self.photos[self.idx]
            is_video = os.path.splitext(filename)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
            if is_video:
                messagebox.showinfo("Rotation non disponible", "La rotation des fichiers vidéo n'est pas prise en charge.")
                return
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
                        # "Passer" ajouté pour l'action Corbeille (v1.12.9)
                        if "supprimer" in cmd or "corbeille" in cmd or "passer" in cmd or re.search(r'\b(non|nan|no|nope|nom)\b', cmd): 
                            self.after(0, lambda: self.process_photo("trash"))
                        elif "garder" in cmd or "sauvegarder" in cmd or re.search(r'\b(ok|okay|oui|ouais|yes|yep|we)\b', cmd): 
                            self.after(0, lambda: self.process_photo("save"))
                        elif "rotation" in cmd or "tourner" in cmd: 
                            if self.idx < len(self.photos):
                                filename = self.photos[self.idx]
                                is_video = os.path.splitext(filename)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
                                if is_video: continue
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
        mtime = os.path.getmtime(path)
        ctime = os.path.getctime(path)
        return datetime.fromtimestamp(min(mtime, ctime))

    def calculate_md5(self, file_path):
        """Calcule l'empreinte MD5 d'un fichier."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except: return None

    def generate_video_placeholder(self, path):
        """Génère une image de prévisualisation élégante pour les fichiers vidéo."""
        from PIL import ImageDraw, ImageFont
        width, height = 800, 600
        img = Image.new("RGBA", (width, height), "#1a252f")
        draw = ImageDraw.Draw(img)
        
        # Dessiner un bouton play stylisé au centre
        cx, cy = 400, 240
        r = 55
        # Cercle extérieur avec dégradé subtil/bordure
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill="#e67e22", outline="#d35400", width=4)
        
        # Triangle de lecture
        tr_w = 26
        tr_h = 32
        p1 = (cx - 8, cy - tr_h // 2)
        p2 = (cx - 8, cy + tr_h // 2)
        p3 = (cx + tr_w - 8, cy)
        draw.polygon([p1, p2, p3], fill="white")
        
        # Informations sur le fichier
        filename = os.path.basename(path)
        try:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            size_str = f"{size_mb:.2f} Mo"
        except:
            size_str = "Taille inconnue"
            
        ext = os.path.splitext(filename)[1].upper()
        
        text_title = f"FICHIER VIDÉO {ext}"
        text_desc = f"{filename}\n({size_str})"
        
        # Tentative d'utiliser des polices système standard pour un rendu premium
        font_title = None
        font_desc = None
        for font_name in ["arial.ttf", "calibri.ttf", "Segoe UI.ttf"]:
            try:
                font_title = ImageFont.truetype(font_name, 26)
                font_desc = ImageFont.truetype(font_name, 16)
                break
            except:
                pass
                
        if font_title and font_desc:
            w_t = draw.textlength(text_title, font=font_title)
            draw.text((400 - w_t//2, 350), text_title, fill="#f39c12", font=font_title)
            
            lines = text_desc.split('\n')
            curr_y = 400
            for line in lines:
                w_d = draw.textlength(line, font=font_desc)
                draw.text((400 - w_d//2, curr_y), line, fill="#ecf0f1", font=font_desc)
                curr_y += 24
        else:
            # Fallback simple
            draw.text((320, 350), text_title, fill="#f39c12")
            draw.text((300, 400), text_desc, fill="#ecf0f1")
            
        # Ajouter une note explicative moderne
        note_text = "▶ Cliquer ici pour lire la vidéo • Entrée / Flèche Droite pour classer"
        try:
            font_note = ImageFont.truetype("arial.ttf", 13) if font_title else None
            if font_note:
                w_n = draw.textlength(note_text, font=font_note)
                draw.text((400 - w_n//2, 520), note_text, fill="#7f8c8d", font=font_note)
            else:
                draw.text((250, 520), note_text, fill="#7f8c8d")
        except: pass
            
        return img

    def load_index(self):
        """Charge l'index et peuple les bases MD5 et Nom de fichier."""
        self.index_file = os.path.join(self.dest_dir, ".photosorter_index.json")
        self.checksum_db = {}
        self.filename_db = {}
        
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    raw_db = json.load(f)
                    
                # Normalisation du dossier de destination pour comparaison
                dest_norm = os.path.abspath(self.dest_dir).lower()
                
                for md5, path in raw_db.items():
                    path_norm = os.path.abspath(path)
                    # On garde si le fichier existe, même si le chemin racine a légèrement changé (v1.13.0)
                    if os.path.exists(path_norm):
                        self.checksum_db[md5] = path_norm
                        fname = os.path.basename(path_norm).lower()
                        self.filename_db[fname] = path_norm
                
                if len(self.checksum_db) != len(raw_db):
                    self.save_index()
            except: pass
        
        self.btn_reset_index.grid(row=15, column=0, padx=10, pady=(20, 0), sticky="e")

    def save_index(self):
        """Sauvegarde l'index des doublons."""
        if not self.dest_dir or not self.index_file: return
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.checksum_db, f, ensure_ascii=False, indent=2)
        except: pass

    def reset_duplicate_index(self):
        """Supprime l'index actuel et relance un scan."""
        if not self.dest_dir: return
        if messagebox.askyesno("Réinitialiser l'index", "Voulez-vous supprimer l'index des doublons et relancer un scan complet ?"):
            self.checksum_db = {}
            if os.path.exists(self.index_file):
                os.remove(self.index_file)
            self.start_background_scan()

    def start_background_scan(self):
        """Lance le scan de la destination en arrière-plan."""
        if self.is_scanning: return
        self.is_scanning = True
        self.scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self.scan_thread.start()

    def _scan_worker(self):
        extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.mp4', '.mov', '.heic', '.webp')
        count = 0
        # Création d'un set des chemins déjà indexés pour la performance
        indexed_paths = set(self.checksum_db.values())
        
        for root, dirs, files in os.walk(self.dest_dir, followlinks=True):
            # Feedback visuel du dossier en cours (tronqué si trop long)
            folder_name = os.path.basename(root)
            self.after(0, lambda f=folder_name: self.lbl_scan_status.configure(text=f"📂 Scan : {f}..."))
            
            for file in files:
                if file.lower().endswith(extensions):
                    full_path = os.path.normpath(os.path.join(root, file))
                    if full_path in indexed_paths:
                        count += 1
                        continue
                        
                    try:
                        md5 = self.calculate_md5(full_path)
                        if md5: 
                            self.checksum_db[md5] = full_path
                            self.filename_db[file.lower()] = full_path # Indexation nom
                            indexed_paths.add(full_path)
                            count += 1
                            if count % 20 == 0:
                                self.after(0, lambda c=count: self.lbl_scan_status.configure(text=f"🔍 Index : {c} fichiers"))
                    except: continue
            
            # Sauvegarde régulière par dossier
            self.save_index()
            time.sleep(0.001)
            
        self.is_scanning = False
        self.after(0, lambda c=count: self.lbl_scan_status.configure(text=f"✅ Index prêt ({c} photos)", text_color="#2ecc71"))
        self.save_index()

    def show_current(self):
        self.lbl_dup_warning.place_forget()
        self.frame_label.grid_forget()
        self.awaiting_label = False
        self.is_renaming = False
        
        # REPRISE DE FOCUS (v1.12.7) : Garantit que les raccourcis clavier fonctionnent
        self.focus_set()
        
        if self.idx < len(self.photos):
            self.update_ui_state()
            filename = self.photos[self.idx]
            p = os.path.join(self.source_dir, filename)
            
            # Affichage du sous-répertoire source (v1.13.21)
            subdir = os.path.dirname(filename)
            if subdir:
                self.lbl_src_subdir.configure(text=f"📂 Origine : {subdir}")
            else:
                self.lbl_src_subdir.configure(text="")
            
            self.lbl_filename.configure(text=os.path.basename(p))
            
            # Récupération de la date pour affichage
            date_obj = self.get_safe_date(p)
            self.lbl_file_date.configure(text=f"📅 Date : {date_obj.strftime('%d/%m/%Y')}")
            
            if not os.path.exists(p):
                self.image_label.configure(image="", text=f"⚠ Fichier introuvable :\n{self.photos[self.idx]}")
                self.image_label.image = None
                return

            # --- PRÉVISUALISATION DESTINATION (v1.12.1) ---
            self.update_folder_preview(p)

            # --- DÉTECTION DE DOUBLONS (v1.13.27) ---
            # Désormais basée UNIQUEMENT sur le contenu (Checksum MD5)
            # Les conflits de noms sans correspondance de contenu ne sont plus signalés.
            current_md5 = self.calculate_md5(p)
            found_path = None
            
            if current_md5 in self.checksum_db:
                found_path = self.checksum_db[current_md5]
                
                # Vérification de sécurité : le doublon existe-t-il vraiment sur le disque ?
                if not os.path.exists(found_path):
                    del self.checksum_db[current_md5]
                    # Nettoyage index nom par sécurité
                    fname_lower = os.path.basename(p).lower()
                    if fname_lower in self.filename_db: del self.filename_db[fname_lower]
                    found_path = None
                    self.save_index()
                else:
                    # Affichage du chemin relatif pour plus de clarté (v1.13.27)
                    rel_folder = os.path.relpath(os.path.dirname(found_path), self.dest_dir)
                    self.lbl_dup_warning.configure(text=f"⚠️ DOUBLON (CONTENU IDENTIQUE)\n(Déjà dans : {rel_folder})")
                    self.lbl_dup_warning.place(relx=0.5, rely=0.1, anchor="center")

            # Fallback v1.13.28 : Si non trouvé dans l'index, mais qu'un fichier du même nom 
            # existe déjà dans le dossier cible prédit, on compare leurs MD5 en direct.
            if not found_path and self.previewed_folder:
                potential_file = os.path.join(self.previewed_folder, os.path.basename(p))
                if os.path.exists(potential_file):
                    dest_md5 = self.calculate_md5(potential_file)
                    if dest_md5 and dest_md5 == current_md5:
                        found_path = potential_file
                        # On répare l'index au passage
                        self.checksum_db[current_md5] = potential_file
                        rel_folder = os.path.relpath(os.path.dirname(found_path), self.dest_dir)
                        self.lbl_dup_warning.configure(text=f"⚠️ DOUBLON (DÉTECTION DIRECTE)\n(Déjà dans : {rel_folder})")
                        self.lbl_dup_warning.place(relx=0.5, rely=0.1, anchor="center")

            # Détection du type de média
            is_video = os.path.splitext(p)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
            
            if is_video:
                try:
                    img = self.generate_video_placeholder(p)
                    ci = ctk.CTkImage(img, size=(800, 600))
                    self.image_label.configure(image=ci, text="", cursor="hand2")
                    self.image_label.image = ci
                except Exception as e:
                    self.image_label.configure(image=None, text=f"🎥 Fichier Vidéo :\n{os.path.basename(p)}", cursor="hand2")
            else:
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
                        self.image_label.configure(image=ci, text="", cursor="")
                        self.image_label.image = ci
                except Exception as e:
                    self.image_label.configure(image="", text=f"⚠ Erreur de lecture :\n{self.photos[self.idx]}\n(Format non supporté ou fichier corrompu)", cursor="")
                    self.image_label.image = None
        else: 
            # ÉCRAN DE FIN PROPRE (v1.12.8)
            self.update_ui_state()
            self.image_label.configure(image="", text="✨ Félicitations !\nTous vos médias (photos & vidéos) sont triés.", cursor="")
            self.image_label.image = None
            self.lbl_filename.configure(text="")
            self.lbl_file_date.configure(text="")
            self.lbl_dest_preview.configure(text="✅ Travail terminé", text_color="#2ecc71")
            self.frame_folder_actions.grid_forget()
            self.lbl_dup_warning.place_forget()

    def update_folder_preview(self, src_path):
        """Calcule et affiche le dossier de destination probable avant action."""
        self.previewed_folder = None
        if not self.dest_dir:
            self.lbl_dest_preview.configure(text="🎯 Destination non définie", text_color="#95a5a6", fg_color="transparent")
            self.frame_folder_actions.grid_forget()
            return

        try:
            p_norm = os.path.normpath(src_path)
            date_obj = self.get_safe_date(p_norm)
            date_prefix = date_obj.strftime('%Y-%m-%d')
            is_video = os.path.splitext(p_norm)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
            media_subfolder = "video" if is_video else "photo"
            year_folder = os.path.join(self.dest_dir, media_subfolder, date_obj.strftime('%Y'))

            # 1. Dossier de la session en cours
            if self.current_target_folder and os.path.exists(self.current_target_folder):
                if os.path.basename(self.current_target_folder).startswith(date_prefix):
                    self.lbl_dest_preview.configure(text=f"📂 {os.path.basename(self.current_target_folder)}", text_color="#2ecc71", fg_color="transparent")
                    self.previewed_folder = self.current_target_folder
                    self.frame_folder_actions.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
                    return

            # 2. Dossier existant sur le disque
            existing_folder = None
            if os.path.exists(year_folder):
                for d in os.listdir(year_folder):
                    if d.startswith(date_prefix):
                        existing_folder = os.path.join(year_folder, d)
                        break

            if existing_folder:
                self.lbl_dest_preview.configure(text=f"📁 {os.path.basename(existing_folder)}", text_color="#f1c40f", fg_color="transparent")
                self.previewed_folder = existing_folder
                self.frame_folder_actions.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
            else:
                self.lbl_dest_preview.configure(text=f"✨ Nouveau :\n{date_prefix} ...", text_color="#3498db", fg_color="transparent")
                self.frame_folder_actions.grid_forget()
            
            self.update_idletasks()
        except Exception as e:
            self.lbl_dest_preview.configure(text=f"⚠ Erreur : {str(e)[:20]}", text_color="#e74c3c", fg_color="transparent")
            self.update_idletasks()

    def process_photo(self, action):
        if self.is_copying: return "break"
        # Sécurité v1.13.22 : Ignorer si le prompt de saisie est ouvert
        if self.frame_label.winfo_viewable():
            return "break"
            
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
            is_video = os.path.splitext(src_path)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
            media_subfolder = "video" if is_video else "photo"
            year_folder = os.path.join(self.dest_dir, media_subfolder, date_obj.strftime('%Y'))
            
            # 1. On vérifie si le dossier courant de la session correspond à la date
            if self.current_target_folder and os.path.exists(self.current_target_folder):
                if os.path.basename(self.current_target_folder).startswith(date_prefix):
                    self.finalize_save(src_path, self.current_target_folder)
                    return

            # 2. Sinon, on cherche s'il existe UN dossier pour cette date
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

    def start_new_event(self):
        """Force la création d'un nouveau dossier pour la photo actuelle même si un existe."""
        if self.is_copying: return
        if self.idx >= len(self.photos): return
        self.is_renaming = False
        src_path = os.path.join(self.source_dir, self.photos[self.idx])
        date_obj = self.get_safe_date(src_path)
        self.temp_save_data = (src_path, date_obj)
        self.show_label_prompt()

    def show_label_prompt(self):
        self.awaiting_label = True
        self.lbl_dest_preview.configure(text="En attente de libellé...", text_color="#e74c3c")
        self.frame_folder_actions.grid_forget()
        self.lbl_prompt.configure(text="NOUVEAU DOSSIER !\nNommez l'événement :")
        self.frame_label.grid(row=6, column=0, padx=10, pady=5, sticky="ew")
        self.entry_label.delete(0, 'end')
        self.entry_label.focus()

    def start_rename(self):
        if self.is_copying: return
        target = self.current_target_folder or self.previewed_folder
        if not target: return
        
        # On définit le dossier à renommer comme dossier courant
        self.current_target_folder = target
        
        self.is_renaming = True
        self.awaiting_label = True
        self.lbl_prompt.configure(text="RENOMMER DOSSIER :\nNouveau libellé :")
        self.frame_label.grid(row=6, column=0, padx=10, pady=5, sticky="ew")
        
        # Pré-remplir avec le libellé actuel (après YYYY-MM-DD )
        current_name = os.path.basename(target)
        if len(current_name) >= 11:
            self.entry_label.delete(0, 'end')
            self.entry_label.insert(0, current_name[11:])
        self.entry_label.focus()

    def confirm_label(self, label_text):
        if not self.awaiting_label: return "break"
        self.awaiting_label = False
        self.frame_label.grid_forget()
        self.focus_set() # Rendre le focus à la fenêtre principale
        
        if self.is_renaming:
            self.execute_rename(label_text)
            self.is_renaming = False
            return
            
        src_path, date_obj = self.temp_save_data
        
        folder_name = f"{date_obj.strftime('%Y-%m-%d')} {label_text}".strip()
        is_video = os.path.splitext(src_path)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
        media_subfolder = "video" if is_video else "photo"
        target_folder = os.path.join(self.dest_dir, media_subfolder, date_obj.strftime('%Y'), folder_name)
        os.makedirs(target_folder, exist_ok=True)
        
        self.finalize_save(src_path, target_folder)
        return "break"

    def execute_rename(self, new_label):
        old_path = self.current_target_folder
        if not old_path or not os.path.exists(old_path): return
        
        parent = os.path.dirname(old_path)
        base = os.path.basename(old_path)
        prefix = base[:10] # YYYY-MM-DD
        
        new_name = f"{prefix} {new_label}".strip()
        new_path = os.path.normpath(os.path.join(parent, new_name))
        old_path = os.path.normpath(old_path)
        
        # Gestion spécifique Windows : Changement de casse uniquement
        if old_path.lower() == new_path.lower() and old_path != new_path:
            try:
                # Sur Windows, on ne peut pas renommer directement "A" en "a"
                # Il faut passer par un nom temporaire
                temp_path = old_path + "_temp_rename"
                os.rename(old_path, temp_path)
                os.rename(temp_path, new_path)
                self.current_target_folder = new_path
                self.lbl_dest_preview.configure(text=f"📁 Dossier : {os.path.basename(new_path)}")
                return
            except Exception as e:
                messagebox.showerror("Erreur", f"Échec du changement de casse : {e}")
                return

        if old_path == new_path: return
        
        try:
            if os.path.exists(new_path):
                # Fusionner si le dossier existe déjà
                for f in os.listdir(old_path):
                    src_f = os.path.join(old_path, f)
                    dst_f = os.path.join(new_path, f)
                    
                    # Gestion des conflits de noms de fichiers lors de la fusion
                    if os.path.exists(dst_f):
                        name, ext = os.path.splitext(f)
                        counter = 1
                        while os.path.exists(os.path.join(new_path, f"{name}_{counter}{ext}")):
                            counter += 1
                        dst_f = os.path.join(new_path, f"{name}_{counter}{ext}")
                    
                    shutil.move(src_f, dst_f)
                
                # Petite pause pour laisser Windows libérer les handles
                time.sleep(0.2)
                
                # Tentative de suppression robuste
                try:
                    os.rmdir(old_path)
                except OSError:
                    # Si rmdir échoue (ex: Thumbs.db réapparu), on tente un nettoyage forcé
                    for f in os.listdir(old_path):
                        try: os.remove(os.path.join(old_path, f))
                        except: pass
                    time.sleep(0.1)
                    try: os.rmdir(old_path)
                    except: pass # Si ça échoue encore, on laisse tomber pour ne pas bloquer l'utilisateur
            else:
                os.rename(old_path, new_path)
                
            self.current_target_folder = new_path
            self.lbl_dest_preview.configure(text=f"📁 Dossier : {os.path.basename(new_path)}")
            
            # Mettre à jour l'historique pour éviter de casser l'Undo
            for h in self.history:
                if "dest" in h and h["dest"]:
                    h["dest"] = os.path.normpath(h["dest"])
                    if h["dest"].startswith(old_path):
                        h["dest"] = h["dest"].replace(old_path, new_path)
            
            # Mettre à jour l'index des doublons (v1.13.25)
            # On met à jour les chemins dans les bases MD5 et Nom
            self.checksum_db = {k: (v.replace(old_path, new_path) if v.startswith(old_path) else v) 
                               for k, v in self.checksum_db.items()}
            self.filename_db = {k: (v.replace(old_path, new_path) if v.startswith(old_path) else v) 
                               for k, v in self.filename_db.items()}
            self.save_index()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec du renommage : {e}")


    def set_ui_buttons_state(self, state):
        # La rotation n'est disponible que pour les photos (v1.14.7)
        if state == "normal":
            t = len(self.photos)
            if t > 0 and self.idx < t:
                filename = self.photos[self.idx]
                is_video = os.path.splitext(filename)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
                self.btn_rotate.configure(state="disabled" if is_video else "normal")
            else:
                self.btn_rotate.configure(state="disabled")
        else:
            self.btn_rotate.configure(state="disabled")
            
        self.btn_trash.configure(state=state)
        self.btn_save.configure(state=state)
        self.btn_undo.configure(state="normal" if state == "normal" and self.history else "disabled")
        self.btn_src.configure(state=state)
        self.btn_dest.configure(state=state)
        try:
            self.btn_rename.configure(state=state)
            self.btn_new_event.configure(state=state)
        except: pass

    def finalize_save(self, src_path, target_folder):
        # Sécurité : On s'assure que le dossier cible existe bien
        try:
            os.makedirs(target_folder, exist_ok=True)
        except: pass
        
        self.current_target_folder = target_folder
        self.lbl_dest_preview.configure(text=f"📁 Dossier : {os.path.basename(target_folder)}", text_color="#2ecc71")
        self.frame_folder_actions.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        filename = os.path.basename(src_path)
        dest_path = os.path.join(target_folder, filename)
        
        # Gestion des conflits de noms
        final_dest = os.path.normpath(dest_path)
        counter = 1
        name, ext = os.path.splitext(filename)
        while os.path.exists(final_dest):
            final_dest = os.path.join(target_folder, f"{name}_{counter}{ext}")
            counter += 1
            
        is_video = os.path.splitext(src_path)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')

        # Activer le verrou de copie et désactiver le UI
        self.is_copying = True
        self.set_ui_buttons_state("disabled")

        if is_video:
            self.lbl_scan_status.configure(text="⚡ Copie de la vidéo en cours...", text_color="#e67e22")
            self.image_label.configure(text=f"⚡ Classement et copie de la vidéo en cours...\n\n{filename}\n\nVeuillez patienter...", image="")
            self.image_label.image = None
        else:
            self.lbl_scan_status.configure(text="⚡ Enregistrement...", text_color="#e67e22")

        def _background_copy():
            try:
                if is_video:
                    shutil.copy2(src_path, final_dest)
                else:
                    # OPTIMISATION v1.13.28 : Préservation de l'original si aucune transformation n'est requise.
                    needs_transform = (self.rotation != 0)
                    if not needs_transform:
                        try:
                            exif_dict = piexif.load(src_path)
                            orientation = exif_dict.get("0th", {}).get(piexif.ImageIFD.Orientation, 1)
                            if orientation != 1:
                                needs_transform = True
                        except: pass

                    if not needs_transform:
                        shutil.copy2(src_path, final_dest)
                    else:
                        with Image.open(src_path) as img:
                            img = ImageOps.exif_transpose(img)
                            if self.rotation != 0: 
                                img = img.rotate(self.rotation, expand=True)
                            
                            is_bmp = final_dest.lower().endswith('.bmp')
                            if is_bmp:
                                img.save(final_dest)
                            else:
                                try:
                                    exif_dict = piexif.load(src_path)
                                    if "0th" in exif_dict and piexif.ImageIFD.Orientation in exif_dict["0th"]:
                                        exif_dict["0th"][piexif.ImageIFD.Orientation] = 1 # Normalisation
                                    
                                    exif_bytes = piexif.dump(exif_dict)
                                    img.save(final_dest, quality=95, exif=exif_bytes)
                                except: 
                                    img.save(final_dest, quality=95)
                
                try:
                    stat = os.stat(src_path)
                    os.utime(final_dest, (stat.st_atime, stat.st_mtime))
                except: pass
                
                self.after(0, lambda: self._on_copy_success(src_path, final_dest, filename))
            except Exception as e:
                # Fallback ultime en cas de problème
                try:
                    shutil.copy2(src_path, final_dest)
                    self.after(0, lambda: self._on_copy_success(src_path, final_dest, filename))
                except Exception as copy_err:
                    self.after(0, lambda err=copy_err: self._on_copy_error(err))

        threading.Thread(target=_background_copy, daemon=True).start()

    def _on_copy_success(self, src_path, final_dest, filename):
        self.is_copying = False
        self.set_ui_buttons_state("normal")
        self.lbl_scan_status.configure(text="✅ Classement effectué", text_color="#2ecc71")
        
        # Mémoriser dans l'index
        md5 = self.calculate_md5(final_dest)
        if md5: 
            self.checksum_db[md5] = final_dest
            self.save_index()

        archive_dir = os.path.join(self.source_dir, "_archive_traitee")
        os.makedirs(archive_dir, exist_ok=True)
        
        # Gestion des doublons dans l'archive (v1.13.19)
        arch_path = os.path.join(archive_dir, filename)
        if os.path.exists(arch_path):
            name, ext = os.path.splitext(filename)
            arch_path = os.path.join(archive_dir, f"{name}_{int(time.time())}{ext}")
            
        try:
            shutil.move(src_path, arch_path)
            self.history.append({"action": "save", "src": src_path, "dest": final_dest, "arch": arch_path})
        except Exception as e:
            messagebox.showerror("Erreur Archivage", f"Impossible d'archiver le fichier original :\n{e}")
            
        self.next_photo()

    def _on_copy_error(self, err):
        self.is_copying = False
        self.set_ui_buttons_state("normal")
        self.lbl_scan_status.configure(text="❌ Erreur de classement", text_color="#e74c3c")
        messagebox.showerror("Erreur Fatale", f"Impossible de copier le fichier :\n{err}")
        self.show_current()

    def finalize_trash(self, src_path):
        trash_dir = os.path.join(self.source_dir, "_corbeille_tri")
        os.makedirs(trash_dir, exist_ok=True)
        filename = os.path.basename(src_path)
        arch_path = os.path.join(trash_dir, filename)
        
        # Gestion des doublons dans la corbeille (v1.13.19)
        if os.path.exists(arch_path):
            name, ext = os.path.splitext(filename)
            arch_path = os.path.join(trash_dir, f"{name}_{int(time.time())}{ext}")
            
        shutil.move(src_path, arch_path)
        self.history.append({"action": "trash", "src": src_path, "arch": arch_path})
        self.next_photo()

    def next_photo(self):
        self.idx += 1
        self.rotation = 0
        self.update_ui_state()
        self.show_current()

    def undo_last(self):
        if self.is_copying: return
        if not self.history: return
        h = self.history.pop()
        try:
            if os.path.exists(h["arch"]):
                # 1. On restaure le fichier source
                shutil.move(h["arch"], h["src"])
                
                # 2. Si c'était un classement, on nettoie la destination et l'INDEX
                if h["action"] == "save":
                    if os.path.exists(h["dest"]):
                        # Retirer de l'index MD5 (v1.12.4)
                        md5_to_remove = self.calculate_md5(h["dest"])
                        if md5_to_remove in self.checksum_db:
                            del self.checksum_db[md5_to_remove]
                        
                        os.remove(h["dest"])
                        self.save_index()

                # 3. On recule l'index
                self.idx -= 1
                self.awaiting_label = False # Sécurité (v1.12.5)
                self.frame_label.grid_forget()
                self.update_ui_state()
                
                # Petite pause pour laisser l'OS libérer le fichier
                self.after(50, self.show_current)
            else:
                messagebox.showerror("Erreur Annuler", "Impossible de retrouver le fichier dans l'archive/corbeille.")
        except Exception as e:
            messagebox.showerror("Erreur Annuler", f"Erreur lors de la restauration :\n{e}")

    def load_source(self):
        p = filedialog.askdirectory()
        if p:
            if hasattr(self, 'dest_dir') and self.dest_dir and os.path.normpath(p) == os.path.normpath(self.dest_dir):
                messagebox.showerror("Erreur", "Le dossier source ne peut pas être le même que le dossier de destination !")
                return
            self.source_dir = p
            self.lbl_src_path.configure(text=p)
            self.btn_rename.grid_forget()
            self.current_target_folder = None
            
            # Scan récursif v1.13.20
            self.photos = []
            video_count = 0
            other_count = 0
            photo_ext = ('.jpg', '.jpeg', '.png', '.bmp')
            video_ext = ('.mov', '.mp4', '.avi', '.mkv', '.api')
            
            for root, dirs, files in os.walk(p):
                # On ignore nos propres dossiers techniques
                if "_archive_traitee" in root or "_corbeille_tri" in root:
                    continue
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in photo_ext or ext in video_ext:
                        # On stocke le chemin relatif
                        rel_path = os.path.relpath(os.path.join(root, file), p)
                        self.photos.append(rel_path)
                        if ext in video_ext:
                            video_count += 1
                    else:
                        other_count += 1
            
            self.lbl_video_info.configure(text=f"🎥 {video_count} vidéos prêtes à trier")
            self.lbl_other_files_info.configure(text=f"📁 {other_count} fichiers restants (hors médias)")
            self.idx = 0
            self.update_ui_state()
            self.show_current()

    def load_dest(self):
        p = filedialog.askdirectory()
        if p:
            if hasattr(self, 'source_dir') and self.source_dir and os.path.normpath(p) == os.path.normpath(self.source_dir):
                messagebox.showerror("Erreur", "Le dossier de destination ne peut pas être le même que le dossier source !")
                return
            self.dest_dir = p
            self.lbl_dest_path.configure(text=p)
            try: self.lbl_dest_preview.configure(text="")
            except: pass
            self.btn_rename.grid_forget()
            self.current_target_folder = None
            self.load_index()
            self.start_background_scan()
            self.show_current() # CRUCIAL : Relancer l'analyse v1.13.11

    def update_ui_state(self):
        t = len(self.photos)
        if t > 0:
            if self.idx >= t:
                self.lbl_stats.configure(text=f"{t} / {t}")
                self.progress_bar.set(1.0)
            else:
                self.lbl_stats.configure(text=f"{self.idx + 1} / {t}")
                self.progress_bar.set(self.idx / t)
        else:
            self.lbl_stats.configure(text="0 / 0")
            self.progress_bar.set(0)
            
        self.btn_undo.configure(state="normal" if self.history else "disabled")
        
        # Gestion dynamique de l'activation du bouton rotation (v1.14.7)
        if t > 0 and self.idx < t:
            filename = self.photos[self.idx]
            is_video = os.path.splitext(filename)[1].lower() in ('.mov', '.mp4', '.avi', '.mkv', '.api')
            self.btn_rotate.configure(state="disabled" if is_video else "normal")
        else:
            self.btn_rotate.configure(state="disabled")

if __name__ == "__main__":
    app = ModernPhotoSorter()
    app.mainloop()