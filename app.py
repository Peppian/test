import streamlit as st
import pandas as pd
import base64
import requests
import io
import unicodedata
import re

# Import library yang dibutuhkan untuk Google API
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ==============================================================================
# KONFIGURASI APLIKASI
# ==============================================================================

USERNAME = "legoas"
PASSWORD = "admin"
GOOGLE_DRIVE_FILE_ID = "1t41znrid0K9KJf393dFYsZ2sV15hNhcI"

GRADE_FACTORS = {
    'A (Sangat Baik)': 1.0, 'B (Baik)': 0.94, 'C (Cukup)': 0.80,
    'D (Kurang)': 0.58, 'E (Buruk)': 0.23,
}

st.set_page_config(
    page_title="Estimasi Harga Kendaraan Bekas",
    page_icon="🚗",
    layout="wide"
)

st.markdown("""
    <style>
        .error-message { color: #E74C3C; font-weight: bold; text-align: center; }
        .login-container { max-width: 450px; margin: auto; padding: 2rem; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; }
        .login-icon { font-size: 3rem; margin-bottom: 1rem; }
        .login-title { color: #2C3E50; margin-bottom: 1.5rem; }
        .login-footer { margin-top: 2rem; font-size: 0.9rem; color: #7F8C8D; }
    </style>
""", unsafe_allow_html=True)


# ==============================================================================
# FUNGSI-FUNGSI HELPER
# ==============================================================================

def clean_string(text):
    """Fungsi pembersihan string yang sangat kuat."""
    if not isinstance(text, str):
        return text
    # 1. Normalisasi Unicode (mengatasi karakter aneh)
    text = unicodedata.normalize('NFKC', text)
    # 2. Hapus karakter non-printable kecuali spasi
    text = re.sub(r'[^\x20-\x7E]+', '', text)
    # 3. Hapus spasi berlebih di awal, akhir, dan tengah
    text = re.sub(r'\s+', ' ', text).strip()
    return text

@st.cache_data(ttl=3600)
def load_data_from_drive(file_id):
    """Mengunduh dan memuat data dari Google Drive dengan pembersihan total."""
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        with st.spinner("Menghubungi Google Drive..."):
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        # Coba baca dengan encoding utf-8-sig untuk mengatasi BOM (Byte Order Mark)
        df = pd.read_json(file_stream, encoding='utf-8-sig')

        # 1. Pembersihan String Total
        string_cols = ['name', 'model', 'varian']
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].apply(clean_string)
        
        # 2. Konversi Kolom Numerik
        numeric_cols = ['tahun', 'harga_terendah', 'harga_baru', 'residu', 'depresiasi', 
                        'estimasi', 'output']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        st.error(f"Gagal memuat atau memproses data dari Google Drive: {e}")
        return pd.DataFrame()

def format_rupiah(val):
    try:
        return f"Rp {round(float(val)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

def reset_prediction_state():
    for key in ['prediction_made_car', 'selected_data_car', 'ai_response_car']:
        st.session_state.pop(key, None)


# ==============================================================================
# HALAMAN APLIKASI
# ==============================================================================

def login_page():
    # (Fungsi login tidak berubah)
    st.markdown('<div class="login-container"><div class="login-icon">🔒</div><h2 class="login-title">Silakan Login Terlebih Dahulu</h2>', unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", type="password", placeholder="Masukkan password Anda")
        if st.form_submit_button("Masuk", use_container_width=True):
            if username == USERNAME and password == PASSWORD:
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.markdown('<p class="error-message">Username atau password salah</p>', unsafe_allow_html=True)
    st.markdown('<div class="login-footer">Sistem Estimasi Harga Kendaraan Bekas<br>© 2025</div></div>', unsafe_allow_html=True)

def main_page():
    if 'df_mobil' not in st.session_state:
        st.session_state.df_mobil = load_data_from_drive(GOOGLE_DRIVE_FILE_ID)

    df_mobil = st.session_state.df_mobil
    
    if df_mobil.empty:
        st.error("Data mobil tidak dapat dimuat. Aplikasi tidak dapat dilanjutkan.")
        return

    with st.sidebar:
        st.image("https://i.imgur.com/eLh1vGn.png", width=140) # Ganti dengan logo Anda jika perlu
        st.markdown("---")
        tipe_estimasi = st.radio("Menu", ["Estimasi Mobil"], on_change=reset_prediction_state)
        st.markdown("---")
        if st.button("🔒 Keluar", use_container_width=True):
            st.session_state.is_logged_in = False
            st.rerun()

    st.markdown('<div class="main-content">', unsafe_allow_html=True)

    if tipe_estimasi == "Estimasi Mobil":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Mobil Bekas</h2>", unsafe_allow_html=True)
        
        df_source = df_mobil
        
        # --- Dropdown Filters ---
        col1, col2 = st.columns(2)
        with col1:
            brand_options = ["-"] + sorted(df_source["name"].unique())
            brand = st.selectbox("Brand", brand_options, on_change=reset_prediction_state)
        with col2:
            model_options = ["-"] + (sorted(df_source[df_source["name"] == brand]["model"].unique()) if brand != "-" else [])
            model = st.selectbox("Model", model_options, on_change=reset_prediction_state, key=f"model_{brand}")

        col3, col4 = st.columns(2)
        with col3:
            varian_options = ["-"] + (sorted(df_source[(df_source["name"] == brand) & (df_source["model"] == model)]["varian"].unique()) if brand != "-" and model != "-" else [])
            varian = st.selectbox("Varian", varian_options, on_change=reset_prediction_state, key=f"varian_{brand}_{model}")
        with col4:
            year_options = ["-"] + (sorted(df_source[(df_source["name"] == brand) & (df_source["model"] == model) & (df_source["varian"] == varian)]["tahun"].astype(int).unique(), reverse=True) if brand != "-" and model != "-" and varian != "-" else [])
            year = st.selectbox("Tahun", [str(y) for y in year_options], on_change=reset_prediction_state, key=f"year_{brand}_{model}_{varian}")

        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True):
            if "-" in [brand, model, varian, year]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
            else:
                mask = ( (df_source["name"] == brand) & (df_source["model"] == model) & (df_source["varian"] == varian) & (df_source["tahun"] == int(year)) )
                results = df_source[mask]
                
                if not results.empty:
                    st.session_state.prediction_made_car = True
                    st.session_state.selected_data_car = results.iloc[0]
                    if len(results) > 1:
                         st.warning(f"⚠️ Ditemukan {len(results)} data duplikat. Menampilkan hasil pertama.")
                else:
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                    reset_prediction_state()
        
        if st.session_state.get('prediction_made_car'):
            selected_data = st.session_state.selected_data_car
            initial_price = selected_data.get("output", 0)
            st.markdown("---")
            st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
            
            grade_selection = st.selectbox("Pilih Grade Kondisi Kendaraan", options=list(GRADE_FACTORS.keys()))
            adjusted_price = initial_price * GRADE_FACTORS[grade_selection]
            st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")
            
    st.markdown("</div>", unsafe_allow_html=True)


# ==============================================================================
# LOGIKA EKSEKUSI UTAMA
# ==============================================================================

def main():
    if not st.session_state.get("is_logged_in", False):
        login_page()
    else:
        main_page()

if __name__ == "__main__":
    main()
