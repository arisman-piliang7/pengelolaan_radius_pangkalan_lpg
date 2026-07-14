# DDMS — Sistem Manajemen Pangkalan LPG

Aplikasi berbasis **Streamlit** untuk pengelolaan data pangkalan LPG,
analisis konflik radius, dan rekomendasi lokasi.

---

## ⚡ Cara Menjalankan

### 1. Install dependensi
```bash
pip install -r requirements.txt
```

### 2. Jalankan aplikasi
```bash
streamlit run app.py
```

Aplikasi akan terbuka otomatis di browser: `http://localhost:8501`

---

## 📁 Import Data Awal

1. Buka menu **📥 Import / Export**
2. Upload file `sample_data.xlsx` (disertakan)
3. Pilih **"Ganti semua data"** → klik **Proses Import**

---

## 🧭 Fitur-Fitur

| Menu | Fungsi |
|------|--------|
| 🏠 Dashboard | Ringkasan & statistik pangkalan |
| 📋 Master Data | CRUD + filter + search |
| ➕ Tambah Pangkalan | Cek radius 100 m otomatis sebelum simpan |
| 📊 Analisis Jarak | Tabel jarak & konflik per pangkalan |
| 🗺️ Peta Konflik | Visualisasi interaktif lingkaran & garis konflik |
| ✅ Rekomendasi Lokasi | Grid slot bebas konflik (tabel + peta) |
| 🔄 Rekomendasi Geser | Analisis pergeseran + alternatif titik |
| 📥 Import / Export | Import Excel, export data & laporan konflik |

---

## 🗄️ Penyimpanan

Data disimpan di file `pangkalan_db.csv` di folder yang sama dengan `app.py`.  
Untuk backup, cukup copy file tersebut.

---

## 📐 Rumus Jarak

Menggunakan **Haversine formula** untuk akurasi jarak di permukaan bumi.  
Radius default konflik: **100 meter** (dapat diubah di slider).
