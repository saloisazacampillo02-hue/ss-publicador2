#!/usr/bin/env python3
"""
calendario.py — S&S Solutions
El Calendario es la FUENTE de lo que se publica. Cada semana tiene Feed/ e
Historias/ con las imágenes nombradas por fecha/hora. El publicador lee de aquí
(vía paths_for), así que lo que ves en la carpeta de la semana es lo que sale.

- paths_for(item): rutas en el Calendario para un item del schedule. Si faltan,
  las crea copiando desde Piezas/ (sin sobrescribir, para respetar reemplazos
  manuales tuyos).
- rebuild(): asegura que existan las imágenes de todas las semanas del schedule.
- cleanup(dias=14): mueve a la Papelera (~/.Trash) las semanas más viejas que
  `dias`. NO borra permanentemente.

Uso manual:
  python3 calendario.py            # asegura la vista por semanas
  python3 calendario.py --limpiar  # + limpia (>14 días a Papelera)
"""
import json, shutil, datetime, argparse
from pathlib import Path

BASE = Path(__file__).parent
CONT = BASE.parent / "Contenido"
PIEZAS = CONT / "Piezas"
HIST = PIEZAS / "historias"
APROB = CONT / "aprobados_semana.json"
APROB2 = CONT / "aprobados_semana2.json"
SCHED = BASE / "schedule.json"
CAL = CONT / "Calendario"
TRASH = Path.home() / ".Trash"

DIAS_ES = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
ABBR = {"Lunes": "lun", "Martes": "mar", "Miércoles": "mie", "Jueves": "jue", "Viernes": "vie"}


def _safe(s):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in s).strip().replace(" ", "_")


def p_key(p):
    return f"{ABBR[p['dia']]}_p{p['pieza']}"


def _week(dt):
    monday = dt.date() - datetime.timedelta(days=dt.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return f"Semana {monday:%Y-%m-%d} al {sunday:%m-%d}"


def _load():
    d1 = {p_key(p): p for p in json.load(open(APROB))["piezas"]} if APROB.exists() else {}
    d2 = {p["key"]: p for p in json.load(open(APROB2))["piezas"]} if APROB2.exists() else {}
    return d1, d2


_WK = {}
def _week_data(sem):
    """Carga (cacheada) aprobados_semana{sem}.json -> {key: pieza}."""
    if sem not in _WK:
        f = CONT / f"aprobados_semana{sem}.json"
        _WK[sem] = {p["key"]: p for p in json.load(open(f))["piezas"]} if f.exists() else {}
    return _WK[sem]


_W7=None
def _week7():
    global _W7
    if _W7 is None:
        f=CONT/"aprobados_semana7.json"
        _W7={f"p{p['n']}":p for p in json.load(open(f))["piezas"]} if f.exists() else {}
    return _W7

def _targets(it, d1, d2):
    """Devuelve [(src_en_Piezas, dst_en_Calendario), ...] en orden EN, ES."""
    dt = datetime.datetime.strptime(it["cuando"], "%Y-%m-%d %H:%M")
    wk = CAL / _week(dt)
    dia = DIAS_ES[dt.weekday()]
    stamp = f"{dt:%Y-%m-%d}_{dia}_{dt:%Hh%M}"
    tipo = it.get("tipo", "post")
    out = []
    if tipo == "historia":
        modo = it.get("modo", "tip")
        out.append((HIST / it["archivo"], wk / "Historias" / f"{stamp}_{modo}.jpg"))
    elif tipo == "post2":
        sem = it.get("sem", 2)                 # semana (2, 3, ...)
        key = it["key"]; p = _week_data(sem).get(key, {}); pilar = _safe(p.get("pilar", ""))
        pref = f"pieza_w{sem}_{key}"
        if p.get("lang") == "bi":
            out.append((PIEZAS / f"{pref}_EN.jpg", wk / "Feed" / f"{stamp}_{key}_{pilar}_1EN.jpg"))
            out.append((PIEZAS / f"{pref}_ES.jpg", wk / "Feed" / f"{stamp}_{key}_{pilar}_2ES.jpg"))
        else:
            out.append((PIEZAS / f"{pref}_ES.jpg", wk / "Feed" / f"{stamp}_{key}_{pilar}.jpg"))
    elif tipo == "post7":
        import glob as _g
        key = it["key"]; p = _week7().get(key, {}); fmt = p.get("formato", "")
        sk = f"{stamp}_{key}"
        if "Reel" in fmt:
            out.append((PIEZAS / f"reel_w7_{key}.mp4", wk / "Feed" / f"{sk}_reel.mp4"))
        elif "Imagen" in fmt:
            out.append((PIEZAS / f"pieza_w7_{key}_EN.jpg", wk / "Feed" / f"{sk}.jpg"))
        elif "Oferta" in fmt:
            out.append((PIEZAS / f"pieza_w7_{key}_EN.jpg", wk / "Feed" / f"{sk}_1EN.jpg"))
            out.append((PIEZAS / f"pieza_w7_{key}_ES.jpg", wk / "Feed" / f"{sk}_2ES.jpg"))
        else:
            for i, sp in enumerate(sorted(_g.glob(str(PIEZAS / f"carr_w7_{key}_*.jpg"))), 1):
                out.append((Path(sp), wk / "Feed" / f"{sk}_s{i:02d}.jpg"))
    else:
        key = it["pieza"]; p = d1.get(key, {}); pilar = _safe(p.get("pilar", ""))
        out.append((PIEZAS / f"pieza_{key}_EN.jpg", wk / "Feed" / f"{stamp}_{key}_{pilar}_1EN.jpg"))
        out.append((PIEZAS / f"pieza_{key}_ES.jpg", wk / "Feed" / f"{stamp}_{key}_{pilar}_2ES.jpg"))
    return out


def _ensure(src, dst):
    if not dst.exists() and src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return dst


def paths_for(it):
    """Rutas (en el Calendario) de las imágenes de este item, en orden EN, ES.
    Las crea desde Piezas/ si faltan, sin sobrescribir reemplazos manuales."""
    d1, d2 = _load()
    return [_ensure(src, dst) for src, dst in _targets(it, d1, d2)]


def rebuild():
    d1, d2 = _load()
    sched = json.load(open(SCHED))
    CAL.mkdir(parents=True, exist_ok=True)
    for it in sched["items"]:
        for src, dst in _targets(it, d1, d2):
            _ensure(src, dst)
    return CAL


def cleanup(dias=14):
    """Mueve a la Papelera las semanas cuyo fin ya pasó hace > `dias`."""
    if not CAL.exists():
        return []
    hoy = datetime.date.today()
    movidas = []
    for wk in CAL.iterdir():
        if not (wk.is_dir() and wk.name.startswith("Semana")):
            continue
        try:
            ini = datetime.datetime.strptime(wk.name.split()[1], "%Y-%m-%d").date()
            fin = ini + datetime.timedelta(days=6)
        except Exception:
            continue
        if (hoy - fin).days > dias:
            TRASH.mkdir(parents=True, exist_ok=True)
            dest = TRASH / wk.name; i = 1
            while dest.exists():
                dest = TRASH / f"{wk.name} ({i})"; i += 1
            shutil.move(str(wk), str(dest))
            movidas.append(wk.name)
    return movidas


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limpiar", action="store_true", help="mover semanas >14 días a la Papelera")
    a = ap.parse_args()
    rebuild()
    print(f"✅ Calendario asegurado en: {CAL}")
    if a.limpiar:
        m = cleanup(14)
        print("🗑️  Movidas a Papelera:", m if m else "ninguna")
