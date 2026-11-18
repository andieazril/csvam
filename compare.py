import contextlib
import csv
import glob
import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile

import csvam

TIMEOUT = 10  # detik per program per soal
HERE = os.path.dirname(os.path.abspath(__file__))
METHODS = ["CSVAM-TOC", "SAM", "FVAM", "RBSM", "CSM"]
OTHERS = ["SAM", "FVAM", "RBSM", "CSM"]


def exe(name):
    path = os.path.join(HERE, name)
    return path + ".exe" if os.path.exists(path + ".exe") else path


# Balancing
def read_optimum(path):
    """Angka setelah demand (jika ada) = nilai optimal soal tersebut."""
    tok = open(path, encoding="utf-8").read().split()
    m, n = int(tok[0]), int(tok[1])
    rest = tok[2 + m * n + m + n:]
    return round(float(rest[0])) if rest else None


def lp_optimum(problem):
    """Nilai optimal sebenarnya via linear programming (butuh scipy).
    Mengembalikan None jika scipy tidak terpasang."""
    try:
        from scipy.optimize import linprog
    except ImportError:
        return None
    costs, supply, demand = problem
    m, n = len(costs), len(costs[0])
    c = [costs[i][j] for i in range(m) for j in range(n)]
    A, b = [], []
    for i in range(m):
        A.append([1 if k // n == i else 0 for k in range(m * n)])
        b.append(supply[i])
    for j in range(n):
        A.append([1 if k % n == j else 0 for k in range(m * n)])
        b.append(demand[j])
    r = linprog(c, A_eq=A, b_eq=b, bounds=(0, None), method="highs")
    return round(r.fun) if r.success else None


def balanced_text(path):
    with open(path, encoding="utf-8") as fh:
        costs, supply, demand, _ = csvam.parse_problem(fh.read())
    with contextlib.redirect_stdout(io.StringIO()):
        costs, supply, demand = csvam.balance(costs, supply, demand)

    def num(x):
        return str(int(x)) if float(x).is_integer() else str(x)

    lines = [f"{len(costs)} {len(costs[0])}"]
    lines += [" ".join(num(c) for c in row) for row in costs]
    lines.append(" ".join(num(v) for v in supply))
    lines.append(" ".join(num(v) for v in demand))
    return "\n".join(lines) + "\n", (costs, supply, demand)


# Menjalankan tiap metode
def run_csvam(problem):
    costs, supply, demand = problem
    _, total = csvam.csvam([r[:] for r in costs], list(supply), list(demand))
    return round(total), "ok"


def feasible(out, problem):
    """Cek tabel alokasi terakhir di output: jumlah baris = supply,
    jumlah kolom = demand, dan tidak ada alokasi negatif."""
    costs, supply, demand = problem
    m, n = len(costs), len(costs[0])
    cells = re.findall(r"(-?\d+)\s?\[(-?\d+)\]", out)[-m * n:]
    if len(cells) < m * n:
        return True  # tabel tidak terbaca, jangan dianggap gagal
    X = [[int(cells[i * n + j][1]) for j in range(n)] for i in range(m)]
    return (
        all(abs(sum(X[i]) - supply[i]) < 1e-6 for i in range(m))
        and all(abs(sum(X[i][j] for i in range(m)) - demand[j]) < 1e-6
                for j in range(n))
        and all(x >= 0 for row in X for x in row)
    )


def run_program(method, path, problem):
    """Jalankan program C/C++ asli dan ambil TCC dari output-nya."""
    if method == "SAM":
        cmd, stdin = [exe("sam"), path], ""
    else:
        # Menu interaktif: 2 = custom file, lalu 3 = exit
        cmd, stdin = [exe(method.lower())], f"2\n{path}\n3\n"

    try:
        out = subprocess.run(
            cmd, input=stdin, capture_output=True, text=True,
            timeout=TIMEOUT, errors="replace", cwd=os.path.dirname(path),
        ).stdout
    except subprocess.TimeoutExpired:
        return None, "timeout"

    if method == "SAM":
        m = re.findall(r"Total Alokasi tabel adalah: (-?\d+)", out)
        if "ITER LEWAT" in out:
            return (int(m[-1]) if m else None), "iter>20"
    else:
        m = re.findall(r"TCC = (-?\d+)", out)
        if not m and "Soal Salah" in out:
            return None, "soal salah"

    if not m:
        return None, "gagal"
    if not feasible(out, problem):
        return int(m[-1]), "tdk feasible"
    return int(m[-1]), "ok"


# Main
def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "dataset"
    if zipfile.is_zipfile(folder):
        # Ekstrak .txt dari zip ke folder sementara
        tmpzip = tempfile.mkdtemp(prefix="ds")
        for name, text in csvam.load_datasets(folder):
            with open(os.path.join(tmpzip, name + ".txt"), "w") as fh:
                fh.write(text)
        folder = tmpzip
    files = sorted(glob.glob(os.path.join(folder, "*.txt")))
    if not files:
        sys.exit(f"Tidak ada file .txt di folder '{folder}'")

    tmpdir = tempfile.mkdtemp(prefix="tp")
    rows = []
    warnings = []

    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        text, problem = balanced_text(f)
        path = os.path.join(tmpdir, "in.txt")
        with open(path, "w") as fh:
            fh.write(text)

        co, su, de = problem
        res = {"CSVAM": run_csvam(problem)}
        for mth in OTHERS:
            res[mth] = run_program(mth, path, problem)
        opt = read_optimum(f)
        lp = lp_optimum(problem)
        if lp is not None and opt != lp:
            if opt is not None:
                warnings.append(f"{name}: nilai optimal di file = {opt}, "
                                f"hasil LP = {lp} -> dipakai {lp}")
            opt = lp
        rows.append((name, opt, res))

    def ok(r):
        return r[1] == "ok" and r[0] is not None

    hit = {m: 0 for m in METHODS}      # TCC = nilai optimal
    best = {m: 0 for m in METHODS}     # terbaik di antara 5 metode
    fails = {m: 0 for m in METHODS}
    gaps = {m: [] for m in METHODS}
    best_of = {}

    for name, opt, res in rows:
        valid = {m: r[0] for m, r in res.items() if ok(r)}
        for m in METHODS:
            if not ok(res[m]):
                fails[m] += 1
        best_of[name] = min(valid.values()) if valid else None
        for m, v in valid.items():
            if v == best_of[name]:
                best[m] += 1
            if opt is not None:
                if v == opt:
                    hit[m] += 1
                if opt:
                    gaps[m].append(100 * (v - opt) / opt)

    n_opt = sum(opt is not None for _, opt, _ in rows)

    # Tabel
    w = max(len(n) for n, _, _ in rows) + 2
    head = f"{'Dataset':<{w}}{'Optimal':>11}" + "".join(f"{m:>13}" for m in METHODS)
    print(head)
    print("-" * len(head))
    for name, opt, res in rows:
        line = f"{name:<{w}}{(str(opt) if opt is not None else '-'):>11}"
        for m in METHODS:
            v, st = res[m]
            if ok(res[m]):
                mark = "*" if v == opt else ("+" if v == best_of[name] else " ")
                cell = f"{v}{mark}"
            else:
                cell = f"({st}) "
            line += f"{cell:>13}"
        print(line)
    print("-" * len(head))
    print("* = mencapai nilai optimal")
    print("+ = terbaik di antara semua metode, tapi belum optimal\n")

    if warnings:
        print("PERINGATAN: nilai optimal di file tidak sesuai hasil LP")
        for w_ in warnings:
            print("   " + w_)
        print()

    # Ringkasan jumlah optimal
    n = len(rows)
    print(f"JUMLAH OPTIMAL ({n} dataset, {n_opt} dengan nilai optimal)")
    print(f"{'Metode':<8}{'Optimal':>9}{'%':>9}{'Terbaik':>10}{'Rata2 gap':>12}"
          f"{'Gap maks':>11}{'Gagal':>7}")
    order = sorted(METHODS, key=lambda m: (-hit[m], -best[m]))
    for m in order:
        g = gaps[m]
        avg = f"{sum(g) / len(g):.2f}%" if g else "-"
        mx = f"{max(g):.2f}%" if g else "-"
        pct = 100 * hit[m] / n_opt if n_opt else 0
        print(f"{m:<8}{hit[m]:>9}{pct:>8.2f}%{best[m]:>10}{avg:>12}{mx:>11}{fails[m]:>7}")
    print("\nOptimal   = TCC sama dengan nilai optimal (dari file, dicek ulang dengan LP)")
    print("Terbaik   = TCC terkecil di antara semua metode (seri ikut dihitung)")
    print("Gap       = (TCC - optimal) / optimal x 100%")
    print("Gagal     = timeout / soal salah / iter>20 (SAM) /"
          " alokasi tidak feasible / tidak ada output")

    # Head-to-head CSVAM vs tiap metode
    for cv in ("CSVAM",):
      print(f"\n{cv} vs metode lain (lebih baik / sama / lebih buruk)")
      for m in OTHERS:
        b = s = k = 0
        for _, _, res in rows:
            if not (ok(res[cv]) and ok(res[m])):
                continue
            a, o = res[cv][0], res[m][0]
            if a < o:
                b += 1
            elif a == o:
                s += 1
            else:
                k += 1
        print(f"   vs {m:<5}: {b:>3} / {s:>3} / {k:>3}")
    print("\nCSVAM = matriks TOC dihitung ulang tiap iterasi"
          " + pemilihan sel berdasarkan skor (penalti baris + penalti kolom)")

    with open("hasil_perbandingan.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["Dataset", "Optimal"] + METHODS
                    + [f"{m}_optimal" for m in METHODS]
                    + [f"{m}_gap%" for m in METHODS])
        for name, opt, res in rows:
            vals = [res[m][0] if ok(res[m]) else res[m][1] for m in METHODS]
            hits = [int(ok(res[m]) and res[m][0] == opt) for m in METHODS]
            gp = [round(100 * (res[m][0] - opt) / opt, 2)
                  if ok(res[m]) and opt else "" for m in METHODS]
            wr.writerow([name, opt] + vals + hits + gp)
        wr.writerow([])
        wr.writerow(["Jumlah optimal", ""] + [hit[m] for m in METHODS])
        wr.writerow(["Jumlah terbaik", ""] + [best[m] for m in METHODS])
    print("\nHasil disimpan ke hasil_perbandingan.csv")


if __name__ == "__main__":
    main()
