import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeopyError
import time

# --- 1. OLDAL BEÁLLÍTÁSAI ---
st.set_page_config(page_title="Profi Utazás Tervező SQL", layout="wide")

# --- 2. ADATBÁZIS KAPCSOLAT (FELHŐ SQL) ---
# A jelszót a Streamlit Cloud Secrets-ből olvassuk ki!
try:
    db_url = st.secrets["postgres"]["url"]
    engine = create_engine(db_url)
except Exception:
    st.error("Hiba: Nem található az SQL kapcsolat! (Ellenőrizd a Streamlit Secrets-t)")
    st.stop()

# Tábla létrehozása, ha még nem létezik
def init_db():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS helyszinek (
                id SERIAL PRIMARY KEY, 
                nap TEXT, 
                hely TEXT, 
                ar INTEGER, 
                kat TEXT, 
                lat REAL, 
                lon REAL
            )
        """))
        conn.commit()

init_db()

# --- 3. KERESŐMOTOR ÉS SZÍNEK ---
geolocator = Nominatim(user_agent="Travel_Planner_Cloud_2026")

kat_szinek = {
    "Szállás": "red",
    "Étterem": "blue",
    "Látnivaló": "green",
    "Közlekedés": "orange",
    "Egyéb": "gray"
}

# --- 4. OLDALSÁV (ADATBEVITEL) ---
st.sidebar.header("📍 Új helyszín hozzáadása")
with st.sidebar.form("input_form", clear_on_submit=True):
    f_nap = st.text_input("Hányadik nap?")
    f_hely = st.text_input("Helyszín neve (Város, utca)")
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
            st.sidebar.success(f"Siker: {f_hely} mentve a felhőbe!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.sidebar.error("Helyszín nem található.")
    except GeopyError:
        st.sidebar.error("Hálózati hiba a kereséskor.")

# --- 5. ADATOK LEKÉRÉSE ---
df = pd.read_sql("SELECT * FROM helyszinek ORDER BY id", engine)

# --- 6. FŐOLDAL MEGJELENÍTÉSE ---
st.title("🌍 Felhőalapú Utazási Tervező")

if not df.empty:
    # Csak az érvényes koordinátákat mutatjuk a térképen
    df_map = df.dropna(subset=['lat', 'lon'])

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🗺️ Interaktív Térkép")
        
        # 1. Kiszámoljuk az alaphelyzetet
        if not df_map.empty:
            kozep_lat = df_map['lat'].mean()
            kozep_lon = df_map['lon'].mean()
            # Ha van adat, oda ugrunk
            start_coord = [kozep_lat, kozep_lon]
            start_zoom = 13
        else:
            # HA ÜRES VAGY NEM TALÁLJA: Budapest fix koordinátái
            start_coord = [47.4979, 19.0402]
            start_zoom = 12

        # 2. Térkép objektum létrehozása (alapértelmezett csempék nélkül)
        m = folium.Map(location=start_coord, zoom_start=start_zoom, tiles=None)
        
        # 3. Google Maps réteg - Próbáljuk meg ezt a stabilabb linket
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
            attr='Google',
            name='Google Maps',
            overlay=False, # Ez legyen False, hogy ez legyen az alapréteg
            control=True
        ).add_to(m)

        # 4. Pontok felrakása
        if not df_map.empty:
            for _, row in df_map.iterrows():
                szin = kat_szinek.get(row['kat'], "blue")
                
                # Itt használjuk a sima Markert, hogy biztosan látszódjon
                folium.Marker(
                    location=[row['lat'], row['lon']],
                    icon=folium.Icon(color=szin, icon="info-sign"),
                    tooltip=row['hely']
                ).add_to(m)

        # 5. Térkép megjelenítése
        st_folium(m, width=700, height=500, returned_objects=[])

    with col2:
        st.subheader("📊 Lista kezelése")
        st.info("Törléshez jelöld ki a sort és nyomj **Delete**-et!")
        
        edited_df = st.data_editor(
            df, 
            column_order=("nap", "hely", "ar", "kat"),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="travel_editor"
        )
        
        if st.button("Változtatások véglegesítése"):
            with engine.connect() as conn:
                conn.execute(text("TRUNCATE TABLE helyszinek")) # Tábla ürítése
                edited_df.to_sql("helyszinek", engine, if_exists="append", index=False)
                conn.commit()
            st.success("Adatbázis frissítve!")
            st.rerun()
            
        st.metric("Összköltség", f"{df['ar'].sum():,} Ft")
else:
    st.info("Nincs rögzített adat. Használd a bal oldali menüt!")
