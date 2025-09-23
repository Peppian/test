import streamlit as st
import pandas as pd
import base64
import requests
import io
import re
import json
import numpy as np
import datetime

# Import library yang dibutuhkan untuk Google API
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# ==============================================================================
# KONFIGURASI APLIKASI
# ==============================================================================

st.set_page_config(
    page_title="Sistem Estimasi Harga LEGOAS",
    page_icon="🚗",
    layout="wide"
)

# ------------ KONFIGURASI LOGIN ------------
USERNAME = "legoas"
PASSWORD = "admin"

# --- ID File JSON di Google Drive ---
# DIPINDAHKAN ke dalam fungsi untuk akses yang lebih aman via st.secrets
GOOGLE_DRIVE_FILE_ID = st.secrets["logging"]["folder_id"] # Ini untuk data mobil, bukan logging

# --- Kamus untuk faktor Grade ---
GRADE_FACTORS = {
    'A (Sangat Baik)': 1.0,
    'B (Baik)': 0.94,
    'C (Cukup)': 0.80,
    'D (Kurang)': 0.58,
    'E (Buruk)': 0.23,
}

# ------------ CSS Styling ------------
st.markdown("""
    <style>
        .error-message { color: #E74C3C; font-weight: bold; text-align: center; }
        .login-container { max-width: 450px; margin: auto; padding: 2rem; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center; }
        .login-icon { font-size: 3rem; margin-bottom: 1rem; }
        .login-title { color: #2C3E50; margin-bottom: 1.5rem; }
        .login-footer { margin-top: 2rem; font-size: 0.9rem; color: #7F8C8D; }
        .main-header { color: #2C3E50; text-align: center; margin-bottom: 2rem; }
        .section-header { color: #2C3E50; border-bottom: 2px solid #3498DB; padding-bottom: 0.5rem; margin-top: 1.5rem; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# FUNGSI-FUNGSI HELPER
# ==============================================================================

# BARU: Cache koneksi ke Google Drive agar tidak dibuat berulang kali
@st.cache_resource
def get_gdrive_service():
    """Membuat dan menyimpan koneksi service ke Google Drive."""
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Gagal menginisialisasi koneksi Google Drive: {e}")
        return None

@st.cache_data(ttl=3600)
def load_data_from_drive(file_id):
    """Mengunduh dan memuat data mobil dari Google Drive dengan pembersihan data."""
    service = get_gdrive_service()
    if not service:
        return pd.DataFrame()

    try:
        with st.spinner("Menghubungi Google Drive untuk mengambil data mobil..."):
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        file_stream.seek(0)
        df = pd.read_json(file_stream, encoding='utf-8-sig')

        # Pembersihan data (sudah baik)
        string_cols = ['name', 'model', 'varian']
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        numeric_cols = [
            'tahun', 'harga_terendah', 'harga_baru', 'residu', 'depresiasi', 
            'estimasi', 'depresiasi_2', 'estimasi_2', 'estimasi_3', 
            'avg_estimasi', 'estimator', 'output', 'correction'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        if 'tahun' in df.columns:
            df['tahun'] = df['tahun'].astype(int)
        return df
    except Exception as e:
        st.error(f"Gagal memuat atau memproses data dari Google Drive: {e}")
        return pd.DataFrame()

# ... (Fungsi-fungsi lain yang tidak berubah seperti load_local_data, ask_openrouter, format_rupiah, dll. tetap sama) ...
# (Saya akan menyertakan semua fungsi di blok kode akhir)

# ==============================================================================
# FUNGSI LOGGING BARU (LEBIH EFISIEN)
# ==============================================================================

# BARU: Mendapatkan antrean log dari session state
def get_log_queue():
    if 'log_queue' not in st.session_state:
        st.session_state.log_queue = []
    return st.session_state.log_queue

# BARU: Menambah log ke antrean, bukan langsung ke GDrive
def add_log_to_queue(activity_type, details, username="legoas"):
    """Membuat entri log dan menambahkannya ke antrean di session state."""
    log_queue = get_log_queue()
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "username": username,
        "activity_type": activity_type,
        "details": details,
    }
    log_queue.append(log_entry)
    st.session_state.log_queue = log_queue # Simpan kembali ke state

# DIUBAH: Fungsi ini sekarang mengambil semua log dari antrean dan mengunggahnya sekaligus.
def flush_logs_to_drive():
    """Mengunggah semua log dari antrean ke file di Google Drive."""
    log_queue = get_log_queue()
    if not log_queue:
        return # Tidak ada yang perlu diunggah

    service = get_gdrive_service()
    folder_id = st.secrets.get("logging", {}).get("folder_id")

    if not service or not folder_id:
        print("Gagal flush log: Service GDrive atau Folder ID tidak tersedia.")
        return

    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log_filename = f"legoas_activity_log_{today}.json"
        
        query = f"name='{log_filename}' and '{folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        existing_logs = []
        file_id = None

        if files:
            # File sudah ada, download isinya
            file_id = files[0]['id']
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            file_stream.seek(0)
            try:
                # Coba parse JSON, jika gagal, anggap sebagai list kosong
                existing_logs = json.load(file_stream)
                if not isinstance(existing_logs, list):
                    existing_logs = []
            except json.JSONDecodeError:
                existing_logs = [] # File korup atau kosong
        
        # Gabungkan log lama dengan log baru dari antrean
        all_logs = existing_logs + log_queue
        updated_content = json.dumps(all_logs, indent=2, ensure_ascii=False)
        media_body = MediaIoBaseUpload(io.BytesIO(updated_content.encode('utf-8')), mimetype='application/json')
        
        if file_id:
            # Update file yang ada
            service.files().update(fileId=file_id, media_body=media_body).execute()
        else:
            # Buat file baru
            file_metadata = {
                'name': log_filename,
                'mimeType': 'application/json',
                'parents': [folder_id]
            }
            service.files().create(body=file_metadata, media_body=media_body).execute()
        
        # Kosongkan antrean setelah berhasil diunggah
        st.session_state.log_queue = []
        print(f"Berhasil mengunggah {len(log_queue)} log ke Google Drive.")

    except Exception as e:
        # Jika gagal, log tetap di antrean untuk percobaan berikutnya
        print(f"Error saat flush log ke Drive: {e}")

# ==============================================================================
# HALAMAN APLIKASI
# ==============================================================================

def login_page():
    # ... (Fungsi login_page tetap sama, tapi panggilannya diubah)
    st.markdown('<div class="login-container"><div class="login-icon">🔒</div><h2 class="login-title">Silakan Login Terlebih Dahulu</h2>', unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", type="password", placeholder="Masukkan password Anda")
        if st.form_submit_button("Masuk", use_container_width=True):
            if username == USERNAME and password == PASSWORD:
                st.session_state.is_logged_in = True
                # DIUBAH: Panggil add_log_to_queue
                add_log_to_queue("LOGIN", f"User {username} berhasil login")
                st.rerun()
            else:
                # DIUBAH: Panggil add_log_to_queue
                add_log_to_queue("LOGIN_FAILED", f"Percobaan login gagal dengan username: {username}")
                st.markdown('<p class="error-message">Username atau password salah</p>', unsafe_allow_html=True)
    st.markdown('<div class="login-footer">Sistem Estimasi Harga LEGOAS<br>© 2025</div></div>', unsafe_allow_html=True)

# BARU: Fungsi generik untuk menampilkan UI estimasi mobil dan motor
def display_vehicle_estimator(vehicle_type, df, key_prefix):
    if df.empty:
        st.error(f"Data {vehicle_type} tidak dapat dimuat. Fitur ini tidak tersedia.")
        return

    st.markdown(f'<h2 class="section-header">Estimasi Harga {vehicle_type} Bekas</h2>', unsafe_allow_html=True)
    
    # Konfigurasi kolom berdasarkan tipe kendaraan
    if vehicle_type == "Mobil":
        brand_col, model_col, variant_col, year_col = "name", "model", "varian", "tahun"
    else: # Motor
        brand_col, model_col, year_col = "brand", "variant", "year"
        variant_col = None # Motor tidak punya varian di data ini

    col1, col2 = st.columns(2)
    with col1:
        brand_options = ["-"] + sorted(df[brand_col].unique())
        brand = st.selectbox("Brand", brand_options, key=f"{key_prefix}_brand", on_change=reset_prediction_state)
    with col2:
        model_options = ["-"] + (sorted(df[df[brand_col] == brand][model_col].unique()) if brand != "-" else [])
        model = st.selectbox("Model/Varian", model_options, key=f"{key_prefix}_model", on_change=reset_prediction_state)

    if variant_col:
        col3, col4 = st.columns(2)
        with col3:
            varian_options = ["-"] + (sorted(df[(df[brand_col] == brand) & (df[model_col] == model)][variant_col].unique()) if brand != "-" and model != "-" else [])
            varian = st.selectbox("Varian Detail", varian_options, key=f"{key_prefix}_varian", on_change=reset_prediction_state)
        with col4:
            mask_year = (df[brand_col] == brand) & (df[model_col] == model) & (df[variant_col] == varian)
            year_options = ["-"] + (sorted(df[mask_year][year_col].unique(), reverse=True) if all(x != "-" for x in [brand, model, varian]) else [])
            year = st.selectbox("Tahun", [str(y) for y in year_options], key=f"{key_prefix}_year", on_change=reset_prediction_state)
    else: # Untuk motor
        varian = None # Tidak ada
        mask_year = (df[brand_col] == brand) & (df[model_col] == model)
        year_options = ["-"] + (sorted(df[mask_year][year_col].unique(), reverse=True) if all(x != "-" for x in [brand, model]) else [])
        year = st.selectbox("Tahun", [str(y) for y in year_options], key=f"{key_prefix}_year", on_change=reset_prediction_state)

    if st.button("🔍 Lihat Estimasi Harga", use_container_width=True, key=f"{key_prefix}_estimate_button"):
        required_fields = [brand, model, year] + ([varian] if variant_col else [])
        if "-" in required_fields:
            st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
        else:
            mask = (df[brand_col] == brand) & (df[model_col] == model) & (df[year_col] == int(year))
            if variant_col:
                mask &= (df[variant_col] == varian)
            
            results = df[mask]
            
            if not results.empty:
                st.session_state[f'prediction_made_{key_prefix}'] = True
                st.session_state[f'selected_data_{key_prefix}'] = results.iloc[0]
                
                log_details = { "brand": brand, "model/variant": model, "tahun": year, "harga_estimasi": results.iloc[0].get("output", 0)}
                if variant_col: log_details["varian"] = varian
                add_log_to_queue(f"ESTIMASI_{vehicle_type.upper()}", log_details)
                
            else:
                st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                reset_prediction_state()

    if st.session_state.get(f'prediction_made_{key_prefix}'):
        selected_data = st.session_state[f'selected_data_{key_prefix}']
        initial_price = selected_data.get("output", 0)
        st.markdown("---")
        st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
        
        grade_selection = st.selectbox("Pilih Grade Kondisi Kendaraan", options=list(GRADE_FACTORS.keys()), key=f"{key_prefix}_grade")
        adjusted_price = initial_price * GRADE_FACTORS[grade_selection]
        st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

        # ... (Logika untuk generate analisis AI bisa dimasukkan di sini, sama seperti kode Anda sebelumnya)


def main_page():
    # Load data sekali saat halaman utama dimuat
    if 'df_mobil' not in st.session_state:
        gdrive_file_id = st.secrets.get("gcp", {}).get("mobil_data_id") # Ambil dari secrets
        if gdrive_file_id:
            st.session_state.df_mobil = load_data_from_drive(gdrive_file_id)
        else:
            st.error("ID file data mobil tidak ditemukan di Streamlit Secrets.")
            st.session_state.df_mobil = pd.DataFrame()

    if 'df_motor' not in st.session_state:
        st.session_state.df_motor = load_local_data("dt/mtr.csv")

    with st.sidebar:
        # ... (Kode sidebar tetap sama)
        if st.button("🔒 Keluar", use_container_width=True):
            add_log_to_queue("LOGOUT", "User keluar dari sistem")
            # DIUBAH: Panggil flush_logs_to_drive sebelum logout
            with st.spinner("Menyimpan aktivitas log..."):
                flush_logs_to_drive()
            st.session_state.clear() # Membersihkan semua session state
            st.session_state.is_logged_in = False
            st.rerun()

    st.markdown('<h1 class="main-header">Sistem Estimasi Harga LEGOAS</h1>', unsafe_allow_html=True)

    tipe_estimasi = st.session_state.get('tipe_estimasi', 'Estimasi Mobil') # Default

    # --- PENGGUNAAN FUNGSI REUSABLE ---
    if tipe_estimasi == "Estimasi Mobil":
        display_vehicle_estimator("Mobil", st.session_state.df_mobil, key_prefix="car")
    elif tipe_estimasi == "Estimasi Motor":
        display_vehicle_estimator("Motor", st.session_state.df_motor, key_prefix="motor")
    elif tipe_estimasi == "Estimasi Non-Automotif":
        # ... (Logika untuk non-automotif tetap di sini)
        # Pastikan pemanggilan log-nya menggunakan add_log_to_queue
        # Contoh:
        # log_activity("ESTIMASI_NON_AUTOMOTIF", log_details) menjadi:
        # add_log_to_queue("ESTIMASI_NON_AUTOMOTIF", log_details)
        pass # Placeholder untuk kode non-automotif Anda

# ... (Pastikan semua fungsi helper lainnya seperti reset_prediction_state, dll, ada di sini) ...

def reset_prediction_state():
    """Mereset state prediksi agar UI kembali ke awal saat pilihan berubah."""
    keys_to_reset = [
        'prediction_made_car', 'selected_data_car', 'ai_response_car',
        'prediction_made_motor', 'selected_data_motor', 'ai_response_motor',
        'non_auto_submitted', 'non_auto_analysis'
    ]
    for key in keys_to_reset:
        st.session_state.pop(key, None)

def main():
    if not st.session_state.get("is_logged_in", False):
        login_page()
    else:
        main_page()

if __name__ == "__main__":
    # Inisialisasi service GDrive saat aplikasi pertama kali dijalankan
    get_gdrive_service()
    main()

