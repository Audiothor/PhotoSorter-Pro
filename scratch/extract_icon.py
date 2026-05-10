from PIL import Image
import os

# Chemins
base_path = r"c:\Users\comme\Documents\GitHub\PhotoSorter Pro"
img_path = os.path.join(base_path, "assets", "illustration.png")
out_path = os.path.join(base_path, "assets", "app_icon.png")

if os.path.exists(img_path):
    img = Image.open(img_path)
    # On essaye de trouver l'icone dans le coin supérieur gauche.
    # Dans l'illustration générée, elle est souvent vers (40, 40) avec une taille d'environ 60-80px.
    # On va prendre un crop généreux et le retailler si besoin.
    # On va chercher l'icone circulaire.
    
    # Basé sur le mockup typique:
    # On crop le haut gauche (0, 0, 150, 150) puis on réduit
    icon = img.crop((45, 45, 125, 125)) # Zone approximative de l'icone
    icon.save(out_path)
    print("Icone extraite avec succès.")
else:
    print("Illustration introuvable.")
