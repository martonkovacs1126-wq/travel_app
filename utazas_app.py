from fasthtml.common import *
import pandas as pd
from sqlalchemy import create_engine, text

# --- 1. ADATBÁZIS ÉS ALAPOK ---
db_url = "ID_TEDD_BE_A_SUPABASE_URL_ED"
engine = create_engine(db_url)

# Adatbázis sémája (FastHTML-nél gyakran használnak mini-ORM-et, de maradjunk az SQL-nél)
def get_data():
    with engine.connect() as conn:
        return pd.read_sql("SELECT * FROM helyszinek ORDER BY id", conn)

# --- 2. STÍLUS ÉS TÉRKÉP SCRIPT (A "Fejléc") ---
# Itt adjuk meg a Leaflet.js-t és a Font Awesome-ot
hd = (
    Link(rel="stylesheet", href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"),
    Script(src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"),
    Link(rel="stylesheet", href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css"),
    Style("""
        #map { height: 600px; width: 100%; border-radius: 10px; }
        .marker-pin { display: flex; justify-content: center; align-items: center; }
    """)
)

app, rt = fast_app(pwa=True, hd=hd)

# --- 3. KOMPONENSEK (HTML darabkák) ---
def MapComponent(df):
    # Ez a rész generálja a térképhez szükséges JavaScript adatot
    locations = df.to_json(orient="records")
    return Div(id="map-container")(
        Div(id="map"),
        Script(f"""
            var map = L.map('map').setView([47.4979, 19.0402], 13);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
            var data = {locations};
            data.forEach(loc => {{
                if(loc.lat && loc.lon) {{
                    var icon = L.divIcon({{
                        className: 'custom-div-icon',
                        html: `<div style="color:red; font-size:24px; text-shadow: 1px 1px black;">
                               <i class="fa fa-bed"></i></div>`,
                        iconSize: [30, 42],
                        iconAnchor: [15, 42]
                    }});
                    L.marker([loc.lat, loc.lon], {{icon: icon}}).addTo(map)
                     .bindTooltip(loc.hely);
                }
            }});
        """)
    )

# --- 4. OLDALAK (Route-ok) ---

@rt("/")
def get():
    df = get_data()
    # Az oldal felépítése: Bal oldal (Form), Jobb oldal (Térkép + Lista)
    return Titled("London Tervező - FastHTML",
        Grid(
            # Bal oszlop: Form
            Card(
                Form(hx_post="/add", hx_target="#main-content")(
                    Input(placeholder="Nap (pl. 1)", name="nap"),
                    Input(placeholder="Helyszín", name="hely"),
                    Input(placeholder="Ár", name="ar", type="number"),
                    Select(Option("Szállás"), Option("Étterem"), name="kat"),
                    Button("Hozzáadás", cls="primary")
                )
            ),
            # Jobb oszlop: Térkép és Lista
            Div(id="main-content")(
                MapComponent(df),
                Table(
                    Thead(Tr(Th("Nap"), Th("Hely"), Th("Ár"), Th("Művelet"))),
                    Tbody(*[Tr(Td(r.nap), Td(r.hely), Td(r.ar), 
                               Td(Button("Törlés", hx_delete=f"/del/{r.id}", hx_target="#main-content"))) 
                            for i, r in df.iterrows()])
                )
            )
        )
    )

@rt("/add")
def post(nap:str, hely:str, ar:int, kat:str):
    # 1. Geocoding (itt is ugyanúgy meghívhatod a geopy-t)
    # 2. SQL INSERT
    # 3. Visszaküldjük az egészet frissítve
    return get()

@rt("/del/{id}")
def delete(id:int):
    # SQL DELETE WHERE id = id
    return get()

serve()
