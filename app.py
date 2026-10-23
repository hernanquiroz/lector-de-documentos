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

# ---------------- Estilos ----------------
st.markdown(
    """
    <style>
      .hero {
        background: linear-gradient(120deg, #1e3a8a 0%, #7c3aed 100%);
        padding: 1.6rem 2rem; border-radius: 1rem; color: white;
        margin-bottom: 1.5rem;
      }
      .hero h1 { margin: 0; font-size: 1.9rem; font-weight: 700; }
      .hero p  { margin: 0.35rem 0 0; opacity: 0.9; font-size: 1rem; }
      .card {
        background: rgba(128,128,128,0.06);
        border: 1px solid rgba(128,128,128,0.18);
        border-radius: 0.9rem; padding: 1.1rem 1.3rem; margin-bottom: 1rem;
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

st.markdown(
    """
    <div class="hero">
      <h1>📖 Lector de Documentos y Texto</h1>
      <p>Lee documentos grandes de 10 páginas en 10 páginas, preguntándote si deseas continuar.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Voces ----------------
VOICES = {
    "🇨🇴 Español (Colombia) – Voz masculina": "es-CO-AlvaroNeural",
    "🇨🇴 Español (Colombia) – Voz femenina": "es-CO-SalomeNeural",
    "🇪🇸 Español (España) – Voz femenina": "es-ES-ElviraNeural",
    "🇲🇽 Español (México) – Voz femenina": "es-MX-DaliaNeural",
    "🇺🇸 Español (EE.UU.) – Voz femenina": "es-US-PalomaNeural",
    "🇺🇸 Inglés (EE.UU.) – Voz femenina": "en-US-AriaNeural",
}

PAGINAS_POR_BLOQUE = 10

# ---------------- Utilidades ----------------
def validar_rate(v: str) -> str:
    m = re.fullmatch(r"([+-])(\d+)%", v)
    return f"{m.group(1)}{m.group(2)}%" if m else "+0%"


@st.cache_data(show_spinner="Extrayendo texto del documento...")
def extraer_paginas(archivo) -> list:
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
                paginas.append(texto[:2500]); texto = texto[2500:]
        elif nombre.endswith((".txt", ".md")):
            texto = archivo.read().decode("utf-8", errors="ignore")
            while texto:
                paginas.append(texto[:2500]); texto = texto[2500:]
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
    """MP3 de un fragmento con reintentos y pausas (evita errores 429)."""
    for intento in range(4):
        buffer = bytearray()
        try:
            comun = edge_tts.Communicate(trozo.strip(), voz, rate=rate)
            async for mensaje in comun.stream():
                if mensaje.get("type") == "audio":
                    buffer.extend(mensaje.get("data", b""))
            if buffer:
                return bytes(buffer)
            time.sleep(2)
        except edge_tts.exceptions.NoAudioReceived:
            if intento == 3:
                raise
            time.sleep(3 * (intento + 1))
    return b""


def generar_audio_gtts(texto: str, idioma: str, progreso=None) -> bytes:
    """Respaldo gTTS por fragmentos, con pausas y reintentos ante el 429."""
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
                    time.sleep(5 * (intento + 1))
                else:
                    raise
        if progreso:
            progreso.progress((i + 1) / len(trozos),
                              text=f"Google TTS: fragmento {i + 1} de {len(trozos)}")
        time.sleep(1.5)
    return b"".join(partes)


def generar_audio_bloque(texto: str, voz: str, rate: str, etiqueta: str) -> bytes:
    """Genera el audio de un bloque de páginas (Edge con respaldo Google)."""
    fragmentos = dividir_en_fragmentos(texto)
    progreso = st.progress(0.0, text="Preparando...")
    audio = b""
    partes = []
    try:
        for i, trozo in enumerate(fragmentos):
            partes.append(asyncio.run(generar_fragmento(trozo, voz, rate)))
            if i % 10 == 9:
                time.sleep(2)
            progreso.progress((i + 1) / len(fragmentos),
                              text=f"Edge TTS ({etiqueta}): fragmento {i+1} de {len(fragmentos)}")
        audio = b"".join(partes)
    except Exception:
        audio = b""
    if not audio:
        st.info("Edge no respondió. Generando con el respaldo de Google...")
        idioma = "en" if voz.startswith("en") else "es"
        try:
            audio = generar_audio_gtts(texto, idioma, progreso)
        except Exception as e:
            progreso.empty()
            st.error(f"Error al generar el audio: {e}")
    progreso.empty()
    return audio

# ---------------- Estado de la sesión ----------------
ss = st.session_state
defaults = {
    "activo": False,        # ¿hay lectura por bloques en curso?
    "pag_actual": 0,        # índice de la página inicial del bloque actual
    "audio_bloque": b"",    # audio del bloque actual
    "audio_total": b"",     # audio acumulado de todos los bloques leídos
    "num_bloque": 0,        # número de bloque actual
}
for clave, valor in defaults.items():
    if clave not in ss:
        ss[clave] = valor

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
    st.caption(f"Lectura por bloques de {PAGINAS_POR_BLOQUE} páginas, "
               "preguntando si deseas continuar.")
    st.caption(f"edge-tts: {getattr(edge_tts, '__version__', 'desconocida')}")

    st.divider()
    st.markdown(
        "<p class='credit'>Diseñado con la IA por<br><b>Ing. Hernán Quiroz</b></p>",
        unsafe_allow_html=True,
    )

# ---------------- Cargar documento ----------------
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
        "<small>PDF, TXT, MD o DOCX — lectura por bloques de "
        f"{PAGINAS_POR_BLOQUE} páginas.</small></div>",
        unsafe_allow_html=True)
    archivo = st.file_uploader("Documento", type=["pdf", "txt", "md", "docx"],
                              label_visibility="collapsed")

