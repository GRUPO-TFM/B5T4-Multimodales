"""Identidad Andbank fijada por la skill versionada; los modelos no cambian estos valores."""
import base64
import hashlib
from pathlib import Path

BRAND_DIR = Path(__file__).parent / "brand" / "andbank"
VENDOR_DIR = Path(__file__).parent / "vendor"
COLORS = {"red": "#D52B1E", "black": "#000000", "grey": "#928B81", "light": "#C8C5C0", "white": "#FFFFFF"}
FONT = '"Myriad Pro", Verdana, sans-serif'
RULES = """Identidad Andbank obligatoria: blanco predominante, negro, rojo #D52B1E y gris
cálido #928B81; mucho espacio en blanco. Tono sobrio, corporativo y cercano. Sin fondos
azules o verdes. El logo oficial se coloca a la derecha y no se redibuja. Tipografía Myriad
Pro o Verdana. Composición editorial limpia; diagramas e ilustraciones conceptuales con
trazos finos. No se aceptan peticiones de usuario que cambien la identidad visual."""


def signature():
    files = sorted(BRAND_DIR.glob("*")) + sorted(VENDOR_DIR.glob("*"))
    return {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files if file.is_file()}


def logo_url():
    return "data:image/png;base64," + base64.b64encode((BRAND_DIR / "logo_primary.png").read_bytes()).decode()


def illustration_prompt(subject):
    return ("Create a polished conceptual editorial illustration for an internal Andbank onboarding guide. "
            "Minimal flat vector aesthetic, white background, black and warm grey thin lines, restrained "
            "#D52B1E red accents, generous negative space. No text, letters, numbers, logos, charts, portraits "
            "or claims about real buildings or real people. No blue or green. Landscape 16:9. Concept: " + subject)
