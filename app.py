import asyncio
import re

import edge_tts
import streamlit as st
from pypdf import PdfReader

# ---------------- Configuración de página ----------------
st.set_page_config(page_title="📖 Lector de Documentos", page_icon="📖")
st.title("📖 Lector de Documentos y Texto")
st.caption("Pega un texto o sube un documento (PDF, TXT, DOCX) y escúchalo en voz alta.")

# ---------------- Voces disponibles ----------------
VOICES = {
    "Español (Colombia) – Voz masculina": "es-CO-AlvaroNeural",
    "Español (Colombia) – Voz femenina": "es-CO-SalomeNeural",
    "Español (España) – Voz femenina": "es-ES-ElviraNeural",
    "Español (México) – Voz femenina": "es-MX-DaliaNeural",
    "Español (EE.UU.) – Voz femenina": "es-US-PalomaNeural",
    "Inglés (EE.UU.) – Voz femenina": "en-US-AriaNeural",
}

# ---------------- Utilidades ----------------
def extraer_texto(archivo) -> str:
    """Extrae el texto de un archivo subido (PDF, DOCX, TXT, MD)."""
    nombre = archivo.name.lower()
    try:
        if nombre.endswith(".pdf"):
            lector = PdfReader(archivo)
            return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
        if nombre.endswith(".docx"):
            import docx
            doc = docx.Document(archivo)
            return "\n".join(p.text for p in doc.paragraphs)
        if nombre.endswith((".txt", ".md")):
            return archivo.read().decode("utf-8", errors="ignore")
    except Exception as e:
        st.error(f"No pude leer el archivo: {e}")
    return ""


def validar_rate(v: str) -> str:
    """edge-tts exige formato '+25%' o '-50%'; devuelve '+0%' si es inválido."""
    m = re.fullmatch(r"([+-])(\d+)%", v)
    return f"{m.group(1)}{m.group(2)}%" if m else "+0%"


def dividir_en_fragmentos(texto: str, maximo: int = 2500) -> list:
    """Divide el texto en fragmentos: la API falla con textos muy largos."""
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


async def generar_audio(texto: str, voz: str, rate: str) -> bytes:
    """Genera el audio por fragmentos con reintentos y lo une en un MP3.
    Compatible con cualquier versión de edge-tts (itera el stream manualmente)."""
    partes = []
    for trozo in dividir_en_fragmentos(texto):
        buffer = bytearray()
        for intento in range(3):
            try:
                buffer = bytearray()  # reiniciar por si hubo reintento parcial
                comun = edge_tts.Communicate(trozo.strip(), voz, rate=rate)
                async for mensaje in comun.stream():
                    if mensaje.get("type") == "audio":
                        buffer.extend(mensaje.get("data", b""))
                if len(buffer) > 0:
                    break  # fragmento exitoso
                # sin audio: tratarlo como fallo y reintentar
                await asyncio.sleep(1)
            except edge_tts.exceptions.NoAudioReceived:
                if intento == 2:
                    raise
                await asyncio.sleep(1)
        if len(buffer) > 0:
            partes.append(bytes(buffer))
    return b"".join(partes)

# ---------------- Interfaz ----------------
pestana_texto, pestana_doc = st.tabs(["📝 Texto", "📄 Documento"])

with pestana_texto:
    texto_manual = st.text_area("Escribe o pega el texto a leer:", height=200)

with pestana_doc:
    archivo = st.file_uploader("Sube un documento", type=["pdf", "txt", "md", "docx"])
    texto_archivo = extraer_texto(archivo) if archivo else ""
    if archivo and texto_archivo:
        st.success(f"Texto extraído: {len(texto_archivo):,} caracteres")
        with st.expander("Ver texto extraído (primeros 3.000 caracteres)"):
            st.text(texto_archivo[:3000])
    elif archivo:
        st.error("No pude extraer texto del documento (¿es un PDF escaneado?).")

texto = texto_manual.strip() or texto_archivo.strip()

col_voz, col_vel = st.columns(2)
with col_voz:
    voz_nombre = st.selectbox("Voz", list(VOICES.keys()))
with col_vel:
    velocidad = st.select_slider(
        "Velocidad", options=["-50%", "-25%", "Normal", "+25%", "+50%"],
        value="Normal",
    )

# ---------------- Generar y reproducir audio ----------------
if st.button("🔊 Leer en voz alta", type="primary", disabled=not texto):
    if not texto:
        st.warning("Pega un texto o sube un documento primero.")
    else:
        rate = validar_rate(velocidad if velocidad != "Normal" else "+0%")
        with st.spinner("Generando audio..."):
            try:
                audio_bytes = asyncio.run(generar_audio(texto, VOICES[voz_nombre], rate))
                if not audio_bytes:
                    st.error(
                        "No se recibió audio del servicio. Prueba con otra voz, "
                        "un texto más corto, o revisa la versión de edge-tts "
                        "(debe ser 7.x o superior)."
                    )
                else:
                    st.success("✅ Audio listo — reprodúcelo abajo.")
                    st.audio(audio_bytes, format="audio/mp3")
                    st.download_button(
                        "⬇️ Descargar MP3", audio_bytes, "lectura.mp3", "audio/mp3"
                    )
            except edge_tts.exceptions.NoAudioReceived:
                st.error(
                    "El servicio de voz no respondió. Prueba con otra voz o un "
                    "texto más corto. Si persiste, actualiza edge-tts en "
                    "requirements.txt a la versión 7.x."
                )
            except Exception as e:
                st.error(f"Error al generar el audio: {e}")
