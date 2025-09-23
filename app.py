# ==============================================================================
# BAGIAN 1: IMPOR, KONFIGURASI, DAN FUNGSI HELPER
# ==============================================================================

# --- Impor Library Standar dan Pihak Ketiga ---
import streamlit as st
import pandas as pd
import base64
import requests
import io
import re
import json
import numpy as np
from datetime import datetime
import pytz
import gspread

# --- Impor Library Google API ---
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload

# ==============================================================================
# KONFIGURASI APLIKASI
# ==============================================================================

# --- Kamus untuk Faktor Grade ---
GRADE_FACTORS = {
    'A (Sangat Baik)': 1.0,
    'B (Baik)': 0.94,
    'C (Cukup)': 0.80,
    'D (Kurang)': 0.58,
    'E (Buruk)': 0.23,
}

# --- Konfigurasi Halaman Streamlit ---
st.set_page_config(
    page_title="Sistem Estimasi Harga LEGOAS",
    page_icon="🚗",
    layout="wide"
)

# --- Styling CSS ---
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

# GANTI LAGI DENGAN VERSI FINAL DEBUG INI
# Impor library gspread di bagian atas file Anda
import gspread

# HAPUS fungsi log_activity_to_drive YANG LAMA dan GANTI dengan ini:
def log_activity_to_sheet(log_data: dict):
    """
    Menyimpan log aktivitas sebagai baris baru di Google Spreadsheet yang ditentukan.
    """
    try:
        # Menggunakan kredensial yang sama, tetapi dengan scopes untuk Sheets DAN Drive
        creds_info = st.secrets["gcp_service_account"]
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)

        # Buka spreadsheet berdasarkan namanya. Pastikan nama ini sama persis.
        spreadsheet = client.open("Log Aplikasi LEGOAS") 
        worksheet = spreadsheet.sheet1 # Ambil sheet pertama

        # Siapkan baris data yang akan ditambahkan
        # PENTING: Urutan data di sini harus SAMA PERSIS dengan urutan kolom di Sheet Anda
        new_row = [
            log_data.get('timestamp', ''),
            log_data.get('user', ''),
            log_data.get('tipe_estimasi', ''),
            # Gabungkan detail query menjadi satu kolom agar rapi
            log_data.get('detail_query', ''),
            log_data.get('grade_dipilih', ''),
            log_data.get('harga_awal', ''),
            log_data.get('harga_disesuaikan', ''),
            log_data.get('respon_llm', '')
        ]
        
        # Tambahkan baris baru ke bagian paling bawah sheet
        worksheet.append_row(new_row)

    except Exception as e:
        # Tampilkan error di UI jika gagal, agar mudah di-debug
        st.error(f"Gagal menyimpan log ke Google Sheet: {e}")

# --- Fungsi API OpenRouter ---
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

# --- Fungsi Pemuatan Data Otomotif ---
@st.cache_data(ttl=3600)
def load_data_from_drive(file_id):
    """Mengunduh dan memuat data mobil dari Google Drive dengan pembersihan data."""
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

        # Pembersihan data string dan numerik
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

@st.cache_data
def load_local_data(path):
    """Memuat data motor dari file lokal dengan pembersihan data."""
    try:
        df = pd.read_csv(path)
        df.columns = df.columns.str.strip().str.lower()
        
        string_cols_motor = ['brand', 'variant']
        for col in string_cols_motor:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()

        numeric_cols_csv = ['output', 'residu', 'depresiasi_residu', 'estimasi_1', 'year']
        for col in numeric_cols_csv:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        if 'year' in df.columns:
            df['year'] = df['year'].astype(int)

        return df
    except FileNotFoundError:
        st.error(f"File data motor tidak ditemukan di path: {path}")
        return pd.DataFrame()

# --- Fungsi Umum & UI ---
def format_rupiah(val):
    """Memformat angka menjadi string mata uang Rupiah."""
    try:
        return f"Rp {round(float(val)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

