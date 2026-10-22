import asyncio
import tempfile
import pathlib

import edge_tts
import streamlit as st
from pypdf import PdfReader

st.set_page_config(page_title="📖 Lector de Documentos", page_icon="📖")
st.title("📖 Lector de Documentos y Texto")
st.caption("Pega un texto o sube un documento (PDF, TXT, DOCX) y escúchalo en voz alta.")

# --- Voces en español (puedes añadir más) ---
VOICES = {
    "Español (Colombia) – Male": "es-CO-AlvaroNeural",
    "Español (Colombia) – Female": "es-CO-SalomeNeural",
    "Español (España) – Female": "es-ES-ElviraNeural",
    "Español (México) – Female": "es-MX-DaliaNeural",
    "Español (EE.UU.) – Female": "es-US-PalomaNeural",
    "Inglés (EE.UU.) – Female": "en-US-AriaNeural",
}

# --- Extraer texto del documento subido ---
def extraer_texto(archivo) -> str:
    nombre = archivo.name.lower()
    if nombre.endswith(".pdf"):
        lector = PdfReader(archivo)
        return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    if nombre.endswith(".docx"):
        import docx
        doc = docx.Document(archivo)
        return "\n".join(p.text for p in doc.paragraphs)
    if nombre.endswith((".txt", ".md")):
        return archivo.read().decode("utf-8", errors="ignore")
    return ""

# --- UI ---
pestañas = st.tabs(["📝 Texto", "📄 Documento"])

with pestañas[0]:
    texto_manual = st.text_area("Escribe o pega el texto a leer:", height=200)

with pestañas[1]:
    archivo = st.file_uploader(
        "Sube un documento", type=["pdf", "txt", "md", "docx"]
    )
    texto_archivo = extraer_texto(archivo) if archivo else ""
    if archivo and texto_archivo:
        st.success(f"Texto extraído: {len(texto_archivo):,} caracteres")
        with st.expander("Ver texto extraído"):
            st.write_text(texto_archivo[:3000])
    elif archivo:
        st.error("No pude extraer texto del documento (¿es un PDF escaneado?).")

texto = texto_manual.strip() or texto_archivo.strip()

col1, col2 = st.columns(2)
with col1:
    voz = st.selectbox("Voz", list(VOICES.keys()))
with col2:
    velocidad = st.select_slider(
        "Velocidad", options=["-50%", "-25%", "Normal", "+25%", "+50%"], value="Normal"
    )

if st.button("🔊 Leer en voz alta", type="primary", disabled=not texto):
    if not texto:
        st.warning("Pega un texto o sube un documento primero.")
    else:
        with st.spinner("Generando audio..."):
            rate = "+0%" if velocidad == "Normal" else velocidad
            ssml_rate = f"{rate.replace('%', '%')}"
            comunicar = edge_tts.Communicate(
                texto, VOICES[voz], rate=ssml_rate
            )
            # edge-tts es async: lo ejecutamos en un loop
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                asyncio.run(comunicar.save(tmp.name))
                audio_bytes = pathlib.Path(tmp.name).read_bytes()
        st.audio(audio_bytes, format="audio/mp3")
        st.download_button("⬇️ Descargar MP3", audio_bytes, "lectura.mp3", "audio/mp3")
