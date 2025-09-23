import streamlit as st
import pandas as pd
import base64
import requests
import io
import re
import json
import numpy as np
import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

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
        .debug-section { background-color: #f8f9fa; padding: 1rem; border-radius: 5px; margin: 1rem 0; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# FUNGSI-FUNGSI HELPER (DIPERBAIKI)
# ==============================================================================

# PERBAIKAN: Fungsi koneksi Google Drive yang lebih robust
@st.cache_resource
def get_gdrive_service():
    """Membuat koneksi service ke Google Drive dengan error handling yang lebih baik"""
    try:
        # Validasi apakah secrets sudah dikonfigurasi
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Konfigurasi 'gcp_service_account' tidak ditemukan di Streamlit Secrets")
            return None
            
        # Pastikan semua field required ada
        required_fields = ["type", "project_id", "private_key_id", "private_key", 
                          "client_email", "client_id", "auth_uri", "token_uri"]
        
        missing_fields = [field for field in required_fields if field not in st.secrets["gcp_service_account"]]
        if missing_fields:
            st.error(f"❌ Field berikut tidak ditemukan di gcp_service_account: {', '.join(missing_fields)}")
            return None
        
        # Format private key dengan benar
        creds_info = dict(st.secrets["gcp_service_account"])
        creds_info["private_key"] = creds_info["private_key"].replace('\\n', '\n')
        
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        # Test koneksi dengan request sederhana
        service.files().list(pageSize=1).execute()
        st.success("✅ Koneksi Google Drive berhasil")
        return service
        
    except Exception as e:
        st.error(f"❌ Gagal menginisialisasi koneksi Google Drive: {str(e)}")
        return None

# PERBAIKAN: Fungsi load data dengan error handling yang lebih baik
@st.cache_data(ttl=3600, show_spinner="Memuat data dari Google Drive...")
def load_data_from_drive(file_id):
    """Mengunduh dan memuat data mobil dari Google Drive dengan error handling lengkap"""
    service = get_gdrive_service()
    if not service:
        return pd.DataFrame()

    try:
        # Validasi file exists dan dapat diakses
        file_metadata = service.files().get(fileId=file_id, fields="id,name,mimeType").execute()
        st.info(f"📁 Memuat file: {file_metadata.get('name', 'Unknown')}")
        
        # Download file
        request = service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        
        progress_bar = st.progress(0)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                progress = status.progress() if status else 0
                progress_bar.progress(progress)

        file_stream.seek(0)
        progress_bar.empty()
        
        # Deteksi format file dan load sesuai
        mime_type = file_metadata.get('mimeType', '')
        
        if 'json' in mime_type or file_metadata.get('name', '').endswith('.json'):
            df = pd.read_json(file_stream, encoding='utf-8-sig')
        elif 'csv' in mime_type or file_metadata.get('name', '').endswith('.csv'):
            file_stream.seek(0)
            df = pd.read_csv(file_stream, encoding='utf-8-sig')
        elif 'excel' in mime_type or 'spreadsheet' in mime_type or file_metadata.get('name', '').endswith(('.xlsx', '.xls')):
            file_stream.seek(0)
            df = pd.read_excel(file_stream)
        else:
            # Coba semua format
            file_stream.seek(0)
            try:
                df = pd.read_json(file_stream, encoding='utf-8-sig')
            except:
                file_stream.seek(0)
                try:
                    df = pd.read_csv(file_stream, encoding='utf-8-sig')
                except:
                    file_stream.seek(0)
                    try:
                        df = pd.read_excel(file_stream)
                    except Exception as e:
                        st.error(f"❌ Tidak dapat membaca format file: {e}")
                        return pd.DataFrame()
        
        # Pembersihan data
        if not df.empty:
            # Clean string columns
            string_cols = df.select_dtypes(include=['object']).columns
            for col in string_cols:
                df[col] = df[col].astype(str).str.strip()
            
            # Clean numeric columns
            numeric_patterns = ['harga', 'price', 'estimasi', 'estimate', 'tahun', 'year', 'depresiasi', 'residu']
            for col in df.columns:
                if any(pattern in col.lower() for pattern in numeric_patterns):
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace('[^0-9.-]', '', regex=True), errors='coerce')
            
            st.success(f"✅ Data berhasil dimuat: {len(df)} baris, {len(df.columns)} kolom")
            return df
        else:
            st.warning("⚠️ File berhasil dibaca tetapi datanya kosong")
            return pd.DataFrame()
        
    except HttpError as e:
        error_msg = str(e)
        if "404" in error_msg:
            st.error("❌ File tidak ditemukan. Pastikan File ID benar.")
        elif "403" in error_msg:
            st.error("❌ Akses ditolak. Pastikan service account memiliki permission untuk file ini.")
        elif "401" in error_msg:
            st.error("❌ Autentikasi gagal. Periksa kredensial service account.")
        else:
            st.error(f"❌ Error Google Drive API: {error_msg}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Error tidak terduga: {str(e)}")
        return pd.DataFrame()

