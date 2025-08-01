import streamlit as st
import pandas as pd
import base64
import requests
import re
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ------------ KONFIGURASI LOGIN & FAKTOR GRADE ------------
USERNAME = "legoas"
PASSWORD = "admin"
GRADE_FACTORS = {
    'A (Sangat Baik)': 1.0,
    'B (Baik)': 0.94,
    'C (Cukup)': 0.80,
    'D (Kurang)': 0.58,
    'E (Buruk)': 0.23,
}

# --- ID File JSON di Google Drive ---
# Cara mendapatkan ID: Klik kanan pada file di GDrive > Get link > Salin bagian ini:
# https://drive.google.com/file/d/INI_ADALAH_ID_NYA/view?usp=sharing
GOOGLE_DRIVE_FILE_ID = "1unFiGov9gRo15wRSCiRs96roM5idAYob"


# ------------ FUNGSI-FUNGSI UTAMA ------------

def ask_openrouter(prompt: str) -> str:
    """Mengirim prompt ke OpenRouter API dan mengembalikan respons."""
    # ... (Fungsi ini tidak diubah)
    try:
        api_key = st.secrets["openrouter"]["api_key"]
        model = st.secrets["openrouter"]["model"]
    except (KeyError, FileNotFoundError):
        return "⚠️ Konfigurasi API Key OpenRouter tidak ditemukan di Streamlit Secrets."
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    json_data = {"model": model, "messages": [{"role": "system", "content": "Anda adalah seorang analis keuangan dan pasar otomotif profesional."}, {"role": "user", "content": prompt}]}
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data, timeout=60)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"⚠️ Error dari OpenRouter ({response.status_code}): {response.text}"
    except requests.exceptions.RequestException as e:
        return f"⚠️ Gagal terhubung ke OpenRouter: {e}"

# --- FUNGSI BARU: Mengambil data dari Google Drive ---
@st.cache_data(ttl=3600) # Cache data selama 1 jam
def load_data_from_drive(file_id):
    """Mengautentikasi, mengunduh, dan memuat file JSON dari Google Drive."""
    try:
        # Menggunakan st.secrets untuk otentikasi yang aman
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)

        st.info("Menghubungi Google Drive untuk mengambil data mobil...")
        request = service.files().get_media(fileId=file_id)
        
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        
        done = False
        progress_bar = st.progress(0, "Mengunduh data...")
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                progress_bar.progress(int(status.progress() * 100), f"Mengunduh data... {int(status.progress() * 100)}%")
        
        progress_bar.empty()
        file_stream.seek(0)
        
        # Langsung ubah menjadi DataFrame Pandas
        df = pd.read_json(file_stream)
        
        # Lakukan konversi tipe data yang diperlukan di sini
        general_numeric_cols = ['output', 'residu', 'depresiasi', 'estimasi', 'tahun']
        for col in general_numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
            
    except Exception as e:
        st.error(f"Gagal memuat data dari Google Drive: {e}")
        st.error(f"Pastikan file ID '{file_id}' sudah di-share ke email service account: {st.secrets.get('gcp_service_account', {}).get('client_email', 'Tidak Ditemukan')}")
        return pd.DataFrame()

# --- Fungsi load_data untuk file lokal (motor) ---
@st.cache_data
def load_local_data(path):
    """Memuat data dari file lokal (khusus untuk data motor)."""
    if path.endswith('.csv'):
        df = pd.read_csv(path)
        df.columns = df.columns.str.strip().str.lower()
        numeric_cols_csv = ['output', 'residu', 'depresiasi_residu', 'estimasi_1']
        for col in numeric_cols_csv:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    else:
        st.error(f"Format file lokal tidak didukung: {path}")
        return pd.DataFrame()

# --- Fungsi lainnya (tidak diubah) ---
def format_rupiah(val):
    try:
        num = float(val)
        return f"Rp {round(num):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

def image_to_base64(image_path):
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None

def reset_prediction_state():
    keys_to_reset = ['prediction_made_car', 'selected_data_car', 'ai_response_car', 'prediction_made_motor', 'selected_data_motor', 'ai_response_motor']
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]

# ------------ Konfigurasi Halaman & CSS ------------
st.set_page_config(page_title="Estimasi Harga Kendaraan Bekas", page_icon="🚗", layout="wide")
# CSS disembunyikan untuk keringkasan
st.markdown("""<style> ... </style>""", unsafe_allow_html=True) 

# ------------ Sistem Login & Halaman Utama ------------
def login_page():
    # ... (Kode login tidak diubah)
    st.markdown('<div class="login-container">...</div>', unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", type="password", placeholder="Masukkan password Anda")
        if st.form_submit_button("Masuk", use_container_width=True):
            if username == USERNAME and password == PASSWORD:
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.markdown('<p class="error-message">Username atau password salah</p>', unsafe_allow_html=True)

def main_page():
    # Load data hanya jika belum dimuat
    if 'df_mobil' not in st.session_state:
        # --- PERUBAHAN UTAMA DI SINI ---
        # Memuat data mobil dari Google Drive
        st.session_state.df_mobil = load_data_from_drive(GOOGLE_DRIVE_FILE_ID)
        # Memuat data motor dari file lokal
        st.session_state.df_motor = load_local_data("dt/mtr.csv")
    
    df_mobil = st.session_state.df_mobil
    df_motor = st.session_state.df_motor
    
    # Cek jika data mobil gagal dimuat
    if df_mobil.empty:
        st.error("Data mobil tidak dapat dimuat. Aplikasi tidak dapat melanjutkan. Harap periksa konfigurasi Google Drive.")
        return # Menghentikan eksekusi jika data utama gagal dimuat

    # --- Sisa kode UI (Sidebar dan Konten Utama) tidak diubah ---
    # ... (Kode UI untuk sidebar dan konten utama tetap sama persis seperti yang Anda berikan)
    # ... (Kode untuk menampilkan pilihan Brand, Model, Varian, Tahun)
    # ... (Kode untuk menampilkan hasil estimasi dan analisis AI)
    # ... (Kode untuk menu Estimasi Motor)

    # Contoh integrasi (hanya bagian relevan yang ditampilkan)
    with st.sidebar:
        # ... (kode sidebar)
        pass

    st.markdown('<div class="main-content">', unsafe_allow_html=True)
    
    tipe_estimasi = st.sidebar.radio("Menu", ["Estimasi Mobil", "Estimasi Motor"], on_change=reset_prediction_state)

    if tipe_estimasi == "Estimasi Mobil":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Mobil Bekas</h2>", unsafe_allow_html=True)
        # ... (Sisa kode untuk estimasi mobil tidak diubah)
        # ... (Anda bisa copy-paste seluruh blok 'if tipe_estimasi == "Estimasi Mobil":' dari skrip asli Anda ke sini)
    
    elif tipe_estimasi == "Estimasi Motor":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Motor Bekas</h2>", unsafe_allow_html=True)
        # ... (Sisa kode untuk estimasi motor tidak diubah)
        # ... (Anda bisa copy-paste seluruh blok 'elif tipe_estimasi == "Estimasi Motor":' dari skrip asli Anda ke sini)

    st.markdown("</div>", unsafe_allow_html=True)


# ------------ Main App Logic ------------
def main():
    if "is_logged_in" not in st.session_state:
        st.session_state.is_logged_in = False
    
    if not st.session_state.is_logged_in:
        login_page()
    else:
        main_page()

if __name__ == "__main__":
    main()
