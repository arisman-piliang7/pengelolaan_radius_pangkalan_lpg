"""
Sistem Manajemen Radius Pangkalan LPG
Jalankan: streamlit run app.py
Dependensi: pip install streamlit pandas folium streamlit-folium scipy openpyxl geopy
"""

import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from scipy.spatial import cKDTree
import math
import io
import os
import json
from datetime import datetime

st.set_page_config(
    page_title=" - Manajemen Radius dan Pergerakan Pangkalan",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
[data-testid="stSidebar"] { background: #1a1a2e; }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px; padding: 16px; color: white; text-align: center;
    margin: 4px;
}
.metric-card h2 { font-size: 2rem; margin: 0; }
.metric-card p  { margin: 0; opacity: .8; font-size:.85rem; }
.conflict-row { background-color: #fff3cd !important; }
.stDataFrame { border: 1px solid #e0e0e0; border-radius: 8px; }
h1,h2,h3 { color: #1a1a2e; }
</style>
""",
    unsafe_allow_html=True,
)

DB_FILE = "pangkalan_db.csv"
RADIUS_M = 100.0

COLUMNS = [
    "SoldTo",
    "NamaAgen",
    "Wilayah",
    "TipePangkalan",
    "IDRegistrasi",
    "NamaPangkalan",
    "EmailPangkalan",
    "NoHPPemilik",
    "NoKTPPemilik",
    "NamaPemilik",
    "NomorNIB",
    "QtyKontrak",
    "Catatan",
    "TipePembayaran",
    "NoRekening",
    "NamaBank",
    "NamaAkunBank",
    "TanggalDiapproveSAM",
    "Provinsi",
    "Kota",
    "Kecamatan",
    "Kelurahan",
    "RT",
    "RW",
    "KodePos",
    "Alamat",
    "IntegrasiMAP",
    "MID",
    "Latitude",
    "Longitude",
    "StatusPembaharuan",
]


# ── Helpers ──────────────────────────────────────────────────────────────────
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


@st.cache_data(ttl=5)
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE, dtype=str)
        for c in ["Latitude", "Longitude", "QtyKontrak"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    return pd.DataFrame(columns=COLUMNS)


def save_data(df: pd.DataFrame):
    df.to_csv(DB_FILE, index=False)
    load_data.clear()


def import_from_excel(uploaded):
    try:
        raw = pd.read_excel(uploaded, dtype=str)
        # normalise column names
        raw.columns = [c.strip() for c in raw.columns]
        # merge Status + Pembaharuan if split
        if (
            "Status" in raw.columns
            and "Pembaharuan" in raw.columns
            and "StatusPembaharuan" not in raw.columns
        ):
            raw["StatusPembaharuan"] = (
                raw["Status"].fillna("") + " " + raw["Pembaharuan"].fillna("")
            )
            raw["StatusPembaharuan"] = raw["StatusPembaharuan"].str.strip()
            raw.drop(columns=["Status", "Pembaharuan"], inplace=True)
        for c in COLUMNS:
            if c not in raw.columns:
                raw[c] = ""
        return raw[COLUMNS], None
    except Exception as e:
        return None, str(e)


def build_kdtree(df):
    valid = df.dropna(subset=["Latitude", "Longitude"])
    if len(valid) < 2:
        return None, valid
    coords_rad = np.radians(valid[["Latitude", "Longitude"]].values)
    tree = cKDTree(coords_rad)
    return tree, valid


# Cache konflik — kunci berdasarkan hash DataFrame agar otomatis invalide saat data berubah
@st.cache_data(show_spinner=False)
def find_conflicts_cached(df_hash_key, lats, lons, idxs_arr, radius_m=RADIUS_M):
    """Versi cached dari find_conflicts — dipanggil lewat find_conflicts()."""
    coords = np.column_stack([lats, lons])
    coords_rad = np.radians(coords)
    tree = cKDTree(coords_rad)
    r_rad = radius_m / 6_371_000
    conflicts = {}
    for i, row in enumerate(coords_rad):
        hits = tree.query_ball_point(row, r_rad)
        neighbours = []
        for j in hits:
            if j == i:
                continue
            d = haversine_m(lats[i], lons[i], lats[j], lons[j])
            if d < radius_m:
                neighbours.append((int(idxs_arr[j]), round(d, 1)))
        if neighbours:
            conflicts[int(idxs_arr[i])] = neighbours
    return conflicts


def find_conflicts(df, radius_m=RADIUS_M):
    """Wrapper yang meneruskan ke versi cached."""
    valid = df.dropna(subset=["Latitude", "Longitude"])
    if len(valid) < 2:
        return {}
    lats = valid["Latitude"].values.astype(float)
    lons = valid["Longitude"].values.astype(float)
    idxs = valid.index.values.astype(int)
    # hash key: jumlah baris + checksum koordinat ringan
    hash_key = f"{len(valid)}_{lats.sum():.4f}_{lons.sum():.4f}_{radius_m}"
    return find_conflicts_cached(hash_key, lats, lons, idxs, radius_m)


def suggest_free_slots(df, grid_spacing_m=150, bbox_pad=0.01):
    valid = df.dropna(subset=["Latitude", "Longitude"])
    if valid.empty:
        return []
    lat_min = valid["Latitude"].min() - bbox_pad
    lat_max = valid["Latitude"].max() + bbox_pad
    lon_min = valid["Longitude"].min() - bbox_pad
    lon_max = valid["Longitude"].max() + bbox_pad
    dlat = grid_spacing_m / 111_320
    dlon = grid_spacing_m / (111_320 * math.cos(math.radians((lat_min + lat_max) / 2)))
    tree, _ = build_kdtree(valid)
    r_rad = RADIUS_M / 6_371_000
    slots = []
    lat = lat_min
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            pt = np.radians([lat, lon])
            hits = tree.query_ball_point(pt, r_rad) if tree else []
            if not hits:
                slots.append((round(lat, 6), round(lon, 6)))
            lon += dlon
        lat += dlat
    return slots[:500]


# ── Sidebar nav ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⛽ DDMS Pangkalan")
    st.markdown("---")
    menu = st.radio(
        "Navigasi",
        [
            "🏠 Dashboard",
            "📋 Master Data",
            "➕ Tambah Pangkalan",
            "📊 Analisis Jarak",
            "🗺️ Peta Konflik",
            "✅ Rekomendasi Lokasi",
            "🔄 Rekomendasi Geser",
            "📥 Import / Export",
        ],
    )

# ── Load ─────────────────────────────────────────────────────────────────────
df = load_data()

# ═══════════════════════════════════════════════════════════════════════════════
# 1. DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
if menu == "🏠 Dashboard":
    st.title("⛽ DDMS — Dashboard Pangkalan LPG")

    valid_geo = df.dropna(subset=["Latitude", "Longitude"])

    # Hitung konflik hanya jika ada data — hasil di-cache otomatis
    if not valid_geo.empty:
        with st.spinner("Menghitung statistik konflik..."):
            conflicts = find_conflicts(df)
        n_conflict = len(conflicts)
    else:
        conflicts = {}
        n_conflict = 0

    c1, c2, c3, c4 = st.columns(4)
    for col, val, lbl in [
        (c1, len(df), "Total Pangkalan"),
        (c2, n_conflict, "Pangkalan Konflik"),
        (c3, len(valid_geo), "Koordinat Valid"),
        (
            c4,
            len(
                df[df["StatusPembaharuan"].str.contains("Active", case=False, na=False)]
            ),
            "Status Active",
        ),
    ]:
        col.markdown(
            f'<div class="metric-card"><h2>{val}</h2><p>{lbl}</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    if not df.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribusi per Wilayah")
            if "Wilayah" in df.columns:
                vc = df["Wilayah"].value_counts().head(10)
                st.bar_chart(vc)
        with col2:
            st.subheader("Distribusi per Tipe Pangkalan")
            if "TipePangkalan" in df.columns:
                vc2 = df["TipePangkalan"].value_counts()
                st.bar_chart(vc2)

        if n_conflict:
            st.warning(
                f"⚠️ Terdapat **{n_conflict}** pangkalan yang memiliki konflik radius <{RADIUS_M:.0f} m"
            )

# ═══════════════════════════════════════════════════════════════════════════════
# 2. MASTER DATA
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "📋 Master Data":
    st.title("📋 Master Data Pangkalan")

    # Filter
    with st.expander("🔍 Filter Data", expanded=False):
        fc1, fc2, fc3 = st.columns(3)
        prov_opts = ["(Semua)"] + sorted(df["Provinsi"].dropna().unique().tolist())
        prov_sel = fc1.selectbox("Provinsi", prov_opts)
        kota_df = df if prov_sel == "(Semua)" else df[df["Provinsi"] == prov_sel]
        kota_opts = ["(Semua)"] + sorted(kota_df["Kota"].dropna().unique().tolist())
        kota_sel = fc2.selectbox("Kota", kota_opts)
        tipe_opts = ["(Semua)"] + sorted(df["TipePangkalan"].dropna().unique().tolist())
        tipe_sel = fc3.selectbox("Tipe", tipe_opts)
        search = st.text_input("🔎 Cari nama/IDRegistrasi/MID")

    fdf = df.copy()
    if prov_sel != "(Semua)":
        fdf = fdf[fdf["Provinsi"] == prov_sel]
    if kota_sel != "(Semua)":
        fdf = fdf[fdf["Kota"] == kota_sel]
    if tipe_sel != "(Semua)":
        fdf = fdf[fdf["TipePangkalan"] == tipe_sel]
    if search:
        mask = (
            fdf["NamaPangkalan"].str.contains(search, case=False, na=False)
            | fdf["IDRegistrasi"].str.contains(search, case=False, na=False)
            | fdf["MID"].str.contains(search, case=False, na=False)
        )
        fdf = fdf[mask]

    st.info(f"Menampilkan **{len(fdf)}** dari **{len(df)}** pangkalan")
    st.dataframe(fdf, use_container_width=True, height=400)

    # Edit / Delete
    st.markdown("---")
    st.subheader("✏️ Edit / Hapus Pangkalan")
    if not df.empty:
        id_list = df["IDRegistrasi"].dropna().tolist()
        sel_id = st.selectbox("Pilih IDRegistrasi", id_list)
        sel_row = df[df["IDRegistrasi"] == sel_id]
        if not sel_row.empty:
            idx = sel_row.index[0]
            with st.form("edit_form"):
                cols = st.columns(3)
                edited = {}
                for i, col in enumerate(COLUMNS):
                    edited[col] = cols[i % 3].text_input(
                        col,
                        value=str(df.at[idx, col] if pd.notna(df.at[idx, col]) else ""),
                    )
                s1, s2 = st.columns(2)
                if s1.form_submit_button("💾 Simpan Perubahan"):
                    for col, val in edited.items():
                        df.at[idx, col] = val
                    save_data(df)
                    st.success("Data berhasil diperbarui!")
                    st.rerun()
                if s2.form_submit_button("🗑️ Hapus Pangkalan", type="secondary"):
                    df = df.drop(idx).reset_index(drop=True)
                    save_data(df)
                    st.success("Pangkalan dihapus!")
                    st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# 3. TAMBAH PANGKALAN
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "➕ Tambah Pangkalan":
    st.title("➕ Tambah Pangkalan Baru")
    st.info(f"Sistem akan memeriksa radius **{RADIUS_M:.0f} m** sebelum menyimpan.")

    with st.form("add_form"):
        c1, c2, c3 = st.columns(3)
        new_data = {}
        for i, col in enumerate(COLUMNS):
            new_data[col] = [c1, c2, c3][i % 3].text_input(col)

        submitted = st.form_submit_button("✅ Periksa & Simpan", type="primary")

    if submitted:
        try:
            lat = float(new_data["Latitude"])
            lon = float(new_data["Longitude"])
        except ValueError:
            st.error("Latitude / Longitude harus berupa angka desimal.")
            st.stop()

        valid = df.dropna(subset=["Latitude", "Longitude"])
        conflicts_found = []
        for _, row in valid.iterrows():
            d = haversine_m(lat, lon, row["Latitude"], row["Longitude"])
            if d < RADIUS_M:
                conflicts_found.append(
                    (row["NamaPangkalan"], row["IDRegistrasi"], round(d, 1))
                )

        if conflicts_found:
            st.error(
                f"❌ Tidak dapat ditambahkan! Terdapat **{len(conflicts_found)}** pangkalan dalam radius {RADIUS_M:.0f} m:"
            )
            st.dataframe(
                pd.DataFrame(
                    conflicts_found,
                    columns=["NamaPangkalan", "IDRegistrasi", "Jarak (m)"],
                )
            )
        else:
            new_row = pd.DataFrame([new_data])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.success("✅ Pangkalan berhasil ditambahkan!")
            st.balloons()

# ═══════════════════════════════════════════════════════════════════════════════
# 4. ANALISIS JARAK (TABEL)
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "📊 Analisis Jarak":
    st.title("📊 Analisis Jarak Antar Pangkalan")

    valid = df.dropna(subset=["Latitude", "Longitude"])
    if valid.empty:
        st.warning("Tidak ada data koordinat.")
        st.stop()

    radius_filter = st.slider("Radius filter (m)", 50, 1000, int(RADIUS_M), 10)
    selected_name = st.selectbox("Pilih Pangkalan", valid["NamaPangkalan"].tolist())

    run_analisis = st.button("🔍 Hitung Jarak", type="primary")

    if run_analisis:
        sel = valid[valid["NamaPangkalan"] == selected_name].iloc[0]
        rows = []
        for _, row in valid.iterrows():
            d = haversine_m(
                sel["Latitude"], sel["Longitude"], row["Latitude"], row["Longitude"]
            )
            if row["IDRegistrasi"] != sel["IDRegistrasi"]:
                rows.append(
                    {
                        "IDRegistrasi": row["IDRegistrasi"],
                        "NamaPangkalan": row["NamaPangkalan"],
                        "Kota": row["Kota"],
                        "Jarak (m)": round(d, 1),
                        "Status Radius": (
                            "⚠️ KONFLIK" if d < radius_filter else "✅ Aman"
                        ),
                    }
                )
        dist_df = pd.DataFrame(rows).sort_values("Jarak (m)")

        st.subheader(f"Jarak dari: **{selected_name}**")
        col1, col2 = st.columns(2)
        col1.metric(
            "Konflik (< radius)", len(dist_df[dist_df["Jarak (m)"] < radius_filter])
        )
        col2.metric("Pangkalan Diperiksa", len(dist_df))

        conflict_df = dist_df[dist_df["Jarak (m)"] < radius_filter]
        if not conflict_df.empty:
            st.error(f"Pangkalan dalam radius {radius_filter} m:")
            st.dataframe(conflict_df, use_container_width=True)

        with st.expander("📋 Semua jarak (terdekat dahulu)"):
            st.dataframe(dist_df.head(50), use_container_width=True)

    # Summary table all conflicts — hanya setelah klik tombol terpisah
    st.markdown("---")
    st.subheader("📑 Ringkasan Semua Konflik")
    run_summary = st.button("📑 Hitung Semua Konflik", type="secondary")
    if run_summary:
        with st.spinner("Menghitung konflik seluruh data..."):
            all_c = find_conflicts(df, radius_filter)
        summary = []
        for idx, neighbours in all_c.items():
            row = df.loc[idx]
            for n_idx, n_dist in neighbours:
                n_row = df.loc[n_idx]
                summary.append(
                    {
                        "Pangkalan A": row["NamaPangkalan"],
                        "ID A": row["IDRegistrasi"],
                        "Pangkalan B": n_row["NamaPangkalan"],
                        "ID B": n_row["IDRegistrasi"],
                        "Jarak (m)": n_dist,
                    }
                )
        if summary:
            sum_df = pd.DataFrame(summary).drop_duplicates().sort_values("Jarak (m)")
            st.dataframe(sum_df, use_container_width=True, height=350)
        else:
            st.success(f"Tidak ada konflik dalam radius {radius_filter} m!")

# ═══════════════════════════════════════════════════════════════════════════════
# 5. PETA KONFLIK
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "🗺️ Peta Konflik":
    st.title("🗺️ Peta Visual Konflik Radius")

    valid = df.dropna(subset=["Latitude", "Longitude"])
    if valid.empty:
        st.warning("Tidak ada data koordinat.")
        st.stop()

    # ── Filter wilayah bertingkat (wajib diisi sebelum render peta) ──────────
    st.subheader("🔍 Filter Wilayah")
    st.info("Pilih wilayah terlebih dahulu untuk mempercepat rendering peta.")

    fw1, fw2, fw3, fw4 = st.columns(4)
    prov_opts = ["(Semua)"] + sorted(valid["Provinsi"].dropna().unique().tolist())
    prov_sel = fw1.selectbox("Provinsi", prov_opts, key="map_prov")

    kota_src = valid if prov_sel == "(Semua)" else valid[valid["Provinsi"] == prov_sel]
    kota_opts = ["(Semua)"] + sorted(kota_src["Kota"].dropna().unique().tolist())
    kota_sel = fw2.selectbox("Kota / Kabupaten", kota_opts, key="map_kota")

    kec_src = (
        kota_src if kota_sel == "(Semua)" else kota_src[kota_src["Kota"] == kota_sel]
    )
    kec_opts = ["(Semua)"] + sorted(kec_src["Kecamatan"].dropna().unique().tolist())
    kec_sel = fw3.selectbox("Kecamatan", kec_opts, key="map_kec")

    kel_src = (
        kec_src if kec_sel == "(Semua)" else kec_src[kec_src["Kecamatan"] == kec_sel]
    )
    kel_opts = ["(Semua)"] + sorted(kel_src["Kelurahan"].dropna().unique().tolist())
    kel_sel = fw4.selectbox("Kelurahan", kel_opts, key="map_kel")

    # Terapkan filter ke data valid
    filtered_valid = valid.copy()
    if prov_sel != "(Semua)":
        filtered_valid = filtered_valid[filtered_valid["Provinsi"] == prov_sel]
    if kota_sel != "(Semua)":
        filtered_valid = filtered_valid[filtered_valid["Kota"] == kota_sel]
    if kec_sel != "(Semua)":
        filtered_valid = filtered_valid[filtered_valid["Kecamatan"] == kec_sel]
    if kel_sel != "(Semua)":
        filtered_valid = filtered_valid[filtered_valid["Kelurahan"] == kel_sel]

    st.caption(
        f"Data terpilih: **{len(filtered_valid)}** pangkalan dari total {len(valid)}"
    )

    # ── Opsi & Tombol ────────────────────────────────────────────────────────
    st.markdown("---")
    radius_m = st.slider("Radius (m)", 50, 500, int(RADIUS_M), 10, key="map_radius")
    show_radius = st.checkbox("Tampilkan lingkaran radius", value=True)
    show_lines = st.checkbox("Tampilkan garis konflik", value=True)
    filter_name = st.selectbox(
        "Fokus ke pangkalan (opsional)",
        ["(Semua)"] + filtered_valid["NamaPangkalan"].tolist(),
        key="map_focus",
    )

    render_btn = st.button("🗺️ Tampilkan Peta", type="primary")

    if not render_btn and "map_rendered" not in st.session_state:
        st.info("👆 Atur filter wilayah di atas lalu klik **Tampilkan Peta**.")
        st.stop()

    if render_btn:
        st.session_state["map_rendered"] = True

    # ── Hitung konflik hanya untuk subset terpilih ───────────────────────────
    with st.spinner("Menghitung konflik dan merender peta..."):
        conflicts = find_conflicts(filtered_valid.reset_index(drop=True), radius_m)

    center_lat = filtered_valid["Latitude"].mean()
    center_lon = filtered_valid["Longitude"].mean()
    if filter_name != "(Semua)":
        frow = filtered_valid[filtered_valid["NamaPangkalan"] == filter_name].iloc[0]
        center_lat, center_lon = frow["Latitude"], frow["Longitude"]

    m = folium.Map(
        location=[center_lat, center_lon], zoom_start=14, tiles="CartoDB positron"
    )

    # Conflict IDs berdasarkan posisi integer di filtered_valid
    conflict_pos = set(conflicts.keys())
    fv_reset = filtered_valid.reset_index(drop=True)

    if filter_name != "(Semua)":
        focus_pos = fv_reset[fv_reset["NamaPangkalan"] == filter_name].index[0]
        neighbour_pos = {n[0] for n in conflicts.get(focus_pos, [])}
        show_pos = {focus_pos} | neighbour_pos
        draw_df = fv_reset[fv_reset.index.isin(show_pos)]
    else:
        draw_df = fv_reset

    for pos, row in draw_df.iterrows():
        is_conflict = pos in conflict_pos
        color = "red" if is_conflict else "green"
        tooltip = (
            f"<b>{row['NamaPangkalan']}</b><br>"
            f"ID: {row['IDRegistrasi']}<br>"
            f"Kota: {row['Kota']}<br>"
            f"{'⚠️ Ada konflik' if is_conflict else '✅ Aman'}"
        )
        folium.CircleMarker(
            [row["Latitude"], row["Longitude"]],
            radius=8,
            color=color,
            fill=True,
            fill_opacity=0.8,
            tooltip=tooltip,
        ).add_to(m)
        if show_radius:
            folium.Circle(
                [row["Latitude"], row["Longitude"]],
                radius=radius_m,
                color=color,
                fill=True,
                fill_opacity=0.05,
                weight=1,
            ).add_to(m)

    if show_lines:
        drawn = set()
        for pos, neighbours in conflicts.items():
            if pos not in draw_df.index:
                continue
            r1 = fv_reset.loc[pos]
            for n_pos, dist in neighbours:
                key = tuple(sorted([pos, n_pos]))
                if key in drawn or n_pos not in draw_df.index:
                    continue
                r2 = fv_reset.loc[n_pos]
                folium.PolyLine(
                    [
                        [r1["Latitude"], r1["Longitude"]],
                        [r2["Latitude"], r2["Longitude"]],
                    ],
                    color="orange",
                    weight=2,
                    opacity=0.7,
                    tooltip=f"Jarak: {dist} m",
                ).add_to(m)
                drawn.add(key)

    # Legend
    legend = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;background:white;
                padding:10px;border-radius:8px;box-shadow:2px 2px 6px rgba(0,0,0,.3);font-size:13px">
        <b>Legend</b><br>
        🔴 Pangkalan konflik<br>
        🟢 Pangkalan aman<br>
        🟠 Garis konflik
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))

    st_folium(m, width=None, height=600)
    st.caption(
        f"🔴 {len(conflict_pos)} konflik  |  🟢 {len(filtered_valid)-len(conflict_pos)} aman  |  Radius: {radius_m} m  |  Area: {prov_sel} › {kota_sel} › {kec_sel} › {kel_sel}"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# 6. REKOMENDASI LOKASI BARU
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "✅ Rekomendasi Lokasi":
    st.title("✅ Rekomendasi Lokasi Pangkalan Baru")
    st.info(
        "Sistem mencari titik-titik yang **bebas konflik** berdasarkan grid di sekitar pangkalan yang sudah ada."
    )

    valid = df.dropna(subset=["Latitude", "Longitude"])
    if valid.empty:
        st.warning("Tidak ada data koordinat.")
        st.stop()

    # Filter wilayah untuk mempersempit area grid
    rl1, r12 = st.columns(2)
    prov_opts_r = ["(Semua)"] + sorted(valid["Provinsi"].dropna().unique().tolist())
    prov_sel_r = rl1.selectbox("Filter Provinsi", prov_opts_r, key="rek_prov")
    kota_src_r = (
        valid if prov_sel_r == "(Semua)" else valid[valid["Provinsi"] == prov_sel_r]
    )
    kota_opts_r = ["(Semua)"] + sorted(kota_src_r["Kota"].dropna().unique().tolist())
    kota_sel_r = rl2.selectbox("Filter Kota", kota_opts_r, key="rek_kota")

    area_df = (
        kota_src_r
        if kota_sel_r == "(Semua)"
        else kota_src_r[kota_src_r["Kota"] == kota_sel_r]
    )
    st.caption(f"Mencari di area: **{len(area_df)}** pangkalan terpilih")

    grid_spacing = st.slider("Jarak antar grid (m)", 100, 500, 150, 50)
    bbox_pad = st.slider("Padding area (derajat)", 0.005, 0.05, 0.01, 0.005)

    run_rek = st.button("✅ Cari Rekomendasi Lokasi", type="primary")

    if run_rek:
        with st.spinner("Menghitung slot bebas konflik..."):
            slots = suggest_free_slots(area_df, grid_spacing, bbox_pad)
        st.session_state["rek_slots"] = slots
        st.session_state["rek_valid_snapshot"] = valid.copy()

    if "rek_slots" not in st.session_state:
        st.info("👆 Atur filter dan parameter, lalu klik **Cari Rekomendasi Lokasi**.")
        st.stop()

    slots = st.session_state["rek_slots"]
    valid = st.session_state["rek_valid_snapshot"]

    st.success(f"Ditemukan **{len(slots)}** titik potensial bebas konflik.")

    tab1, tab2 = st.tabs(["📋 Tabel", "🗺️ Peta"])

    with tab1:
        slots_df = pd.DataFrame(slots, columns=["Latitude", "Longitude"])
        slots_df.index += 1
        st.dataframe(slots_df, use_container_width=True, height=400)

        buf = io.BytesIO()
        slots_df.to_excel(buf, index=False)
        st.download_button(
            "📥 Unduh Rekomendasi (.xlsx)",
            buf.getvalue(),
            "rekomendasi_lokasi.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with tab2:
        center_lat = valid["Latitude"].mean()
        center_lon = valid["Longitude"].mean()
        m2 = folium.Map(
            location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron"
        )

        for _, row in valid.iterrows():
            folium.CircleMarker(
                [row["Latitude"], row["Longitude"]],
                radius=6,
                color="blue",
                fill=True,
                fill_opacity=0.6,
                tooltip=row["NamaPangkalan"],
            ).add_to(m2)
        for lat, lon in slots[:200]:
            folium.CircleMarker(
                [lat, lon],
                radius=5,
                color="lime",
                fill=True,
                fill_opacity=0.9,
                tooltip=f"Rekomendasi: {lat},{lon}",
            ).add_to(m2)

        leg2 = """<div style="position:fixed;bottom:30px;left:30px;z-index:9999;background:white;
                  padding:10px;border-radius:8px;box-shadow:2px 2px 6px rgba(0,0,0,.3);font-size:13px">
            🔵 Pangkalan ada &nbsp; 🟢 Slot rekomendasi</div>"""
        m2.get_root().html.add_child(folium.Element(leg2))
        st_folium(m2, width=None, height=580)


elif menu == "🔄 Rekomendasi Geser":
    st.title("🔄 Rekomendasi Pergeseran Pangkalan")

    valid = df.dropna(subset=["Latitude", "Longitude"])
    if valid.empty:
        st.warning("Tidak ada data koordinat.")
        st.stop()

    sel_name = st.selectbox(
        "Pilih pangkalan yang ingin digeser", valid["NamaPangkalan"].tolist()
    )
    sel_row = valid[valid["NamaPangkalan"] == sel_name].iloc[0]

    # ── Otomatis tampil koordinat pangkalan terpilih ──
    st.markdown(
        f"""
    **📍 Koordinat Saat Ini:**  
    - Latitude : `{sel_row['Latitude']}`  
    - Longitude: `{sel_row['Longitude']}`  
    - Alamat   : {sel_row.get('Alamat','-')}
    """
    )

    st.markdown("---")
    st.info(
        "👇 Klik titik mana saja di peta untuk mengecek apakah lokasi tersebut bisa dijadikan titik geser."
    )

    # ── Slider kontrol jumlah titik ──────────────────────────────────────────
    col_s1, col_s2 = st.columns(2)
    max_tampil = col_s1.slider(
        "🔢 Jumlah pangkalan terdekat ditampilkan di peta",
        min_value=10,
        max_value=300,
        value=50,
        step=10,
        help="Lebih sedikit = lebih cepat. Lebih banyak = area lebih luas.",
    )
    show_circle = col_s2.checkbox("Tampilkan lingkaran radius 100m", value=True)

    # ── Hitung jarak semua pangkalan, urutkan, ambil sejumlah slider ─────────
    nearby = []
    for _, row in valid.iterrows():
        if row["IDRegistrasi"] == sel_row["IDRegistrasi"]:
            continue
        d = haversine_m(
            sel_row["Latitude"], sel_row["Longitude"], row["Latitude"], row["Longitude"]
        )
        nearby.append((row, d))

    nearby.sort(key=lambda x: x[1])
    nearby = nearby[:max_tampil]

    jarak_terjauh = nearby[-1][1] if nearby else 0
    st.caption(
        f"Menampilkan **{len(nearby)}** pangkalan terdekat "
        f"— terjauh **{jarak_terjauh:.0f} m** dari {sel_name}"
    )

    # ── Render peta ──────────────────────────────────────────────────────────
    m = folium.Map(
        location=[sel_row["Latitude"], sel_row["Longitude"]],
        zoom_start=16,
        tiles="CartoDB positron",
    )

    # Pangkalan yang dipilih (biru)
    folium.Marker(
        [sel_row["Latitude"], sel_row["Longitude"]],
        tooltip=f"📍 Posisi sekarang: {sel_name}",
        icon=folium.Icon(color="blue", icon="home"),
    ).add_to(m)
    if show_circle:
        folium.Circle(
            [sel_row["Latitude"], sel_row["Longitude"]],
            radius=RADIUS_M,
            color="blue",
            fill=True,
            fill_opacity=0.05,
            weight=1,
        ).add_to(m)

    # Pangkalan sekitar (merah) sejumlah pilihan slider
    for row, d in nearby:
        popup_html = f"""
        <div style="font-size:13px;min-width:180px">
            <b>🏪 {row['NamaPangkalan']}</b><br>
            📋 ID: {row['IDRegistrasi']}<br>
            📍 {row.get('Alamat','-')}<br>
            🏙️ {row.get('Kecamatan','-')}, {row.get('Kota','-')}<br>
            📏 Jarak: <b>{d:.0f} m</b> dari {sel_name}
        </div>
        """
        folium.CircleMarker(
            [row["Latitude"], row["Longitude"]],
            radius=7,
            color="red",
            fill=True,
            fill_opacity=0.7,
            tooltip=f"🔴 {row['NamaPangkalan']} | {d:.0f}m",
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(m)
        if show_circle:
            folium.Circle(
                [row["Latitude"], row["Longitude"]],
                radius=RADIUS_M,
                color="red",
                fill=True,
                fill_opacity=0.05,
                weight=1,
            ).add_to(m)

    # Ambil hasil klik dari peta
    map_result = st_folium(m, width=None, height=500, key="geser_map")

    # ── Proses titik yang diklik ──────────────────────────────────────────────
    clicked = None
    if map_result and map_result.get("last_clicked"):
        clicked = map_result["last_clicked"]

    tree_df = valid[valid["IDRegistrasi"] != sel_row["IDRegistrasi"]].copy()
    tree_df = tree_df.dropna(subset=["Latitude", "Longitude"]).reset_index(drop=True)

    if not tree_df.empty:
        coords_rad = np.radians(tree_df[["Latitude", "Longitude"]].values)
        kdtree = cKDTree(coords_rad)
    else:
        kdtree = None

    if clicked:
        clat = clicked["lat"]
        clon = clicked["lng"]

        st.markdown(f"### 🖱️ Titik yang diklik: `{clat:.6f}, {clon:.6f}`")

        # Cek konflik pakai KDTree — jauh lebih cepat!
        blockers = []
        if kdtree is not None:
            pt_rad = np.radians([clat, clon])
            r_rad = RADIUS_M / 6_371_000
            hits = kdtree.query_ball_point(pt_rad, r_rad)
            for i in hits:
                row = tree_df.iloc[i]
                d = haversine_m(clat, clon, row["Latitude"], row["Longitude"])
                if d < RADIUS_M:
                    blockers.append(
                        {
                            "NamaPangkalan": row["NamaPangkalan"],
                            "IDRegistrasi": row["IDRegistrasi"],
                            "Jarak (m)": round(d, 1),
                        }
                    )

        if not blockers:
            dist_from_now = haversine_m(
                sel_row["Latitude"], sel_row["Longitude"], clat, clon
            )
            st.success(
                f"✅ **Lokasi ini AMAN!** Tidak ada pangkalan dalam radius {RADIUS_M:.0f} m.\n\n"
                f"Jarak pergeseran dari posisi sekarang: **{dist_from_now:.1f} m**"
            )
        else:
            st.error(
                f"❌ **Lokasi ini TIDAK BISA digunakan!** "
                f"Ada **{len(blockers)}** pangkalan dalam radius {RADIUS_M:.0f} m:"
            )
            st.dataframe(pd.DataFrame(blockers), use_container_width=True)
    else:
        st.caption("Belum ada titik yang diklik.")

        # ── Tabel pangkalan terdekat + highlight ─────────────────────────────────
    st.markdown("---")
    st.subheader("📋 Daftar Pangkalan Terdekat")
    st.info(
        "👆 Klik nama pangkalan di tabel → peta akan zoom & tandai lokasi tersebut."
    )

    # Buat dataframe nearby untuk tabel
    nearby_data = []
    for row, d in nearby:
        nearby_data.append(
            {
                "NamaPangkalan": row["NamaPangkalan"],
                "IDRegistrasi": row["IDRegistrasi"],
                "Kecamatan": row.get("Kecamatan", "-"),
                "Kota": row.get("Kota", "-"),
                "Jarak (m)": round(d, 1),
                "Latitude": row["Latitude"],
                "Longitude": row["Longitude"],
            }
        )
    nearby_tbl = pd.DataFrame(nearby_data)

    # Pilih pangkalan dari tabel via selectbox
    pilih_dari_tabel = st.selectbox(
        "🔎 Pilih pangkalan dari daftar untuk highlight di peta:",
        ["(Tidak ada)"] + nearby_tbl["NamaPangkalan"].tolist(),
        key="tbl_highlight",
    )

    # Tampilkan tabel dengan warna highlight baris terpilih
    def warnai_baris(row):
        if row["NamaPangkalan"] == pilih_dari_tabel:
            return ["background-color: #fff3cd; font-weight: bold"] * len(row)
        elif row["Jarak (m)"] < RADIUS_M:
            return ["background-color: #ffd6d6"] * len(row)
        else:
            return [""] * len(row)

    st.dataframe(
        nearby_tbl[
            ["NamaPangkalan", "IDRegistrasi", "Kecamatan", "Kota", "Jarak (m)"]
        ].style.apply(warnai_baris, axis=1),
        use_container_width=True,
        height=300,
    )

    # Jika ada yang dipilih dari tabel → tampilkan peta mini fokus ke titik itu
    if pilih_dari_tabel != "(Tidak ada)":
        sel_tbl = nearby_tbl[nearby_tbl["NamaPangkalan"] == pilih_dari_tabel].iloc[0]
        jarak_tbl = sel_tbl["Jarak (m)"]

        # Cek apakah titik itu konflik dengan pangkalan lain
        blockers_tbl = []
        if kdtree is not None:
            pt_rad2 = np.radians([sel_tbl["Latitude"], sel_tbl["Longitude"]])
            r_rad2 = RADIUS_M / 6_371_000
            hits2 = kdtree.query_ball_point(pt_rad2, r_rad2)
            for i in hits2:
                rr = tree_df.iloc[i]
                d2 = haversine_m(
                    sel_tbl["Latitude"],
                    sel_tbl["Longitude"],
                    rr["Latitude"],
                    rr["Longitude"],
                )
                if d2 < RADIUS_M and rr["IDRegistrasi"] != sel_tbl["IDRegistrasi"]:
                    blockers_tbl.append(rr["NamaPangkalan"])

        # Peta mini fokus ke pangkalan terpilih dari tabel
        m_focus = folium.Map(
            location=[sel_tbl["Latitude"], sel_tbl["Longitude"]],
            zoom_start=17,
            tiles="CartoDB positron",
        )
        # Titik pangkalan asal (biru)
        folium.Marker(
            [sel_row["Latitude"], sel_row["Longitude"]],
            tooltip=f"📍 Asal: {sel_name}",
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(m_focus)
        # Titik pangkalan terpilih dari tabel (kuning/oranye)
        folium.Marker(
            [sel_tbl["Latitude"], sel_tbl["Longitude"]],
            tooltip=f"🎯 {sel_tbl['NamaPangkalan']} | {jarak_tbl:.0f}m",
            icon=folium.Icon(color="orange", icon="star"),
        ).add_to(m_focus)
        folium.Circle(
            [sel_tbl["Latitude"], sel_tbl["Longitude"]],
            radius=RADIUS_M,
            color="orange",
            fill=True,
            fill_opacity=0.1,
            weight=2,
        ).add_to(m_focus)
        # Garis penghubung asal → terpilih
        folium.PolyLine(
            [
                [sel_row["Latitude"], sel_row["Longitude"]],
                [sel_tbl["Latitude"], sel_tbl["Longitude"]],
            ],
            color="orange",
            weight=2,
            dash_array="6",
            tooltip=f"Jarak: {jarak_tbl:.0f} m",
        ).add_to(m_focus)

        if blockers_tbl:
            st.warning(
                f"⚠️ **{sel_tbl['NamaPangkalan']}** berdekatan dengan: "
                f"{', '.join(blockers_tbl)}"
            )
        else:
            st.success(
                f"✅ **{sel_tbl['NamaPangkalan']}** aman, tidak ada pangkalan "
                f"dalam radius {RADIUS_M:.0f}m di sekitarnya."
            )

        st_folium(m_focus, width=None, height=400, key="focus_map")
# ═══════════════════════════════════════════════════════════════════════════════
# 8. IMPORT / EXPORT
# ═══════════════════════════════════════════════════════════════════════════════
elif menu == "📥 Import / Export":
    st.title("📥 Import & Export Data")

    tab_imp, tab_exp = st.tabs(["📤 Import", "📥 Export"])

    with tab_imp:
        st.subheader("Import dari Excel (.xlsx)")
        uploaded = st.file_uploader("Upload file Excel", type=["xlsx", "xls"])
        mode = st.radio(
            "Mode import", ["Tambah ke data yang ada", "Ganti semua data (overwrite)"]
        )
        if uploaded and st.button("🚀 Proses Import"):
            imported, err = import_from_excel(uploaded)
            if err:
                st.error(f"Error: {err}")
            else:
                if mode == "Ganti semua data (overwrite)":
                    save_data(imported)
                    st.success(
                        f"✅ Data diganti dengan **{len(imported)}** baris baru."
                    )
                else:
                    combined = pd.concat(
                        [df, imported], ignore_index=True
                    ).drop_duplicates(subset=["IDRegistrasi"], keep="last")
                    save_data(combined)
                    st.success(
                        f"✅ Ditambahkan. Total sekarang: **{len(combined)}** pangkalan."
                    )
                st.rerun()

    with tab_exp:
        st.subheader("Export Data")
        if df.empty:
            st.warning("Tidak ada data.")
        else:
            c1, c2 = st.columns(2)
            buf_xlsx = io.BytesIO()
            df.to_excel(buf_xlsx, index=False)
            c1.download_button(
                "📊 Export Excel (.xlsx)",
                buf_xlsx.getvalue(),
                f"pangkalan_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            buf_csv = df.to_csv(index=False).encode("utf-8")
            c2.download_button(
                "📄 Export CSV (.csv)",
                buf_csv,
                f"pangkalan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
            )

            st.markdown("---")
            st.subheader("📑 Export Laporan Konflik")
            gen_conf = st.button("⚙️ Generate Laporan Konflik", type="secondary")
            if gen_conf:
                with st.spinner("Menghitung konflik seluruh data..."):
                    all_c = find_conflicts(df)
                if all_c:
                    rows = []
                    for idx, neighbours in all_c.items():
                        r = df.loc[idx]
                        for n_idx, d in neighbours:
                            n = df.loc[n_idx]
                            rows.append(
                                {
                                    "Pangkalan A": r["NamaPangkalan"],
                                    "ID A": r["IDRegistrasi"],
                                    "Pangkalan B": n["NamaPangkalan"],
                                    "ID B": n["IDRegistrasi"],
                                    "Jarak (m)": d,
                                }
                            )
                    conf_df = pd.DataFrame(rows).drop_duplicates()
                    buf_conf = io.BytesIO()
                    conf_df.to_excel(buf_conf, index=False)
                    st.success(f"Ditemukan {len(conf_df)} pasang konflik.")
                    st.download_button(
                        "⚠️ Export Laporan Konflik (.xlsx)",
                        buf_conf.getvalue(),
                        "konflik_pangkalan.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                else:
                    st.success("Tidak ada konflik saat ini.")

        st.markdown("---")
        st.subheader("🗑️ Reset Database")
        if st.button("⚠️ Hapus Semua Data", type="secondary"):
            if st.session_state.get("confirm_reset"):
                save_data(pd.DataFrame(columns=COLUMNS))
                st.session_state["confirm_reset"] = False
                st.success("Database dikosongkan.")
                st.rerun()
            else:
                st.session_state["confirm_reset"] = True
                st.warning("Klik sekali lagi untuk konfirmasi penghapusan semua data.")
