import streamlit as st
import pandas as pd
import base64
import requests
import io
import re
import json
import numpy as np

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
GOOGLE_DRIVE_FILE_ID = st.secrets["logging"]["folder_id"]

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
    page_title="Sistem Estimasi Harga LEGOAS",
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
        .main-header { color: #2C3E50; text-align: center; margin-bottom: 2rem; }
        .section-header { color: #2C3E50; border-bottom: 2px solid #3498DB; padding-bottom: 0.5rem; margin-top: 1.5rem; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# FUNGSI-FUNGSI HELPER UNTUK AUTOMOTIF
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
                # PERBAIKAN DI SINI: Hapus koma sebelum konversi ke numerik
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
                    # Hapus juga koma jika ada di data motor
                    df[col] = df[col].astype(str).str.replace(',', '', regex=False)
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
        'prediction_made_motor', 'selected_data_motor', 'ai_response_motor',
        'non_auto_submitted', 'non_auto_analysis'
    ]
    for key in keys_to_reset:
        st.session_state.pop(key, None)
        
# ==============================================================================
# FUNGSI LOGGING KE GOOGLE DRIVE
# ==============================================================================

def setup_logging_service():
    """Setup service untuk Google Drive logging"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"Gagal setup logging service: {e}")
        return None

def create_log_entry(activity_type, details, username="legoas"):
    """Membuat entri log"""
    import datetime
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "username": username,
        "activity_type": activity_type,
        "details": details,
        "ip_address": get_client_ip()  # Fungsi untuk mendapatkan IP client
    }

def get_client_ip():
    """Mendapatkan IP address client (hanya bekerja di beberapa environment)"""
    try:
        import streamlit as st
        # Cara alternatif mendapatkan IP (mungkin tidak bekerja di semua deployment)
        ctx = st.runtime.scriptrunner.get_script_run_ctx()
        if ctx and hasattr(ctx, 'request'):
            return ctx.request.remote_ip
        return "Unknown"
    except:
        return "Unknown"

def save_log_to_drive(log_entry, folder_id=None):
    """Menyimpan log ke Google Drive"""
    try:
        service = setup_logging_service()
        if not service:
            return False
        
        # Nama file log berdasarkan tanggal
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log_filename = f"legoas_activity_log_{today}.json"
        
        # Cari file log hari ini
        query = f"name='{log_filename}' and trashed=false"
        if folder_id:
            query += f" and '{folder_id}' in parents"
        
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if files:
            # File sudah ada, update isinya
            file_id = files[0]['id']
            # Download file existing
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            file_stream.seek(0)
            existing_content = file_stream.read().decode('utf-8')
            
            # Parse existing logs
            try:
                existing_logs = json.loads(existing_content)
            except:
                existing_logs = []
            
            # Tambah log baru
            existing_logs.append(log_entry)
            
            # Upload kembali
            updated_content = json.dumps(existing_logs, indent=2, ensure_ascii=False)
            media_body = MediaIoBaseUpload(io.BytesIO(updated_content.encode('utf-8')), 
                                         mimetype='application/json')
            service.files().update(fileId=file_id, media_body=media_body).execute()
            
        else:
            # Buat file baru
            file_metadata = {
                'name': log_filename,
                'mimeType': 'application/json'
            }
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            logs_content = json.dumps([log_entry], indent=2, ensure_ascii=False)
            media_body = MediaIoBaseUpload(io.BytesIO(logs_content.encode('utf-8')), 
                                         mimetype='application/json')
            service.files().create(body=file_metadata, media_body=media_body).execute()
        
        return True
        
    except Exception as e:
        print(f"Error saving log to Drive: {e}")  # Print error untuk debugging
        return False

def log_activity(activity_type, details, username="legoas"):
    """Fungsi utama untuk logging aktivitas"""
    log_entry = create_log_entry(activity_type, details, username)
    
    # Simpan ke Google Drive (gunakan folder ID dari secrets jika ada)
    folder_id = st.secrets.get("logging", {}).get("folder_id")
    success = save_log_to_drive(log_entry, folder_id)
    
    # Juga simpan ke session state untuk cache lokal
    if 'activity_logs' not in st.session_state:
        st.session_state.activity_logs = []
    st.session_state.activity_logs.append(log_entry)
    
    return success

# ==============================================================================
# FUNGSI-FUNGSI UNTUK NON-AUTOMOTIF
# ==============================================================================

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
    """Melakukan pencarian menggunakan API."""
    params["api_key"] = api_key
    try:
        response = requests.get("https://serpapi.com/search.json", params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Gagal menghubungi SerpAPI: {e}")
        return None

def filter_and_extract_text_for_llm(serpapi_data, product_name):
    """Mengekstrak teks relevan DARI HASIL YANG SUDAH DIFILTER untuk presisi."""
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
    """Fungsi untuk mengekstrak harga dari teks menggunakan regex."""
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
    """Mengirim teks yang sudah diproses ke OpenRouter untuk dianalisis dengan memperhitungkan grade."""
    llm_model = st.secrets["openrouter"]["model"]
    
    # Menambahkan instruksi kalkulasi grade ke dalam prompt
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
                # LOG ACTIVITY
                log_activity("LOGIN", f"User {username} berhasil login")
                st.rerun()
            else:
                # LOG FAILED ATTEMPT
                log_activity("LOGIN_FAILED", f"Percobaan login gagal dengan username: {username}")
                st.markdown('<p class="error-message">Username atau password salah</p>', unsafe_allow_html=True)
    st.markdown('<div class="login-footer">Sistem Estimasi Harga LEGOAS<br>© 2025</div></div>', unsafe_allow_html=True)

def main_page():
    if 'df_mobil' not in st.session_state:
        st.session_state.df_mobil = load_data_from_drive(GOOGLE_DRIVE_FILE_ID)
        st.session_state.df_motor = load_local_data("dt/mtr.csv")

    df_mobil = st.session_state.df_mobil
    df_motor = st.session_state.df_motor
    
    with st.sidebar:
        logo_path = "dt/logo.png"
        img_base64 = image_to_base64(logo_path)
        if img_base64:
            st.image(f"data:image/png;base64,{img_base64}", width=140)
        st.markdown("---")
        tipe_estimasi = st.radio("Menu", ["Estimasi Mobil", "Estimasi Motor", "Estimasi Non-Automotif"], on_change=reset_prediction_state)
        
        # Tampilkan pengaturan pencarian hanya untuk non-automotif
        if tipe_estimasi == "Estimasi Non-Automotif":
            st.markdown("---")
            st.subheader("Pengaturan Pencarian")
            category = st.selectbox(
                "1. Pilih Kategori Barang",
                ["Umum", "Spare Part", "Alat Berat", "Scrap"]
            )
            time_filter_options = {"Semua Waktu": "Semua Waktu", "Setahun Terakhir": "qdr:y", "Sebulan Terakhir": "qdr:m", "Seminggu Terakhir": "qdr:w"}
            selected_time_filter = st.selectbox("2. Filter Waktu", options=list(time_filter_options.keys()))
            time_filter_value = time_filter_options[selected_time_filter]

            st.subheader("Filter Lanjutan")
            use_condition_filter = st.checkbox(
                "Fokus Barang Bekas", value=True,
                help="Jika aktif, AI akan fokus mencari barang bekas dan mengabaikan iklan barang baru atau segel."
            )
            use_url_filter = st.checkbox(
                "Fokus Situs Jual-Beli", value=True,
                help="Jika aktif, pencarian akan diprioritaskan pada situs jual-beli utama untuk hasil yang lebih relevan."
            )
        
        # Menambahkan spasi untuk mendorong tombol keluar ke bawah
        st.markdown("---")
        st.markdown("<div style='flex-grow: 1;'></div>", unsafe_allow_html=True)
        
        # Di dalam main_page(), modifikasi tombol keluar:
        if st.button("🔒 Keluar", use_container_width=True):
            # LOG ACTIVITY
            log_activity("LOGOUT", "User keluar dari sistem")
            st.session_state.is_logged_in = False
            st.rerun()

    st.markdown('<div class="main-content">', unsafe_allow_html=True)
    st.markdown('<h1 class="main-header">Sistem Estimasi Harga LEGOAS</h1>', unsafe_allow_html=True)

    # --- BAGIAN ESTIMASI MOBIL ---
    if tipe_estimasi == "Estimasi Mobil":
        st.markdown('<h2 class="section-header">Estimasi Harga Mobil Bekas</h2>', unsafe_allow_html=True)
        
        if df_mobil.empty:
            st.error("Data mobil tidak dapat dimuat. Aplikasi tidak dapat dilanjutkan.")
            return
            
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

        # Di bagian estimasi mobil, setelah tombol "Lihat Estimasi Harga"
        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True, key="car_estimate_button"):
            if "-" in [brand, model, varian, year]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
            else:
                mask = ( (df_source["name"] == brand) & (df_source["model"] == model) & (df_source["varian"] == varian) & (df_source["tahun"] == int(year)) )
                results = df_source[mask]
        
                if not results.empty:
                    st.session_state.prediction_made_car = True
                    st.session_state.selected_data_car = results.iloc[0]
            
                    # LOG ACTIVITY
                    selected_data = results.iloc[0]
                    log_details = {
                        "brand": brand,
                        "model": model, 
                        "varian": varian,
                        "tahun": year,
                        "harga_estimasi": selected_data.get("output", 0)
                    }
                    log_activity("ESTIMASI_MOBIL", log_details)
            
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
            
            grade_selection = st.selectbox("Pilih Grade Kondisi Kendaraan", options=list(GRADE_FACTORS.keys()), key="car_grade")
            adjusted_price = initial_price * GRADE_FACTORS[grade_selection]
            st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

            if st.button("🤖 Generate Analisis Profesional", use_container_width=True, key="car_ai_button"):
                with st.spinner("Menganalisis harga mobil..."):
                    prompt = f"""
                    Sebagai seorang analis pasar otomotif yang bekerja di balai lelang digital bernama LEGOAS, berikan analisis harga untuk mobil bekas dengan spesifikasi berikut:
                    - Brand: {selected_data['name']}
                    - Model: {selected_data['model']}
                    - Varian: {selected_data['varian']}
                    - Tahun: {int(selected_data['tahun'])}
                    - Grade Kondisi: {grade_selection}

                    Data keuangan internal kami menunjukkan detail berikut:
                    - Estimasi Harga Akhir (setelah penyesuaian Grade): {format_rupiah(adjusted_price)}

                    Tugas Anda:
                    Jelaskan secara profesional mengapa Estimasi Harga Akhir ({format_rupiah(adjusted_price)}) adalah angka yang wajar. Hubungkan penjelasan Anda dengan Grade Kondisi yang dipilih. Sebutkan juga faktor eksternal seperti sentimen pasar, popularitas model, dan kondisi ekonomi di tahun {pd.Timestamp.now().year}.
                    
                    Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                    """
                    st.session_state.ai_response_car = ask_openrouter(prompt)

            if st.session_state.get('ai_response_car'):
                st.markdown("---")
                st.subheader("🤖 AI Analisis LEGOAS untuk Estimasi Harga")
                st.markdown(st.session_state.ai_response_car)

    # --- BAGIAN ESTIMASI MOTOR ---
    elif tipe_estimasi == "Estimasi Motor":
        st.markdown('<h2 class="section-header">Estimasi Harga Motor Bekas</h2>', unsafe_allow_html=True)
        
        if df_motor.empty:
            st.warning("Data motor tidak dapat dimuat. Fitur ini tidak tersedia.")
        else:
            df_source = df_motor

            col1, col2 = st.columns(2)
            with col1:
                brand_options = ["-"] + sorted(df_source["brand"].unique())
                brand = st.selectbox("Brand", brand_options, key="motor_brand", on_change=reset_prediction_state)
            with col2:
                variant_options = ["-"] + (sorted(df_source[df_source["brand"] == brand]["variant"].unique()) if brand != "-" else [])
                variant = st.selectbox("Varian", variant_options, key="motor_variant", on_change=reset_prediction_state)

            year_options = ["-"] + (sorted(df_source[(df_source["brand"] == brand) & (df_source["variant"] == variant)]["year"].unique(), reverse=True))
            year = st.selectbox("Tahun", [str(y) for y in year_options], key="motor_year", on_change=reset_prediction_state)

        # Di bagian estimasi motor, setelah tombol "Lihat Estimasi Harga"
        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True, key="motor_estimate_button"):
            if "-" in [brand, variant, year]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
                else:
                mask = ( (df_source["brand"] == brand) & (df_source["variant"] == variant) & (df_source["year"] == int(year)) )
                results = df_source[mask]
        
                if not results.empty:
                    st.session_state.prediction_made_motor = True
                    st.session_state.selected_data_motor = results.iloc[0]
            
                    # LOG ACTIVITY
                    selected_data = results.iloc[0]
                    log_details = {
                        "brand": brand,
                        "variant": variant,
                        "tahun": year,
                        "harga_estimasi": selected_data.get("output", 0)
                    }
                    log_activity("ESTIMASI_MOTOR", log_details)
            
                    if len(results) > 1:
                        st.warning(f"⚠️ Ditemukan {len(results)} data duplikat. Menampilkan hasil pertama.")
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
                        prompt = f"""
                        Sebagai seorang analis pasar otomotif, berikan analisis harga untuk motor bekas dengan spesifikasi berikut:
                        - Brand: {selected_data['brand']}
                        - Varian: {selected_data['variant']}
                        - Tahun: {int(selected_data['year'])}
                        - Grade Kondisi: {grade_selection}

                        Data keuangan internal kami menunjukkan detail berikut:
                        - Estimasi Harga Akhir (setelah penyesuaian Grade): {format_rupiah(adjusted_price)}

                        Tugas Anda:
                        Jelaskan secara profesional mengapa Estimasi Harga Akhir ({format_rupiah(adjusted_price)}) adalah angka yang wajar. Hubungkan penjelasan Anda dengan Grade Kondisi yang dipilih. Sebutkan juga faktor eksternal seperti sentimen pasar, popularitas model, dan kondisi ekonomi di tahun {pd.Timestamp.now().year}.
                        
                        Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                        """
                        st.session_state.ai_response_motor = ask_openrouter(prompt)

                if st.session_state.get('ai_response_motor'):
                    st.markdown("---")
                    st.subheader("🤖 AI Analisis LEGOAS untuk Estimasi Harga")
                    st.markdown(st.session_state.ai_response_motor)

    # --- BAGIAN ESTIMASI NON-AUTOMOTIF ---
    elif tipe_estimasi == "Estimasi Non-Automotif":
        st.markdown('<h2 class="section-header">Estimasi Harga Barang Non-Automotif</h2>', unsafe_allow_html=True)
        
        # Form untuk input non-automotif
        with st.form("non_auto_form"):
            product_name_display = ""
            grade_input = "A"  # Default grade

            # Langkah 1: Pengguna mengisi detail barang terlebih dahulu
            if category == "Umum":
                st.subheader("📦 Detail Barang Umum")
                keywords = st.text_input("Masukkan Nama Barang", "iPhone 14 Pro 256GB", help="Tips: Coba sespesifik mungkin untuk hasil terbaik.")
                product_name_display = keywords.lower()
            elif category == "Spare Part":
                st.subheader("⚙️ Detail Spare Part")
                keywords = st.text_input("Masukkan Nama Spare Part", "Busi Honda Vario 125", help="Contoh: 'Kampas rem Avanza', 'Filter oli Xenia 1.3'")
                product_name_display = keywords.lower()
            elif category == "Alat Berat":
                st.subheader("🛠️ Detail Alat Berat")
                alat_type = st.text_input("Jenis Alat", "Excavator")
                brand = st.text_input("Merek", "Komatsu")
                model = st.text_input("Model / Kapasitas", "PC200-8")
                year = st.text_input("Tahun (Wajib)", "2015")
                product_name_display = f"{alat_type} {brand} {model} {year}".strip().lower()
            elif category == "Scrap":
                st.subheader("♻️ Detail Limbah (Scrap)")
                scrap_options = ["Besi Tua", "Tembaga", "Aluminium", "Kuningan", "Aki Bekas", "Minyak Jelantah", "Oli Bekas", "Kardus Bekas", "Botol Plastik PET"]
                scrap_type = st.selectbox("Pilih Jenis Limbah", scrap_options)
                unit_options = ["per kg", "per liter", "per drum", "per unit"]
                unit = st.selectbox("Pilih Satuan Harga", unit_options)
                product_name_display = f"{scrap_type} ({unit})"

            # Langkah 2: Pengguna memilih grade sebagai opsi terakhir (jika bukan Scrap)
            if category in ["Umum", "Spare Part", "Alat Berat"]:
                st.subheader("⭐ Pilih Grade Kondisi Barang")
                grade_input = st.selectbox(
                    "Grade", 
                    options=["A", "B", "C", "D", "E"],
                    help="Pilih kondisi barang: A (Sangat Baik), B (Baik), C (Cukup), D (Kurang), E (Buruk)."
                )

            # Langkah 3: Tombol Submit
            submitted = st.form_submit_button("Analisis Harga Sekarang!")
            
        # Proses analisis non-automotif
        if submitted:
            SERPAPI_API_KEY = st.secrets["openrouter"]["serpapi"]
            OPENROUTER_API_KEY = st.secrets["openrouter"]["api_key"]
            LLM_MODEL = st.secrets["openrouter"]["model"]

            if not all([SERPAPI_API_KEY, OPENROUTER_API_KEY, LLM_MODEL]):
                st.error("Harap konfigurasikan SERPAPI_API_KEY, OPENROUTER_API_KEY, dan LLM_MODEL di Streamlit Secrets!")
            else:
                params = {}
                if category == "Umum":
                    params = build_common_query(keywords, time_filter_value, use_condition_filter, use_url_filter)
                elif category == "Spare Part":
                    params = build_spare_part_query(keywords, time_filter_value, use_condition_filter, use_url_filter)
                elif category == "Alat Berat":
                    params = build_heavy_equipment_query(alat_type, brand, model, year, time_filter_value, use_condition_filter, use_url_filter)
                elif category == "Scrap":
                    params = build_scrap_query(scrap_type, unit, time_filter_value)

                with st.spinner(f"Menganalisis harga untuk '{product_name_display}' (Grade {grade_input if category != 'Scrap' else 'N/A'})..."):
                    st.info("Langkah 1/4: Mengambil data pencarian dari API...")
                    serpapi_data = search_with_serpapi(params, SERPAPI_API_KEY)

                    if serpapi_data:
                        st.info("Langkah 2/4: Memfilter hasil pencarian untuk akurasi...")
                        context_text = filter_and_extract_text_for_llm(serpapi_data, product_name_display)

                        if context_text:
                            st.info("Langkah 3/4: Mengirim data bersih ke AI untuk analisis harga...")
                            # Melewatkan nilai grade_input ke fungsi analisis AI
                            ai_analysis = analyze_with_llm_non_auto(context_text, product_name_display, OPENROUTER_API_KEY, grade_input)

                            if ai_analysis:
                                st.info("Langkah 4/4: Menyiapkan laporan hasil analisis...")
                                st.balloons()
                                st.success("Analisis Harga Selesai!")
                                
                                # LOG ACTIVITY
                                log_details = {
                                    "kategori": category,
                                    "produk": product_name_display,
                                    "grade": grade_input if category != "Scrap" else "N/A",
                                    "filter_waktu": selected_time_filter
                                    }
                                    log_activity("ESTIMASI_NON_AUTOMOTIF", log_details)
            
                                st.subheader(f"📝 Analisis AI LEGOAS untuk Harga {product_name_display}")
                                st.markdown("### Rekomendasi & Analisis AI")
                                st.write(ai_analysis)

                                extracted_prices = extract_prices_from_text(context_text)
                                if not extracted_prices:
                                    st.info("Catatan: AI tidak menemukan angka harga spesifik dalam hasil pencarian, analisis mungkin bersifat lebih umum.")
                                
                                # Simpan state
                                st.session_state.non_auto_submitted = True
                                st.session_state.non_auto_analysis = ai_analysis
                            else:
                                st.error("Analisis Gagal: Tidak menerima respons dari AI.")
                        else:
                            st.error("Ekstraksi Teks Gagal: Tidak ada hasil pencarian yang relevan ditemukan setelah filtering.")
                            st.warning("**Saran:** Coba sederhanakan nama barang Anda, periksa kembali ejaan, atau nonaktifkan filter di sidebar untuk memperluas pencarian.")
                    else:
                        st.error("Pengambilan Data Gagal: Tidak menerima data dari SerpAPI.")

        # Tampilkan hasil analisis jika sudah ada
        if st.session_state.get('non_auto_submitted') and st.session_state.get('non_auto_analysis'):
            st.markdown("---")
            st.subheader(f"📝 Analisis AI LEGOAS untuk Harga {product_name_display}")
            st.markdown("### Rekomendasi & Analisis AI")
            st.write(st.session_state.non_auto_analysis)

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



