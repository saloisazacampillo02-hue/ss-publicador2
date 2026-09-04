#!/usr/bin/env python3
"""
run_scheduled.py — S&S Solutions
Revisa schedule.json y publica las piezas cuya hora ya llegó y que no se hayan
publicado aún (Instagram + Facebook). Es idempotente: si corre varias veces o
tarde (porque el Mac estaba dormido), solo publica lo pendiente y vencido.

Lo dispara launchd a las 10:00, 16:00 y 20:00 (ver com.ss.publisher.plist).
"""
import json, datetime, os, time, errno
from pathlib import Path
import meta_publish as mp
import calendario

BASE = Path(__file__).parent
SCHED = BASE / "schedule.json"
LOG = BASE / "publicaciones.log"
LOCK = BASE / "run.lock"
LOCK_STALE = 1800  # 30 min: si un lock es más viejo, se considera abandonado

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def acquire_lock():
    """Evita corridas simultáneas (lo que causaba publicaciones duplicadas)."""
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        if age < LOCK_STALE:
            return False  # otra corrida está activa
        LOCK.unlink(missing_ok=True)  # lock viejo/abandonado
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
        return True
    except OSError as e:
        if e.errno == errno.EEXIST:
            return False
        raise

def save(sched):
    json.dump(sched, open(SCHED, "w"), ensure_ascii=False, indent=2)

def main():
    if not acquire_lock():
        log("⏭️  Otra corrida en progreso (lock activo). Salgo para no duplicar.")
        return
    try:
        env = mp.load_env(mp.ENV)
        data = json.load(open(mp.APROB)) if mp.APROB.exists() else None
        sched = json.load(open(SCHED))
        now = datetime.datetime.now()
        changed = False
        for it in sched["items"]:
            if it.get("publicado"):
                continue
            cuando = datetime.datetime.strptime(it["cuando"], "%Y-%m-%d %H:%M")
            if cuando <= now:
                tipo = it.get("tipo", "post")
                nombre = it.get("archivo") or it.get("key") or it.get("pieza")
                try:
                    log(f"▶ Publicando [{tipo}] {nombre} (programada {it['cuando']})")
                    imgs = calendario.paths_for(it)  # rutas en el Calendario (fuente)
                    if tipo == "historia":
                        mp.publish_historia(env, str(imgs[0]))
                    elif tipo == "post2":
                        sem = it.get("sem", 2)
                        dfile = mp.APROB2 if sem == 2 else (mp.APROB2.parent / f"aprobados_semana{sem}.json")
                        data_w = json.load(open(dfile))
                        mp.publish_piece2(env, data_w, it["key"], images=imgs)
                    elif tipo == "post7":
                        p7 = json.load(open(mp.APROB2.parent / "aprobados_semana7.json"))
                        piece = next(x for x in p7["piezas"] if f"p{x['n']}" == it["key"])
                        fmt = piece["formato"]; idi = piece.get("idioma", "es")
                        hashtags = mp.HASH_LOCAL if idi == "es" else mp.HASH
                        caption = piece["caption"] + "\n\n" + hashtags
                        paths = [str(x) for x in imgs]
                        if "Reel" in fmt:
                            mp.publish_reel(env, paths[0], caption)
                        elif "Imagen" in fmt:
                            mp.publish_image(env, paths[0], caption)
                        else:
                            mp.publish_carousel(env, paths, caption)
                    else:
                        mp.publish_piece(env, data, it["pieza"], images=imgs)
                    it["publicado"] = True
                    it["publicado_en"] = now.strftime("%Y-%m-%d %H:%M:%S")
                    save(sched)          # guardar TRAS CADA pieza (evita duplicados)
                    changed = True
                    log(f"✅ OK {nombre}")
                except (Exception, SystemExit) as e:
                    log(f"❌ ERROR {nombre}: {e}")
        if not changed:
            log("Sin piezas pendientes vencidas.")
        # Mantener la vista por semanas al día y limpiar (>14 días -> Papelera)
        try:
            calendario.rebuild()
            movidas = calendario.cleanup(14)
            if movidas:
                log(f"🗑️  Semanas movidas a la Papelera (>14 días): {movidas}")
        except Exception as e:
            log(f"⚠️  Calendario no actualizado: {e}")
    finally:
        LOCK.unlink(missing_ok=True)

    # Mantener la vista por semanas al día y limpiar (>14 días -> Papelera)
    try:
        calendario.rebuild()
        movidas = calendario.cleanup(14)
        if movidas:
            log(f"🗑️  Semanas movidas a la Papelera (>14 días): {movidas}")
    except Exception as e:
        log(f"⚠️  Calendario no actualizado: {e}")

if __name__ == "__main__":
    main()