# Fungsi load data lokal untuk motor
@st.cache_data
def load_local_data(path):
    """Memuat data motor dari file lokal dengan pembersihan data."""
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path, encoding='utf-8-sig')
        elif path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(path)
        else:
            st.error(f"❌ Format file tidak didukung: {path}")
            return pd.DataFrame()
            
        if df.empty:
            st.warning("⚠️ File ditemukan tetapi kosong.")
            return pd.DataFrame()
            
        # Clean column names
        df.columns = df.columns.str.strip().str.lower()
        
        # Clean string data
        string_cols = df.select_dtypes(include=['object']).columns
        for col in string_cols:
            df[col] = df[col].astype(str).str.strip()
        
        # Clean numeric data
        for col in df.columns:
            if any(keyword in col.lower() for keyword in ['harga', 'price', 'estimasi', 'tahun', 'year']):
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('[^0-9.-]', '', regex=True), errors='coerce')
        
        st.success(f"✅ Data motor berhasil dimuat: {len(df)} baris")
        return df
        
    except FileNotFoundError:
        st.error(f"❌ File data motor tidak ditemukan di: {path}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Error memuat file data motor: {e}")
        return pd.DataFrame()

# Fungsi format Rupiah
def format_rupiah(amount):
    """Format angka menjadi format Rupiah"""
    try:
        if pd.isna(amount) or amount == 0:
            return "Rp 0"
        return "Rp {:,.0f}".format(amount).replace(",", ".")
    except:
        return "Rp 0"

# ==============================================================================
# FUNGSI LOGGING (DIPERBAIKI)
# ==============================================================================

def get_log_queue():
    if 'log_queue' not in st.session_state:
        st.session_state.log_queue = []
    return st.session_state.log_queue

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
    st.session_state.log_queue = log_queue

def flush_logs_to_drive():
    """Mengunggah semua log dari antrean ke file di Google Drive."""
    log_queue = get_log_queue()
    if not log_queue:
        return

    service = get_gdrive_service()
    folder_id = st.secrets.get("logging", {}).get("folder_id")

    if not service or not folder_id:
        st.warning("⚠️ Gagal flush log: Service GDrive atau Folder ID tidak tersedia.")
        return

    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log_filename = f"legoas_activity_log_{today}.json"
        
        # Cari file log hari ini
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
                existing_logs = json.load(file_stream)
                if not isinstance(existing_logs, list):
                    existing_logs = []
            except json.JSONDecodeError:
                existing_logs = []
        
        # Gabungkan log lama dengan log baru
        all_logs = existing_logs + log_queue
        updated_content = json.dumps(all_logs, indent=2, ensure_ascii=False)
        media_body = MediaIoBaseUpload(io.BytesIO(updated_content.encode('utf-8')), mimetype='application/json')
        
        if file_id:
            service.files().update(fileId=file_id, media_body=media_body).execute()
        else:
            file_metadata = {
                'name': log_filename,
                'mimeType': 'application/json',
                'parents': [folder_id]
            }
            service.files().create(body=file_metadata, media_body=media_body).execute()
        
        # Kosongkan antrean setelah berhasil diunggah
        st.session_state.log_queue = []
        st.success("✅ Log aktivitas berhasil disimpan")
        
    except Exception as e:
        st.error(f"❌ Error saat menyimpan log: {e}")

# ==============================================================================
# FUNGSI DEBUGGING (BARU)
# ==============================================================================

