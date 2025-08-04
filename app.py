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

# ------------ KONFIGURASI LOGIN (Catatan: Untuk production, gunakan metode yang lebih aman) ------------
USERNAME = "legoas"
PASSWORD = "admin"

# --- ID File JSON di Google Drive ---
# Cara mendapatkan ID: Klik kanan pada file di GDrive > Get link > Salin bagian ini:
# https://drive.google.com/file/d/INI_ADALAH_ID_NYA/view?usp=sharing
GOOGLE_DRIVE_FILE_ID = "1unFiGov9gRo15wRSCiRs96roM5idAYob"


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
        .error-message {
            color: #E74C3C;
            font-weight: bold;
            text-align: center;
        }
        .login-container {
            max-width: 450px;
            margin: auto;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            text-align: center; /* Menambahkan perataan tengah */
        }
        .login-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        .login-title {
            color: #2C3E50;
            margin-bottom: 1.5rem;
        }
        .login-footer {
            margin-top: 2rem;
            font-size: 0.9rem;
            color: #7F8C8D;
        }
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Anda adalah seorang analis keuangan dan pasar otomotif profesional."},
            {"role": "user", "content": prompt}
        ]
    }
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
        while not done:
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
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path)
            # Membersihkan nama kolom untuk konsistensi
            df.columns = df.columns.str.strip().str.lower()
            # Kolom yang harusnya numerik di dataset motor
            numeric_cols_csv = ['output', 'residu', 'depresiasi_residu', 'estimasi_1', 'year']
            for col in numeric_cols_csv:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            return df
        else:
            st.error(f"Format file lokal tidak didukung: {path}")
            return pd.DataFrame()
    except FileNotFoundError:
        st.error(f"File data motor tidak ditemukan di path: {path}")
        return pd.DataFrame()

# Fungsi baru untuk memuat data average
# VERSI BARU YANG BENAR
@st.cache_data
def load_avg_data():
    """Memuat data average dari file CSV lokal."""
    try:
        df = pd.read_csv("dt/avg.csv")

        # PERBAIKAN: Langsung gunakan kolom vehicleModelDate sebagai tahun
        # 1. Konversi kolom 'vehicleModelDate' ke tipe numerik, paksa error menjadi NaN (Not a Number)
        df['tahun'] = pd.to_numeric(df['vehicleModelDate'], errors='coerce')

        # 2. Hapus baris di mana konversi tahun gagal (menjadi NaN)
        df = df.dropna(subset=['tahun'])

        # 3. Ubah tipe data kolom 'tahun' menjadi integer (bilangan bulat)
        df['tahun'] = df['tahun'].astype(int)
        
        # Konversi kolom harga ke numerik
        if 'avg_price' in df.columns:
             df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce').fillna(0)
             
        return df
    except FileNotFoundError:
        st.error("File data average tidak ditemukan di path: dt/avg.csv")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Gagal memuat data average: {e}")
        return pd.DataFrame()

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
    """Mereset semua state yang berhubungan dengan prediksi agar UI kembali ke awal."""
    keys_to_reset = [
        'prediction_made_car', 'selected_data_car', 'ai_response_car',
        'prediction_made_motor', 'selected_data_motor', 'ai_response_motor'
    ]
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]

# ==============================================================================
# HALAMAN APLIKASI
# ==============================================================================

def login_page():
    # PERBAIKAN: Menambahkan class CSS yang sudah didefinisikan agar style teraplikasi
    st.markdown("""
        <div class="login-container">
            <div class="login-icon">🔒</div>
            <h2 class="login-title">Silakan Login Terlebih Dahulu</h2>
    """, unsafe_allow_html=True)
    
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", key="username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", key="password", type="password", placeholder="Masukkan password Anda")
        submit_button = st.form_submit_button("Masuk", use_container_width=True)
        
        if submit_button:
            if username == USERNAME and password == PASSWORD:
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.markdown('<p class="error-message">Username atau password salah</p>', unsafe_allow_html=True)
    
    st.markdown("""
            <div class="login-footer">
                Sistem Estimasi Harga Kendaraan Bekas<br>© 2025
            </div>
        </div>
    """, unsafe_allow_html=True)


