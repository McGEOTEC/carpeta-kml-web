# Carpeta a KML (CARPETA_KML) — versión web

Prueba de despliegue web de la herramienta de escritorio `CARPETA_KML`: sube
un `.zip` con una carpeta por punto/predio/sitio (cada una con sus fotos
georreferenciadas) y descarga un KMZ autónomo con un Placemark por carpeta
(coordenada = centroide de las fotos válidas) y un visor HTML con
miniaturas ampliables al hacer clic en Google Earth. Misma lógica de
negocio que la app de escritorio (`logica.py` es una copia directa de
`src/carpeta_kml_core.py`, que ya era código puro sin Tkinter), solo cambia
la entrada: subir un `.zip` con la estructura de carpetas en vez de elegir
una carpeta local.

**Acceso restringido:** la app pide una contraseña (`APP_PASSWORD`, guardada
en Secrets de Streamlit Cloud — nunca en este repo). El repositorio es
público (requisito del plan gratis de Streamlit Community Cloud), pero eso
solo expone el código, no el uso de la app.

## Probar en local

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
REM edita .streamlit\secrets.toml y pon tu propia clave
.venv\Scripts\streamlit run streamlit_app.py
```

## Desplegar en Streamlit Community Cloud

1. Este repo ya está en GitHub (público).
2. Entra a https://share.streamlit.io con tu cuenta de GitHub.
3. "New app" → elige este repositorio, rama `main`, archivo `streamlit_app.py`.
4. Antes de que quede público de verdad: en **Settings → Secrets** de la app
   pega:
   ```
   APP_PASSWORD = "la-clave-que-quieras"
   ```
5. Deploy. Streamlit te da un link público tipo `https://algo.streamlit.app`
   — solo entra quien tenga la contraseña.

## Estructura

```
streamlit_app.py   # interfaz web (subir .zip, barra de progreso, descarga del KMZ)
logica.py           # logica pura reutilizada de CARPETA_KML (sin Tkinter)
.streamlit/
  config.toml        # tema visual (colores INAMSILCO)
  secrets.toml.example  # plantilla, secrets.toml real NO se sube (gitignore)
requirements.txt
```
