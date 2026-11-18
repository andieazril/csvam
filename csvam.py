import contextlib
import io
import os
import sys
import zipfile

EPS = 1e-9
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def parse_problem(text):
    nums = list(map(float, text.split()))

    m, n = int(nums[0]), int(nums[1])
    pos = 2

    costs = [
        nums[pos + i * n:pos + (i + 1) * n]
        for i in range(m)
    ]
    pos += m * n

    supply = nums[pos:pos + m]
    demand = nums[pos + m:pos + m + n]

    if len(demand) != n:
        raise ValueError(
            "File ended early: expected m*n costs, m supplies and n demands."
        )

    rest = nums[pos + m + n:]
    optimal = rest[0] if rest else None

    return costs, supply, demand, optimal


def balance(costs, supply, demand):
    gap = sum(supply) - sum(demand)

    if gap < -EPS:
        costs.append([0.0] * len(demand))
        supply.append(-gap)
        print(f"Tidak seimbang: ditambahkan sumber dummy dengan supply {-gap:g}")

    elif gap > EPS:
        for row in costs:
            row.append(0.0)
        demand.append(gap)
        print(f"Tidak seimbang: ditambahkan tujuan dummy dengan demand {gap:g}")

    return costs, supply, demand


# Format angka
def fmt(x):
    """20.0 -> '20', 3.3333 -> '3.33'."""
    if abs(x - round(x)) <= 1e-6:
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def sub(k):
    """1 -> '₁'."""
    return str(k).translate(SUB)


# Keep, Lose, q, dan penalti (Langkah 3-6)
def fill(cells, need):
    """Kirim `need` unit lewat sel (label, nilai TOC, kapasitas), termurah dulu.

    Mengembalikan (total, rincian). Rincian berisi
    (biaya, sisa_kebutuhan, kapasitas, diambil) untuk dicetak.
    """
    total = 0.0
    terms = []

    for _, c, k in cells:
        take = min(need, k)
        terms.append((c, need, k, take))
        total += take * c
        need -= take

        if need <= EPS:
            return total, terms

    # Kapasitas tidak cukup: sisa dibebankan ke sel termahal
    if cells:
        c = cells[-1][1]
        terms.append((c, need, None, need))
        total += need * c

    return total, terms


def csvam_penalty(cells, need):
    """
    Aturan tie-breaking 1 (nilai TOC termurah sama):
      1.1 Keep dihitung seperti biasa.
      1.2 Lose mengabaikan HANYA SATU sel termurah, yaitu yang kapasitasnya
          terbesar (jika masih sama, indeks terkecil). Sel termurah lainnya
          tetap dipakai dan diisi lebih dahulu.
      1.3 q dihitung pada sel yang diabaikan: q = min(s_i, d_j).
    """
    order = sorted(range(len(cells)), key=lambda t: cells[t][1])
    srt = [cells[t] for t in order]

    # 1.2 Sel termurah yang diabaikan: kapasitas terbesar
    cmin = srt[0][1]
    cheapest = [t for t in order if abs(cells[t][1] - cmin) <= EPS]
    skip = max(cheapest, key=lambda t: cells[t][2])  # seri -> indeks terkecil
    rest = [cells[t] for t in order if t != skip]

    # 1.3 q pada sel yang diabaikan
    q = min(need, cells[skip][2])

    keep, keep_terms = fill(srt, need)
    lose, lose_terms = fill(rest, need)
    p = (lose - keep) / q if q > EPS else 0.0

    return {
        "p": p, "skip": skip, "keep": keep, "lose": lose, "q": q,
        "order": srt, "keep_terms": keep_terms, "lose_terms": lose_terms,
        "need": need, "cap": cells[skip][2],
    }


def better(a, b):
    """Aturan tie-breaking 2: apakah sel a lebih baik dari sel b?
    key = (skor sel, nilai TOC sel, q)
      2.1 skor sel terbesar
      2.2 jika sama, nilai TOC paling kecil
      2.3 jika sama, q terbesar
      2.4 jika masih sama, kandidat yang lebih dulu menang
          (sel dari baris diperiksa sebelum kolom, indeks kecil lebih dulu)
    """
    if b is None:
        return True

    p1, c1, q1 = a
    p2, c2, q2 = b

    if abs(p1 - p2) > EPS:
        return p1 > p2
    if abs(c1 - c2) > EPS:
        return c1 < c2
    if abs(q1 - q2) > EPS:
        return q1 > q2
    return False


