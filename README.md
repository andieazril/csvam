# CSVAM: Capacity-Sensitive Vogel's Approximation Method

Implementasi metode **CSVAM** untuk mencari solusi awal (*Initial Basic Feasible Solution*) pada **masalah transportasi**, sebagai modifikasi dari *Vogel's Approximation Method* (VAM).

Proyek Kelompok 9 — Modifikasi VAM, mata kuliah Riset Operasi, Informatika ITS.

## Anggota Kelompok

| Nama | NRP |
|---|---|
| Andie Azril Alfrianto | 5025241054 |
| Rendy Tanuwijaya | 5025241099 |
| Joaquin Fairuz Nawfal Ismono | 5025241106 |
| Shifa Alya Dewi | 5025241176 |

## Latar Belakang

VAM klasik menghitung penalti dari selisih dua biaya terkecil, tanpa memperhitungkan **kapasitas** sel alternatif. Akibatnya, penalti VAM bisa tidak mencerminkan kenaikan biaya yang sebenarnya.

CSVAM memperbaikinya dengan tiga ide:

1. **Penalti berbasis kapasitas (Keep–Lose)**: penalti dihitung dari selisih total biaya saat sel termurah dipakai (*Keep*) dan saat tidak dipakai (*Lose*), dibagi jumlah unit yang bisa dialokasikan (*q*).
2. **Total Opportunity Cost (TOC)**: penalti dihitung dari matriks TOC yang menggabungkan sudut pandang baris dan kolom, dan **dihitung ulang setiap iterasi**.
3. **Skor sel**: alokasi dilakukan ke sel dengan skor terbesar, yaitu penalti baris + penalti kolom.

## Flowchart Program

Flowchart berikut menggambarkan alur program dari saat pengguna menjalankan `csvam.py`, memilih mode eksekusi, sampai program
menghasilkan biaya transportasi.

![Flowchart CSVAM](image/CSVAMt.png)

## Langkah-Langkah Metode

| Langkah | Keterangan | Rumus |
|---|---|---|
| 1 | Hitung nilai TOC setiap sel | TOC = (c − min baris) + (c − min kolom) |
| 2 | Urutkan nilai TOC pada setiap baris dan kolom | — |
| 3 | Hitung nilai Keep | K = Σ TOC × x |
| 4 | Hitung nilai Lose (sel termurah diabaikan) | L = Σ TOC × x |
| 5 | Hitung nilai q | q = min(sᵢ, dⱼ) |
| 6 | Hitung penalti setiap baris dan kolom | Penalti = (Lose − Keep) / q |
| 7 | Hitung skor sel termurah | Skor = Penalti baris + Penalti kolom |
| 8 | Alokasikan ke sel dengan skor terbesar | Alokasi = min(sᵢ, dⱼ) |
| 9 | Perbarui supply dan demand, coret baris/kolom yang habis | — |
| 10 | Hitung ulang TOC dan ulangi Langkah 2–9; jika tinggal satu baris/kolom, alokasikan langsung | — |
| 11 | Hitung total biaya dengan **biaya asli** | TC = Σ c × x |

## Aturan Tie-Breaking

**1. Perhitungan Lose dan q saat nilai TOC sama**
1. Keep dihitung seperti biasa.
2. Lose mengabaikan hanya satu sel termurah, yaitu sel dengan kapasitas terbesar. Sel termurah lainnya tetap digunakan dan diisi lebih dahulu.
3. q dihitung pada sel yang diabaikan: q = min(sᵢ, dⱼ).

**2. Pemilihan sel untuk alokasi**
1. Pilih sel dengan skor terbesar.
2. Jika skor sama, pilih sel dengan nilai TOC paling kecil.
3. Jika masih sama, pilih sel dengan nilai q terbesar.
4. Jika masih sama, dahulukan sel dari baris daripada kolom, lalu indeks terkecil.

## Hasil Pengujian

Diuji pada **69 dataset** dan dibandingkan dengan nilai optimal (dicek ulang dengan *linear programming*).

| Metode | Optimal | % | Rata-rata gap | Gap maks |
|---|---|---|---|---|
| **CSVAM** | **55** | **79,71%** | **0,42%** | **6,89%** |
| SAM | 48 | 69,57% | 1,79% | 21,53% |
| RBSM | 45 | 65,22% | 2,47% | 24,27% |
| CSM | 43 | 62,32% | 3,79% | 85,71% |
| Fractional VAM | 28 | 40,58% | 3,98% | 35,71% |

CSVAM dibanding metode lain:

