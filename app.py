
import asyncio
import pathlib
import re
import tempfile
import time

import edge_tts
import streamlit as st
from gtts import gTTS
from pypdf import PdfReader

# ---------------- Configuración de página ----------------
st.set_page_config(
    page_title="📖 Lector de Documentos",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- Estilos personalizados ----------------
st.markdown(
    """
    <style>
      .hero {
        background: linear-gradient(120deg, #1e3a8a 0%, #7c3aed 100%);
        padding: 1.6rem 2rem;
        border-radius: 1rem;
        color: white;
        margin-bottom: 1.5rem;
      }
      .hero h1 { margin: 0; font-size: 1.9rem; font-weight: 700; }
      .hero p  { margin: 0.35rem 0 0; opacity: 0.9; font-size: 1rem; }
      .card {
        background: rgba(128,128,128,0.06);
        border: 1px solid rgba(128,128,128,0.18);
        border-radius: 0.9rem;
        padding: 1.1rem 1.3rem;
        margin-bottom: 1rem;
      }
      .stButton > button[kind="primary"] {
        width: 100%; height: 3rem; font-size: 1.1rem; border-radius: 0.7rem;
      }
      .credit { text-align: center; padding: 1rem 0 0.2rem; font-size: 0.9rem; }
      .credit b { font-size: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------- Encabezado ----------------
st.markdown(
    """
    <div class="hero">
      <h1>📖 Lector de Documentos y Texto</h1>
      <p>Textos y documentos grandes (PDF, TXT, DOCX — hasta 300+ páginas) leídos en voz alta.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Voces disponibles ----------------
VOICES = {
    "🇨🇴 Español (Colombia) – Voz masculina": "es-CO-AlvaroNeural",
    "🇨🇴 Español (Colombia) – Voz femenina": "es-CO-SalomeNeural",
    "🇪🇸 Español (España) – Voz femenina": "es-ES-ElviraNeural",
    "🇲🇽 Español (México) – Voz femenina": "es-MX-DaliaNeural",
    "🇺🇸 Español (EE.UU.) – Voz femenina": "es-US-PalomaNeural",
    "🇺🇸 Inglés (EE.UU.) – Voz femenina": "en-US-AriaNeural",
}

MAX_PAGINAS = 400          # límite de seguridad
MAX_CARACTERES = 1_500_000  # ~300 páginas de texto denso

# ---------------- Utilidades ----------------
def validar_rate(v: str) -> str:
    m = re.fullmatch(r"([+-])(\d+)%", v)
    return f"{m.group(1)}{m.group(2)}%" if m else "+0%"


@st.cache_data(show_spinner="Extrayendo texto del documento...")
def extraer_paginas(archivo) -> list:
    """Devuelve una lista con el texto de cada página. Cacheado para no reextraer."""
    nombre = archivo.name.lower()
    paginas = []
    try:
        if nombre.endswith(".pdf"):
            lector = PdfReader(archivo)
            for pagina in lector.pages:
                paginas.append(pagina.extract_text() or "")
        elif nombre.endswith(".docx"):
            import docx
            doc = docx.Document(archivo)
            texto = "\n".join(p.text for p in doc.paragraphs)
            while texto:
                paginas.append(texto[:2500])
                texto = texto[2500:]
        elif nombre.endswith((".txt", ".md")):
            texto = archivo.read().decode("utf-8", errors="ignore")
            while texto:
                paginas.append(texto[:2500])
                texto = texto[2500:]
        else:
            st.error("Formato no soportado.")
    except Exception as e:
        st.error(f"No pude leer el archivo: {e}")
    return paginas


def dividir_en_fragmentos(texto: str, maximo: int = 2500) -> list:
    trozos, actual = [], ""
    for linea in texto.splitlines():
        if len(actual) + len(linea) + 1 > maximo:
            if actual.strip():
                trozos.append(actual)
            actual = linea
        else:
            actual += "\n" + linea
    if actual.strip():
        trozos.append(actual)
    return trozos


async def generar_fragmento(trozo: str, voz: str, rate: str) -> bytes:
    """Genera el MP3 de un fragmento con reintentos y pausas (evita errores 429)."""
    for intento in range(4):
        buffer = bytearray()
        try:
            comun = edge_tts.Communicate(trozo.strip(), voz, rate=rate)
            async for mensaje in comun.stream():
                if mensaje.get("type") == "audio":
                    buffer.extend(mensaje.get("data", b""))
            if buffer:
                return bytes(buffer)
            time.sleep(2)  # sin audio: esperar y reintentar
        except edge_tts.exceptions.NoAudioReceived:
            if intento == 3:
                raise
            time.sleep(3 * (intento + 1))  # espera creciente: 3, 6, 9 s
    return b""


def generar_audio_gtts(texto: str, idioma: str, progreso=None) -> bytes:
    """Respaldo gTTS: fragmentos de <4.500 caracteres, con pausas y reintentos
    ante el error 429 (Too Many Requests)."""
    trozos = dividir_en_fragmentos(texto, maximo=4500)
    partes = []
    for i, trozo in enumerate(trozos):
        if not trozo.strip():
            continue
        for intento in range(4):
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    gTTS(text=trozo.strip(), lang=idioma).save(tmp.name)
                    partes.append(pathlib.Path(tmp.name).read_bytes())
                break
            except Exception as e:
                if "429" in str(e) or "Too Many" in str(e):
                    if intento == 3:
                        raise
                    time.sleep(5 * (intento + 1))  # 5, 10, 15 s antes de reintentar
                else:
                    raise
        if progreso:
            progreso.progress((i + 1) / len(trozos),
                              text=f"Google TTS: fragmento {i + 1} de {len(trozos)}")
        time.sleep(1.5)  # pausa fija entre peticiones: evita el 429
    return b"".join(partes)

# ---------------- Barra lateral ----------------
with st.sidebar:
    st.markdown("### ⚙️ Configuración")

    st.markdown("**🎤 Voz**")
    voz_nombre = st.selectbox("Selecciona la voz", list(VOICES.keys()),
                              label_visibility="collapsed")

    st.markdown("**⏩ Velocidad**")
    velocidad = st.select_slider(
        "Velocidad de lectura",
        options=["-50%", "-25%", "Normal", "+25%", "+50%"],
        value="Normal", label_visibility="collapsed")

    st.divider()
    st.markdown("#### ℹ️ Formatos soportados")
    st.markdown("📄 PDF · 📝 TXT / MD · 📄 DOCX")
    st.caption("Documentos de hasta 300+ páginas.")

    st.divider()
    st.caption(f"edge-tts versión: {getattr(edge_tts, '__version__', 'desconocida')}")

    st.divider()
    st.markdown(
        "<p class='credit'>Diseñado con la IA por<br><b>Ing. Hernán Quiroz</b></p>",
        unsafe_allow_html=True,
    )

# ---------------- Contenido principal ----------------
col_texto, col_doc = st.columns(2)

with col_texto:
    st.markdown(
        "<div class='card'><b>📝 Escribir texto</b><br>"
        "<small>Pega aquí el texto que quieres escuchar.</small></div>",
        unsafe_allow_html=True)
    texto_manual = st.text_area("Texto", height=180, label_visibility="collapsed")

with col_doc:
    st.markdown(
        "<div class='card'><b>📄 Subir documento</b><br>"
        "<small>PDF, TXT, MD o DOCX — hasta 300+ páginas.</small></div>",
        unsafe_allow_html=True)
    archivo = st.file_uploader("Documento", type=["pdf", "txt", "md", "docx"],
                              label_visibility="collapsed")

    texto_paginas = []
    if archivo:
        texto_paginas = extraer_paginas(archivo)
        if len(texto_paginas) > MAX_PAGINAS:
            st.warning(f"El documento tiene {len(texto_paginas)} páginas; "
                       f"se leerán las primeras {MAX_PAGINAS}.")
            texto_paginas = texto_paginas[:MAX_PAGINAS]
        if texto_paginas:
            st.success(f"✅ Documento cargado: **{len(texto_paginas)} páginas**")

# ---------------- Selección de páginas ----------------
if texto_paginas:
    with st.expander("📑 Seleccionar rango de páginas", expanded=len(texto_paginas) > 20):
        total = len(texto_paginas)
        col_desde, col_hasta = st.columns(2)
        pag_desde = col_desde.number_input("Desde la página", 1, total, 1)
        pag_hasta = col_hasta.number_input("Hasta la página", 1, total, total)
        if pag_hasta < pag_desde:
            st.error("La página final debe ser mayor o igual a la inicial.")
        seleccion = "\n".join(texto_paginas[pag_desde - 1: pag_hasta])
        st.caption(f"Selección: {len(seleccion):,} caracteres — "
                   f"~{max(1, len(seleccion) // 1000)} min de audio estimados.")
else:
    seleccion = ""

texto = texto_manual.strip() or seleccion.strip()

if texto and len(texto) > MAX_CARACTERES:
    st.warning(f"Texto muy largo ({len(texto):,} caracteres). "
               f"Se leerán los primeros {MAX_CARACTERES:,}.")

# ---------------- Generar y reproducir audio ----------------
st.markdown("")
if st.button("🔊  Leer en voz alta", type="primary",
             disabled=not texto, use_container_width=True):
    if not texto:
        st.warning("Pega un texto o sube un documento primero.")
    else:
        texto = texto[:MAX_CARACTERES]
        rate = validar_rate(velocidad if velocidad != "Normal" else "+0%")
        voz = VOICES[voz_nombre]
        fragmentos = dividir_en_fragmentos(texto)
        progreso = st.progress(0.0, text="Preparando...")
        audio_bytes = b""
        usar_gtts = False

        # 1) Edge TTS fragmento a fragmento, con pausas y progreso en vivo
        partes = []
        try:
            for i, trozo in enumerate(fragmentos):
                partes.append(asyncio.run(generar_fragmento(trozo, voz, rate)))
                if i % 10 == 9:
                    time.sleep(2)  # pausa cada 10 fragmentos (~25.000 caracteres)
                progreso.progress(
                    (i + 1) / len(fragmentos),
                    text=f"Edge TTS: fragmento {i + 1} de {len(fragmentos)}...")
            audio_bytes = b"".join(partes)
        except Exception:
            usar_gtts = True

        # 2) Respaldo gTTS si Edge falló
        if usar_gtts or not audio_bytes:
            st.info("Edge no respondió. Generando con el respaldo de Google "
                    "(voz menos natural)...")
            idioma = "en" if voz.startswith("en") else "es"
            try:
                audio_bytes = generar_audio_gtts(texto, idioma, progreso)
            except Exception as e:
                progreso.empty()
                st.error(f"Error al generar el audio: {e}")
                audio_bytes = b""

        progreso.empty()

        # 3) Reproducir
        if audio_bytes:
            st.success("✅ Audio listo — reprodúcelo abajo o descárgalo.")
            st.audio(audio_bytes, format="audio/mp3")
            col_dl, col_info = st.columns([2, 3])
            with col_dl:
                st.download_button("⬇️ Descargar MP3", audio_bytes,
                                   "lectura.mp3", "audio/mp3",
                                   use_container_width=True)
            with col_info:
                mb = len(audio_bytes) / 1_048_576
                st.metric("📦 Tamaño del audio", f"{mb:.1f} MB")

# ---------------- Créditos ----------------
st.markdown(
    "<div class='credit'>📖 Lector de Documentos — Diseñado con la IA por "
    "<b>Ing. Hernán Quiroz</b></div>",
    unsafe_allow_html=True,
)