def tie_reason(a, b):
    """Aturan tie-breaking 2 mana yang memutuskan sel a mengalahkan sel b."""
    if abs(a[0] - b[0]) > EPS:
        return None
    if abs(a[1] - b[1]) > EPS:
        return "aturan 2.2: nilai TOC lebih kecil"
    if abs(a[2] - b[2]) > EPS:
        return "aturan 2.3: q lebih besar"
    return "aturan 2.4: baris didahulukan, lalu indeks terkecil"


# Tampilan seperti PPT
def history(vals):
    """[80, 60, 10, 0] -> '80→60→10→0'."""
    return "→".join(fmt(v) for v in vals)


def print_table(costs, X, s_hist, d_hist, info, new_cell=None, show_kl=True):
    m, n = len(costs), len(costs[0])
    head = [""] + [f"D{j + 1}" for j in range(n)] + ["Supply"]
    if show_kl:
        head += ["Keep", "Lose", "q", "Penalti"]

    def cell(i, j):
        txt = fmt(costs[i][j])
        if X[i][j] > EPS:
            mark = "*" if (i, j) == new_cell else ""
            txt += f" [{fmt(X[i][j])}]{mark}"
        return txt

    def extra(name):
        r = info.get(name)
        if not show_kl:
            return []
        if r is None:
            return ["", "", "", ""]
        return [fmt(r["keep"]), fmt(r["lose"]), fmt(r["q"]), fmt(r["p"])]

    rows = [head]
    for i in range(m):
        rows.append(
            [f"S{i + 1}"] + [cell(i, j) for j in range(n)]
            + [history(s_hist[i])] + extra(f"S{i + 1}")
        )

    rows.append(
        ["Demand"] + [history(d_hist[j]) for j in range(n)]
        + [fmt(sum(h[0] for h in s_hist))]
        + ([""] * 4 if show_kl else [])
    )

    if show_kl:
        for label, key in (("Keep", "keep"), ("Lose", "lose"),
                           ("q", "q"), ("Penalti", "p")):
            line = [label]
            for j in range(n):
                r = info.get(f"D{j + 1}")
                line.append(fmt(r[key]) if r else "")
            rows.append(line + [""] * 5)

    widths = [max(len(r[c]) for r in rows) for c in range(len(head))]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    print(sep)
    for k, r in enumerate(rows):
        print("| " + " | ".join(
            r[c].ljust(widths[c]) if c == 0 else r[c].center(widths[c])
            for c in range(len(head))
        ) + " |")
        if k == 0 or k == m or k == m + 1:
            print(sep)
    if show_kl:
        print(sep)

    if new_cell:
        print("  [x] = alokasi, * = alokasi pada iterasi ini, a→b = nilai sebelum→sesudah")


def print_terms(name, letter, idx, terms, total, named=True):
    pad = " " * (len(name) + 3)
    for k, (c, need, cap, take) in enumerate(terms):
        lead = f"   {name} : " if k == 0 and named else "   " + pad
        if cap is None:
            print(f"{lead}{fmt(c)} × sisa {fmt(take)} = {fmt(c * take)}"
                  "  (kapasitas tidak cukup)")
        else:
            print(f"{lead}{fmt(c)} × min({fmt(need)}, {fmt(cap)}) = "
                  f"{fmt(c)} × {fmt(take)} = {fmt(c * take)}")

    parts = [fmt(c * take) for c, _, _, take in terms]
    rhs = " + ".join(parts) + f" = {fmt(total)}" if len(parts) > 1 else fmt(total)
    print(f"   {pad}{letter}{sub(idx)} = {rhs}")


