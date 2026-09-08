# -*- coding: utf-8 -*-
"""Núcleo del generador CARPETA_KML, reutilizado tal cual desde
REGISTRO_FOTOGRAFICO/CARPETA_KML/src/carpeta_kml_core.py -- ya era codigo
puro sin Tkinter, apto para un backend web sin cambios.

Recorre un directorio raíz con subcarpetas (una por punto/predio/sitio),
extrae las coordenadas GPS de los metadatos EXIF de las fotografías,
evita nombres duplicados asignando números consecutivos, y construye un
archivo KMZ autónomo con las fotos embebidas y visor HTML en cada Placemark.
En la version web, ese directorio raiz se arma extrayendo un .zip subido
por el navegador a una carpeta temporal.
"""

from __future__ import annotations

import html
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageOps

try:
    import exifread
except ImportError:
    exifread = None


@dataclass
class PointRecord:
    original_folder_name: str
    placemark_name: str
    folder_path: Path
    lat: float
    lon: float
    photos: List[Path] = field(default_factory=list)


def parse_dms_rational(val) -> Optional[float]:
    """Convierte tupla/lista de 3 números racionales a grados decimales."""
    try:
        if hasattr(val, "values") and len(val.values) >= 3:
            d = float(val.values[0].num) / float(val.values[0].den)
            m = float(val.values[1].num) / float(val.values[1].den)
            s = float(val.values[2].num) / float(val.values[2].den)
            return d + (m / 60.0) + (s / 3600.0)
        elif isinstance(val, (list, tuple)) and len(val) >= 3:
            def _num(x):
                if hasattr(x, "num") and hasattr(x, "den"):
                    return float(x.num) / float(x.den)
                return float(x)
            return _num(val[0]) + (_num(val[1]) / 60.0) + (_num(val[2]) / 3600.0)
    except Exception:
        return None
    return None


def extract_gps_from_exif(image_path: Path | str) -> Optional[Tuple[float, float]]:
    """Extrae coordenadas GPS (lat, lon) descartando ceros y tags corruptos."""
    path = Path(image_path)
    if not path.is_file():
        return None

    # Método 1: exifread
    if exifread is not None:
        try:
            with open(path, "rb") as f:
                tags = exifread.process_file(f, details=False)
                lat_tag = tags.get("GPS GPSLatitude")
                lat_ref = tags.get("GPS GPSLatitudeRef")
                lon_tag = tags.get("GPS GPSLongitude")
                lon_ref = tags.get("GPS GPSLongitudeRef")
                if lat_tag and lat_ref and lon_tag and lon_ref:
                    lat = parse_dms_rational(lat_tag)
                    lon = parse_dms_rational(lon_tag)
                    if lat is not None and lon is not None:
                        if str(lat_ref).strip().upper() == "S":
                            lat = -lat
                        if str(lon_ref).strip().upper() == "W":
                            lon = -lon
                        if not (abs(lat) < 1e-5 and abs(lon) < 1e-5):
                            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                                return (lat, lon)
        except Exception:
            pass

    # Método 2: Fallback Pillow
    try:
        with Image.open(path) as img:
            exif_data = img.getexif()
            if not exif_data:
                return None
            from PIL.ExifTags import GPSTAGS, TAGS
            gps_info = {}
            for key, val in exif_data.items():
                if TAGS.get(key) == "GPSInfo":
                    gps_info = val
                    break
            if not gps_info:
                # Puede estar en ifd(0x8825)
                try:
                    gps_info = exif_data.get_ifd(0x8825)
                except Exception:
                    pass

            if gps_info:
                gps_tags = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}
                lat_raw = gps_tags.get("GPSLatitude")
                lat_ref = gps_tags.get("GPSLatitudeRef")
                lon_raw = gps_tags.get("GPSLongitude")
                lon_ref = gps_tags.get("GPSLongitudeRef")
                if lat_raw and lat_ref and lon_raw and lon_ref:
                    lat = parse_dms_rational(lat_raw)
                    lon = parse_dms_rational(lon_raw)
                    if lat is not None and lon is not None:
                        if str(lat_ref).strip().upper() == "S":
                            lat = -lat
                        if str(lon_ref).strip().upper() == "W":
                            lon = -lon
                        if not (abs(lat) < 1e-5 and abs(lon) < 1e-5):
                            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                                return (lat, lon)
    except Exception:
        pass

    return None