def debug_data_loading():
    """Fungsi untuk debugging proses loading data"""
    st.markdown("---")
    st.markdown("### 🔍 Debug Data Loading")
    
    with st.expander("Klik untuk melihat informasi debugging"):
        st.markdown('<div class="debug-section">', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Test Koneksi Google Drive")
            if st.button("Test Koneksi"):
                service = get_gdrive_service()
                if service:
                    try:
                        results = service.files().list(pageSize=5, fields="files(id, name)").execute()
                        files = results.get('files', [])
                        if files:
                            st.success("✅ Koneksi berhasil! File yang dapat diakses:")
                            for file in files:
                                st.write(f"- {file['name']} (ID: {file['id']})")
                        else:
                            st.info("📂 Tidak ada file yang ditemukan")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
        
        with col2:
            st.subheader("Test Load File Spesifik")
            test_file_id = st.text_input("Masukkan File ID untuk test:")
            if test_file_id and st.button("Test Load File"):
                df = load_data_from_drive(test_file_id)
                if not df.empty:
                    st.success(f"✅ File berhasil dimuat: {len(df)} baris")
                    st.dataframe(df.head())
                    st.write("Info kolom:", df.dtypes)
                else:
                    st.error("❌ Gagal memuat file")
        
        st.subheader("Informasi Konfigurasi")
        st.write("Secrets yang tersedia:", list(st.secrets.keys()))
        
        if "gcp_service_account" in st.secrets:
            st.write("Service Account terkonfigurasi: ✅")
            st.write("Client Email:", st.secrets["gcp_service_account"].get("client_email", "Tidak ada"))
        else:
            st.write("Service Account terkonfigurasi: ❌")
            
        if "data_sources" in st.secrets:
            st.write("Data Sources:", dict(st.secrets["data_sources"]))
        
        st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# FUNGSI UTAMA APLIKASI
# ==============================================================================

def login_page():
    st.markdown('<div class="login-container"><div class="login-icon">🔒</div><h2 class="login-title">Silakan Login Terlebih Dahulu</h2>', unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", type="password", placeholder="Masukkan password Anda")
        if st.form_submit_button("Masuk", use_container_width=True):
            if username == USERNAME and password == PASSWORD:
                st.session_state.is_logged_in = True
                add_log_to_queue("LOGIN", f"User {username} berhasil login")
                st.rerun()
            else:
                add_log_to_queue("LOGIN_FAILED", f"Percobaan login gagal dengan username: {username}")
                st.markdown('<p class="error-message">Username atau password salah</p>', unsafe_allow_html=True)
    st.markdown('<div class="login-footer">Sistem Estimasi Harga LEGOAS<br>© 2025</div></div>', unsafe_allow_html=True)

def reset_prediction_state():
    """Mereset state prediksi agar UI kembali ke awal saat pilihan berubah."""
    keys_to_reset = [
        'prediction_made_car', 'selected_data_car', 'ai_response_car',
        'prediction_made_motor', 'selected_data_motor', 'ai_response_motor',
        'non_auto_submitted', 'non_auto_analysis'
    ]
    for key in keys_to_reset:
        st.session_state.pop(key, None)

def display_vehicle_estimator(vehicle_type, df, key_prefix):
    """Menampilkan UI estimator untuk kendaraan (mobil/motor)"""
    if df.empty:
        st.error(f"❌ Data {vehicle_type} tidak dapat dimuat. Fitur ini tidak tersedia.")
        return

    st.markdown(f'<h2 class="section-header">Estimasi Harga {vehicle_type} Bekas</h2>', unsafe_allow_html=True)
    
    # Konfigurasi kolom berdasarkan tipe kendaraan
    if vehicle_type == "Mobil":
        brand_col, model_col, variant_col, year_col = "name", "model", "varian", "tahun"
    else:  # Motor
        brand_col, model_col, year_col = "brand", "variant", "year"
        variant_col = None

    col1, col2 = st.columns(2)
    with col1:
        brand_options = ["-"] + sorted(df[brand_col].astype(str).unique())
        brand = st.selectbox("Brand", brand_options, key=f"{key_prefix}_brand", on_change=reset_prediction_state)
    with col2:
        model_options = ["-"] + (sorted(df[df[brand_col] == brand][model_col].astype(str).unique()) if brand != "-" else [])
        model = st.selectbox("Model/Varian", model_options, key=f"{key_prefix}_model", on_change=reset_prediction_state)

    if variant_col:
        col3, col4 = st.columns(2)
        with col3:
            varian_options = ["-"] + (sorted(df[(df[brand_col] == brand) & (df[model_col] == model)][variant_col].astype(str).unique()) if brand != "-" and model != "-" else [])
            varian = st.selectbox("Varian Detail", varian_options, key=f"{key_prefix}_varian", on_change=reset_prediction_state)
        with col4:
            mask_year = (df[brand_col] == brand) & (df[model_col] == model) & (df[variant_col] == varian)
            year_options = ["-"] + (sorted(df[mask_year][year_col].unique(), reverse=True) if all(x != "-" for x in [brand, model, varian]) else [])
            year = st.selectbox("Tahun", [str(y) for y in year_options], key=f"{key_prefix}_year", on_change=reset_prediction_state)
    else:  # Untuk motor
        varian = None
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
                
                log_details = {"brand": brand, "model/variant": model, "tahun": year}
                if variant_col: 
                    log_details["varian"] = varian
                add_log_to_queue(f"ESTIMASI_{vehicle_type.upper()}", log_details)
                
                st.success("✅ Data ditemukan! Lihat estimasi di bawah.")
            else:
                st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                reset_prediction_state()

    if st.session_state.get(f'prediction_made_{key_prefix}'):
        selected_data = st.session_state[f'selected_data_{key_prefix}']
        
        # Cari kolom yang berisi harga estimasi
        price_columns = [col for col in selected_data.index if any(keyword in col.lower() for keyword in ['harga', 'price', 'estimasi', 'output'])]
        initial_price = selected_data[price_columns[0]] if price_columns else 0
        
        st.markdown("---")
        st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
        
        grade_selection = st.selectbox("Pilih Grade Kondisi Kendaraan", options=list(GRADE_FACTORS.keys()), key=f"{key_prefix}_grade")
        adjusted_price = initial_price * GRADE_FACTORS[grade_selection]
        st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

def main_page():
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Konfigurasi")
        st.session_state.tipe_estimasi = st.radio(
            "Pilih Tipe Estimasi:",
            ["Estimasi Mobil", "Estimasi Motor", "Estimasi Non-Automotif"],
            index=0
        )
        
        st.markdown("---")
        st.header("ℹ️ Informasi")
        st.write(f"Pengguna: {USERNAME}")
        st.write(f"Tanggal: {datetime.datetime.now().strftime('%d/%m/%Y')}")
        
        if st.button("🔒 Keluar", use_container_width=True):
            add_log_to_queue("LOGOUT", "User keluar dari sistem")
            with st.spinner("Menyimpan aktivitas log..."):
                flush_logs_to_drive()
            st.session_state.clear()
            st.session_state.is_logged_in = False
            st.rerun()

    # Header utama
    st.markdown('<h1 class="main-header">Sistem Estimasi Harga LEGOAS</h1>', unsafe_allow_html=True)

    # Load data berdasarkan tipe estimasi
    if st.session_state.tipe_estimasi == "Estimasi Mobil":
        if 'df_mobil' not in st.session_state:
            mobil_data_file_id = st.secrets.get("data_sources", {}).get("mobil_data_id")
            
            if mobil_data_file_id:
                with st.spinner("🔄 Memuat data mobil dari Google Drive..."):
                    st.session_state.df_mobil = load_data_from_drive(mobil_data_file_id)
            else:
                st.error("❌ 'mobil_data_id' tidak dikonfigurasi di secrets.toml")
                st.session_state.df_mobil = pd.DataFrame()
        
        display_vehicle_estimator("Mobil", st.session_state.df_mobil, "car")
        
    elif st.session_state.tipe_estimasi == "Estimasi Motor":
        if 'df_motor' not in st.session_state:
            with st.spinner("🔄 Memuat data motor dari file lokal..."):
                st.session_state.df_motor = load_local_data("dt/mtr.csv")
        
        display_vehicle_estimator("Motor", st.session_state.df_motor, "motor")
        
    else:  # Estimasi Non-Automotif
        st.markdown('<h2 class="section-header">Estimasi Harga Non-Automotif</h2>', unsafe_allow_html=True)
        st.info("Fitur estimasi non-automotif akan segera hadir!")
        # Tambahkan logika untuk non-automotif di sini

    # Tampilkan debugging section (bisa dihide di production)
    debug_data_loading()

def main():
    # Inisialisasi session state
    if 'is_logged_in' not in st.session_state:
        st.session_state.is_logged_in = False
    
    # Inisialisasi koneksi Google Drive
    if 'gdrive_service' not in st.session_state:
        st.session_state.gdrive_service = get_gdrive_service()

    if not st.session_state.is_logged_in:
        login_page()
    else:
        main_page()

if __name__ == "__main__":
    main()