texto_paginas = []
if archivo:
    texto_paginas = extraer_paginas(archivo)
    if texto_paginas:
        st.success(f"✅ Documento cargado: **{len(texto_paginas)} páginas** "
                   f"(se leerá en {len(range(0, len(texto_paginas), PAGINAS_POR_BLOQUE))} bloques)")

# ---------------- Selección de rango ----------------
if texto_paginas:
    with st.expander("📑 Seleccionar rango de páginas a leer"):
        total = len(texto_paginas)
        col_desde, col_hasta = st.columns(2)
        pag_desde = col_desde.number_input("Desde la página", 1, total, 1)
        pag_hasta = col_hasta.number_input("Hasta la página", 1, total, total)
        if pag_hasta < pag_desde:
            st.error("La página final debe ser mayor o igual a la inicial.")

# ---------------- Iniciar lectura ----------------
st.markdown("")

# Caso A: documento por bloques
if archivo and texto_paginas and pag_hasta >= pag_desde:
    inicio_idx = int(pag_desde) - 1
    fin_idx = int(pag_hasta)

    if st.button("🔊  Comenzar lectura por bloques", type="primary",
                 use_container_width=True):
        ss.activo = True
        ss.pag_actual = inicio_idx
        ss.audio_bloque = b""
        ss.audio_total = b""
        ss.num_bloque = 0
        st.rerun()

    # Caso B: texto manual (lectura única)
elif texto_manual.strip():
    if st.button("🔊  Leer en voz alta", type="primary", use_container_width=True):
        rate = validar_rate(velocidad if velocidad != "Normal" else "+0%")
        audio = generar_audio_bloque(texto_manual.strip(), VOICES[voz_nombre],
                                    rate, "texto")
        if audio:
            st.success("✅ Audio listo — reprodúcelo abajo o descárgalo.")
            st.audio(audio, format="audio/mp3")
            st.download_button("⬇️ Descargar MP3", audio, "lectura.mp3",
                               "audio/mp3", use_container_width=True)

