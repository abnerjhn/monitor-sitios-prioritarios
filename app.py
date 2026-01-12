import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import os
import glob
import zipfile
import xml.etree.ElementTree as ET
from folium.features import GeoJsonPopup

# -----------------------------------------------------------------------------
# 1. CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Monitor de Sitios Prioritarios",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# CSS STYLING
# -----------------------------------------------------------------------------
st.markdown("""
    <style>
        /* Main Background */
        .stApp {
            background-color: #0b0e11;
        }
        
        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #151921;
        }
        
        /* Typography */
        h1, h2, h3 {
            color: #ffffff !important;
            font-family: 'Source Sans Pro', sans-serif;
        }
        p, div, label {
            color: #d1d5db;
        }
        
        /* Buttons */
        .stButton>button {
            background-color: #8b31c7;
            color: white;
            border-radius: 8px;
            border: none;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #a14add;
            border: 1px solid #d4a5f3;
        }
        
        /* Cards / Metrics / Expanders styling */
        div[data-testid="stMetric"], div[data-testid="stExpander"] {
            background-color: #1a1e26;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #2d333b;
        }
        
        /* Metric Label & Value Colors */
        [data-testid="stMetricLabel"] {
            color: #9ca3af !important;
        }
        [data-testid="stMetricValue"] {
            color: #ffffff !important;
        }
        
        /* Custom Header Gradient Text */
        .gradient-text {
            background: -webkit-linear-gradient(45deg, #a742ea, #00d4ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: bold;
        }

        /* Expander Header */
        .streamlit-expanderHeader {
            background-color: transparent !important;
            color: #ffffff !important;
        }
        
        /* Scrollbars (Webkit) */
        ::-webkit-scrollbar {
            width: 8px;
            background: #0b0e11;
        }
        ::-webkit-scrollbar-thumb {
            background: #2d333b; 
            border-radius: 4px;
        }

        /* FIX: Force Dark Theme on HTML Tables (PopupInfo) */
        div[data-testid="stMarkdownContainer"] table {
            width: 100% !important;
            border-collapse: collapse !important;
            background-color: #1a1e26 !important;
            color: #ffffff !important;
        }
        div[data-testid="stMarkdownContainer"] tr {
            background-color: #1a1e26 !important;
            border-bottom: 1px solid #2d333b !important;
        }
        div[data-testid="stMarkdownContainer"] td, 
        div[data-testid="stMarkdownContainer"] th {
            background-color: #1a1e26 !important; /* Override light blue backgrounds from KML */
            color: #ffffff !important;           /* Force white text */
            border: none !important;
            padding: 8px !important;
        }
        div[data-testid="stMarkdownContainer"] th {
            border-bottom: 2px solid #8b31c7 !important; /* Purple accent for headers */
            font-weight: bold !important;
        }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def get_kmz_descriptions(kmz_files):
    """
    Parses KMZ files to extract Placemark descriptions (HTML PopupInfo).
    Returns a dictionary: {Name: Description}
    """
    descriptions = {}
    
    for kmz_path in kmz_files:
        if not os.path.exists(kmz_path):
            continue
            
        try:
            with zipfile.ZipFile(kmz_path, 'r') as kmz:
                # Find the first kml file
                kml_filename = [f for f in kmz.namelist() if f.endswith('.kml')][0]
                with kmz.open(kml_filename, 'r') as kml_file:
                    tree = ET.parse(kml_file)
                    root = tree.getroot()
                    
                    # Handle namespaced KML (usually http://www.opengis.net/kml/2.2)
                    # We'll use a wildcard approach for tag names to be robust
                    # Iterate all elements that end with 'Placemark'
                    for placemark in root.findall(".//"):
                        if placemark.tag.endswith('Placemark'):
                            name_tag = None
                            desc_tag = None
                            for child in placemark:
                                if child.tag.endswith('name'):
                                    name_tag = child
                                if child.tag.endswith('description'):
                                    desc_tag = child
                            
                            if name_tag is not None and desc_tag is not None:
                                name = name_tag.text.strip()
                                desc = desc_tag.text
                                descriptions[name] = desc
                                
        except Exception as e:
            # st.warning(f"Error parseando KMZ {kmz_path}: {e}")
            pass
            
    return descriptions

# -----------------------------------------------------------------------------
# 3. DATA LOADING
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=True)
def load_data():
    """
    Loads and processes all necessary data (Originals and Proposed).
    Handles chunk loading for Proposed sites.
    """
    # --- 3.1 Load Originals ---
    # GeoJSON
    path_orig_geo = os.path.join("data", "sitios_prior_originales.json")
    if not os.path.exists(path_orig_geo):
        st.error(f"Archivo no encontrado: {path_orig_geo}")
        return None, None
        
    gdf_orig = gpd.read_file(path_orig_geo)
    
    # Attributes
    path_orig_attr = os.path.join("data", "sitios_prior_originales (1).json")
    if os.path.exists(path_orig_attr):
        df_orig_attr = pd.read_json(path_orig_attr)
        # Merge on Codrnap
        if 'Codrnap' in gdf_orig.columns and 'Codrnap' in df_orig_attr.columns:
            # Only merge columns that are not already in gdf_orig (except key)
            cols_to_use = df_orig_attr.columns.difference(gdf_orig.columns).tolist()
            cols_to_use.append('Codrnap')
            gdf_orig = gdf_orig.merge(df_orig_attr[cols_to_use], on='Codrnap', how='left')
    else:
        st.warning("No se encontró el archivo de atributos de Sitios Originales")

    # --- 3.2 Load Proposed (Chunks) ---
    chunk_files = glob.glob(os.path.join("data", "chunks", "*.geojson"))
    if not chunk_files:
        st.error("No se encontraron chunks de datos propuestos en data/chunks/")
        return gdf_orig, None

    gdf_list = []
    for file in chunk_files:
        try:
            gdf_chunk = gpd.read_file(file)
            gdf_list.append(gdf_chunk)
        except Exception as e:
            st.warning(f"Error cargando chunk {file}: {e}")
            
    if gdf_list:
        gdf_prop = pd.concat(gdf_list, ignore_index=True)
    else:
        gdf_prop = gpd.GeoDataFrame()
        
    # Attributes Proposed
    path_prop_attr = os.path.join("data", "sitios_prior_propuestos (1).json")
    if os.path.exists(path_prop_attr):
        df_prop_attr = pd.read_json(path_prop_attr)
        # Merge on Name
        if 'Name' in gdf_prop.columns and 'Name' in df_prop_attr.columns:
            # Only merge columns that are not already in gdf_prop (except key)
            cols_to_use_p = df_prop_attr.columns.difference(gdf_prop.columns).tolist()
            cols_to_use_p.append('Name')
            gdf_prop = gdf_prop.merge(df_prop_attr[cols_to_use_p], on='Name', how='left')

    # --- 3.3 Load KMZ Descriptions (PopupInfo recovery) ---
    kmz_files = [
        os.path.join("data", "MacroZonaNorte.kmz"),
        os.path.join("data", "MacroZonaCentro.kmz"),
        os.path.join("data", "MacroZonaSur.kmz")
    ]
    kmz_descriptions = get_kmz_descriptions(kmz_files)
    
    # Apply descriptions to gdf_prop
    if kmz_descriptions:
        # We assume 'Name' maps to the Placemark name
        # If 'PopupInfo' exists and is empty/null, we fill it. If it doesn't exist, we create it.
        if 'PopupInfo' not in gdf_prop.columns:
            gdf_prop['PopupInfo'] = None
            
        # Map values
        gdf_prop['PopupInfo_KMZ'] = gdf_prop['Name'].map(kmz_descriptions)
        
        # Coalesce: Use KMZ if valid, else keep existing
        gdf_prop['PopupInfo_KMZ'] = gdf_prop['PopupInfo_KMZ'].fillna(gdf_prop['PopupInfo'])
        gdf_prop['PopupInfo'] = gdf_prop['PopupInfo_KMZ']
        
    return gdf_orig, gdf_prop

# Load data
gdf_orig, gdf_prop = load_data()

if gdf_orig is None or gdf_prop is None:
    st.stop()

# -----------------------------------------------------------------------------
# 4. HEADER & CONTEXT
# -----------------------------------------------------------------------------
st.title("Monitor de Sitios Prioritarios - Ley 21.600")

with st.expander("ℹ️ Sobre el Proyecto (Contexto)"):
    st.markdown("""
    ### **Contexto General**
    El Servicio de Biodiversidad y Áreas Protegidas (SBAP), creado bajo la **Ley 21.600**, establece un nuevo marco para la gestión de la biodiversidad en Chile. Un componente clave de esta ley es la redefinición y homologación de los **Sitios Prioritarios para la Conservación de la Biodiversidad**.
    
    Este "Monitor de Sitios Prioritarios" tiene como objetivo facilitar el análisis comparativo entre:
    1.  **La Cartografía Original (Ley 19.300 / Estrategias Regionales):** Basada en los límites definidos históricamente por las Estrategias Regionales de Biodiversidad y otros instrumentos previos.
    2.  **La Propuesta de Homologación (Ley 21.600):** La nueva cartografía ajustada que busca cumplir con los estándares técnicos y legales del nuevo servicio SBAP.
    
    ### **Objetivo del Dashboard**
    Esta herramienta interactiva permite a técnicos, autoridades y ciudadanos visualizar las diferencias espaciales y de atributos entre ambas versiones, apoyando el proceso de toma de decisiones y la transparencia en la gestión ambiental.
    
    ### **Funcionalidades**
    *   **Comparación Dual:** Visualización simultánea de la geometría original vs. propuesta.
    *   **Métricas en Tiempo Real:** Cálculo automático de diferencias en Superficie (ha) y Perímetro (km).
    *   **Acceso a Información Oficial:** Vínculos directos a las fichas SIMBIO y visualización de fichas técnicas estáticas.
    *   **Detalle de Atributos:** Acceso a la data normativa (Resoluciones, Macro Zonas, Designaciones).
    """)

st.markdown("---")

# -----------------------------------------------------------------------------
# 5. SITE SELECTION (Top of page)
# -----------------------------------------------------------------------------
# Create selection list: "Codrnap (NombreOrig)"
if 'NombreOrig' in gdf_orig.columns and 'Codrnap' in gdf_orig.columns:
    gdf_orig['display_name'] = gdf_orig.apply(lambda x: f"{x['Codrnap']} ({x['NombreOrig']})", axis=1)
    # Sort for better UX
    options = sorted(gdf_orig['display_name'].tolist())
else:
    st.error("Las columnas 'NombreOrig' o 'Codrnap' no existen en los datos originales.")
    st.stop()

selected_option = st.selectbox("Seleccione Sitio Prioritario:", options)

# Extract ID (Codrnap) from selection
# Assuming format "ID (Name)" - split by first space/paren
selected_id = selected_option.split(' ')[0].strip()

# Display Selected Site Title
st.header(f"Sitio: {selected_option}")

# -----------------------------------------------------------------------------
# 6. DATA FILTERING
# -----------------------------------------------------------------------------
# Filter Originals
site_orig = gdf_orig[gdf_orig['Codrnap'] == selected_id]

# Filter Proposed (using Name as ID as per instructions)
site_prop = gdf_prop[gdf_prop['Name'] == selected_id]

if site_orig.empty:
    st.warning(f"No se encontró información original para el código {selected_id}")
    
# -----------------------------------------------------------------------------
# 7. LAYOUT & VISUALIZATION
# -----------------------------------------------------------------------------
col1, col2 = st.columns(2)

# --- MAP FUNCTION ---
def create_dual_map(feature_orig, feature_prop, primary='orig'):
    """
    Creates a map with both layers, but sets visibility based on primary.
    """
    # Determine center and bounds from the primary feature found
    center_geom = None
    if primary == 'orig' and not feature_orig.empty:
        center_geom = feature_orig.geometry.iloc[0]
        bounds = feature_orig.total_bounds
    elif primary == 'prop' and not feature_prop.empty:
        center_geom = feature_prop.geometry.iloc[0]
        bounds = feature_prop.total_bounds
    
    # If primary is missing, try the other
    if center_geom is None:
        if not feature_orig.empty:
            center_geom = feature_orig.geometry.iloc[0]
            bounds = feature_orig.total_bounds
        elif not feature_prop.empty:
            center_geom = feature_prop.geometry.iloc[0]
            bounds = feature_prop.total_bounds
        else:
            return None # No geometry at all

    center = center_geom.centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=10, tiles='Esri.WorldImagery', attr='Esri')

    # Styles
    style_orig = {'fillColor': '#ff0000', 'color': 'red', 'weight': 2, 'fillOpacity': 0.5}
    style_prop = {'fillColor': '#00ff00', 'color': 'green', 'weight': 2, 'fillOpacity': 0.5}

    # Add Original Layer
    if not feature_orig.empty:
        gj_orig = folium.GeoJson(
            feature_orig,
            name='Sitio Original',
            style_function=lambda x: style_orig,
            tooltip=folium.GeoJsonTooltip(fields=['NombreOrig'], aliases=['Nombre:']) if 'NombreOrig' in feature_orig.columns else None,
            show=(primary == 'orig')
        )
        gj_orig.add_to(m)

    # Add Proposed Layer
    if not feature_prop.empty:
        gj_prop = folium.GeoJson(
            feature_prop,
            name='Sitio Propuesto',
            style_function=lambda x: style_prop,
             tooltip=folium.GeoJsonTooltip(fields=['Name'], aliases=['Código:']) if 'Name' in feature_prop.columns else None,
            show=(primary == 'prop')
        )
        gj_prop.add_to(m)

    folium.LayerControl().add_to(m)
    
    if bounds is not None:
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    
    return m

def render_metric(label, value, unit, delta_val=None):
    """
    Renders a metric with 50% reduced size and inline delta.
    """
    delta_html = ""
    if delta_val is not None:
        color = "green" if delta_val >= 0 else "red"
        sign = "+" if delta_val > 0 else ""
        delta_html = f"<span style='color:{color}; font-size: 0.8em; margin-left: 5px;'>({sign}{delta_val:,.2f})</span>"
    
    st.markdown(f"""
    <div style="margin-bottom: 10px;">
        <div style="font-size: 0.8rem; color: #888;">{label}</div>
        <div style="font-size: 1.2rem; font-weight: bold;">
            {value:,.2f} {unit} {delta_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


# === COLUMN 1: ORIGINAL ===
with col1:
    st.subheader("Sitio Original (Ley 19.300)")
    
    if not site_orig.empty:
        row = site_orig.iloc[0]
        
        # Metrics
        has = row['Has'] if 'Has' in row else 0
        perim = row['Perim_km'] if 'Perim_km' in row else 0
        
        c1a, c1b = st.columns(2)
        with c1a:
            render_metric("Superficie", has, "ha")
        with c1b:
            render_metric("Perímetro", perim, "km")
        
        # Map
        m_orig = create_dual_map(site_orig, site_prop, primary='orig')
        if m_orig:
            st_folium(m_orig, use_container_width=True, height=400, key="map_orig")
            
        # Legend/Color info
        designacion = row['designacio'] if 'designacio' in row else "N/A"
        st.caption(f"**Designación:** {designacion}")
        
        # SIMBIO Link
        url_simbio = row['URL_SIMBIO'] if 'URL_SIMBIO' in row else None
        if url_simbio:
            st.link_button("🔗 Ver Descripción en SIMBIO", url_simbio)
            
        # Dataframe
        with st.expander("Ver Atributos Detallados", expanded=True):
            # Clean dataframe: drop duplicates columns ending in _attr and geometry
            cols_to_drop = ['geometry'] + [c for c in site_orig.columns if c.endswith('_attr')]
            display_df = pd.DataFrame(site_orig.drop(columns=[c for c in cols_to_drop if c in site_orig.columns]))
            st.dataframe(display_df.T)
    else:
        st.info("Sin datos para este sitio.")

# === COLUMN 2: PROPOSED ===
with col2:
    st.subheader("Sitio Propuesto (Ley 21.600)")
    
    if not site_prop.empty:
        row_p = site_prop.iloc[0]
        
        # Metrics
        has_p = row_p['Has'] if 'Has' in row_p else 0
        perim_p = row_p['Perim_km'] if 'Perim_km' in row_p else 0
        
        # Determine deltas if possible (Prop - Orig)
        has = 0
        perim = 0
        if not site_orig.empty:
            has = site_orig.iloc[0]['Has'] if 'Has' in site_orig.iloc[0] else 0
            perim = site_orig.iloc[0]['Perim_km'] if 'Perim_km' in site_orig.iloc[0] else 0

        # Delta calc
        delta_has = has_p - has if not site_orig.empty else 0
        delta_perim = perim_p - perim if not site_orig.empty else 0

        c2a, c2b = st.columns(2)
        with c2a:
            render_metric("Superficie", has_p, "ha", delta_has)
        with c2b:
            render_metric("Perímetro", perim_p, "km", delta_perim)
        
        # Map
        m_prop = create_dual_map(site_orig, site_prop, primary='prop')
        if m_prop:
            st_folium(m_prop, use_container_width=True, height=400, key="map_prop")
            
        # Legend info
        zona = row_p['FolderPath'] if 'FolderPath' in row_p else "N/A"
        st.caption(f"**Macro Zona / Carpeta:** {zona}")
        
        # Image Viewer (Ficha)
        ficha_path = os.path.join("data", "Fichas", f"{selected_id}.jpg")
        
        with st.expander("🖼️ Ver Ficha Técnica (Mapa Estático)", expanded=False):
            if os.path.exists(ficha_path):
                st.image(ficha_path, caption=f"Ficha: {selected_id}", use_container_width=True)
            else:
                st.warning(f"No se encontró ficha (imagen) para {selected_id}")
                
        # PopupInfo Render
        with st.expander("Ver Descripción Propuesta (PopupInfo)", expanded=True):
            if 'PopupInfo' in row_p and row_p['PopupInfo']:
                 st.markdown(row_p['PopupInfo'], unsafe_allow_html=True)
            else:
                 st.info("Sin información detallada en PopupInfo.")
    else:
        st.warning("No se encontró geometría propuesta para este sitio.")