def sanitize_filename(name: str) -> str:
    """Limpia caracteres inválidos para nombres de archivos."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", name)
    return cleaned.strip()


def deduplicate_name(base_name: str, used_names: set[str], counts: dict[str, int]) -> str:
    """Garantiza que un nombre de Placemark sea único agregando consecutivos (2), (3), etc."""
    clean = base_name.strip() or "Punto"
    clean_lower = clean.lower()
    
    if clean_lower not in counts:
        counts[clean_lower] = 1
        used_names.add(clean)
        return clean

    counts[clean_lower] += 1
    new_name = f"{clean} ({counts[clean_lower]})"
    while new_name.lower() in [n.lower() for n in used_names]:
        counts[clean_lower] += 1
        new_name = f"{clean} ({counts[clean_lower]})"
    
    used_names.add(new_name)
    return new_name


def optimize_image(
    src_path: Path,
    dest_path: Path,
    max_dimension: int = 1280,
    jpeg_quality: int = 85,
) -> bool:
    """Redimensiona y optimiza una imagen respetando su orientación EXIF."""
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src_path) as img:
            # Enderezar si trae rotación en EXIF
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            img.save(dest_path, format="JPEG", quality=jpeg_quality, optimize=True)
            return True
    except Exception:
        # Si falla optimización, copiar archivo original
        try:
            import shutil
            shutil.copy2(src_path, dest_path)
            return True
        except Exception:
            return False


def build_kml_document(points: List[PointRecord], project_title: str = "Puntos de Campo") -> str:
    """Construye el contenido XML de doc.kml."""
    kml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '  <Document>',
        f'    <name>{html.escape(project_title)}</name>',
        '    <open>1</open>',
        '    <Style id="photoPoint">',
        '      <IconStyle>',
        '        <scale>1.1</scale>',
        '        <Icon>',
        '          <href>http://maps.google.com/mapfiles/kml/shapes/camera.png</href>',
        '        </Icon>',
        '      </IconStyle>',
        '    </Style>',
        '    <Folder>',
        f'      <name>{html.escape(project_title)}</name>',
        '      <open>1</open>',
    ]

    for p_idx, p in enumerate(points, 1):
        # Armar HTML de fotos
        photos_html_list = []
        for f_idx, photo_name in enumerate(p.photos, 1):
            esc_name = html.escape(photo_name.name)
            resource_name = f"{p_idx:03d}_{f_idx:02d}_{esc_name}"
            photos_html_list.append(
                f'<div style="display: inline-block; margin: 4px; text-align: center;">'
                f'  <a href="files/{resource_name}" target="_blank" title="Clic para ampliar">'
                f'    <img src="files/{resource_name}" width="220" style="border-radius: 4px; border: 1px solid #ccc; max-height: 180px; object-fit: cover;" />'
                f'  </a><br/>'
                f'  <span style="font-size: 10px; color: #666;">{esc_name}</span>'
                f'</div>'
            )

        photos_section = "".join(photos_html_list) if photos_html_list else "<p><i>Sin fotografías</i></p>"

        desc = (
            f'<div style="font-family: Segoe UI, Arial, sans-serif; max-width: 480px; color: #222;">'
            f'  <h3 style="color: #1b4d3e; margin-top: 0; margin-bottom: 6px; border-bottom: 2px solid #a3b18a; padding-bottom: 4px;">{html.escape(p.placemark_name)}</h3>'
            f'  <table style="font-size: 12px; margin-bottom: 10px; width: 100%;">'
            f'    <tr><td><b>Carpeta origen:</b></td><td>{html.escape(p.original_folder_name)}</td></tr>'
            f'    <tr><td><b>Latitud:</b></td><td>{p.lat:.6f}°</td></tr>'
            f'    <tr><td><b>Longitud:</b></td><td>{p.lon:.6f}°</td></tr>'
            f'    <tr><td><b>Total fotos:</b></td><td>{len(p.photos)}</td></tr>'
            f'  </table>'
            f'  <div style="max-height: 380px; overflow-y: auto; background: #f9f9f9; padding: 6px; border: 1px solid #eee; border-radius: 4px;">'
            f'    {photos_section}'
            f'  </div>'
            f'</div>'
        )

        kml_lines.extend([
            '      <Placemark>',
            f'        <name>{html.escape(p.placemark_name)}</name>',
            '        <styleUrl>#photoPoint</styleUrl>',
            '        <description>',
            f'          <![CDATA[{desc}]]>',
            '        </description>',
            '        <Point>',
            f'          <coordinates>{p.lon:.7f},{p.lat:.7f},0</coordinates>',
            '        </Point>',
            '      </Placemark>',
        ])

    kml_lines.extend([
        '    </Folder>',
        '  </Document>',
        '</kml>',
    ])

    return "\n".join(kml_lines)


def process_folders_to_kmz(
    root_folder: Path | str,
    output_kmz_path: Path | str,
    max_photo_dimension: int = 1280,
    jpeg_quality: int = 85,
    log_fn: Optional[Callable[[str], None]] = None,
    progress_fn: Optional[Callable[[int, int], None]] = None,
) -> Tuple[int, int, Path]:
    """Procesa una carpeta raíz y genera un KMZ con puntos y fotos embebidas.
    
    Retorna: (total_puntos_creados, total_fotos_embebidas, ruta_kmz)
    """
    def _log(msg: str):
        if log_fn:
            log_fn(msg)

    root = Path(root_folder).resolve()
    if not root.is_dir():
        raise ValueError(f"La carpeta raíz especificada no existe: {root}")

    out_kmz = Path(output_kmz_path).resolve()
    out_kmz.parent.mkdir(parents=True, exist_ok=True)

    _log(f"Iniciando escaneo en: {root}")

    # Encontrar todas las subcarpetas directas o que contienen fotos
    subdirs = [p for p in root.iterdir() if p.is_dir()]
    if not subdirs:
        raise ValueError("No se encontraron subcarpetas dentro del directorio raíz seleccionado.")

    subdirs.sort(key=lambda p: p.name.lower())
    total_subdirs = len(subdirs)
    _log(f"Se encontraron {total_subdirs} subcarpetas para procesar.")

    used_names: set[str] = set()
    name_counts: dict[str, int] = {}
    points: List[PointRecord] = []
    sin_coordenadas: List[str] = []

    for idx, folder in enumerate(subdirs, 1):
        if progress_fn:
            progress_fn(idx, total_subdirs)

        folder_name = folder.name
        # Buscar fotos dentro de la subcarpeta (recursivo por si hay subcarpetas como marcadas)
        photos = []
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                photos.append(p)

        if not photos:
            _log(f"  [OMITIDA] '{folder_name}' - No contiene fotografías.")
            continue

        # Ordenar fotos alfabéticamente
        photos.sort(key=lambda x: x.name.lower())

        # Extraer coordenadas de las fotos
        valid_coords: List[Tuple[float, float]] = []
        for ph in photos:
            coord = extract_gps_from_exif(ph)
            if coord:
                valid_coords.append(coord)

        if not valid_coords:
            _log(f"  [SIN COORDENADAS] '{folder_name}' ({len(photos)} fotos) - Ninguna foto tiene GPS.")
            sin_coordenadas.append(folder_name)
            continue

        # Centroide (promedio) de las coordenadas válidas encontradas
        avg_lat = sum(c[0] for c in valid_coords) / len(valid_coords)
        avg_lon = sum(c[1] for c in valid_coords) / len(valid_coords)

        # Deduplicar nombre de Placemark
        placemark_name = deduplicate_name(folder_name, used_names, name_counts)

        points.append(
            PointRecord(
                original_folder_name=folder_name,
                placemark_name=placemark_name,
                folder_path=folder,
                lat=avg_lat,
                lon=avg_lon,
                photos=photos,
            )
        )
        _log(f"  [OK] '{placemark_name}' -> Lat: {avg_lat:.5f}, Lon: {avg_lon:.5f} ({len(photos)} fotos, {len(valid_coords)} con GPS)")

    if not points:
        raise ValueError(
            "Ninguna subcarpeta contenía fotos con coordenadas GPS válidas. No se puede generar el KML."
        )

    _log(f"\nGenerando archivo KMZ con {len(points)} puntos georreferenciados...")

    with tempfile.TemporaryDirectory(prefix="carpeta_kml_") as temp_dir:
        temp_path = Path(temp_dir)
        files_dir = temp_path / "files"
        files_dir.mkdir(parents=True, exist_ok=True)

        total_photos_count = 0
        for p_idx, p in enumerate(points, 1):
            for f_idx, photo_path in enumerate(p.photos, 1):
                safe_name = photo_path.name
                dest_filename = f"{p_idx:03d}_{f_idx:02d}_{safe_name}"
                dest_file = files_dir / dest_filename

                if max_photo_dimension > 0:
                    optimize_image(photo_path, dest_file, max_photo_dimension, jpeg_quality)
                else:
                    import shutil
                    shutil.copy2(photo_path, dest_file)

                total_photos_count += 1

        # Construir KML
        kml_content = build_kml_document(points, project_title=root.name)
        kml_path = temp_path / "doc.kml"
        kml_path.write_text(kml_content, encoding="utf-8")

        # Comprimir a KMZ
        _log(f"Empaquetando KMZ en: {out_kmz} ...")
        with zipfile.ZipFile(out_kmz, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(kml_path, arcname="doc.kml")
            for f in files_dir.iterdir():
                if f.is_file():
                    zf.write(f, arcname=f"files/{f.name}")

    _log(f"\n¡Éxito! KMZ creado con {len(points)} puntos y {total_photos_count} fotos embebidas.")
    if sin_coordenadas:
        _log(f"Aviso: {len(sin_coordenadas)} carpetas no tenían coordenadas GPS y fueron omitidas.")

    return len(points), total_photos_count, out_kmz
