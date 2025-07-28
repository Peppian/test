import streamlit as st
import pandas as pd
import base64
import requests
import re

# ------------ KONFIGURASI LOGIN ------------
USERNAME = "legoas"
PASSWORD = "admin"

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
    
    # Kolom yang akan dikonversi ke numerik
    numeric_cols = ['output', 'residu', 'depresiasi_residu', 'estimasi_1']
    
    for col in numeric_cols:
        if col in df.columns:
            # Hapus karakter non-digit dan konversi ke numerik
            # df[col] = df[col].astype(str).apply(lambda x: re.sub(r'[^\d.]', '', x.strip()))
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
        tipe_estimasi = st.radio("Menu", ["Estimasi Mobil", "Estimasi Motor"])
        st.markdown("---")
        if st.button("🔒 Keluar", use_container_width=True):
            st.session_state.is_logged_in = False
            st.rerun()

    # ------------ Konten Utama ------------
    st.markdown('<div class="main-content">', unsafe_allow_html=True)

    if tipe_estimasi == "Estimasi Mobil":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Mobil Bekas</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color: #7F8C8D;'>Pilih spesifikasi mobil Anda untuk melihat estimasi harga pasarnya.</p>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            brand_options = ["-"] + sorted(df_mobil["brand"].dropna().unique())
            brand = st.selectbox("Brand", brand_options)

        with col2:
            model_options = ["-"] + (sorted(df_mobil[df_mobil["brand"] == brand]["model"].dropna().unique()) if brand != "-" else [])
            model = st.selectbox("Model", model_options)

        col3, col4 = st.columns(2)
        with col3:
            type_options = ["-"] + (sorted(df_mobil[(df_mobil["brand"] == brand) & (df_mobil["model"] == model)]["type"].dropna().unique()) if brand != "-" and model != "-" else [])
            type_ = st.selectbox("Tipe", type_options)

        with col4:
            year_options = ["-"] + (sorted(df_mobil[(df_mobil["brand"] == brand) & (df_mobil["model"] == model) & (df_mobil["type"] == type_)]["year"].dropna().astype(int).astype(str).unique(), reverse=True) if brand != "-" and model != "-" and type_ != "-" else [])
            year = st.selectbox("Tahun", year_options)

        trans_options = ["-"] + (sorted(df_mobil[(df_mobil["brand"] == brand) & (df_mobil["model"] == model) & (df_mobil["type"] == type_) & (df_mobil["year"].astype(str) == year)]["transmisi"].dropna().unique()) if brand != "-" and model != "-" and type_ != "-" and year != "-" else [])
        transmisi = st.selectbox("Transmisi", trans_options)

        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True):
            if "-" in [brand, model, type_, year, transmisi]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
            else:
                mask = (
                    (df_mobil["brand"] == brand) &
                    (df_mobil["model"] == model) &
                    (df_mobil["type"] == type_) &
                    (df_mobil["year"].astype(str) == year) &
                    (df_mobil["transmisi"] == transmisi)
                )
                if mask.any():
                    # --- MODIFIED START ---
                    # Ambil seluruh baris data yang relevan, bukan hanya 'output'
                    selected_data = df_mobil.loc[mask].iloc[0]
                    
                    # Ekstrak semua nilai yang dibutuhkan
                    output_val = selected_data.get("output", 0)
                    residu_val = selected_data.get("residu", 0)
                    depresiasi_val = selected_data.get("depresiasi_residu", 0)
                    estimasi_val = selected_data.get("estimasi_1", 0)
                    
                    st.success(f"💰 Estimasi harga pasar: **{format_rupiah(output_val)}**")
                    
                    st.markdown("---")
                    st.subheader("🤖 Analisis Profesional Estimasi Harga")
                    
                    # Buat prompt baru yang lebih detail dengan data keuangan
                    prompt = f"""
                    Sebagai seorang analis pasar otomotif, berikan analisis harga untuk mobil bekas dengan spesifikasi berikut:
                    - Brand: {brand}
                    - Model: {model}
                    - Tipe: {type_}
                    - Tahun: {year}
                    - Transmisi: {transmisi}

                    Data keuangan internal kami menunjukkan detail berikut:
                    - Nilai Buku (Estimasi Tahun Ini): **{format_rupiah(estimasi_val)}**
                    - Depresiasi Tahunan: **{format_rupiah(depresiasi_val)}**
                    - Nilai Residu (Akhir Masa Manfaat): **{format_rupiah(residu_val)}**
                    - Estimasi Harga Pasar (Output): **{format_rupiah(output_val)}**

                    Tugas Anda:
                    Jelaskan secara profesional mengapa **Estimasi Harga Pasar ({format_rupiah(output_val)})** adalah angka yang wajar. Hubungkan penjelasan Anda dengan **Nilai Buku ({format_rupiah(estimasi_val)})**. Jelaskan bahwa Nilai Buku adalah dasar perhitungan internal berdasarkan usia dan depresiasi tahunan, sedangkan Harga Pasar juga mempertimbangkan faktor eksternal seperti sentimen pasar, popularitas model, biaya perawatan umum, dan kondisi ekonomi di tahun 2025.
                    
                    Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                    """
                    # --- MODIFIED END ---
                    
                    with st.spinner("Menganalisis harga mobil..."):
                        ai_response = ask_openrouter(prompt)
                    
                    st.markdown(ai_response)
                else:
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")

    elif tipe_estimasi == "Estimasi Motor":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Motor Bekas</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color: #7F8C8D;'>Pilih spesifikasi motor Anda untuk melihat estimasi harga pasarnya.</p>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            brand_options = ["-"] + sorted(df_motor["brand"].dropna().unique())
            brand = st.selectbox("Brand", brand_options, key="motor_brand")

        with col2:
            variant_options = ["-"] + (sorted(df_motor[df_motor["brand"] == brand]["variant"].dropna().unique()) if brand != "-" else [])
            variant = st.selectbox("Varian", variant_options, key="motor_variant")

        year_options = ["-"] + (sorted(df_motor[(df_motor["brand"] == brand) & (df_motor["variant"] == variant)]["year"].dropna().astype(int).astype(str).unique(), reverse=True) if brand != "-" and variant != "-" else [])
        year = st.selectbox("Tahun", year_options, key="motor_year")

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
                    # --- MODIFIED START ---
                    # Ambil seluruh baris data yang relevan
                    selected_data = df_motor.loc[mask].iloc[0]

                    # Ekstrak semua nilai yang dibutuhkan
                    output_val = selected_data.get("output", 0)
                    residu_val = selected_data.get("residu", 0)
                    depresiasi_val = selected_data.get("depresiasi_residu", 0)
                    estimasi_val = selected_data.get("estimasi_1", 0)

                    st.success(f"💰 Estimasi harga pasar: **{format_rupiah(output_val)}**")
                    
                    st.markdown("---")
                    st.subheader("🤖 Analisis Profesional Estimasi Harga")

                    # Buat prompt baru yang lebih detail dengan data keuangan
                    prompt = f"""
                    Sebagai seorang analis pasar otomotif, berikan analisis harga untuk motor bekas dengan spesifikasi berikut:
                    - Brand: {brand}
                    - Varian: {variant}
                    - Tahun: {year}

                    Data keuangan internal kami menunjukkan detail berikut:
                    - Nilai Buku (Estimasi Tahun Ini): **{format_rupiah(estimasi_val)}**
                    - Depresiasi Tahunan: **{format_rupiah(depresiasi_val)}**
                    - Nilai Residu (Akhir Masa Manfaat): **{format_rupiah(residu_val)}**
                    - Estimasi Harga Pasar (Output): **{format_rupiah(output_val)}**

                    Tugas Anda:
                    Jelaskan secara profesional mengapa **Estimasi Harga Pasar ({format_rupiah(output_val)})** adalah angka yang wajar. Hubungkan penjelasan Anda dengan **Nilai Buku ({format_rupiah(estimasi_val)})**. Jelaskan bahwa Nilai Buku adalah dasar perhitungan internal berdasarkan usia dan depresiasi tahunan, sedangkan Harga Pasar juga mempertimbangkan faktor eksternal seperti sentimen pasar, popularitas model, biaya perawatan umum, dan kondisi ekonomi di tahun 2025.
                    
                    Buat penjelasan dalam format poin-poin yang ringkas dan mudah dipahami.
                    """
                    # --- MODIFIED END ---

                    with st.spinner("Menganalisis harga motor..."):
                        ai_response = ask_openrouter(prompt)
                    
                    st.markdown(ai_response)
                else:
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")

    st.markdown("</div>", unsafe_allow_html=True)

# ------------ Main App Logic ------------
def main():
    # Inisialisasi session state
    if "is_logged_in" not in st.session_state:
        st.session_state.is_logged_in = False
    
    if not st.session_state.is_logged_in:
        login_page()
    else:
        main_page()

if __name__ == "__main__":
    main()
