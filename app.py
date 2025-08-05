import streamlit as st
import pandas as pd
import base64
import requests
import io

# Import library yang dibutuhkan untuk Google API
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ==============================================================================
# KONFIGURASI APLIKASI
# ==============================================================================

# ------------ KONFIGURASI LOGIN ------------
USERNAME = "legoas"
PASSWORD = "admin"

# --- ID File JSON di Google Drive ---
GOOGLE_DRIVE_FILE_ID = "1t41znrid0K9KJf393dFYsZ2sV15hNhcI"


# --- Kamus untuk faktor Grade ---
GRADE_FACTORS = {
    'A (Sangat Baik)': 1.0,
    'B (Baik)': 0.94,
    'C (Cukup)': 0.80,
    'D (Kurang)': 0.58,
    'E (Buruk)': 0.23,
}

# ------------ Konfigurasi Halaman ------------
st.set_page_config(
    page_title="Estimasi Harga Kendaraan Bekas",
    page_icon="🚗",
    layout="wide"
)

# ------------ CSS Styling ------------
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

def ask_openrouter(prompt: str) -> str:
    """Mengirim prompt ke OpenRouter API dan mengembalikan respons."""
    try:
        api_key = st.secrets["openrouter"]["api_key"]
        model = st.secrets["openrouter"]["model"]
    except (KeyError, FileNotFoundError):
        return "⚠️ Konfigurasi API Key OpenRouter tidak ditemukan di Streamlit Secrets."

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    json_data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Anda adalah seorang analis keuangan dan pasar otomotif profesional."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data, timeout=60)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"⚠️ Gagal terhubung ke OpenRouter: {e}"
    except Exception as e:
        return f"⚠️ Terjadi error saat menghubungi API: {e}"

@st.cache_data(ttl=3600)
def load_data_from_drive(file_id):
    """Mengunduh dan memuat data dari Google Drive dengan pembersihan data."""
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        
        with st.spinner("Menghubungi Google Drive untuk mengambil data mobil..."):
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        
        file_stream.seek(0)
        df = pd.read_json(file_stream, encoding='utf-8-sig')

        string_cols = ['name', 'model', 'varian']
        for col in string_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        numeric_cols = [
            'tahun', 'harga_terendah', 'harga_baru', 'residu', 'depresiasi', 
            'estimasi', 'depresiasi_2', 'estimasi_2', 'estimasi_3', 
            'avg_estimasi', 'estimator', 'output'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        if 'tahun' in df.columns:
            df['tahun'] = df['tahun'].astype(int)

        return df
    except Exception as e:
        st.error(f"Gagal memuat atau memproses data dari Google Drive: {e}")
        return pd.DataFrame()

@st.cache_data
def load_local_data(path):
    """Memuat data dari file lokal (motor) dengan pembersihan data."""
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path)
            df.columns = df.columns.str.strip().str.lower()
            
            string_cols_motor = ['brand', 'variant']
            for col in string_cols_motor:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()

            numeric_cols_csv = ['output', 'residu', 'depresiasi_residu', 'estimasi_1', 'year']
            for col in numeric_cols_csv:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            if 'year' in df.columns:
                df['year'] = df['year'].astype(int)

            return df
        else:
            st.error(f"Format file lokal tidak didukung: {path}")
            return pd.DataFrame()
    except FileNotFoundError:
        st.error(f"File data motor tidak ditemukan di path: {path}")
        return pd.DataFrame()

def format_rupiah(val):
    try:
        return f"Rp {round(float(val)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

def image_to_base64(image_path):
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None

def reset_prediction_state():
    """Mereset state prediksi agar UI kembali ke awal saat pilihan berubah."""
    keys_to_reset = [
        'prediction_made_car', 'selected_data_car', 'ai_response_car',
        'prediction_made_motor', 'selected_data_motor', 'ai_response_motor'
    ]
    for key in keys_to_reset:
        st.session_state.pop(key, None)

# ==============================================================================
# HALAMAN APLIKASI
# ==============================================================================

