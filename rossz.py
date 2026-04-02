import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import time

# --- 1. ADATBÁZIS KAPCSOLAT (JAVÍTVA) ---
try:
    # Fontos: A Streamlit Secrets-ben kell lennie a 'postgres' -> 'url' bejegyzésnek!
    db_url = st.secrets["postgres"]["url"]
    engine = create_engine(db_url, pool_pre_ping=True)
except Exception:
    st.error("Hiba: Az adatbázis URL nem található a Secrets-ben!")
    st.stop()

# --- 2. BEÁLLÍTÁSOK ---
st.set_page_config(page_title="Profi London Tervező", layout="wide")

# CSS hack a zöld gombokhoz és az elrendezéshez
st.markdown("""
    <style>
    button[kind="primary"] { background-color: #28a745 !important; border: none !important; }
    .stForm { background-color: #f8f9fa; padding: 20px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

geolocator = Nominatim(user_agent="London_Trip_Planner_v2026")
nap_szinek = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue", "darkpurple", "pink"]

# --- 3. ADATOK LEKÉRÉSE ---
def get_data():
    with engine.connect() as conn:
        return pd.read_sql("SELECT * FROM helyszinek ORDER BY id", conn)

# --- 4. FRAGMENT: CSAK A TÉRKÉP (GYORSÍTÁS) ---
@st.fragment
def show_map(df):
    df_map = df.dropna(subset=['lat', 'lon'])
    
    # Alap térkép (London)
    start_coord = [51.5074, -0.1278] if df_map.empty else [df_map['lat'].mean(), df_map['lon'].mean()]
    m = folium.Map(location=start_coord, zoom_start=12, tiles='OpenStreetMap')
    
    # Google Maps réteg
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
        attr='Google', name='Google Maps', overlay=True
    ).add_to(m)

    for _, row in df_map.iterrows():
        # Nap ellenőrzése
        is_empty_day = pd.isna(row['nap']) or str(row['nap']).strip().lower() in ["", "nan", "null"]
        
        try:
            if not is_empty_day:
                nap_szam = int(''.join(filter(str.isdigit, str(row['nap']))))
                ikon_szine = nap_szinek[(nap_szam - 1) % len(nap_szinek)]
                opacity = "1.0"
            else:
                ikon_szine, opacity = "gray", "0.4"
        except:
            ikon_szine, opacity = "black", "1.0"

        # Ikon típus
        ik_map = {"Szállás":"bed", "Étterem":"cutlery", "Látnivaló":"university", "Múzeum":"university", "Reptér":"plane", "Park":"leaf"}
        ikon_nev = ik_map.get(row['kat'], "map-marker")

        question_mark = '<i class="fa fa-question" style="position:absolute; color:orange; font-size:14px; z-index:10; font-weight:bold;"></i>' if is_empty_day else ""

        # HTML Ikon - A DUPLA KAPCSOS ZÁRÓJELEK JAVÍTJÁK A SYNTAX ERRORT
        icon_html = f"""
            <div style="display:flex; justify-content:center; align-items:center; position:relative; width:30px; height:30px; font-size:20px; color:{ikon_szine}; text-shadow:-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000, 2px 2px 5px rgba(0,0,0,0.5);">
                <i class="fa fa-{ikon_nev}" style="opacity:{opacity};"></i>
                {question_mark}
            </div>
        """

        folium.Marker(
            location=[row['lat'], row['lon']],
            icon=folium.DivIcon(html=icon_html, icon_size=(30,30), icon_anchor=(15,15)),
            tooltip=f"{row['nap']} - {row['hely']}"
        ).add_to(m)

    if not df_map.empty:
        m.fit_bounds(df_map[['lat', 'lon']].values.tolist())
    
    st_folium(m, width="100%", height=600, key="london_map")

# --- 5. FŐ OLDAL ---
st.title("🇬🇧 London Utazás Tervező")

df = get_data()

col1, col2 = st.columns([2, 1])

with col1:
    show_map(df)

with col2:
    st.subheader("📍 Új helyszín")
    with st.form("input_form", clear_on_submit=True):
        f_nap = st.text_input("Nap")
        f_hely = st.text_input("Helyszín neve (pl. Big Ben, London)")
        f_ar = st.number_input("Költség", min_value=0)
        f_kat = st.selectbox("Kategória", ["Szállás", "Étterem", "Látnivaló", "Múzeum", "Reptér", "Park"])
        submit = st.form_submit_button("Hozzáadás")

    if submit and f_hely:
        try:
            loc = geolocator.geocode(f_hely, timeout=15)
            if loc:
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO helyszinek (nap, hely, ar, kat, lat, lon) VALUES (:n, :h, :a, :k, :la, :lo)"),
                                 {"n":f_nap, "h":f_hely, "a":f_ar, "k":f_kat, "la":loc.latitude, "lo":loc.longitude})
                st.success("Mentve!")
                time.sleep(0.5)
                st.rerun()
        except:
            st.error("Keresési hiba.")

    st.divider()
    
    # Szerkesztés és Törlés
    edited_df = st.data_editor(df, column_order=("nap", "hely", "ar", "kat"), num_rows="dynamic", hide_index=True, key="main_editor")
    
    if st.button("Változtatások véglegesítése", type="primary"):
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE TABLE helyszinek RESTART IDENTITY"))
            if not edited_df.empty:
                to_save = edited_df.drop(columns=['id'], errors='ignore')
                to_save.to_sql("helyszinek", engine, if_exists="append", index=False)
        st.success("Szinkronizálva!")
        time.sleep(0.5)
        st.rerun()

    st.metric("Összköltség", f"{df['ar'].sum():,} Ft")
