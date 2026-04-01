import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeopyError
import time

# --- 1. OLDAL BEÁLLÍTÁSAI ---
st.set_page_config(page_title="Profi Utazás Tervező", layout="wide")

# --- 2. ADATBÁZIS ÉS KERESŐMOTOR ---
conn = sqlite3.connect("utazas_adatok.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS helyszinek 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, 
              nap TEXT, hely TEXT, ar INTEGER, kat TEXT, lat REAL, lon REAL)''')
conn.commit()

geolocator = Nominatim(user_agent="Travel_Planner_App_Final_2026")

kat_szinek = {
    "Szállás": "red", "Étterem": "blue", "Látnivaló": "green", "Közlekedés": "orange", "Egyéb": "gray"
}

# --- 3. OLDALSÁV (ADATBEVITEL) ---
st.sidebar.header("📍 Új helyszín hozzáadása")
with st.sidebar.form("input_form", clear_on_submit=True):
    f_nap = st.text_input("Hányadik nap?")
    f_hely = st.text_input("Helyszín neve (Város, utca)")
    f_ar = st.number_input("Költség (Ft)", min_value=0, step=500)
    f_kat = st.selectbox("Kategória", list(kat_szinek.keys()))
    submit = st.form_submit_button("Mentés és Térképre küldés")

if submit and f_hely:
    try:
        location = geolocator.geocode(f_hely, timeout=10)
        if location:
            c.execute("INSERT INTO helyszinek (nap, hely, ar, kat, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", 
                      (f_nap, f_hely, f_ar, f_kat, location.latitude, location.longitude))
            conn.commit()
            st.sidebar.success(f"Siker: {f_hely} rögzítve!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.sidebar.error("Nem található helyszín.")
    except GeopyError:
        st.sidebar.error("Hálózati hiba.")

# --- 4. ADATOK LEKÉRÉSE ---
df = pd.read_sql_query("SELECT * FROM helyszinek", conn)

# --- 5. FŐOLDAL ---
st.title("🌍 Utazási Tervező")

if not df.empty:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🗺️ Térkép")
        m = folium.Map(location=[df['lat'].mean(), df['lon'].mean()], zoom_start=13)
        folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', attr='Google', name='Google Maps', overlay=True).add_to(m)

        for _, row in df.iterrows():
            szin = kat_szinek.get(row['kat'], "gray")
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8, weight=2, color="white", fill=True, fill_color=szin, fill_opacity=0.8,
                tooltip=folium.Tooltip(f"<b>{row['hely']}</b>", style=f"color:white;background-color:{szin};padding:3px;border-radius:4px;")
            ).add_to(m)

        st_folium(m, width="100%", height=600, returned_objects=[])

    with col2:
        st.subheader("📊 Lista kezelése")
        st.write("Törléshez jelöld ki a sort és nyomj **Delete**-et, vagy használd a sor melletti ikont!")
        
        # JAVÍTOTT SZERKESZTŐ: num_rows="dynamic" engedélyezi a törlést
        edited_df = st.data_editor(
            df, 
            column_order=("nap", "hely", "ar", "kat"), # Csak ezeket mutassuk
            num_rows="dynamic", # EZ ENGEDÉLYEZI A TÖRLÉST ÉS HOZZÁADÁST
            hide_index=True,
            use_container_width=True
        )
        
        if st.button("Változtatások mentése (Törlés véglegesítése)"):
            # Töröljük a régit és betöltjük az újat az adatbázisba
            c.execute("DELETE FROM helyszinek")
            edited_df.to_sql("helyszinek", conn, if_exists="append", index=False)
            conn.commit()
            st.success("Módosítások elmentve!")
            st.rerun()
            
        st.metric("Összesen", f"{df['ar'].sum():,} Ft")
else:
    st.info("Nincs adat.")

conn.close()