| Pembanding | Lebih baik | Sama | Lebih buruk |
|---|---|---|---|
| SAM | 16 | 47 | 4 |
| Fractional VAM | 36 | 29 | 4 |
| RBSM | 24 | 39 | 6 |
| CSM | 25 | 39 | 5 |

> Gap = (TCC − optimal) / optimal × 100%. SAM gagal (batas 20 iterasi) pada 2 dataset. Nilai optimal G6_N04 di file dataset (555) dikoreksi menjadi 1580 sesuai hasil LP.

## Struktur Repository

```
├── csvam.py      # Implementasi CSVAM (step by step & batch)
├── compare.py    # Perbandingan CSVAM dengan SAM, FVAM, RBSM, CSM
├── SAM.c         # Metode pembanding: SAM
├── FVAM.cpp      # Metode pembanding: Fractional VAM
├── RBSM.cpp      # Metode pembanding: RBSM
├── CSM.cpp       # Metode pembanding: CSM
└── dataset.zip   # 69 dataset uji
```

## Format Input

File `.txt` dengan format:

```
m n
c11 c12 ... c1n
...
cm1 cm2 ... cmn
s1 s2 ... sm
d1 d2 ... dn
optimal
```

- `m`, `n`: jumlah sumber (baris) dan tujuan (kolom)
- `cij`: biaya per unit dari sumber i ke tujuan j
- `si`, `dj`: supply dan demand
- `optimal`: nilai optimal (opsional, untuk menghitung gap)

Contoh:

```
3 3
10 5 12
8 23 5
25 6 9
20 30 80
60 20 50
1260
```

Jika total supply ≠ total demand, program otomatis menambahkan baris/kolom dummy berbiaya 0.

## Cara Menjalankan

### Kebutuhan

- Python 3.8+
- `scipy` (opsional, untuk verifikasi nilai optimal dengan LP): `pip install scipy`
- Compiler C/C++ (`gcc`/`g++`), hanya untuk `compare.py`

### CSVAM

```bash
# Satu soal: langsung menampilkan step by step (Langkah 1–11)
python csvam.py soal.txt

# Banyak soal: ringkasan hasil seluruh dataset
python csvam.py dataset.zip

# Banyak soal: step by step untuk setiap soal
python csvam.py dataset.zip --steps
```

Input dapat berupa satu file `.txt`, file `.zip`, atau folder berisi file `.txt`.

### Perbandingan dengan Metode Lain

Kompilasi dulu keempat program pembanding di folder yang sama dengan `compare.py`:

```bash
gcc SAM.c -o sam
g++ FVAM.cpp -o fvam
g++ RBSM.cpp -o rbsm
g++ CSM.cpp -o csm
```

Di Windows, gunakan nama `sam.exe`, `fvam.exe`, `rbsm.exe`, dan `csm.exe`.

Lalu jalankan:

```bash
python compare.py dataset.zip
```

Output berupa tabel TCC per dataset, jumlah optimal setiap metode, rata-rata gap, dan perbandingan CSVAM dengan setiap metode. Hasil juga disimpan ke `hasil_perbandingan.csv`.

## Contoh Output (Soal 3×3)

```
ITERASI 1
Langkah 1: Menghitung nilai Total Opportunity Cost (TOC)
  Rumus : TOC = (c − min baris) + (c − min kolom)
  Min baris : S1 = 5, S2 = 5, S3 = 6
  Min kolom : D1 = 8, D2 = 5, D3 = 5
   (S1, D1) = (10 − 5) + (10 − 8) = 5 + 2 = 7
   ...
Langkah 7: Menghitung skor sel
   (S3, D2) : P(S3) + P(D2) = 35 + 1 = 36
   (S2, D1) : P(S2) + P(D1) = 3 + 33 = 36
Langkah 8: Melakukan alokasi pada sel dengan skor terbesar
   Skor sel terbesar = 36 pada sel (S3, D2)
   Seri dengan sel (S2, D1) → (S3, D2) dipilih (aturan 2.2: nilai TOC lebih kecil)
   ...
Langkah 11: Menghitung total biaya transportasi (memakai biaya asli)
   TC = 10(20) + 8(30) + 25(10) + 6(20) + 9(50)
      = 200 + 240 + 250 + 120 + 450
      = 1260
```

## Catatan

- Metode ini hanya menghasilkan **solusi awal (IBFS)**, tanpa tahap optimasi seperti MODI atau Stepping-Stone.
- Nilai TOC hanya dipakai untuk menentukan urutan alokasi. Total biaya selalu dihitung dengan biaya asli.
