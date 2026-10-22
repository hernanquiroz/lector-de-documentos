import streamlit as st
from pypdf import PdfReader
from gtts import gTTS
import io
import os

# Configuración de la página
st.set_page_config(page_title="Lector de PDF con Voz", page_icon="🎧", layout="wide")

st.title("🎧 Lector de PDF con Voz")
st.markdown("Sube un documento PDF, selecciona la página y escúchalo a través de tus audífonos.")

# 1. Subir el archivo PDF
uploaded_file = st.file_uploader("Carga tu archivo PDF aquí", type=["pdf"])

if uploaded_file is not None:
    # Leer el PDF
    reader = PdfReader(uploaded_file)
    num_pages = len(reader.pages)
    
    # 2. Seleccionar página
    page_num = st.slider("Selecciona la página a leer", 0, num_pages - 1, 0)
    
    # Extraer texto de la página seleccionada
    page = reader.pages[page_num]
    text = page.extract_text()
    
    # Mostrar el texto extraído
    st.subheader(f"📄 Texto de la página {page_num + 1}:")
    
    if text.strip():
        st.text_area("", value=text, height=300)
        
        # 3. Generar el audio
        st.subheader("🔊 Reproductor de Audio:")
        
        # Botón para generar y reproducir
        if st.button("🎙️ Leer esta página en voz alta"):
            with st.spinner("Generando audio... por favor espera"):
                try:
                    # Convertir texto a voz (lang='es' para español)
                    tts = gTTS(text=text, lang='es', tld='com.mx') # tld='com.mx' para acento latino, puedes usar 'es' para España
                    
                    # Guardar el audio en memoria (no en disco)
                    audio_buffer = io.BytesIO()
                    tts.write_to_fp(audio_buffer)
                    audio_buffer.seek(0)
                    
                    # Mostrar el reproductor de audio en Streamlit
                    st.audio(audio_buffer, format='audio/mp3')
                    st.success("¡Audio generado! Conecta tus audífonos y presiona Play.")
                    
                except Exception as e:
                    st.error(f"Error al generar el audio: {e}")
    else:
        st.warning("⚠️ No se pudo extraer texto de esta página. Es probable que sea una imagen escaneada. (Necesitarías agregar OCR en el futuro).")

else:
    st.info("👆 Por favor, sube un archivo PDF para comenzar.")