def image_to_base64(image_path):
    """Mengonversi file gambar menjadi string base64 untuk ditampilkan di HTML."""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None

def reset_prediction_state():
    """Mereset session state terkait prediksi saat pengguna mengubah pilihan."""
    keys_to_reset = [
        'prediction_made_car', 'selected_data_car', 'ai_response_car',
        'prediction_made_motor', 'selected_data_motor', 'ai_response_motor',
        'non_auto_submitted', 'non_auto_analysis'
    ]
    for key in keys_to_reset:
        st.session_state.pop(key, None)


# --- Fungsi-fungsi untuk Non-Automotif ---
def build_common_query(keywords, time_filter, use_condition_filter, use_url_filter):
    """Membangun query fleksibel untuk BARANG UMUM."""
    query_parts = [f'jual {keywords}']
    if use_condition_filter:
        query_parts.append("(inurl:bekas OR inurl:second OR inurl:seken OR inurl:seperti-baru OR inurl:2nd OR inurl:like-new) -BNIB -segel")
    if use_url_filter:
        query_parts.append("(site:tokopedia.com OR site:shopee.co.id)")
    query = " ".join(query_parts)
    params = {"q": query.strip(), "engine": "google", "gl": "id", "hl": "id", "location": "Jakarta, Jakarta, Indonesia"}
    if time_filter != "Semua Waktu":
        params["tbs"] = time_filter
    return params

def build_spare_part_query(keywords, time_filter, use_condition_filter, use_url_filter):
    """Membangun query optimal untuk kategori SPARE PART."""
    query_parts = [f'jual {keywords}']
    if use_condition_filter:
        query_parts.append("(inurl:bekas OR inurl:second OR inurl:seken OR inurl:seperti-baru OR inurl:2nd OR inurl:copotan OR inurl:like-new) -BNIB -segel")
    if use_url_filter:
        query_parts.append("(site:tokopedia.com OR site:shopee.co.id OR site:monotaro.id OR site:olx.co.id)")
    query = " ".join(query_parts)
    params = {"q": query.strip(), "engine": "google", "gl": "id", "hl": "id"}
    if time_filter != "Semua Waktu":
        params["tbs"] = time_filter
    return params

def build_heavy_equipment_query(alat_type, brand, model, year, time_filter, use_condition_filter, use_url_filter):
    """Membangun query optimal untuk kategori ALAT BERAT."""
    search_keywords = f'jual {alat_type} {brand} {model} tahun {year}'
    query_parts = [search_keywords]
    if use_condition_filter:
        query_parts.append("(bekas|second) -sewa -rental -disewakan")
    if use_url_filter:
        query_parts.append("(site:olx.co.id OR site:indotrading.com OR site:alatberat.com OR site:jualo.com)")
    query = " ".join(query_parts)
    params = {"q": query.strip(), "engine": "google", "gl": "id", "hl": "id"}
    if time_filter != "Semua Waktu":
        params["tbs"] = time_filter
    return params

def build_scrap_query(scrap_type, unit, time_filter):
    """Membangun query optimal untuk kategori SCRAP."""
    search_keywords = f'harga {scrap_type} bekas {unit}'
    params = {"q": search_keywords.strip(), "engine": "google", "gl": "id", "hl": "id"}
    if time_filter != "Semua Waktu":
        params["tbs"] = time_filter
    return params

