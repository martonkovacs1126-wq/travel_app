import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeopyError
import time

# --- 1. OLDAL BEÁLLÍTÁSAI ÉS ZÖLD GOMB STÍLUS ---
st.set_page_config(page_title="Profi Utazás Tervező", layout="wide")

# CSS a gomb zöldítéséhez
st.markdown("""
    <style>
    div.stFormSubmitButton > button {
        background-color: #28a745 !important;
        color: white !important;
        border: none;
        width: 100%;
    }
    div.stFormSubmitButton > button:hover {
        background-color: #218838 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ADATBÁZIS KAPCSOLAT (SUPABASE POOLER) ---
try:
    db_url = st.secrets["postgres"]["url"]
    # pool_pre_ping segít életben tartani a kapcsolatot a felhőben
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=300)
except Exception:
    st.error("Hiba: Hiányzik az SQL URL a Secrets-ből!")
    st.stop()

def init_db():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS helyszinek (
                id SERIAL PRIMARY KEY, 
                nap TEXT, hely TEXT, ar INTEGER, kat TEXT, lat REAL, lon REAL
            )
        """))
        conn.commit()

init_db()

# --- 3. SEGEDFUNKCIÓK ---
geolocator = Nominatim(user_agent="Travel_Planner_2026_Final")

kat_szinek = {
    "Szállás": "red",
    "Étterem": "blue",
    "Látnivaló": "green",
    "Közlekedés": "orange",
    "Egyéb": "gray"
}

# --- 4. OLDALSÁV (BEVITEL) ---
st.sidebar.header("📍 Új helyszín")
with st.sidebar.form("input_form", clear_on_submit=True):
    f_nap = st.text_input("Nap (pl. 1. nap)")
    f_hely = st.text_input("Helyszín pontos neve")
    f_ar = st.number_input("Költség (Ft)", min_value=0, step=500)
    f_kat = st.selectbox("Kategória", list(kat_szinek.keys()))
    submit = st.form_submit_button("Hozzáadás")

if submit and f_hely:
    try:
        location = geolocator.geocode(f_hely, timeout=10)
        if location:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO helyszinek (nap, hely, ar, kat, lat, lon) 
                    VALUES (:nap, :hely, :ar, :kat, :lat, :lon)
                """), {
                    "nap": f_nap, "hely": f_hely, "ar": f_ar, 
                    "kat": f_kat, "lat": location.latitude, "lon": location.longitude
                })
                conn.commit()
            st.sidebar.success(f"{f_hely} mentve!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.sidebar.error("Nem találom a helyszínt. Próbáld pontosabban!")
    except GeopyError:
        st.sidebar.error("Keresési hiba (Időtúllépés).")

# --- 5. ADATOK LEKÉRÉSE ---
df = pd.read_sql("SELECT * FROM helyszinek ORDER BY id", engine)
# Csak azokat tartjuk meg a térképhez, amiknek van koordinátája
df_map = df.dropna(subset=['lat', 'lon'])

# --- 6. MEGJELENÍTÉS ---
st.title("🌍 Utazási Tervezőm")

if not df.empty:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🗺️ Interaktív Térkép")
        
        # Alaphelyzet beállítása (London, ha üres, de a fit_bounds felülírja)
        start_coord = [51.5074, -0.1278] if df_map.empty else [df_map['lat'].mean(), df_map['lon'].mean()]
        
        m = folium.Map(location=start_coord, zoom_start=12, tiles=None)
        
        # Google Maps Úthálózat réteg
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
            attr='Google', name='Google Maps', overlay=False
        ).add_to(m)

        # Pontok kirajzolása egyedi ikonokkal
        for _, row in df_map.iterrows():
            szin = kat_szinek.get(row['kat'], "gray")
            
            # Ikon meghatározása
            if row['kat'] == "Szállás": ikon, pref = "bed", "fa"
            elif row['kat'] == "Étterem": ikon, pref = "cutlery", "fa"
            elif row['kat'] == "Közlekedés": ikon, pref = "bus", "fa"
            else: ikon, pref = "info-sign", "glyphicon"

            folium.Marker(
                location=[row['lat'], row['lon']],
                icon=folium.Icon(color=szin, icon=ikon, prefix=pref),
                tooltip=folium.Tooltip(
                    f"<b>{row['hely']}</b>",
                    style=f"color:white; background-color:{szin}; padding:5px; border-radius:5px; font-weight:bold;"
                )
            ).add_to(m)

        # --- FIT BOUNDS: Automatikusan rázoomol a pontokra ---
        if not df_map.empty and len(df_map) > 0:
            sw = df_map[['lat', 'lon']].min().values.tolist()
            ne = df_map[['lat', 'lon']].max().values.tolist()
            m.fit_bounds([sw, ne])

        st_folium(m, width="100%", height=600, returned_objects=[])

    with col2:
        st.subheader("📊 Lista kezelése")
        st.info("Törlés: Jelöld ki a sort -> Delete billentyű")
        
        # A táblázat szerkesztője
        edited_df = st.data_editor(
            df, 
            column_order=("nap", "hely", "ar", "kat"),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="main_editor"
        )
        
        # FIGYELJ A BEHÚZÁSRA: Ez a sor pontosan az 'edited_df' alatt kezdődjön!
        if st.button("Változtatások véglegesítése", type="primary"):
            try:
                with engine.begin() as conn:
                    # Tábla ürítése és sorszámozás alaphelyzetbe állítása
                    conn.execute(text("TRUNCATE TABLE helyszinek RESTART IDENTITY"))
                    
                    if not edited_df.empty:
                        # Az 'id' oszlopot eldobjuk, hogy ne ütközzön a Postgres kulcsaival
                        clean_df = edited_df.drop(columns=['id'], errors='ignore')
                        clean_df.to_sql("helyszinek", engine, if_exists="append", index=False)
                
                st.success("Adatbázis sikeresen frissítve!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Hiba a mentés során: {e}")
            
        st.metric("Összköltség", f"{df['ar'].sum():,} Ft")
