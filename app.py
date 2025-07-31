import streamlit as st
import pandas as pd
import base64
import requests
import re

# ------------ KONFIGURASI LOGIN ------------
USERNAME = "legoas"
PASSWORD = "admin"

# --- BARU: Kamus untuk faktor Grade ---
GRADE_FACTORS = {
    'A (Sangat Baik)': 1.0,
    'B (Baik)': 0.94,
    'C (Cukup)': 0.80,
    'D (Kurang)': 0.58,
    'E (Buruk)': 0.23,
}

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


# ------------ Konfigurasi Halaman ------------
st.set_page_config(
    page_title="Estimasi Harga Kendaraan Bekas",
    page_icon="🚗",
    layout="wide"
)

# ------------ CSS Styling ------------
st.markdown("""
    <style>
        body {
            background-color: #f0f2f6 !important;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .block-container {
            background-color: white !important;
            padding: 2rem !important;
            border-radius: 16px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        }
        header, .css-18e3th9 {
            background: transparent;
        }
        .main .block-container:has(.custom-logo) {
            padding-top: 0rem !important;
        }
        .stApp {
            padding-top: 0rem !important;
        }
        .stSpinner > div {
            text-align: center;
            margin-top: 1rem;
        }
        .login-container {
            max-width: 600px;
            margin: 2rem auto;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
            background-color: white;
            border: 1px solid #eaeaea;
        }
        .login-title {
            text-align: center;
            color: #2C3E50;
            margin-bottom: 1rem;
            font-size: 1.5rem;
            font-weight: 600;
        }
        .login-icon {
            display: flex;
            justify-content: center;
            margin-bottom: 1rem;
            color: #3498db;
            font-size: 2.5rem;
        }
        .login-footer {
            text-align: center;
            margin-top: 1.5rem;
            color: #7f8c8d;
            font-size: 0.85rem;
        }
        .error-message {
            text-align: center;
            margin-top: 1rem;
            color: #e74c3c;
            font-size: 0.9rem;
        }
    </style>
""", unsafe_allow_html=True)

# ------------ Fungsi Autentikasi ------------
def authenticate(username, password):
    return username == USERNAME and password == PASSWORD

# ------------ Sistem Login ------------
def login_page():
    st.markdown("""
        <div class="login-container">
            <div class="login-icon">🔒</div>
            <h2 class="login-title">Silahkan Login Terlebih Dahulu</h2>
    """, unsafe_allow_html=True)
    
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", key="username", placeholder="Masukkan username Anda")
        password = st.text_input("Password", key="password", type="password", placeholder="Masukkan password Anda")
        submit_button = st.form_submit_button("Masuk", use_container_width=True)
        
        if submit_button:
            if authenticate(username, password):
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

# ------------ Load Data ------------
@st.cache_data
def load_data(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    
    numeric_cols = ['output', 'residu', 'depresiasi_residu', 'estimasi_1']
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    return df

# ------------ Format Rupiah ------------
def format_rupiah(val):
    try:
        num = float(val)
        num = round(num)
        return f"Rp {num:,}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

# ------------ Logo ke Base64 ------------
def image_to_base64(image_path):
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None

# --- BARU: Fungsi untuk mereset state jika pilihan diubah ---
def reset_prediction_state():
    keys_to_reset = [
        'prediction_made_car', 'selected_data_car', 'ai_response_car',
        'prediction_made_motor', 'selected_data_motor', 'ai_response_motor'
    ]
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]