# ---------------- Flujo por bloques ----------------
if ss.activo and texto_paginas:
    fin_bloque = min(ss.pag_actual + PAGINAS_POR_BLOQUE, fin_idx)
    paginas_bloque = texto_paginas[ss.pag_actual:fin_bloque]

    if ss.pag_actual >= fin_idx:
        # Fin del documento
        st.success("🏁 **Lectura completada.** Ya no quedan páginas por leer.")
        if ss.audio_total:
            mb = len(ss.audio_total) / 1_048_576
            st.markdown(f"**🎧 Audio completo de la lectura:** {mb:.1f} MB")
            st.download_button("⬇️ Descargar audio completo (MP3)", ss.audio_total,
                               "lectura_completa.mp3", "audio/mp3",
                               use_container_width=True)
        if st.button("🔄 Leer otro rango", use_container_width=True):
            ss.activo = False
            ss.audio_bloque = b""
            ss.audio_total = b""
            st.rerun()

    else:
        # Generar el bloque actual si aún no existe
        if not ss.audio_bloque:
            ss.num_bloque += 1
            texto_bloque = "\n".join(paginas_bloque)
            rate = validar_rate(velocidad if velocidad != "Normal" else "+0%")
            ss.audio_bloque = generar_audio_bloque(
                texto_bloque, VOICES[voz_nombre], rate,
                f"bloque {ss.num_bloque}")
            ss.audio_total += ss.audio_bloque  # acumular

        st.markdown(
            f"### 🎧 Bloque {ss.num_bloque}: páginas "
            f"{ss.pag_actual + 1} – {fin_bloque}"
        )

        if ss.audio_bloque:
            st.audio(ss.audio_bloque, format="audio/mp3")

            # Pregunta 1: ¿descargar este bloque?
            st.markdown("**¿Deseas descargar el audio de este bloque?**")
            col_s, col_n = st.columns(2)
            with col_s:
                if st.button("⬇️ Sí, descargar este bloque", use_container_width=True):
                    pass  # el botón de descarga real está abajo
            with col_n:
                if st.button("No, gracias", use_container_width=True):
                    st.session_state["descargar_bloque"] = False
                    st.rerun()
            if st.session_state.get("descargar_bloque", True):
                st.download_button(
                    "⬇️ Descargar bloque (MP3)", ss.audio_bloque,
                    f"bloque_{ss.num_bloque}_pag{ss.pag_actual+1}-{fin_bloque}.mp3",
                    "audio/mp3", use_container_width=True)

            # Pregunta 2: ¿seguir escuchando?
            hay_mas = fin_bloque < fin_idx
            if hay_mas:
                st.markdown("**¿Deseas seguir escuchando el siguiente bloque?**")
                col_si, col_no = st.columns(2)
                with col_si:
                    if st.button("✅ Sí, siguiente bloque", use_container_width=True):
                        ss.pag_actual = fin_bloque
                        ss.audio_bloque = b""   # fuerza generar el siguiente
                        st.rerun()
                with col_no:
                    if st.button("⏹️ No, detener la lectura", use_container_width=True):
                        st.info("Lectura detenida. Puedes descargar todo lo leído:")
                        st.download_button(
                            "⬇️ Descargar lo leído hasta ahora (MP3)", ss.audio_total,
                            "lectura_parcial.mp3", "audio/mp3", use_container_width=True)
                        ss.activo = False
                        ss.audio_bloque = b""
                        st.rerun()
            else:
                st.info("Este es el último bloque del rango seleccionado. 🎉")
                if st.button("🎧 Finalizar y descargar todo", use_container_width=True):
                    st.rerun()
        else:
            st.error("No se pudo generar el audio de este bloque. "
                     "Intenta de nuevo o prueba con otra voz.")

# ---------------- Créditos ----------------
st.markdown(
    "<div class='credit'>📖 Lector de Documentos — Diseñado con la IA por "
    "<b>Ing. Hernán Quiroz</b></div>",
    unsafe_allow_html=True,
)