def print_steps(it, rows, cols, info):
    """Cetak Langkah 2 sampai 6 untuk satu iterasi."""
    lines = [(f"S{i + 1}", i + 1) for i in rows], [(f"D{j + 1}", j + 1) for j in cols]
    kinds = ("baris", "kolom")

    print("\nLangkah 2: Mengurutkan nilai TOC pada setiap baris dan kolom")
    for kind, group in zip(kinds, lines):
        print(f"  Urutan biaya (TOC) pada {kind} :")
        for name, _ in group:
            r = info[name]
            seq = " → ".join(f"{fmt(c)} ({lab})" for lab, c, _ in r["order"])
            print(f"   {name} : {seq}")

    print("\nLangkah 3: Menghitung nilai Keep pada setiap baris dan kolom")
    print("  Rumus : K = Σ TOC × x  (isi dari sel termurah, tidak melebihi kapasitas)")
    for kind, group in zip(kinds, lines):
        print(f"  Keep {kind} :")
        for name, idx in group:
            r = info[name]
            print_terms(name, "K", idx, r["keep_terms"], r["keep"])

    print("\nLangkah 4: Menghitung nilai Lose pada setiap baris dan kolom")
    print("  Rumus : L = Σ TOC × x  (tanpa sel termurah)")
    for kind, group in zip(kinds, lines):
        print(f"  Lose {kind} :")
        for name, idx in group:
            r = info[name]
            lab = r["order_skip"]
            n_cheap = sum(abs(c - r["order"][0][1]) <= EPS for _, c, _ in r["order"])
            note = " (aturan 1.2: TOC termurah sama, abaikan kapasitas terbesar)" \
                if n_cheap > 1 else ""
            print(f"   {name} : sel {lab} diabaikan{note}")
            print_terms(name, "L", idx, r["lose_terms"], r["lose"], named=False)

    print("\nLangkah 5: Menghitung nilai q pada setiap baris dan kolom")
    print("  Rumus : q = min(sᵢ, dⱼ)")
    for kind, group in zip(kinds, lines):
        print(f"  q {kind} :")
        for name, _ in group:
            r = info[name]
            print(f"   {name} : min({fmt(r['need'])}, {fmt(r['cap'])}) = {fmt(r['q'])}")

    print("\nLangkah 6: Menghitung nilai penalti pada setiap baris dan kolom")
    print("  Rumus : Penalti = (Lose − Keep) / q")
    for kind, group in zip(kinds, lines):
        print(f"  Penalti {kind} :")
        for name, _ in group:
            r = info[name]
            if r["q"] <= EPS:
                print(f"   {name} : q = 0, penalti = 0")
                continue
            diff = r["lose"] - r["keep"]
            print(f"   {name} : ({fmt(r['lose'])} − {fmt(r['keep'])}) / {fmt(r['q'])}"
                  f" = {fmt(diff)} / {fmt(r['q'])} = {fmt(r['p'])}")


# Matriks Total Opportunity Cost (TOC)
def toc_active(real, rows, cols):
    """TOC dihitung ulang hanya dari baris dan kolom yang masih aktif.

    TOC[i][j] = (c[i][j] - min baris aktif i) + (c[i][j] - min kolom aktif j)
    Sel yang tidak aktif diisi 0 (tidak dipakai).
    """
    m, n = len(real), len(real[0])
    rmin = {i: min(real[i][j] for j in cols) for i in rows}
    cmin = {j: min(real[i][j] for i in rows) for j in cols}
    T = [[0.0] * n for _ in range(m)]
    for i in rows:
        for j in cols:
            T[i][j] = (real[i][j] - rmin[i]) + (real[i][j] - cmin[j])
    return T


def print_matrix(title, mat, rows=None, cols=None):
    rows = range(len(mat)) if rows is None else rows
    cols = range(len(mat[0])) if cols is None else cols
    print(title)
    print("        " + "".join(f"{'D' + str(j + 1):>7}" for j in cols))
    for i in rows:
        print(f"   S{i + 1:<3} " + "".join(f"{fmt(mat[i][j]):>7}" for j in cols))


