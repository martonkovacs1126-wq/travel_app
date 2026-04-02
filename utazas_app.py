import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeopyError
import time

# --- 1. OLDAL BEÁLLÍTÁSAI ÉS STÍLUS ---
st.set_page_config(page_title="London", layout="wide")

# Napok színei (sorrendben: 1. nap, 2. nap, stb.)
nap_szinek = ["green", "purple", "pink", "beige", "cadetblue", "orange"]

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
#geolocator = Nominatim(user_agent="Travel_Planner_Final_2026")
# Használj egyedi nevet, és adjunk több időt a válaszra
geolocator = Nominatim(user_agent="London_Trip_Planner_Unique_ID_12345")

kat_szinek = {
    "Szállás": "red",
    "Étterem": "blue",
    "Látnivaló": "green",
    "Közlekedés": "orange",
    "Múzeum": "gray",    
    "Reptér": "gray",
    "Park": "gray",
    "Egyéb": "gray",
}

# --- 4. OLDALSÁV (ADATBEVITEL) ---
st.sidebar.header("📍 Új helyszín")
with st.sidebar.form("input_form", clear_on_submit=True):
    f_nap = st.text_input("Nap (1, 2, 3, 4, 5 = szállás, 6 = étterem)")
    f_hely = st.text_input("Helyszín pontos neve")
    f_ar = st.number_input("Költség (Ft)", min_value=0, step=500)
    f_kat = st.selectbox("Kategória", list(kat_szinek.keys()))
    submit = st.form_submit_button("Hozzáadás")

if submit and f_hely:
    try:
        # Keresés megkönnyítésee
        location = geolocator.geocode(f_hely, timeout=20)
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
st.title("🌍 London 2026")

if not df.empty:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("🗺️ Térkép")
        
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
            # 1. NAP SZÍNÉNEK MEGHATÁROZÁSA + ÜRES NAP ELLENŐRZÉSE
            # Megnézzük, hogy a 'nap' üres-e (None, üres szöveg vagy "null")
            is_empty_day = pd.isna(row['nap']) or str(row['nap']).strip() == "" or str(row['nap']).lower() == "null"
            
            try:
                if is_empty_day:
                    ikon_szine = "gray"  # Ha üres, szürke legyen az alap
                    opacity = "0.4"      # És halványabb az ikon
                else:
                    # Kiszedjük a számot a szövegből
                    nap_szam = int(''.join(filter(str.isdigit, str(row['nap']))))
                    szin_index = (nap_szam - 1) % len(nap_szinek)
                    ikon_szine = nap_szinek[szin_index]
                    opacity = "1.0"
            except:
                ikon_szine = "black"
                opacity = "1.0"
                is_empty_day = False # Ha hiba van, de nem üres, ne tegyen kérdőjelet

            # 2. IKON TÍPUSA
            if row['kat'] == "Szállás": ikon_nev = "bed"
            elif row['kat'] == "Étterem": ikon_nev = "cutlery"
            elif row['kat'] == "Látnivaló": ikon_nev = "camera"
            elif row['kat'] == "Múzeum": ikon_nev = "university" # A 'landmark' fa-4.7-ben 'university'
            elif row['kat'] == "Reptér": ikon_nev = "plane"     # A 'plane-arrival' helyett stabilabb a 'plane'
            elif row['kat'] == "Park": ikon_nev = "leaf"
            else: ikon_nev = "map-marker"

            # 3. KÉRDŐJEL GENERÁLÁSA (Csak ha a nap üres)
            question_mark_html = ""
            if is_empty_day:
                question_mark_html = """
                    <i class="fa fa-question" style="
                        position: absolute;
                        color: orange;
                        font-size: 14px;
                        font-weight: bold;
                        text-shadow: 1px 1px 2px #000;
                        z-index: 10;
                    "></i>
                """

            # 4. EGYEDI HTML IKON (Egymásra rétegezve)
            icon_html = f"""
                <div style="
                    font-size: 16px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    position: relative;
                    width: 20px;
                    height: 20px;
                ">
                    <i class="fa fa-{ikon_nev}" style="
                        color: {ikon_szine};
                        opacity: {opacity};
                        text-shadow: 
                            -1px -1px 0 #000,  1px -1px 0 #000,
                            -1px  1px 0 #000,  1px  1px 0 #000,
                            2px 2px 5px rgba(0,0,0,0.5);
                    "></i>
                    {question_mark_html}
                </div>
            """

            folium.Marker(
                location=[row['lat'], row['lon']],
                icon=folium.DivIcon(html=icon_html),
                tooltip=folium.Tooltip(
                    f"<b>{row['nap'] if not is_empty_day else '???'} - {row['hely']}</b>", 
                    style=f"color:white; background-color:{ikon_szine}; padding:5px; border-radius:5px;"
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
        st.write("**Delete** gomb")
        
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
