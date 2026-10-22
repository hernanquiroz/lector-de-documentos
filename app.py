import streamlit as st
from pypdf import PdfReader
from gtts import gTTS
import io
import os

# Configuración inicial de la página
st.set_page_config(
    page_title="Lector de PDF con Voz",
    page_icon="🎧",
    layout="wide"
)

# Título principal
st.title("🎧 Lector de PDF con Voz")
st.markdown("""
### Sube tu documento PDF y escúchalo a través de tus audífonos
---
""")

# Sidebar con opciones
st.sidebar.header("⚙️ Configuración")
language = st.sidebar.selectbox(
    "Selecciona el idioma de lectura",
    ["es", "en", "fr", "de", "it", "pt"],
    index=0,
    help="es=Español, en=Inglés, fr=Francés, de=Alemán, it=Italiano, pt=Portugués"
)

accent = st.sidebar.selectbox(
    "Selecciona el acento (solo para español)",
    ["com.mx", "es", "com.ar", "com.co"],
    index=0,
    help="com.mx=México, es=España, com.ar=Argentina, com.co=Colombia"
)

# Subir archivo PDF
uploaded_file = st.file_uploader("📄 Carga tu archivo PDF aquí", type=["pdf"])

if uploaded_file is not None:
    try:
        # Leer el PDF
        reader = PdfReader(uploaded_file)
        num_pages = len(reader.pages)
        
        st.success(f"✅ PDF cargado exitosamente. Total de páginas: {num_pages}")
        
        # Selector de página
        page_num = st.slider(
            "Selecciona la página a leer",
            min_value=0,
            max_value=num_pages - 1,
            value=0
        )
        
        # Extraer texto de la página
        page = reader.pages[page_num]
        text = page.extract_text()
        
        # Mostrar el texto
        st.subheader(f"📖 Texto de la página {page_num + 1}:")
        
        if text.strip():
            # Mostrar texto en un área de texto
            st.text_area("", value=text, height=300, label_visibility="collapsed")
            
            # Separador
            st.markdown("---")
            
            # Sección de audio
            st.subheader("🔊 Reproductor de Audio")
            
            # Botón para generar audio
            if st.button("🎙️ Generar y reproducir audio", type="primary"):
                with st.spinner("Generando audio... esto puede tomar unos segundos"):
                    try:
                        # Configurar el idioma y acento
                        if language == "es":
                            tts = gTTS(text=text, lang=language, tld=accent)
                        else:
                            tts = gTTS(text=text, lang=language)
                        
                        # Guardar audio en memoria
                        audio_buffer = io.BytesIO()
                        tts.write_to_fp(audio_buffer)
                        audio_buffer.seek(0)
                        
                        # Mostrar reproductor de audio
                        st.audio(audio_buffer, format='audio/mp3')
                        
                        st.success("✅ ¡Audio generado! Conecta tus audífonos y presiona Play.")
                        
                        # Opción para descargar el audio
                        st.download_button(
                            label="💾 Descargar audio MP3",
                            data=audio_buffer,
                            file_name=f"pagina_{page_num + 1}.mp3",
                            mime="audio/mp3"
                        )
                        
                    except Exception as e:
                        st.error(f"❌ Error al generar el audio: {e}")
        else:
            st.warning("⚠️ No se pudo extraer texto de esta página.")
            st.info("💡 Esto puede suceder si el PDF es una imagen escaneada. En el futuro podemos agregar OCR para resolver esto.")
            
    except Exception as e:
        st.error(f"❌ Error al leer el PDF: {e}")

else:
    # Mensaje inicial cuando no hay archivo
    st.info("👆 Por favor, sube un archivo PDF para comenzar.")
    
    # Información adicional
    st.markdown("""
    ### 📝 Instrucciones:
    1. **Sube un PDF** usando el botón de arriba
    2. **Selecciona la página** que quieres escuchar
    3. **Elige el idioma** en el panel lateral
    4. **Presiona el botón** para generar el audio
    5. **Conecta tus audífonos** y disfruta la lectura
    
    ---
    
    ### 💡 Consejos:
    - Si el PDF es muy grande, lee página por página
    - Puedes descargar el audio para escucharlo offline
    - Ajusta la velocidad de reproducción en el reproductor
    """)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray;'>
    <small>Creado con Streamlit | 🎧 Lector de PDF con Voz</small>
</div>
""", unsafe_allow_html=True)
