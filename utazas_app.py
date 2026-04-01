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
        
        # 1. Térkép alaphelyzete (London, ha üres)
        if not df_map.empty:
            start_coord = [df_map['lat'].mean(), df_map['lon'].mean()]
            start_zoom = 13
        else:
            start_coord = [51.5074, -0.1278] 
            start_zoom = 12

        # Térkép létrehozása, az OpenStreetMap alapértelmezett csempéjével,
        # hogy ha a Google nem töltene be, akkor se üres tengert láss.
        m = folium.Map(location=start_coord, zoom_start=start_zoom, tiles='OpenStreetMap')
        
        # 2. Google Maps réteg - Próbáljuk meg ezt a stabilabb linket
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
            attr='Google',
            name='Google Maps',
            overlay=True # Ez legyen True, hogy ráfeküdjön az OSM-re
        ).add_to(m)

        # 3. Pontok kirajzolása egyedi CSS ikonokkal
        for _, row in df_map.iterrows():
            # Ikon kiválasztása
            if row['kat'] == "Szállás":
                valasztott_ikon = "bed"
            elif row['kat'] == "Étterem":
                valasztott_ikon = "cutlery"
            elif row['kat'] == "Látnivaló":
                valasztott_ikon = "camera"
            elif row['kat'] == "Közlekedés":
                valasztott_ikon = "bus"
            else:
                valasztott_ikon = "map-marker"

            # --- EGYEDI CSS STÍLUS AZ IKONHOZ (Piros, fekete körvonal, árnyék) ---
            # Font Awesome 4.7 ikon, amit a te stílusoddal ruházunk fel
            icon_html = f"""
                <div style="
                    font-size: 24px;
                    color: red;
                    text-shadow: 
                        -1px -1px 0 #000,  1px -1px 0 #000,
                        -1px  1px 0 #000,  1px  1px 0 #000, /* Vékony fekete körvonal */
                        2px 2px 4px rgba(0,0,0,0.5); /* Kicsi árnyék */
                ">
                    <i class="fa fa-{valasztott_ikon}"></i>
                </div>
            """

            # 4. Megjelenítés DivIcon-nal
            folium.Marker(
                location=[row['lat'], row['lon']],
                # A DivIcon használatával a fent definiált HTML-t illesztjük be
                icon=folium.DivIcon(html=icon_html),
                tooltip=folium.Tooltip(
                    f"<b>{row['hely']}</b>", 
                    style=f"color:white; background-color:red; padding:5px; border-radius:5px;"
                )
            ).add_to(m)

        # 5. Automatikus zoom (Fit Bounds)
        if not df_map.empty:
            sw = df_map[['lat', 'lon']].min().values.tolist()
            ne = df_map[['lat', 'lon']].max().values.tolist()
            m.fit_bounds([sw, ne])

        st_folium(m, width="100%", height=600, key="map_final_icon_fix", returned_objects=[])
    with col2:
        st.subheader("📊 Lista és Törlés")
        st.write("Törlés: Jelöld ki a sort (bal szél) és nyomj **Delete**-et!")
        
        # Ez a kulcs: a key="data_editor" miatt a session_state-be kerül az adat
        edited_df = st.data_editor(
            df, 
            column_order=("nap", "hely", "ar", "kat"),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="my_editor"
        )
        
        if st.button("Változtatások véglegesítése", type="primary"):
            try:
                # 1. Megnézzük, mik maradtak a táblázatban (ID-k listája)
                maradt_id_k = edited_df['id'].tolist() if 'id' in edited_df.columns else []
                
                with engine.begin() as conn:
                    if not maradt_id_k:
                        # Ha minden sort kitöröltél a táblázatból: ürítjük az egészet
                        conn.execute(text("TRUNCATE TABLE helyszinek RESTART IDENTITY"))
                    else:
                        # 2. TÖRÖLJÜK azokat, amik NINCSENEK a listában
                        # Ez a SQL parancs: "Törölj mindent, aminek az ID-ja nincs a maradékok között"
                        id_string = ", ".join(map(str, maradt_id_k))
                        conn.execute(text(f"DELETE FROM helyszinek WHERE id NOT IN ({id_string})"))
                        
                        # 3. FRISSÍTJÜK a meglévőket (ha átírtál árat vagy nevet)
                        for _, row in edited_df.iterrows():
                            conn.execute(text("""
                                UPDATE helyszinek 
                                SET nap = :nap, hely = :hely, ar = :ar, kat = :kat 
                                WHERE id = :id
                            """), {
                                "nap": row['nap'], "hely": row['hely'], 
                                "ar": row['ar'], "kat": row['kat'], "id": row['id']
                            })
                
                st.success("Törlés és frissítés sikeres!")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Hiba történt: {e}")
            
        st.metric("Összköltség", f"{df['ar'].sum():,} Ft")
else:
    st.info("Még nincs mentett helyszíned. Adj hozzá egyet a bal oldalon!")
