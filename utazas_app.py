import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeopyError
import time

# --- 1. OLDAL BEÁLLÍTÁSAI ÉS STÍLUS ---
st.set_page_config(page_title="Profi Utazás Tervező", layout="wide")

# Zöld gomb és felület csinosítása
st.markdown("""
    <style>
    div.stFormSubmitButton > button {
        background-color: #28a745 !important;
        color: white !important;
        border: none;
        width: 100%;
    }
    /* A mentés gombot is átszínezzük */
    </style>
    """, unsafe_allow_html=True)

# --- 2. ADATBÁZIS KAPCSOLAT ---
try:
    db_url = st.secrets["postgres"]["url"]
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

# --- 3. SZOLGÁLTATÁSOK ---
geolocator = Nominatim(user_agent="Travel_Planner_Final_2026")

kat_szinek = {
    "Szállás": "red",
    "Étterem": "blue",
    "Látnivaló": "green",
    "Közlekedés": "orange",
    "Egyéb": "gray"
}

# --- 4. OLDALSÁV (ADATBEVITEL) ---
st.sidebar.header("📍 Új helyszín")
with st.sidebar.form("input_form", clear_on_submit=True):
    f_nap = st.text_input("Nap (pl. 1. nap)")
    f_hely = st.text_input("Helyszín pontos neve (Város is!)")
    f_ar = st.number_input("Költség (Ft)", min_value=0, step=500)
    f_kat = st.selectbox("Kategória", list(kat_szinek.keys()))
    submit = st.form_submit_button("Hozzáadás")

if submit and f_hely:
    try:
        # Keresés megkönnyítése
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
            st.sidebar.success(f"{f_hely} hozzáadva!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.sidebar.error("Nem találom a helyszínt. Írd oda a várost is!")
    except GeopyError:
        st.sidebar.error("Keresési hiba. Próbáld újra!")

# --- 5. ADATOK LEKÉRÉSE ---
df = pd.read_sql("SELECT * FROM helyszinek ORDER BY id", engine)
df_map = df.dropna(subset=['lat', 'lon'])

# --- 6. FŐOLDAL ---
st.title("🌍 Utazási Tervezőm")

if not df.empty:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🗺️ Interaktív Térkép")
        
        # Alaphelyzet (ha nincs adat, Budapest)
        start_coord = [47.4979, 19.0402] if df_map.empty else [df_map['lat'].mean(), df_map['lon'].mean()]
        m = folium.Map(location=start_coord, zoom_start=12, tiles=None)
        
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
            attr='Google', name='Google Maps', overlay=False
        ).add_to(m)

        for _, row in df_map.iterrows():
            szin = kat_szinek.get(row['kat'], "gray")
            if row['kat'] == "Szállás": ikon, pref = "bed", "fa"
            elif row['kat'] == "Étterem": ikon, pref = "cutlery", "fa"
            elif row['kat'] == "Közlekedés": ikon, pref = "bus", "fa"
            else: ikon, pref = "info-sign", "glyphicon"

            folium.Marker(
                location=[row['lat'], row['lon']],
                icon=folium.Icon(color=szin, icon=ikon, prefix=pref),
                tooltip=row['hely']
            ).add_to(m)

        # Automatikus ráközelítés a pontokra
        if not df_map.empty:
            sw = df_map[['lat', 'lon']].min().values.tolist()
            ne = df_map[['lat', 'lon']].max().values.tolist()
            m.fit_bounds([sw, ne])

        st_folium(m, width="100%", height=600, key="map", returned_objects=[])

    with col2:
        st.subheader("📊 Lista és Törlés")
        st.write("Törléshez kattints a sor szélére és nyomj **Delete**-et!")
        
        edited_df = st.data_editor(
            df, 
            column_order=("nap", "hely", "ar", "kat"),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="data_editor_main"
        )
        
        if st.button("Változtatások véglegesítése", type="primary"):
            try:
                # Tranzakció indítása: vagy minden sikerül, vagy semmi
                with engine.begin() as conn:
                    # 1. Töröljük a régi adatokat és a számlálót
                    conn.execute(text("TRUNCATE TABLE helyszinek RESTART IDENTITY"))
                    
                    # 2. Csak ha maradt adat a táblázatban, akkor töltjük vissza
                    if not edited_df.empty:
                        # Az 'id' oszlopot eldobjuk, hogy a Postgres generáljon újat
                        clean_to_save = edited_df.drop(columns=['id'], errors='ignore')
                        clean_to_save.to_sql("helyszinek", engine, if_exists="append", index=False)
                
                st.success("Sikeres mentés!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Hiba történt: {e}")
            
        st.metric("Összköltség", f"{df['ar'].sum():,} Ft")
else:
    st.info("Még nincs mentett helyszíned. Adj hozzá egyet a bal oldalon!")