# Algoritma CSVAM-TOC
def csvam(costs, supply, demand, steps=False):
    """CSVAM-TOC. Mengembalikan (matriks alokasi, total biaya).

    Langkah 1   : Hitung TOC (iterasi 1)
    Langkah 2-6 : Urutan TOC, Keep, Lose, q, penalti tiap baris/kolom
    Langkah 7   : Skor sel = penalti baris + penalti kolom
    Langkah 8   : Alokasi ke sel dengan skor terbesar
    Langkah 9   : Perbarui supply dan demand
    Langkah 10  : Hitung ulang TOC dan lanjut iterasi; jika tinggal satu
                  baris/kolom, alokasikan langsung
    Langkah 11  : Total biaya (memakai biaya asli)
    """
    real = costs
    m, n = len(costs), len(costs[0])

    s, d = list(supply), list(demand)
    s_hist = [[v] for v in s]
    d_hist = [[v] for v in d]
    rows, cols = list(range(m)), list(range(n))

    X = [[0.0] * n for _ in range(m)]
    total = 0.0
    it = 0

    if steps:
        print("=" * 60)
        print("TABEL AWAL")
        print_table(costs, X, s_hist, d_hist, {}, show_kl=False)

    while rows and cols:
        it += 1

        # Only one row or column left
        if len(rows) == 1 or len(cols) == 1:
            done = []
            for i in rows:
                for j in cols:
                    q = d[j] if len(rows) == 1 else s[i]
                    X[i][j] += q
                    total += q * real[i][j]
                    s[i] -= q
                    d[j] -= q
                    done.append((i, j, q))

            for i in rows:
                s_hist[i].append(max(s[i], 0.0))
            for j in cols:
                d_hist[j].append(max(d[j], 0.0))

            if steps:
                what = "baris" if len(rows) == 1 else "kolom"
                print("\n" + "=" * 60)
                print(f"ITERASI {it}")
                print(f"\nLangkah 10: Hanya tersisa satu {what} aktif,"
                      " sisa supply/demand langsung dialokasikan")
                for i, j, q in done:
                    print(f"   (S{i + 1}, D{j + 1}) ← {fmt(q)} unit, biaya {fmt(real[i][j])}")
            break

        # Langkah 1 / 10: matriks TOC dari baris & kolom aktif
        costs = toc_active(real, rows, cols)

        # Langkah 2-6: penalti tiap baris dan kolom (dari TOC)
        info = {}
        cells = []   # (nama garis, baris sel termurah, kolom sel termurah)
        for i in rows:
            r = csvam_penalty(
                [(f"D{j + 1}", costs[i][j], d[j]) for j in cols], s[i]
            )
            j = cols[r["skip"]]
            r["order_skip"] = f"D{j + 1}"
            info[f"S{i + 1}"] = r
            cells.append((f"S{i + 1}", i, j))

        for j in cols:
            r = csvam_penalty(
                [(f"S{i + 1}", costs[i][j], s[i]) for i in rows], d[j]
            )
            i = rows[r["skip"]]
            r["order_skip"] = f"S{i + 1}"
            info[f"D{j + 1}"] = r
            cells.append((f"D{j + 1}", i, j))

        # Langkah 7-8: skor sel = penalti baris + penalti kolom,
        # pilih skor terbesar (tie-breaking: aturan 2.2-2.4)
        best_key = best_cell = best_name = None
        ranked = []
        scored = []
        for name, ci, cj in cells:
            sc = info[f"S{ci + 1}"]["p"] + info[f"D{cj + 1}"]["p"]
            key = (sc, costs[ci][cj], info[name]["q"])
            ranked.append((key, name))
            scored.append((name, ci, cj, sc))
            if better(key, best_key):
                best_key, best_cell, best_name = key, (ci, cj), name

        i, j = best_cell

        q = min(s[i], d[j])
        X[i][j] += q
        total += q * real[i][j]

        s[i] -= q
        d[j] -= q
        s_hist[i].append(s[i])
        d_hist[j].append(d[j])

        if steps:
            print("\n" + "=" * 60)
            print(f"ITERASI {it}")
            if it == 1:
                print("\nLangkah 1: Menghitung nilai Total Opportunity Cost (TOC)")
            else:
                print("\nLangkah 10: Menghitung ulang TOC dari baris & kolom aktif")
            print("  Rumus : TOC = (c − min baris) + (c − min kolom)")
            print("  Min baris : " + ", ".join(
                f"S{r + 1} = {fmt(min(real[r][c] for c in cols))}" for r in rows))
            print("  Min kolom : " + ", ".join(
                f"D{c + 1} = {fmt(min(real[r][c] for r in rows))}" for c in cols))
            for r in rows:
                for c in cols:
                    a = real[r][c] - min(real[r][k] for k in cols)
                    b = real[r][c] - min(real[k][c] for k in rows)
                    print(f"   (S{r + 1}, D{c + 1}) = ({fmt(real[r][c])} − "
                          f"{fmt(real[r][c] - a)}) + ({fmt(real[r][c])} − "
                          f"{fmt(real[r][c] - b)}) = {fmt(a)} + {fmt(b)} = {fmt(a + b)}")
            print_matrix("  Matriks TOC :", costs, rows, cols)
            print_steps(it, rows, cols, info)

            print("\nLangkah 7: Menghitung skor sel")
            print("  Rumus : Skor = Penalti baris + Penalti kolom")
            print("  Sel termurah :")
            for name, ci, cj in cells:
                print(f"   {name} : (S{ci + 1}, D{cj + 1})")
            print("  Skor sel :")
            seen = set()
            for name, ci, cj, sc in scored:
                if (ci, cj) in seen:
                    continue
                seen.add((ci, cj))
                print(f"   (S{ci + 1}, D{cj + 1}) : P(S{ci + 1}) + P(D{cj + 1}) = "
                      f"{fmt(info[f'S{ci + 1}']['p'])} + "
                      f"{fmt(info[f'D{cj + 1}']['p'])} = {fmt(sc)}")

            print("\nLangkah 8: Melakukan alokasi pada sel dengan skor terbesar")
            print(f"   Skor sel terbesar = {fmt(best_key[0])} pada sel (S{i + 1}, D{j + 1})")
            cell_of = {name: (ci, cj) for name, ci, cj in cells}
            shown = set()
            for key, name in ranked:
                other = cell_of[name]
                if other != (i, j) and other not in shown \
                        and abs(key[0] - best_key[0]) <= EPS:
                    shown.add(other)
                    print(f"   Seri dengan sel (S{other[0] + 1}, D{other[1] + 1})"
                          f" → (S{i + 1}, D{j + 1}) dipilih"
                          f" ({tie_reason(best_key, key)})")
            print(f"   Sel terpilih : (S{i + 1}, D{j + 1}),"
                  f" biaya asli {fmt(real[i][j])}, TOC {fmt(costs[i][j])}")
            print(f"   Alokasi = min({fmt(s[i] + q)}, {fmt(d[j] + q)}) = {fmt(q)}")

            print("\nLangkah 9: Memperbarui nilai supply dan demand")
            print(f"   Supply S{i + 1} : {fmt(s[i] + q)} − {fmt(q)} = {fmt(s[i])}")
            print(f"   Demand D{j + 1} : {fmt(d[j] + q)} − {fmt(q)} = {fmt(d[j])}")

        if s[i] <= EPS:
            rows.remove(i)
            if steps:
                print(f"   Supply S{i + 1} habis → baris S{i + 1} dicoret")
        elif d[j] <= EPS:
            cols.remove(j)
            if steps:
                print(f"   Demand D{j + 1} terpenuhi → kolom D{j + 1} dicoret")

        if steps:
            print()
            print_table(real, X, s_hist, d_hist, info, new_cell=(i, j))
            print("  Keep/Lose/q/Penalti di tabel dihitung dari matriks TOC iterasi ini")

    if steps:
        print("\n" + "=" * 60)
        print("Langkah 11: Menghitung total biaya transportasi (memakai biaya asli)")
        print("  Rumus : TC = Σ c × x")
        print_table(real, X, s_hist, d_hist, {}, show_kl=False)
        terms = [
            (real[i][j], X[i][j])
            for i in range(m) for j in range(n) if X[i][j] > EPS
        ]
        print("\n   TC = " + " + ".join(f"{fmt(c)}({fmt(x)})" for c, x in terms))
        print("      = " + " + ".join(fmt(c * x) for c, x in terms))
        print(f"      = {fmt(total)}")

    return X, total