def main_page():
    # Load data hanya jika belum dimuat
    if 'df_mobil' not in st.session_state:
        st.session_state.df_mobil = load_data_from_drive(GOOGLE_DRIVE_FILE_ID)
        st.session_state.df_motor = load_local_data("dt/mtr.csv")
        st.session_state.df_avg = load_avg_data()

    df_mobil = st.session_state.df_mobil
    df_motor = st.session_state.df_motor
    df_avg = st.session_state.df_avg
    
    # Cek jika data mobil gagal dimuat, hentikan aplikasi
    if df_mobil.empty and df_avg.empty:
        st.error("Proses tidak dapat dilanjutkan karena data utama (mobil dan average) gagal dimuat. Periksa kembali konfigurasi Anda.")
        return

    logo_path = "dt/logo.png"
    img_base64 = image_to_base64(logo_path)

    # ------------ Sidebar ------------
    with st.sidebar:
        if img_base64:
            st.image(f"data:image/png;base64,{img_base64}", width=140)
        else:
            st.warning("Logo tidak ditemukan di dt/logo.png.")
        st.markdown("---")
        tipe_estimasi = st.radio("Menu", ["Estimasi Mobil", "Estimasi Motor"], on_change=reset_prediction_state)
        
        if tipe_estimasi == "Estimasi Mobil":
            st.radio(
                "Metode Estimasi Mobil", 
                ["System", "Average"],
                index=0,
                key="metode_estimasi",
                on_change=reset_prediction_state
            )
        
        st.markdown("---")
        if st.button("🔒 Keluar", use_container_width=True):
            st.session_state.is_logged_in = False
            # Hapus semua state sesi agar bersih saat login kembali
            for key in list(st.session_state.keys()):
                if key != 'is_logged_in':
                    del st.session_state[key]
            st.rerun()

    # ------------ Konten Utama ------------
    st.markdown('<div class="main-content">', unsafe_allow_html=True)

    if tipe_estimasi == "Estimasi Mobil":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Mobil Bekas</h2>", unsafe_allow_html=True)
        metode_aktif = st.session_state.get('metode_estimasi', 'System')
        st.markdown(f"<p style='color: #7F8C8D;'>Metode: <b>{metode_aktif}</b></p>", unsafe_allow_html=True)

        if metode_aktif == "System":
            df_source = df_mobil
            price_column = "output"
            if df_source.empty:
                st.error("Data 'System' tidak tersedia. Silakan pilih metode 'Average'.")
                st.stop()
        else: # Average
            df_source = df_avg
            price_column = "avg_price"
            if df_source.empty:
                st.error("Data 'Average' tidak tersedia. Silakan pilih metode 'System'.")
                st.stop()

        col1, col2 = st.columns(2)
        with col1:
            brand_options = ["-"] + sorted(df_source["name"].dropna().unique())
            brand = st.selectbox("Brand", brand_options, on_change=reset_prediction_state)
        with col2:
            model_options = ["-"] + (sorted(df_source[df_source["name"] == brand]["model"].dropna().unique()) if brand != "-" else [])
            model = st.selectbox("Model", model_options, on_change=reset_prediction_state)

        col3, col4 = st.columns(2)
        with col3:
            varian_options = ["-"] + (sorted(df_source[(df_source["name"] == brand) & (df_source["model"] == model)]["varian"].dropna().unique()) if brand != "-" and model != "-" else [])
            varian = st.selectbox("Varian", varian_options, on_change=reset_prediction_state)
        with col4:
            year_options = ["-"] + (sorted(df_source[(df_source["name"] == brand) & (df_source["model"] == model) & (df_source["varian"] == varian)]["tahun"].dropna().astype(int).astype(str).unique(), reverse=True) if brand != "-" and model != "-" and varian != "-" else [])
            year = st.selectbox("Tahun", year_options, on_change=reset_prediction_state)

        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True):
            if "-" in [brand, model, varian, year]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
            else:
                mask = (
                    (df_source["name"] == brand) & 
                    (df_source["model"] == model) & 
                    (df_source["varian"] == varian) & 
                    (df_source["tahun"].astype(str) == year)
                )
                results = df_source[mask]
                
                # PERBAIKAN LOGIKA: Cek jumlah hasil yang ditemukan
                if len(results) == 1:
                    st.session_state.prediction_made_car = True
                    st.session_state.selected_data_car = results.iloc[0]
                    st.session_state.metode_estimasi_used = metode_aktif
                    if 'ai_response_car' in st.session_state:
                        del st.session_state['ai_response_car']
                elif len(results) > 1:
                    st.warning(f"⚠️ Ditemukan {len(results)} data yang cocok. Hasil mungkin tidak akurat. Harap periksa kembali dataset Anda.")
                    # Tetap tampilkan yang pertama, tapi beri peringatan
                    st.session_state.prediction_made_car = True
                    st.session_state.selected_data_car = results.iloc[0]
                    st.session_state.metode_estimasi_used = metode_aktif
                else: # len(results) == 0
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                    reset_prediction_state()
        
        if st.session_state.get('prediction_made_car', False):
            selected_data = st.session_state.selected_data_car
            metode_used = st.session_state.get('metode_estimasi_used', 'System')
            
            initial_price = selected_data.get(price_column, 0)

            st.markdown("---")
            st.info(f"📊 Estimasi Harga Pasar Awal ({metode_used}): **{format_rupiah(initial_price)}**")
            
            st.markdown("##### 📝 Pilih Grade Kondisi Kendaraan")
            grade_selection = st.selectbox(
                "Grade akan menyesuaikan harga estimasi akhir.", 
                options=list(GRADE_FACTORS.keys())
            )
            
            grade_factor = GRADE_FACTORS[grade_selection]
            adjusted_price = initial_price * grade_factor
            st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

            if st.button("🤖 Generate Analisis Profesional", use_container_width=True):
                with st.spinner("Menganalisis harga mobil..."):
                    if metode_used == "System":
                        residu_val = selected_data.get("residu", 0)
                        depresiasi_val = selected_data.get("depresiasi", 0)
                        estimasi_val = selected_data.get("estimasi", 0)
                        prompt = f"""
                        Sebagai seorang analis pasar otomotif, berikan analisis harga untuk mobil bekas dengan spesifikasi berikut:
                        - Brand: {selected_data['name']}
                        - Model: {selected_data['model']}
                        - Varian: {selected_data['varian']}
                        - Tahun: {int(selected_data['tahun'])}
                        - Grade Kondisi: {grade_selection}

                        Data keuangan internal kami (Metode System) menunjukkan detail berikut:
                        - Nilai Buku (Estimasi): **{format_rupiah(estimasi_val)}**
                        - Depresiasi Tahunan: **{format_rupiah(depresiasi_val)}**
                        - Nilai Residu (Akhir Masa Manfaat): **{format_rupiah(residu_val)}**
                        - Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**
                        - Estimasi Harga Akhir (setelah penyesuaian Grade): **{format_rupiah(adjusted_price)}**

                        Tugas Anda:
                        Jelaskan secara profesional mengapa **Estimasi Harga Akhir ({format_rupiah(adjusted_price)})** adalah angka yang wajar. Hubungkan penjelasan Anda dengan **Estimasi Harga Pasar Awal** dan **Grade Kondisi** yang dipilih. Jelaskan bahwa Harga Awal adalah baseline pasar, dan Grade menyesuaikannya berdasarkan kondisi spesifik. Sebutkan juga faktor eksternal seperti sentimen pasar, popularitas model, dan kondisi ekonomi di tahun 2025.
                        
                        Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                        """
                    else: # Average
                        prompt = f"""
                        Sebagai seorang analis pasar otomotif, berikan analisis harga untuk mobil bekas dengan spesifikasi berikut:
                        - Brand: {selected_data['name']}
                        - Model: {selected_data['model']}
                        - Varian: {selected_data['varian']}
                        - Tahun: {int(selected_data['tahun'])}
                        - Grade Kondisi: {grade_selection}
                        - Metode Estimasi: Average (Rata-rata Pasar)

                        Data yang digunakan adalah harga rata-rata pasar untuk kendaraan sejenis:
                        - Rata-rata Harga Pasar: **{format_rupiah(initial_price)}**
                        - Estimasi Harga Akhir (setelah penyesuaian Grade): **{format_rupiah(adjusted_price)}**

                        Tugas Anda:
                        Jelaskan secara profesional mengapa **Estimasi Harga Akhir ({format_rupiah(adjusted_price)})** adalah angka yang wajar. 
                        Fokuskan analisis pada:
                        1. Penjelasan bahwa harga berasal dari rata-rata harga iklan pasar aktual, yang mencerminkan penawaran dan permintaan riil.
                        2. Pengaruh penyesuaian grade terhadap harga akhir (misalnya, grade A menandakan kondisi di atas rata-rata pasar).
                        3. Faktor-faktor yang mempengaruhi harga rata-rata pasar seperti popularitas model, ketersediaan unit, reputasi merek, dan kondisi ekonomi saat ini (2025).
                        
                        Berikan analisis yang ringkas namun komprehensif dalam format poin-poin.
                        """
                    
                    ai_response = ask_openrouter(prompt)
                    st.session_state.ai_response_car = ai_response

            if 'ai_response_car' in st.session_state:
                st.markdown("---")
                st.subheader("🤖 Analisis Profesional Estimasi Harga")
                st.markdown(st.session_state.ai_response_car)

    elif tipe_estimasi == "Estimasi Motor":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Motor Bekas</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color: #7F8C8D;'>Pilih spesifikasi motor Anda untuk melihat estimasi harga pasarnya.</p>", unsafe_allow_html=True)
        
        if df_motor.empty:
            st.warning("Data motor tidak dapat dimuat. Fitur ini tidak tersedia.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                brand_options = ["-"] + sorted(df_motor["brand"].dropna().unique())
                brand = st.selectbox("Brand", brand_options, key="motor_brand", on_change=reset_prediction_state)
            with col2:
                variant_options = ["-"] + (sorted(df_motor[df_motor["brand"] == brand]["variant"].dropna().unique()) if brand != "-" else [])
                variant = st.selectbox("Varian", variant_options, key="motor_variant", on_change=reset_prediction_state)

            year_options = ["-"] + (sorted(df_motor[(df_motor["brand"] == brand) & (df_motor["variant"] == variant)]["year"].dropna().astype(int).astype(str).unique(), reverse=True) if brand != "-" and variant != "-" else [])
            year = st.selectbox("Tahun", year_options, key="motor_year", on_change=reset_prediction_state)

            if st.button("🔍 Lihat Estimasi Harga", key="btn_motor", use_container_width=True):
                if "-" in [brand, variant, year]:
                    st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
                else:
                    mask = (
                        (df_motor["brand"] == brand) &
                        (df_motor["variant"] == variant) &
                        (df_motor["year"].astype(str) == year)
                    )
                    results = df_motor[mask]

                    # PERBAIKAN LOGIKA: Cek jumlah hasil yang ditemukan
                    if len(results) == 1:
                        st.session_state.prediction_made_motor = True
                        st.session_state.selected_data_motor = results.iloc[0]
                        if 'ai_response_motor' in st.session_state:
                            del st.session_state['ai_response_motor']
                    elif len(results) > 1:
                        st.warning(f"⚠️ Ditemukan {len(results)} data yang cocok. Hasil mungkin tidak akurat. Harap periksa kembali dataset Anda.")
                        st.session_state.prediction_made_motor = True
                        st.session_state.selected_data_motor = results.iloc[0]
                    else: # len(results) == 0
                        st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                        reset_prediction_state()
            
            if st.session_state.get('prediction_made_motor', False):
                selected_data = st.session_state.selected_data_motor
                initial_price = selected_data.get("output", 0)

                st.markdown("---")
                st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
                
                st.markdown("##### 📝 Pilih Grade Kondisi Kendaraan")
                grade_selection = st.selectbox(
                    "Grade akan menyesuaikan harga estimasi akhir.", 
                    options=list(GRADE_FACTORS.keys()),
                    key="grade_motor"
                )
                
                grade_factor = GRADE_FACTORS[grade_selection]
                adjusted_price = initial_price * grade_factor
                st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

                if st.button("🤖 Generate Analisis Profesional", key="btn_analisis_motor", use_container_width=True):
                    with st.spinner("Menganalisis harga motor..."):
                        # PERBAIKAN PROMPT: Menyertakan semua data keuangan yang relevan
                        residu_val = selected_data.get("residu", 0)
                        depresiasi_val = selected_data.get("depresiasi_residu", 0)
                        estimasi_val = selected_data.get("estimasi_1", 0)
                        
                        prompt = f"""
                        Sebagai seorang analis pasar otomotif, berikan analisis harga untuk motor bekas dengan spesifikasi berikut:
                        - Brand: {selected_data['brand']}
                        - Varian: {selected_data['variant']}
                        - Tahun: {int(selected_data['year'])}
                        - Grade Kondisi: {grade_selection}

                        Data keuangan internal kami menunjukkan detail berikut:
                        - Nilai Buku (Estimasi Tahun Ini): **{format_rupiah(estimasi_val)}**
                        - Depresiasi & Residu: **{format_rupiah(depresiasi_val)}**
                        - Nilai Residu: **{format_rupiah(residu_val)}**
                        - Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**
                        - Estimasi Harga Akhir (setelah penyesuaian Grade): **{format_rupiah(adjusted_price)}**

                        Tugas Anda:
                        Jelaskan secara profesional mengapa **Estimasi Harga Akhir ({format_rupiah(adjusted_price)})** adalah angka yang wajar. Hubungkan penjelasan Anda dengan **Estimasi Harga Pasar Awal** dan **Grade Kondisi** yang dipilih. Jelaskan bahwa Harga Awal adalah baseline pasar, dan Grade menyesuaikannya berdasarkan kondisi spesifik. Sebutkan juga faktor eksternal seperti sentimen pasar, popularitas model, dan kondisi ekonomi di tahun 2025.
                        
                        Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                        """
                        ai_response = ask_openrouter(prompt)
                        st.session_state.ai_response_motor = ai_response

                if 'ai_response_motor' in st.session_state:
                    st.markdown("---")
                    st.subheader("🤖 Analisis Profesional Estimasi Harga")
                    st.markdown(st.session_state.ai_response_motor)

    st.markdown("</div>", unsafe_allow_html=True)

# ==============================================================================
# LOGIKA EKSEKUSI UTAMA
# ==============================================================================

def main():
    if "is_logged_in" not in st.session_state:
        st.session_state.is_logged_in = False
    
    if not st.session_state.is_logged_in:
        login_page()
    else:
        main_page()

if __name__ == "__main__":
    main()

