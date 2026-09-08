"""Version web (Streamlit) de la herramienta CARPETA_KML: sube un .zip con
una carpeta por punto/predio/sitio (cada una con sus fotos con GPS en el
EXIF) y descarga un KMZ autonomo con un Placemark por carpeta y un visor
HTML con miniaturas al hacer clic. Misma logica de negocio que la app de
escritorio, solo cambia la entrada: subir un .zip por el navegador en vez
de elegir una carpeta local.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from logica import process_folders_to_kmz

_LOGO_GEOTEC = Path(__file__).resolve().parent / "assets" / "logo_geotec.png"

st.set_page_config(page_title="Carpeta a KML", page_icon=str(_LOGO_GEOTEC), layout="centered")


def _password_ok() -> bool:
    if st.session_state.get("autenticado"):
        return True

    col_logo, col_titulo = st.columns([1, 4], vertical_alignment="center")
    with col_logo:
        st.image(str(_LOGO_GEOTEC), width=140)
    with col_titulo:
        st.title("🗂️ Carpeta a KML")
    st.caption("Acceso restringido — pide la contraseña a quien administra esta herramienta.")
    clave_ingresada = st.text_input("Contraseña", type="password")
    entrar = st.button("Entrar", type="primary")

    if entrar:
        try:
            clave_real = st.secrets["APP_PASSWORD"]
        except Exception:
            st.error(
                "La app no tiene configurada la contraseña (falta APP_PASSWORD en Secrets). "
                "Configúrala en el panel de Streamlit Cloud antes de compartir el link."
            )
            return False
        if clave_ingresada == clave_real:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


if not _password_ok():
    st.stop()

# ─────────────────────────────────────────────
# App principal (solo se ve tras autenticarse)
# ─────────────────────────────────────────────

col_logo, col_titulo = st.columns([1, 4], vertical_alignment="center")
with col_logo:
    st.image(str(_LOGO_GEOTEC), width=140)
with col_titulo:
    st.title("🗂️ Generador de KMZ — Carpeta a KML")
st.caption(
    "Sube un .zip que contenga una carpeta por punto/predio/sitio, cada una con sus "
    "fotos (con GPS en el EXIF). Se genera un KMZ con un Placemark por carpeta "
    "(coordenada = centroide de sus fotos) y un visor con miniaturas."
)

with st.expander("¿Cómo debe estar organizado el .zip?"):
    st.markdown(
        """
        ```
        mi_proyecto.zip
        ├── Punto 1/
        │   ├── foto1.jpg
        │   └── foto2.jpg
        ├── Punto 2/
        │   └── foto1.jpg
        └── ...
        ```
        Cada subcarpeta de primer nivel es un punto; su nombre se usa como
        nombre del Placemark. Comprime la carpeta completa (clic derecho →
        "Enviar a → Carpeta comprimida" en Windows) y sube ese .zip aquí.
        """
    )

titulo_proyecto = st.text_input("Título del proyecto (nombre del KMZ y de la carpeta raíz en el visor)")
max_dimension = st.slider(
    "Tamaño máximo de las fotos embebidas (px)",
    min_value=640,
    max_value=2560,
    value=1280,
    step=64,
    help="Las fotos se redimensionan a este máximo antes de empaquetarlas, para que el KMZ no pese demasiado.",
)

archivo_zip = st.file_uploader("Archivo .zip con las carpetas por punto", type=["zip"])

if archivo_zip and st.button("Generar KMZ", type="primary"):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        extraccion = tmp_path / "extraido"
        extraccion.mkdir()

        try:
            with zipfile.ZipFile(archivo_zip) as zf:
                zf.extractall(extraccion)
        except zipfile.BadZipFile:
            st.error("El archivo subido no es un .zip válido.")
            st.stop()

        # Si el zip trae una unica carpeta contenedora (p.ej. "mi_proyecto/Punto 1/..."),
        # bajamos un nivel para que la raiz real sea la que tiene las carpetas-punto.
        contenido = list(extraccion.iterdir())
        if len(contenido) == 1 and contenido[0].is_dir():
            root_folder = contenido[0]
        else:
            root_folder = extraccion

        salida_kmz = tmp_path / f"{(titulo_proyecto.strip() or root_folder.name or 'puntos_de_campo')}.kmz"

        barra = st.progress(0.0, text="Procesando carpetas...")
        mensajes: list[str] = []

        def _log(mensaje: str) -> None:
            mensajes.append(mensaje)

        def _progress(actual: int, total: int) -> None:
            barra.progress(min(actual / max(total, 1), 1.0), text=f"Procesando carpeta {actual}/{total}...")

        try:
            n_puntos, n_fotos, ruta_kmz = process_folders_to_kmz(
                root_folder=root_folder,
                output_kmz_path=salida_kmz,
                max_photo_dimension=max_dimension,
                log_fn=_log,
                progress_fn=_progress,
            )
        except ValueError as e:
            barra.empty()
            st.error(str(e))
            with st.expander("Detalle del proceso"):
                st.text("\n".join(mensajes))
            st.stop()

        barra.empty()
        st.success(f"¡KMZ generado! {n_puntos} punto(s), {n_fotos} foto(s) embebida(s).")
        st.download_button(
            "⬇ Descargar KMZ",
            data=ruta_kmz.read_bytes(),
            file_name=ruta_kmz.name,
            mime="application/vnd.google-earth.kmz",
            type="primary",
        )
        with st.expander("Detalle del proceso"):
            st.text("\n".join(mensajes))
elif not archivo_zip:
    st.info("Sube un .zip con las carpetas por punto para empezar.")

st.divider()
st.caption("Prueba de despliegue web — misma lógica que la herramienta de escritorio CARPETA_KML.")