def search_with_serpapi(params, api_key):
    """Melakukan pencarian menggunakan SerpAPI."""
    params["api_key"] = api_key
    try:
        response = requests.get("https://serpapi.com/search.json", params=params, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Gagal menghubungi SerpAPI: {e}")
        return None

def filter_and_extract_text_for_llm(serpapi_data, product_name):
    """Mengekstrak teks relevan dari hasil pencarian untuk dianalisis LLM."""
    texts = []
    main_keywords = [word.lower() for word in product_name.split() if len(word) > 2]
    negative_keywords = ['baru', 'bnib', 'resmi', 'official', 'store', 'casing', 'charger', 'aksesoris', 'sewa', 'rental']

    for result in serpapi_data.get('organic_results', []):
        title = result.get('title', '').lower()
        snippet = result.get('snippet', '').lower()
        full_text = title + " " + snippet

        if any(neg_word in full_text for neg_word in negative_keywords):
            continue
        if not any(main_word in full_text for main_word in main_keywords):
            continue

        texts.append(result.get('title', ''))
        texts.append(result.get('snippet', ''))

    for question in serpapi_data.get('related_questions', []):
        texts.append(question.get('question', ''))
        texts.append(question.get('snippet', ''))

    return "\n".join(filter(None, texts))

def extract_prices_from_text(text):
    """Mengekstrak harga dari teks menggunakan regex."""
    price_pattern = r'Rp\s*\.?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)'
    prices = []
    matches = re.findall(price_pattern, text)
    for match in matches:
        price_str = match.replace('.', '').replace(',', '.')
        try:
            price = float(price_str)
            if price > 1000:
                prices.append(price)
        except ValueError:
            continue
    return prices

def analyze_with_llm_non_auto(context_text, product_name, api_key, grade):
    """Mengirim teks yang sudah diproses ke OpenRouter untuk dianalisis."""
    llm_model = st.secrets["openrouter"]["model"]
    
    prompt = f"""
    Anda adalah asisten ahli analisis harga barang bekas yang bekerja di balai lelang digital LEGOAS.
    Tugas Anda adalah menganalisis KONTEKS PENCARIAN untuk menemukan harga pasaran wajar.

    PRODUK YANG DICARI: "{product_name}"
    GRADE KONDISI: "{grade}"

    KONTEKS PENCARIAN:
    ---
    {context_text[:15000]}
    ---

    INSTRUKSI UTAMA:
    1.  Fokus utama Anda adalah pada PRODUK YANG DICARI. Abaikan harga untuk produk atau aksesoris lain.
    2.  Berdasarkan data, berikan analisis singkat mengenai kondisi pasar dan variasi harga yang Anda temukan.
    3.  Berikan satu **rekomendasi harga jual wajar** untuk produk tersebut dalam kondisi bekas layak pakai (ini kita sebut sebagai "Harga Grade A"). Jelaskan alasan di balik angka ini.
    4.  Jika harga barang yang ditemukan bukan harga barang bekas, maka kalikan harga barang baru yang ditemukan dengan 85%.
    5.  Setelah menentukan Harga Grade A, hitung dan tampilkan harga untuk grade lainnya berdasarkan persentase berikut:
        -   **Harga Grade A (Kondisi Sangat Baik):** Tampilkan harga rekomendasi Anda.
        -   **Harga Grade B (Kondisi Baik):** Hitung 94% dari Harga Grade A.
        -   **Harga Grade C (Kondisi Cukup):** Hitung 80% dari Harga Grade A.
        -   **Harga Grade D (Kondisi Kurang):** Hitung 58% dari Harga Grade A.
        -   **Harga Grade E (Kondisi Apa Adanya):** Hitung 23% dari Harga Grade A.
    6.  Sajikan hasil akhir dalam format yang jelas, dimulai dengan analisis pasar, lalu diikuti oleh daftar harga berdasarkan grade. Beri penekanan (misalnya dengan bold) pada harga yang sesuai dengan **GRADE KONDISI** yang diminta pengguna.
    7.  JAWABAN HARUS DALAM BENTUK TEKS BIASA, BUKAN JSON.
    """
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": llm_model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200, "temperature": 0.2
            })
        )
        response.raise_for_status()
        response_data = response.json()
        if 'error' in response_data:
            st.error("API OpenRouter mengembalikan error:"); st.json(response_data)
            return None
        return response_data['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        st.error(f"Gagal menghubungi OpenRouter API: {e}")
        if e.response is not None: st.json(e.response.json())
        return None
    except (KeyError, IndexError) as e:
        st.error(f"Gagal mengolah respons dari AI: {e}"); st.json(response.json())
        return None

# ==============================================================================
# BAGIAN 2: HALAMAN APLIKASI DAN LOGIKA EKSEKUSI UTAMA
# ==============================================================================

# GANTI FUNGSI LOGIN LAMA ANDA DENGAN VERSI BARU INI
def login_page():
    """Menampilkan halaman login untuk pengguna."""
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<div class="login-icon">🔒</div><h2 class="login-title">Silakan Login Terlebih Dahulu</h2>', unsafe_allow_html=True)
    
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", type="password", placeholder="Masukkan password Anda")
        
        if st.form_submit_button("Masuk", use_container_width=True):
            # Mengambil daftar pengguna dari st.secrets
            users = st.secrets["users"]
            
            # Memeriksa apakah username ada dan password-nya cocok
            if username in users and users[username] == password:
                st.session_state.is_logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.markdown('<p class="error-message">Username atau password salah</p>', unsafe_allow_html=True)
                
    st.markdown('<div class="login-footer">Sistem Estimasi Harga LEGOAS<br>© 2025</div></div>', unsafe_allow_html=True)


def main_page():
    """Menampilkan halaman utama aplikasi setelah login berhasil."""
    # --- Muat Data ---
    # Membaca ID file mobil dari secrets
    GOOGLE_DRIVE_FILE_ID = st.secrets["data_sources"]["mobil_data_id"]
    
    # Inisialisasi data di session state jika belum ada
    if 'df_mobil' not in st.session_state:
        st.session_state.df_mobil = load_data_from_drive(GOOGLE_DRIVE_FILE_ID)
        st.session_state.df_motor = load_local_data("dt/mtr.csv")

    df_mobil = st.session_state.df_mobil
    df_motor = st.session_state.df_motor
    
    # --- Sidebar ---
    with st.sidebar:
        logo_path = "dt/logo.png"
        img_base64 = image_to_base64(logo_path)
        if img_base64:
            st.image(f"data:image/png;base64,{img_base64}", width=140)
        st.markdown("---")
        
        # Menu Pilihan Estimasi
        tipe_estimasi = st.radio(
            "Pilih Menu Estimasi", 
            ["Estimasi Mobil", "Estimasi Motor", "Estimasi Non-Automotif"], 
            on_change=reset_prediction_state
        )
        
        # Pengaturan Pencarian dinamis hanya untuk Non-Automotif
        if tipe_estimasi == "Estimasi Non-Automotif":
            st.markdown("---")
            st.subheader("Pengaturan Pencarian")
            category = st.selectbox("1. Pilih Kategori Barang", ["Umum", "Spare Part", "Alat Berat", "Scrap"])
            time_filter_options = {"Semua Waktu": "Semua Waktu", "Setahun Terakhir": "qdr:y", "Sebulan Terakhir": "qdr:m", "Seminggu Terakhir": "qdr:w"}
            selected_time_filter = st.selectbox("2. Filter Waktu", options=list(time_filter_options.keys()))
            time_filter_value = time_filter_options[selected_time_filter]

            st.subheader("Filter Lanjutan")
            use_condition_filter = st.checkbox("Fokus Barang Bekas", value=True, help="Fokus mencari barang bekas dan mengabaikan iklan barang baru.")
            use_url_filter = st.checkbox("Fokus Situs Jual-Beli", value=True, help="Pencarian diprioritaskan pada situs jual-beli utama.")
        
        # Tombol Keluar di bagian bawah
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("🔒 Keluar", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- Halaman Utama ---
    st.markdown('<h1 class="main-header">Sistem Estimasi Harga LEGOAS</h1>', unsafe_allow_html=True)

    # ========================
    # --- ESTIMASI MOBIL ---
    # ========================
    if tipe_estimasi == "Estimasi Mobil":
        st.markdown('<h2 class="section-header">Estimasi Harga Mobil Bekas</h2>', unsafe_allow_html=True)
        
        if df_mobil.empty:
            st.error("Data mobil tidak dapat dimuat. Aplikasi tidak dapat dilanjutkan.")
            return
            
        col1, col2 = st.columns(2)
        with col1:
            brand = st.selectbox("Brand", ["-"] + sorted(df_mobil["name"].unique()), key="car_brand", on_change=reset_prediction_state)
        with col2:
            model_options = ["-"] + (sorted(df_mobil[df_mobil["name"] == brand]["model"].unique()) if brand != "-" else [])
            model = st.selectbox("Model", model_options, key="car_model", on_change=reset_prediction_state)

        col3, col4 = st.columns(2)
        with col3:
            varian_options = ["-"] + (sorted(df_mobil[(df_mobil["name"] == brand) & (df_mobil["model"] == model)]["varian"].unique()) if brand != "-" and model != "-" else [])
            varian = st.selectbox("Varian", varian_options, key="car_varian", on_change=reset_prediction_state)
        with col4:
            year_options = ["-"] + (sorted(df_mobil[(df_mobil["name"] == brand) & (df_mobil["model"] == model) & (df_mobil["varian"] == varian)]["tahun"].unique(), reverse=True))
            year = st.selectbox("Tahun", [str(y) for y in year_options], key="car_year", on_change=reset_prediction_state)

        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True, key="car_estimate_button"):
            if "-" in [brand, model, varian, year]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
            else:
                mask = ( (df_mobil["name"] == brand) & (df_mobil["model"] == model) & (df_mobil["varian"] == varian) & (df_mobil["tahun"] == int(year)) )
                results = df_mobil[mask]
                if not results.empty:
                    st.session_state.prediction_made_car = True
                    st.session_state.selected_data_car = results.iloc[0]
                else:
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
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
                    prompt = f"""Sebagai analis pasar otomotif di LEGOAS, berikan analisis harga untuk mobil bekas:
- Detail: {selected_data['name']} {selected_data['model']} {selected_data['varian']} tahun {int(selected_data['tahun'])}
- Grade Kondisi: {grade_selection}
- Estimasi Harga Akhir: {format_rupiah(adjusted_price)}

Tugas Anda: Jelaskan secara profesional mengapa harga tersebut wajar, hubungkan dengan grade, sentimen pasar, popularitas model, dan kondisi ekonomi di tahun {pd.Timestamp.now().year}. Gunakan format poin-poin."""
                    response = ask_openrouter(prompt)
                    st.session_state.ai_response_car = response
                    
                    if response and not response.startswith("⚠️"):
                        # Siapkan timestamp dan user sekarang
                        jakarta_tz = pytz.timezone('Asia/Jakarta')
                        timestamp = datetime.now(jakarta_tz).isoformat()
                        user = st.session_state.get('username', 'unknown')
    
                        # Gabungkan detail pencarian menjadi satu string
                        detail_query = f"Mobil: {selected_data['name']} {selected_data['model']} {selected_data['varian']} ({int(selected_data['tahun'])})"

                        log_payload = {
                            "timestamp": timestamp, "user": user, "tipe_estimasi": "Mobil",
                            "detail_query": detail_query, "grade_dipilih": grade_selection,
                            "harga_awal": initial_price, "harga_disesuaikan": adjusted_price,
                            "respon_llm": response
                        }
                        log_activity_to_sheet(log_payload) # Panggil fungsi yang baru

            if st.session_state.get('ai_response_car'):
                st.markdown("---")
                st.subheader("🤖 AI Analisis LEGOAS")
                st.markdown(st.session_state.ai_response_car)

    # ========================
    # --- ESTIMASI MOTOR ---
    # ========================
    elif tipe_estimasi == "Estimasi Motor":
        st.markdown('<h2 class="section-header">Estimasi Harga Motor Bekas</h2>', unsafe_allow_html=True)
        
        if df_motor.empty:
            st.warning("Data motor tidak dapat dimuat. Fitur ini tidak tersedia.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                brand = st.selectbox("Brand", ["-"] + sorted(df_motor["brand"].unique()), key="motor_brand", on_change=reset_prediction_state)
            with col2:
                variant_options = ["-"] + (sorted(df_motor[df_motor["brand"] == brand]["variant"].unique()) if brand != "-" else [])
                variant = st.selectbox("Varian", variant_options, key="motor_variant", on_change=reset_prediction_state)
            
            year_options = ["-"] + (sorted(df_motor[(df_motor["brand"] == brand) & (df_motor["variant"] == variant)]["year"].unique(), reverse=True))
            year = st.selectbox("Tahun", [str(y) for y in year_options], key="motor_year", on_change=reset_prediction_state)

            if st.button("🔍 Lihat Estimasi Harga", use_container_width=True, key="motor_estimate_button"):
                if "-" in [brand, variant, year]:
                    st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
                else:
                    mask = ( (df_motor["brand"] == brand) & (df_motor["variant"] == variant) & (df_motor["year"] == int(year)) )
                    results = df_motor[mask]
                    if not results.empty:
                        st.session_state.prediction_made_motor = True
                        st.session_state.selected_data_motor = results.iloc[0]
                    else:
                        st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                        reset_prediction_state()

            if st.session_state.get('prediction_made_motor'):
                selected_data = st.session_state.selected_data_motor
                initial_price = selected_data.get("output", 0)
                st.markdown("---")
                st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
                
                grade_selection = st.selectbox("Pilih Grade Kondisi Kendaraan", options=list(GRADE_FACTORS.keys()), key="motor_grade")
                adjusted_price = initial_price * GRADE_FACTORS[grade_selection]
                st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

                if st.button("🤖 Generate Analisis Profesional", use_container_width=True, key="motor_ai_button"):
                    with st.spinner("Menganalisis harga motor..."):
                        prompt = f"""Sebagai analis pasar otomotif di LEGOAS, berikan analisis harga untuk motor bekas:
- Detail: {selected_data['brand']} {selected_data['variant']} tahun {int(selected_data['year'])}
- Grade Kondisi: {grade_selection}
- Estimasi Harga Akhir: {format_rupiah(adjusted_price)}

Tugas Anda: Jelaskan secara profesional mengapa harga tersebut wajar, hubungkan dengan grade, sentimen pasar, popularitas model, dan kondisi ekonomi di tahun {pd.Timestamp.now().year}. Gunakan format poin-poin."""
                        response = ask_openrouter(prompt)
                        st.session_state.ai_response_motor = response

                        if response and not response.startswith("⚠️"):
                            log_payload = { "tipe_estimasi": "Motor", "brand": selected_data['brand'], "varian": selected_data['variant'], "tahun": int(selected_data['year']), "grade_dipilih": grade_selection, "harga_awal": initial_price, "harga_disesuaikan": adjusted_price, "respon_llm": response }
                            log_activity_to_drive(log_payload)

                if st.session_state.get('ai_response_motor'):
                    st.markdown("---")
                    st.subheader("🤖 AI Analisis LEGOAS")
                    st.markdown(st.session_state.ai_response_motor)

    # =============================
    # --- ESTIMASI NON-AUTOMOTIF ---
    # =============================
    elif tipe_estimasi == "Estimasi Non-Automotif":
        st.markdown('<h2 class="section-header">Estimasi Harga Barang Non-Automotif</h2>', unsafe_allow_html=True)
        
        with st.form("non_auto_form"):
            product_name_display = ""
            grade_input = "A" 

            if category == "Umum":
                keywords = st.text_input("Masukkan Nama Barang", "iPhone 14 Pro 256GB", help="Coba sespesifik mungkin untuk hasil terbaik.")
                product_name_display = keywords
            elif category == "Spare Part":
                keywords = st.text_input("Masukkan Nama Spare Part", "Busi Honda Vario 125", help="Contoh: 'Kampas rem Avanza'")
                product_name_display = keywords
            elif category == "Alat Berat":
                alat_type = st.text_input("Jenis Alat", "Excavator")
                brand = st.text_input("Merek", "Komatsu")
                model = st.text_input("Model / Kapasitas", "PC200-8")
                year = st.text_input("Tahun (Wajib)", "2015")
                product_name_display = f"{alat_type} {brand} {model} {year}"
            elif category == "Scrap":
                scrap_type = st.selectbox("Pilih Jenis Limbah", ["Besi Tua", "Tembaga", "Aluminium", "Aki Bekas", "Oli Bekas", "Kardus Bekas"])
                unit = st.selectbox("Pilih Satuan Harga", ["per kg", "per liter", "per drum", "per unit"])
                product_name_display = f"{scrap_type} ({unit})"

            if category != "Scrap":
                grade_input = st.selectbox("Pilih Grade Kondisi Barang", ["A", "B", "C", "D", "E"], help="A (Sangat Baik), E (Buruk).")

            submitted = st.form_submit_button("Analisis Harga Sekarang!", use_container_width=True)

        if submitted:
            SERPAPI_API_KEY = st.secrets["openrouter"]["serpapi"]
            OPENROUTER_API_KEY = st.secrets["openrouter"]["api_key"]
            params = {}
            if category == "Umum": params = build_common_query(keywords, time_filter_value, use_condition_filter, use_url_filter)
            elif category == "Spare Part": params = build_spare_part_query(keywords, time_filter_value, use_condition_filter, use_url_filter)
            elif category == "Alat Berat": params = build_heavy_equipment_query(alat_type, brand, model, year, time_filter_value, use_condition_filter, use_url_filter)
            elif category == "Scrap": params = build_scrap_query(scrap_type, unit, time_filter_value)

            with st.spinner(f"Menganalisis harga untuk '{product_name_display}'..."):
                st.info("Langkah 1/3: Mengambil data dari internet...")
                serpapi_data = search_with_serpapi(params, SERPAPI_API_KEY)

                if serpapi_data:
                    st.info("Langkah 2/3: Memfilter & membersihkan data...")
                    context_text = filter_and_extract_text_for_llm(serpapi_data, product_name_display)
                    if context_text:
                        st.info("Langkah 3/3: Mengirim data ke AI untuk dianalisis...")
                        ai_analysis = analyze_with_llm_non_auto(context_text, product_name_display, OPENROUTER_API_KEY, grade_input)
                        if ai_analysis:
                            st.success("Analisis Selesai!")
                            st.subheader(f"📝 Analisis AI LEGOAS untuk {product_name_display}")
                            st.markdown(ai_analysis)
                            
                            # Simpan log setelah analisis berhasil
                            log_payload = { "tipe_estimasi": "Non-Automotif", "kategori": category, "query_pencarian": product_name_display, "filter_waktu": selected_time_filter, "filter_kondisi": use_condition_filter, "filter_situs": use_url_filter, "grade_dipilih": grade_input if category != 'Scrap' else 'N/A', "respon_llm": ai_analysis }
                            log_activity_to_drive(log_payload)
                        else: st.error("Analisis Gagal: Tidak menerima respons dari AI.")
                    else: st.error("Ekstraksi Teks Gagal: Tidak ada hasil pencarian yang relevan.")
                else: st.error("Pengambilan Data Gagal: Tidak menerima data dari SerpAPI.")

# ==============================================================================
# LOGIKA EKSEKUSI UTAMA
# ==============================================================================

def main():
    """Fungsi utama untuk menjalankan aplikasi."""
    if not st.session_state.get("is_logged_in", False):
        login_page()
    else:
        main_page()

if __name__ == "__main__":
    main()

# --- Akhir dari Skrip ---






