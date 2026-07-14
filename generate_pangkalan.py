import random
import pandas as pd

# 1. Variasi Nama Agen (PT) untuk diacak
nama_agen_list = [
    "PT. RESTU JAYA",
    "PT. MEDAN GAS UTAMA",
    "PT. ENERGI SUMATERA JAYA",
    "PT. PATRA NIAGA MEDAN",
    "PT. BERKAH LPG SEJAHTERA",
    "PT. INTI GAS NUSANTARA",
]

first_names = [
    "Hesti",
    "Agus",
    "Ovi",
    "Ola",
    "Budi",
    "Siti",
    "Andi",
    "Rizky",
    "Mega",
    "Rina",
    "Fauzi",
    "Lestari",
    "Setiawan",
    "Putri",
    "Pratama",
]
last_names = [
    "Wahyuni",
    "Priasa",
    "Ariyani",
    "Shinellah",
    "Santoso",
    "Rahayu",
    "Wijaya",
    "Utami",
    "Nose",
    "Ahmad",
    "Saputra",
    "Dewi",
    "Fitriani",
]
pangkalan_suffixes = ["GAS", "LPG", "ENERGY", "JAYA", "MAJU"]
kecamatans = [
    "MEDAN TIMUR",
    "MEDAN PETISAH",
    "MEDAN PERJUANGAN",
    "MEDAN BARAT",
    "MEDAN KOTA",
]
kelurahans = [
    "GAHARU",
    "PULO BRAYAN DARAT II",
    "SEI PUTIH BARAT",
    "SIDORAME BARAT II",
    "GLUGUR KOTA",
]

data = []

print("Sedang membuat 1.000 data dengan Agen & ID Registrasi acak...")

for i in range(1000):
    fn = random.choice(first_names)
    ln = random.choice(last_names)
    nama_pemilik = f"{fn} {ln}"

    if random.random() > 0.2:
        nama_pangkalan = f"{ln.upper()} {random.choice(pangkalan_suffixes)}"
    else:
        nama_pangkalan = f"SPBU 142011{random.randint(100, 999)}"

    email = f"{fn.lower()}{ln.lower()}{random.randint(10,999)}@gmail.com"
    hp = f"812{random.randint(10000000, 99999999)}"
    ktp = f"1271{random.randint(100000000000, 999999999999)}"
    nib = (
        f"1207{random.randint(10000000, 99999999)}0000"
        if random.random() > 0.15
        else ""
    )

    # 2. Pengacakan IDRegistrasi (mengikuti pola digit data asli)
    id_registrasi = float(
        f"1.2023{random.randint(6,7)}{random.randint(10000000, 99999999)}"
    )

    row = {
        "SoldTo": random.choice([793600, 793601, 793602, 793603]),
        "NamaAgen": random.choice(nama_agen_list),  # Mengacak nama PT/Agen
        "Wilayah": "KOTA MEDAN",
        "TipePangkalan": "Regular",
        "IDRegistrasi": id_registrasi,  # Mengacak ID Registrasi
        "NamaPangkalan": nama_pangkalan,
        "EmailPangkalan": email,
        "NoHPPemilik": hp,
        "NoKTPPemilik": ktp,
        "NamaPemilik": nama_pemilik,
        "NomorNIB": nib,
        "QtyKontrak": random.choice([800, 1120, 1650, 1000]),
        "Catatan": "11 OKTOBER 2019" if random.random() > 0.8 else "",
        "TipePembayaran": "Cashless",
        "NoRekening": 1.06001e12,
        "NamaBank": "Bank Mandiri",
        "NamaAkunBank": nama_pemilik.upper(),
        "TanggalDiapproveSAM": "01 Jan 0001",
        "Provinsi": "SUMATERA UTARA",
        "Kota": "KOTA MEDAN",
        "Kecamatan": random.choice(kecamatans),
        "Kelurahan": random.choice(kelurahans),
        "RT": 111,
        "RW": 111,
        "KodePos": random.choice([20114, 20235, 20236]),
        "Alamat": f"Jalan {random.choice(last_names)} No {random.randint(1, 200)}",
        "IntegrasiMAP": "Ya",
        "MID": f"LPG_{random.randint(210000, 229999)}",
        "Latitude": round(random.uniform(3.58, 3.63), 6),
        "Longitude": round(random.uniform(98.66, 98.69), 6),
        "StatusPembaharuan": "Active Diperbaharui",
    }
    data.append(row)

# 3. Simpan langsung ke CSV lokal
df = pd.DataFrame(data)
df.to_csv("pangkalan_db.csv", index=False)

print("Selesai! File 'pangkalan_db.csv' dengan data variatif berhasil diperbarui.")
