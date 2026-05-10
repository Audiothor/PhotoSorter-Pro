from PIL import Image
import os

base_path = r"c:\Users\comme\Documents\GitHub\PhotoSorter Pro"
img_path = os.path.join(base_path, "assets", "illustration.png")

if os.path.exists(img_path):
    img = Image.open(img_path)
    # On va chercher plus bas. 
    # Les boutons (rouge/jaune/vert) étaient en haut.
    # L'icone est probablement juste en dessous.
    icon = img.crop((40, 160, 140, 260)) 
    icon.save(os.path.join(base_path, "assets", "app_icon.png"))
    print("Nouvel essai d'extraction réussi.")
else:
    print("Illustration introuvable.")