def login_page():
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
        st.session_state.df_motor = load_local_data("dt/mtr.csv")

    df_mobil = st.session_state.df_mobil
    df_motor = st.session_state.df_motor
    
    if df_mobil.empty:
        st.error("Data mobil tidak dapat dimuat. Aplikasi tidak dapat dilanjutkan.")
        return

    with st.sidebar:
        logo_path = "dt/logo.png"
        img_base64 = image_to_base64(logo_path)
        if img_base64:
            st.image(f"data:image/png;base64,{img_base64}", width=140)
        st.markdown("---")
        tipe_estimasi = st.radio("Menu", ["Estimasi Mobil", "Estimasi Motor"], on_change=reset_prediction_state)
        st.markdown("---")
        if st.button("🔒 Keluar", use_container_width=True):
            st.session_state.is_logged_in = False
            st.rerun()

    st.markdown('<div class="main-content">', unsafe_allow_html=True)

    if tipe_estimasi == "Estimasi Mobil":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Mobil Bekas</h2>", unsafe_allow_html=True)
        
        df_source = df_mobil
        
        col1, col2 = st.columns(2)
        with col1:
            brand_options = ["-"] + sorted(df_source["name"].unique())
            brand = st.selectbox("Brand", brand_options, key="car_brand", on_change=reset_prediction_state)
        with col2:
            model_options = ["-"] + (sorted(df_source[df_source["name"] == brand]["model"].unique()) if brand != "-" else [])
            model = st.selectbox("Model", model_options, key="car_model", on_change=reset_prediction_state)

        col3, col4 = st.columns(2)
        with col3:
            varian_options = ["-"] + (sorted(df_source[(df_source["name"] == brand) & (df_source["model"] == model)]["varian"].unique()) if brand != "-" and model != "-" else [])
            varian = st.selectbox("Varian", varian_options, key="car_varian", on_change=reset_prediction_state)
        with col4:
            year_options = ["-"] + (sorted(df_source[(df_source["name"] == brand) & (df_source["model"] == model) & (df_source["varian"] == varian)]["tahun"].unique(), reverse=True))
            year = st.selectbox("Tahun", [str(y) for y in year_options], key="car_year", on_change=reset_prediction_state)

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
                    # PERBAIKAN: Reset state HANYA jika tidak ditemukan
                    reset_prediction_state()
        
        if st.session_state.get('prediction_made_car'):
            selected_data = st.session_state.selected_data_car
            initial_price = selected_data.get("output", 0)
            st.markdown("---")
            st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
            
            grade_selection = st.selectbox("Pilih Grade Kondisi Kendaraan", options=list(GRADE_FACTORS.keys()), key="car_grade")
            adjusted_price = initial_price * GRADE_FACTORS[grade_selection]
            st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

            if st.button("🤖 Generate Analisis Profesional", use_container_width=True, key="car_ai_button"):
                with st.spinner("Menganalisis harga mobil..."):
                    prompt = f"""
                    Sebagai seorang analis pasar otomotif, berikan analisis harga untuk mobil bekas dengan spesifikasi berikut:
                    - Brand: {selected_data['name']}
                    - Model: {selected_data['model']}
                    - Varian: {selected_data['varian']}
                    - Tahun: {int(selected_data['tahun'])}
                    - Grade Kondisi: {grade_selection}

                    Data keuangan internal kami menunjukkan detail berikut:
                    - Estimasi Harga Pasar Awal: {format_rupiah(initial_price)}
                    - Estimasi Harga Akhir (setelah penyesuaian Grade): {format_rupiah(adjusted_price)}

                    Tugas Anda:
                    Jelaskan secara profesional mengapa Estimasi Harga Akhir ({format_rupiah(adjusted_price)}) adalah angka yang wajar. Hubungkan penjelasan Anda dengan Estimasi Harga Pasar Awal dan Grade Kondisi yang dipilih. Jelaskan bahwa Harga Awal adalah baseline pasar, dan Grade menyesuaikannya berdasarkan kondisi spesifik. Sebutkan juga faktor eksternal seperti sentimen pasar, popularitas model, dan kondisi ekonomi di tahun {pd.Timestamp.now().year}.
                    
                    Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                    """
                    st.session_state.ai_response_car = ask_openrouter(prompt)

            if st.session_state.get('ai_response_car'):
                st.markdown("---")
                st.subheader("🤖 Analisis Profesional Estimasi Harga")
                st.markdown(st.session_state.ai_response_car)

    elif tipe_estimasi == "Estimasi Motor":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Motor Bekas</h2>", unsafe_allow_html=True)
        
        if df_motor.empty:
            st.warning("Data motor tidak dapat dimuat. Fitur ini tidak tersedia.")
        else:
            # Placeholder untuk fitur motor
            st.info("Fitur estimasi motor sedang dalam pengembangan.")

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
