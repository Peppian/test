import streamlit as st
import pandas as pd
import base64
import requests
import re

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
        /* CSS tetap sama seperti sebelumnya */
    </style>
""", unsafe_allow_html=True) # CSS disembunyikan untuk keringkasan

# ------------ Fungsi Autentikasi ------------
def authenticate(username, password):
    return username == USERNAME and password == PASSWORD

# ------------ Sistem Login ------------
def login_page():
    # ... (Kode login tetap sama)
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
# --- MODIFIKASI: Fungsi load_data sekarang bisa membaca .json dan .csv ---
@st.cache_data
def load_data(path):
    if path.endswith('.json'):
        df = pd.read_json(path)
    elif path.endswith('.csv'):
        df = pd.read_csv(path)
        df.columns = df.columns.str.strip().str.lower()
        # Kolom numerik khusus untuk file CSV motor
        numeric_cols_csv = ['output', 'residu', 'depresiasi_residu', 'estimasi_1']
        for col in numeric_cols_csv:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    else:
        st.error(f"Format file tidak didukung: {path}")
        return pd.DataFrame()

    # Konversi numerik umum, jika kolom ada
    # JSON sudah memiliki tipe data yang benar, jadi ini lebih untuk keamanan
    general_numeric_cols = ['output', 'residu', 'depresiasi', 'estimasi', 'tahun']
    for col in general_numeric_cols:
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

# --- Fungsi untuk mereset state jika pilihan diubah ---
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
        # --- MODIFIKASI: Menggunakan file schema_1.json untuk mobil ---
        st.session_state.df_mobil = load_data("dt/schema_1.json")
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

        # --- MODIFIKASI: Disesuaikan dengan skema JSON baru ('name', 'varian') ---
        col1, col2 = st.columns(2)
        with col1:
            brand_options = ["-"] + sorted(df_mobil["name"].dropna().unique())
            brand = st.selectbox("Brand", brand_options, on_change=reset_prediction_state)
        with col2:
            model_options = ["-"] + (sorted(df_mobil[df_mobil["name"] == brand]["model"].dropna().unique()) if brand != "-" else [])
            model = st.selectbox("Model", model_options, on_change=reset_prediction_state)

        col3, col4 = st.columns(2)
        with col3:
            varian_options = ["-"] + (sorted(df_mobil[(df_mobil["name"] == brand) & (df_mobil["model"] == model)]["varian"].dropna().unique()) if brand != "-" and model != "-" else [])
            varian = st.selectbox("Varian", varian_options, on_change=reset_prediction_state) # 'Tipe' diubah jadi 'Varian'
        with col4:
            year_options = ["-"] + (sorted(df_mobil[(df_mobil["name"] == brand) & (df_mobil["model"] == model) & (df_mobil["varian"] == varian)]["tahun"].dropna().astype(int).astype(str).unique(), reverse=True) if brand != "-" and model != "-" and varian != "-" else [])
            year = st.selectbox("Tahun", year_options, on_change=reset_prediction_state)

        # --- MODIFIKASI: Opsi transmisi dihilangkan ---

        if st.button("🔍 Lihat Estimasi Harga", use_container_width=True):
            # --- MODIFIKASI: Cek input tanpa transmisi ---
            if "-" in [brand, model, varian, year]:
                st.warning("⚠️ Mohon lengkapi semua pilihan terlebih dahulu.")
            else:
                # --- MODIFIKASI: Mask filter disesuaikan dengan kolom baru ---
                mask = (
                    (df_mobil["name"] == brand) & (df_mobil["model"] == model) & 
                    (df_mobil["varian"] == varian) & (df_mobil["tahun"].astype(str) == year)
                )
                if mask.any():
                    st.session_state.prediction_made_car = True
                    st.session_state.selected_data_car = df_mobil.loc[mask].iloc[0]
                    if 'ai_response_car' in st.session_state:
                         del st.session_state['ai_response_car']
                else:
                    st.error("❌ Kombinasi tersebut tidak ditemukan di dataset.")
                    reset_prediction_state()
        
        if st.session_state.get('prediction_made_car', False):
            selected_data = st.session_state.selected_data_car
            initial_price = selected_data.get("output", 0)

            st.markdown("---")
            st.info(f"📊 Estimasi Harga Pasar Awal: **{format_rupiah(initial_price)}**")
            
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
                    # --- MODIFIKASI: Ekstrak data dari kolom baru ---
                    residu_val = selected_data.get("residu", 0)
                    depresiasi_val = selected_data.get("depresiasi", 0)
                    estimasi_val = selected_data.get("estimasi", 0)

                    # --- MODIFIKASI: Prompt disesuaikan dengan kolom dan data baru ---
                    prompt = f"""
                    Sebagai seorang analis pasar otomotif, berikan analisis harga untuk mobil bekas dengan spesifikasi berikut:
                    - Brand: {selected_data['name']}
                    - Model: {selected_data['model']}
                    - Varian: {selected_data['varian']}
                    - Tahun: {int(selected_data['tahun'])}
                    - Grade Kondisi: {grade_selection}

                    Data keuangan internal kami menunjukkan detail berikut:
                    - Nilai Buku (Estimasi): **{format_rupiah(estimasi_val)}**
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

            if 'ai_response_car' in st.session_state:
                st.markdown("---")
                st.subheader("🤖 Analisis Profesional Estimasi Harga")
                st.markdown(st.session_state.ai_response_car)

    # --- Bagian Estimasi Motor tidak diubah dan tetap berfungsi seperti sebelumnya ---
    elif tipe_estimasi == "Estimasi Motor":
        st.markdown("<h2 style='color: #2C3E50;'>Estimasi Harga Motor Bekas</h2>", unsafe_allow_html=True)
        # ... (Kode motor tetap sama)
        st.markdown("<p style='color: #7F8C8D;'>Pilih spesifikasi motor Anda untuk melihat estimasi harga pasarnya.</p>", unsafe_allow_html=True)
        
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
                    st.session_state.prediction_made_motor = True
                    st.session_state.selected_data_motor = df_motor.loc[mask].iloc[0]
                    if 'ai_response_motor' in st.session_state:
                         del st.session_state['ai_response_motor']
                else:
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