# ------------ Halaman Utama ------------
def main_page():
    # Load data hanya jika belum dimuat
    if 'df_mobil' not in st.session_state:
        st.session_state.df_mobil = load_data("dt/mbl.csv")
        st.session_state.df_motor = load_data("dt/mtr.csv")
    
    df_mobil = st.session_state.df_mobil
    df_motor = st.session_state.df_motor
    
    logo_path = "dt/logo.png"
    img_base64 = image_to_base64(logo_path)

    # ------------ Sidebar ------------
    with st.sidebar:
        if img_base64:
            st.image(f"data:image/png;base64,{img_base64}", width=140)
        else:
            st.warning("Logo tidak ditemukan.")
        st.markdown("---")
        tipe_estimasi = st.radio("Menu", ["Estimasi Mobil", "Estimasi Motor"], on_change=reset_prediction_state)
        st.markdown("---")
        if st.button("🔒 Keluar", use_container_width=True):
            st.session_state.is_logged_in = False
            st.rerun()

    # ------------ Konten Utama ------------
    st.markdown('<div class="main-content">', unsafe_allow_html=True)

    if tipe_estimasi == "Estimasi Mobil":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Mobil Bekas</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color: #7F8C8D;'>Pilih spesifikasi mobil Anda untuk melihat estimasi harga pasarnya.</p>", unsafe_allow_html=True)

        # --- MODIFIKASI: Menambahkan on_change untuk mereset state ---
        col1, col2 = st.columns(2)
        with col1:
            brand_options = ["-"] + sorted(df_mobil["brand"].dropna().unique())
            brand = st.selectbox("Brand", brand_options, on_change=reset_prediction_state)
        with col2:
            model_options = ["-"] + (sorted(df_mobil[df_mobil["brand"] == brand]["model"].dropna().unique()) if brand != "-" else [])
            model = st.selectbox("Model", model_options, on_change=reset_prediction_state)

        col3, col4 = st.columns(2)
        with col3:
            type_options = ["-"] + (sorted(df_mobil[(df_mobil["brand"] == brand) & (df_mobil["model"] == model)]["type"].dropna().unique()) if brand != "-" and model != "-" else [])
            type_ = st.selectbox("Tipe", type_options, on_change=reset_prediction_state)
        with col4:
            year_options = ["-"] + (sorted(df_mobil[(df_mobil["brand"] == brand) & (df_mobil["model"] == model) & (df_mobil["type"] == type_)]["year"].dropna().astype(int).astype(str).unique(), reverse=True) if brand != "-" and model != "-" and type_ != "-" else [])
            year = st.selectbox("Tahun", year_options, on_change=reset_prediction_state)

        trans_options = ["-"] + (sorted(df_mobil[(df_mobil["brand"] == brand) & (df_mobil["model"] == model) & (df_mobil["type"] == type_) & (df_mobil["year"].astype(str) == year)]["transmisi"].dropna().unique()) if brand != "-" and model != "-" and type_ != "-" and year != "-" else [])
        transmisi = st.selectbox("Transmisi", trans_options, on_change=reset_prediction_state)

        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True):
            if "-" in [brand, model, type_, year, transmisi]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
            else:
                mask = (
                    (df_mobil["brand"] == brand) & (df_mobil["model"] == model) & 
                    (df_mobil["type"] == type_) & (df_mobil["year"].astype(str) == year) & 
                    (df_mobil["transmisi"] == transmisi)
                )
                if mask.any():
                    # --- MODIFIKASI: Simpan data ke session_state ---
                    st.session_state.prediction_made_car = True
                    st.session_state.selected_data_car = df_mobil.loc[mask].iloc[0]
                    # Hapus response AI lama jika ada
                    if 'ai_response_car' in st.session_state:
                         del st.session_state['ai_response_car']
                else:
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                    reset_prediction_state()
        
        # --- BLOK BARU: Tampilkan hasil dan opsi lanjutan jika prediksi sudah dibuat ---
        if st.session_state.get('prediction_made_car', False):
            selected_data = st.session_state.selected_data_car
            initial_price = selected_data.get("output", 0)

            st.markdown("---")
            st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
            
            # Opsi Grade
            st.markdown("##### 📝 Pilih Grade Kondisi Kendaraan")
            grade_selection = st.selectbox(
                "Grade akan menyesuaikan harga estimasi akhir.", 
                options=list(GRADE_FACTORS.keys())
            )
            
            # Kalkulasi dan tampilkan harga akhir
            grade_factor = GRADE_FACTORS[grade_selection]
            adjusted_price = initial_price * grade_factor
            st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

            # Tombol untuk generate analisis
            if st.button("🤖 Generate Analisis Profesional", use_container_width=True):
                with st.spinner("Menganalisis harga mobil..."):
                    # Ekstrak data lain untuk prompt
                    residu_val = selected_data.get("residu", 0)
                    depresiasi_val = selected_data.get("depresiasi_residu", 0)
                    estimasi_val = selected_data.get("estimasi_1", 0)

                    # --- MODIFIKASI: Prompt diperbarui dengan data grade dan harga akhir ---
                    prompt = f"""
                    Sebagai seorang analis pasar otomotif, berikan analisis harga untuk mobil bekas dengan spesifikasi berikut:
                    - Brand: {selected_data['brand']}
                    - Model: {selected_data['model']}
                    - Tipe: {selected_data['type']}
                    - Tahun: {int(selected_data['year'])}
                    - Transmisi: {selected_data['transmisi']}
                    - Grade Kondisi: {grade_selection}

                    Data keuangan internal kami menunjukkan detail berikut:
                    - Nilai Buku (Estimasi Tahun Ini): **{format_rupiah(estimasi_val)}**
                    - Depresiasi Tahunan: **{format_rupiah(depresiasi_val)}**
                    - Nilai Residu (Akhir Masa Manfaat): **{format_rupiah(residu_val)}**
                    - Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**
                    - Estimasi Harga Akhir (setelah penyesuaian Grade): **{format_rupiah(adjusted_price)}**

                    Tugas Anda:
                    Jelaskan secara profesional mengapa **Estimasi Harga Akhir ({format_rupiah(adjusted_price)})** adalah angka yang wajar. Hubungkan penjelasan Anda dengan **Estimasi Harga Pasar Awal** dan **Grade Kondisi** yang dipilih. Jelaskan bahwa Harga Awal adalah baseline pasar, dan Grade menyesuaikannya berdasarkan kondisi spesifik. Sebutkan juga faktor eksternal seperti sentimen pasar, popularitas model, dan kondisi ekonomi di tahun 2025.
                    
                    Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                    """
                    ai_response = ask_openrouter(prompt)
                    st.session_state.ai_response_car = ai_response

            # Tampilkan response AI jika sudah ada di session state
            if 'ai_response_car' in st.session_state:
                st.markdown("---")
                st.subheader("🤖 Analisis Profesional Estimasi Harga")
                st.markdown(st.session_state.ai_response_car)


    elif tipe_estimasi == "Estimasi Motor":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Motor Bekas</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color: #7F8C8D;'>Pilih spesifikasi motor Anda untuk melihat estimasi harga pasarnya.</p>", unsafe_allow_html=True)
        
        # --- MODIFIKASI: Menambahkan on_change untuk mereset state ---
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
                if mask.any():
                     # --- MODIFIKASI: Simpan data ke session_state ---
                    st.session_state.prediction_made_motor = True
                    st.session_state.selected_data_motor = df_motor.loc[mask].iloc[0]
                    # Hapus response AI lama jika ada
                    if 'ai_response_motor' in st.session_state:
                         del st.session_state['ai_response_motor']
                else:
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                    reset_prediction_state()
        
        # --- BLOK BARU: Tampilkan hasil dan opsi lanjutan jika prediksi sudah dibuat ---
        if st.session_state.get('prediction_made_motor', False):
            selected_data = st.session_state.selected_data_motor
            initial_price = selected_data.get("output", 0)

            st.markdown("---")
            st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
            
            # Opsi Grade
            st.markdown("##### 📝 Pilih Grade Kondisi Kendaraan")
            grade_selection = st.selectbox(
                "Grade akan menyesuaikan harga estimasi akhir.", 
                options=list(GRADE_FACTORS.keys()),
                key="grade_motor"
            )
            
            # Kalkulasi dan tampilkan harga akhir
            grade_factor = GRADE_FACTORS[grade_selection]
            adjusted_price = initial_price * grade_factor
            st.success(f"💰 Estimasi Harga Akhir (Grade {grade_selection.split(' ')[0]}): **{format_rupiah(adjusted_price)}**")

            # Tombol untuk generate analisis
            if st.button("🤖 Generate Analisis Profesional", key="btn_analisis_motor", use_container_width=True):
                with st.spinner("Menganalisis harga motor..."):
                    # Ekstrak data lain untuk prompt
                    residu_val = selected_data.get("residu", 0)
                    depresiasi_val = selected_data.get("depresiasi_residu", 0)
                    estimasi_val = selected_data.get("estimasi_1", 0)
                    
                    # --- MODIFIKASI: Prompt diperbarui dengan data grade dan harga akhir ---
                    prompt = f"""
                    Sebagai seorang analis pasar otomotif, berikan analisis harga untuk motor bekas dengan spesifikasi berikut:
                    - Brand: {selected_data['brand']}
                    - Varian: {selected_data['variant']}
                    - Tahun: {int(selected_data['year'])}
                    - Grade Kondisi: {grade_selection}

                    Data keuangan internal kami menunjukkan detail berikut:
                    - Nilai Buku (Estimasi Tahun Ini): **{format_rupiah(estimasi_val)}**
                    - Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**
                    - Estimasi Harga Akhir (setelah penyesuaian Grade): **{format_rupiah(adjusted_price)}**

                    Tugas Anda:
                    Jelaskan secara profesional mengapa **Estimasi Harga Akhir ({format_rupiah(adjusted_price)})** adalah angka yang wajar. Hubungkan penjelasan Anda dengan **Estimasi Harga Pasar Awal** dan **Grade Kondisi** yang dipilih. Jelaskan bahwa Harga Awal adalah baseline pasar, dan Grade menyesuaikannya berdasarkan kondisi spesifik. Sebutkan juga faktor eksternal seperti sentimen pasar, popularitas model, dan kondisi ekonomi di tahun 2025.
                    
                    Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                    """
                    ai_response = ask_openrouter(prompt)
                    st.session_state.ai_response_motor = ai_response

            # Tampilkan response AI jika sudah ada di session state
            if 'ai_response_motor' in st.session_state:
                st.markdown("---")
                st.subheader("🤖 Analisis Profesional Estimasi Harga")
                st.markdown(st.session_state.ai_response_motor)

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