# Banyak dataset sekaligus (zip / folder)
def load_datasets(source):
    """Ambil soal dari satu file .txt, file zip, atau folder berisi .txt.
    Mengembalikan list (nama, teks), diurutkan berdasarkan nama."""
    items = []
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as z:
            for info in z.infolist():
                base = os.path.basename(info.filename)
                if info.is_dir() or not base.lower().endswith(".txt"):
                    continue
                if base.startswith(".") or "__MACOSX" in info.filename:
                    continue
                items.append((base[:-4], z.read(info).decode("utf-8-sig")))
    elif os.path.isfile(source) and source.lower().endswith(".txt"):
        base = os.path.basename(source)
        with open(source, encoding="utf-8-sig") as f:
            items.append((base[:-4], f.read()))
    elif os.path.isdir(source):
        for base in os.listdir(source):
            if base.lower().endswith(".txt"):
                with open(os.path.join(source, base), encoding="utf-8-sig") as f:
                    items.append((base[:-4], f.read()))
    else:
        raise SystemExit(f"'{source}' bukan file .txt, file zip, atau folder")
    return sorted(items)


def lp_optimum(costs, supply, demand):
    """Nilai optimal sebenarnya dengan linear programming (butuh scipy).
    Mengembalikan None jika scipy tidak terpasang."""
    try:
        from scipy.optimize import linprog
    except ImportError:
        return None
    m, n = len(costs), len(costs[0])
    c = [costs[i][j] for i in range(m) for j in range(n)]
    A = [[1 if k // n == i else 0 for k in range(m * n)] for i in range(m)]
    A += [[1 if k % n == j else 0 for k in range(m * n)] for j in range(n)]
    r = linprog(c, A_eq=A, b_eq=list(supply) + list(demand),
                bounds=(0, None), method="highs")
    return r.fun if r.success else None


def run_batch(source):
    """Jalankan CSVAM-TOC pada semua dataset di zip/folder."""
    data = load_datasets(source)
    if not data:
        raise SystemExit(f"Tidak ada file .txt di '{source}'")

    rows, warnings = [], []
    for name, text in data:
        costs, supply, demand, opt = parse_problem(text)
        with contextlib.redirect_stdout(io.StringIO()):
            costs, supply, demand = balance(costs, supply, demand)

        lp = lp_optimum(costs, supply, demand)
        if lp is not None and (opt is None or abs(lp - opt) > 1e-6):
            if opt is not None:
                warnings.append(f"{name}: optimal di file = {fmt(opt)},"
                                f" hasil LP = {fmt(lp)} -> dipakai {fmt(lp)}")
            opt = lp

        _, total = csvam([r[:] for r in costs], supply, demand)
        rows.append((name, opt, total))

    def same(a, b):
        return b is not None and abs(a - b) <= 1e-6

    def gap(t, opt):
        return 100 * (t - opt) / opt if opt else None

    # Tabel per dataset
    w = max(len(r[0]) for r in rows) + 2
    print(f"{'Dataset':<{w}}{'Optimal':>12}{'CSVAM-TOC':>13}{'Gap':>9}")
    print("-" * (w + 34))
    for name, opt, t in rows:
        o = fmt(opt) if opt is not None else "-"
        mark = "*" if same(t, opt) else " "
        g = gap(t, opt)
        gs = f"{g:>8.2f}%" if g is not None else f"{'-':>9}"
        print(f"{name:<{w}}{o:>12}{fmt(t) + mark:>13}{gs}")
    print("-" * (w + 34))
    print("* = mencapai nilai optimal")

    if warnings:
        print("\nPERINGATAN: nilai optimal di file tidak sesuai hasil LP")
        for msg in warnings:
            print("   " + msg)

    # Ringkasan
    n = len(rows)
    n_opt = sum(r[1] is not None for r in rows)
    hit = sum(same(t, opt) for _, opt, t in rows)
    gaps = [gap(t, opt) for _, opt, t in rows if opt]
    print(f"\nRINGKASAN CSVAM-TOC ({n} dataset, {n_opt} dengan nilai optimal)")
    if n_opt:
        print(f"   Optimal       : {hit} dari {n_opt} ({100 * hit / n_opt:.2f}%)")
    if gaps:
        print(f"   Rata-rata gap : {sum(gaps) / len(gaps):.2f}%")
        print(f"   Gap maksimum  : {max(gaps):.2f}%")



def main():
    steps = "--steps" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    source = args[0] if args else "dataset.zip"

    if not os.path.exists(source):
        raise SystemExit(
            f"'{source}' tidak ditemukan.\n"
            "Pemakaian: python csvam.py <soal.txt | file.zip | folder> [--steps]"
        )

    single = os.path.isfile(source) and source.lower().endswith(".txt")
    if not steps and not single:
        run_batch(source)
        return

    for name, text in load_datasets(source):
        print("\n" + "#" * 60)
        print(f"# DATASET {name}")
        print("#" * 60)
        costs, supply, demand, _ = parse_problem(text)
        costs, supply, demand = balance(costs, supply, demand)
        _, total = csvam(costs, supply, demand, True)
        print(f"\nTotal biaya transportasi {name}: {total:.2f}")


if __name__ == "__main__":
    main()