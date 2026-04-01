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
# Az adatbázis oszlopnevei: id, nap, hely, ar, kat, lat, lon
conn = sqlite3.connect("utazas_adatok.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS helyszinek 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, 
              nap TEXT, 
              hely TEXT, 
              ar INTEGER, 
              kat TEXT, 
              lat REAL, 
              lon REAL)''')
conn.commit()

# Egyedi név a térképszervernek
geolocator = Nominatim(user_agent="Travel_Planner_App_Final_2026")

# Színkódok a kategóriákhoz
kat_szinek = {
    "Szállás": "red",
    "Étterem": "blue",
    "Látnivaló": "green",
    "Közlekedés": "orange",
    "Egyéb": "gray"
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
        # Cím keresése koordinátákra
        location = geolocator.geocode(f_hely, timeout=10)
        if location:
            # Pontosan 6 oszlop, 6 érték (lat és lon néven)
            c.execute("INSERT INTO helyszinek (nap, hely, ar, kat, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", 
                      (f_nap, f_hely, f_ar, f_kat, location.latitude, location.longitude))
            conn.commit()
            st.sidebar.success(f"Siker: {f_hely} rögzítve!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.sidebar.error("A térkép nem találja ezt a helyet. Próbáld pontosabb címmel!")
    except GeopyError:
        st.sidebar.error("Hálózati hiba a keresés során.")

# --- 4. ADATOK LEKÉRÉSE ---
df = pd.read_sql_query("SELECT * FROM helyszinek", conn)

# --- 5. FŐOLDAL MEGJELENÍTÉSE ---
st.title("🌍 Utazási Tervezőm és Interaktív Térkép")

if not df.empty:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🗺️ Térkép (Húzd rá az egeret a pontokra!)")
        
        # Térkép középpontja az átlagos koordináták alapján
        map_center = [df['lat'].mean(), df['lon'].mean()]
        m = folium.Map(location=map_center, zoom_start=13)
        
        # Google Maps réteg
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
            attr='Google',
            name='Google Maps',
            overlay=True,
            control=True
        ).add_to(m)

        # Pontok és dinamikus feliratok (HOVER) hozzáadása
        for _, row in df.iterrows():
            szin = kat_szinek.get(row['kat'], "gray")
            
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=6,
		weight=2,
                color=szin,
                fill=True,
                fill_color=szin,
                fill_opacity=0.7,
                # Kattintásra felugró ablak
                popup=f"<b>{row['hely']}</b><br>{row['ar']} Ft",
                # CSAK AKKOR JELENIK MEG A KERETES SZÖVEG, HA RÁVISZED A KURZORT
                tooltip=folium.Tooltip(
                    f"<span>{row['hely']}, {row['ar']} £</span>",
                    permanent=False,
                    direction="top",
                    style=f"""
                        color: white; 
                        background-color: {szin}; 
                        padding: 3px 8px; 
                        border-radius: 4px; 
                        border: 2px solid {szin};
                        font-family: sans-serif;
                        font-weight: bold;
                        white-space: nowrap;
                        box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
                        """
                )
            ).add_to(m)

        # Térkép kirajzolása
        st_folium(m, width="100%", height=600, returned_objects=[])

    with col2:
        st.subheader("📊 Költségvetés")
        st.metric("Összesen", f"{df['ar'].sum():,} Ft")
        
        # Szerkeszthető lista
        st.write("Szerkesztés (időpont/hely):")
        edited_df = st.data_editor(df[["id", "nap", "hely", "ar", "kat"]], hide_index=True)
        
        if st.button("Módosítások mentése"):
            for index, row in edited_df.iterrows():
                c.execute("UPDATE helyszinek SET nap=?, hely=?, ar=?, kat=? WHERE id=?", 
                          (row['nap'], row['hely'], row['ar'], row['kat'], row['id']))
            conn.commit()
            st.success("Adatok frissítve!")
            st.rerun()

        if st.button("Minden törlése"):
            c.execute("DELETE FROM helyszinek")
            conn.commit()
            st.rerun()
else:
    st.info("Kezdésként adj hozzá egy helyszínt a bal oldali menüben (pl. 'Budapest, Halászbástya').")

# --- 6. LEZÁRÁS ---
conn.close()