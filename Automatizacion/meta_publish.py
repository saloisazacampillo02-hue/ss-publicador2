#!/usr/bin/env python3
"""
meta_publish.py — S&S Solutions
Publica carruseles bilingües (slide EN + slide ES) en Instagram vía la API
(flujo Instagram Login). Sube las imágenes a una URL pública usando Kie.

Lee los textos de:  ../Contenido/aprobados_semana.json
Lee las imágenes de: ../Contenido/Piezas/pieza_<ab>_p<n>_EN.jpg / _ES.jpg

Uso:
  cd /Users/salo/Documents/S&S/Automatizacion
  python3 meta_publish.py --post lun_p1        # publica UNA pieza (prueba)
  python3 meta_publish.py --all                # publica las 10

Requiere en meta.env: IG_USER_ID, IG_ACCESS_TOKEN, KIE_API_KEY
"""
import sys, os, json, time, base64, argparse, urllib.request, urllib.parse
from pathlib import Path

BASE = Path(__file__).parent
ENV = BASE / "meta.env"
APROB = BASE.parent / "Contenido" / "aprobados_semana.json"
APROB2 = BASE.parent / "Contenido" / "aprobados_semana2.json"
PIEZAS = BASE.parent / "Contenido" / "Piezas"
GV = "v21.0"
IG_HOST = "https://graph.instagram.com"
KIE_UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"
ABBR = {"Lunes": "lun", "Martes": "mar", "Miércoles": "mie", "Jueves": "jue", "Viernes": "vie"}
HASH = "#ssolutionscol #SSSolutions #Colombia #Visas #InvertirEnColombia #VivirEnColombia #Expats #LegalColombia #Inmigración"
HASH_LOCAL = "#ssolutionscol #SSSolutions #Colombia #DerechoLaboral #CentralesDeRiesgo #Datacrédito #HabeasData #DerechosLaborales #Abogados"

def load_env(p):
    """Lee meta.env si existe, y completa/sobrescribe con variables de entorno
    (para la nube / GitHub Secrets, donde no hay meta.env)."""
    d = {}
    try:
        for line in p.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            d[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    for k in ("IG_USER_ID", "IG_ACCESS_TOKEN", "META_PAGE_ID", "META_PAGE_TOKEN",
              "META_APP_ID", "META_APP_SECRET", "KIE_API_KEY"):
        if os.environ.get(k):
            d[k] = os.environ[k]
    return d

def http_json(url, data=None):
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise SystemExit(f"\n❌ Error HTTP {e.code}: {detail}")

def _up_litterbox(rq, path):
    with open(path, "rb") as f:
        r = rq.post("https://litterbox.catbox.moe/resources/internals/api.php",
                    data={"reqtype": "fileupload", "time": "72h"},
                    files={"fileToUpload": (Path(path).name, f, "image/jpeg")}, timeout=300)
    r.raise_for_status(); return r.text.strip()

def _up_catbox(rq, path):
    with open(path, "rb") as f:
        r = rq.post("https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (Path(path).name, f, "image/jpeg")}, timeout=300)
    r.raise_for_status(); return r.text.strip()

def _up_0x0(rq, path):
    with open(path, "rb") as f:
        r = rq.post("https://0x0.st", files={"file": (Path(path).name, f, "image/jpeg")},
                    headers={"User-Agent": "ss-solutions-publisher/1.0"}, timeout=300)
    r.raise_for_status(); return r.text.strip()

def upload_public(img_path):
    """Devuelve una URL pública de la imagen.
    En la nube (GitHub Actions, repo público) usa la URL raw de GitHub — 100% confiable,
    sin depender de hosts externos. En local, sube a un host público (litterbox/catbox/0x0)."""
    ws = os.environ.get("GITHUB_WORKSPACE"); repo = os.environ.get("GITHUB_REPOSITORY")
    ref = os.environ.get("GITHUB_REF_NAME", "main")
    if ws and repo:
        import urllib.parse
        rel = os.path.relpath(str(img_path), ws).replace(os.sep, "/")
        return f"https://raw.githubusercontent.com/{repo}/{ref}/" + urllib.parse.quote(rel)
    try:
        import requests
    except ImportError:
        raise SystemExit("❌ Falta 'requests'. Instala: pip3 install requests --break-system-packages")
    hosts = [("litterbox", _up_litterbox), ("catbox", _up_catbox), ("0x0.st", _up_0x0)]
    ultimo = None
    for nombre, fn in hosts:
        for i in (1, 2):
            try:
                url = fn(requests, img_path)
                if url.startswith("http"):
                    return url
                ultimo = f"{nombre}: respuesta inesperada '{url[:80]}'"
            except Exception as e:
                ultimo = f"{nombre}: {e}"
            print(f"   ⚠️  Upload {nombre} falló (intento {i}/2): {ultimo}. …")
            time.sleep(5 * i)
        print(f"   ↪️  Cambiando de host…")
    raise SystemExit(f"❌ No se pudo subir la imagen a ningún host. Último error: {ultimo}")

def ig_child(ig_id, token, image_url):
    r = http_json(f"{IG_HOST}/{GV}/{ig_id}/media",
                  {"image_url": image_url, "is_carousel_item": "true", "access_token": token})
    return r["id"]

def ig_carousel(ig_id, token, children, caption):
    r = http_json(f"{IG_HOST}/{GV}/{ig_id}/media",
                  {"media_type": "CAROUSEL", "children": ",".join(children),
                   "caption": caption, "access_token": token})
    return r["id"]

def ig_wait_ready(token, creation_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        r = http_json(f"{IG_HOST}/{GV}/{creation_id}?fields=status_code&access_token={token}")
        st = r.get("status_code")
        if st == "FINISHED":
            return
        if st == "ERROR":
            raise SystemExit(f"❌ El contenedor falló: {r}")
        time.sleep(4)

def ig_publish(ig_id, token, creation_id):
    r = http_json(f"{IG_HOST}/{GV}/{ig_id}/media_publish",
                  {"creation_id": creation_id, "access_token": token})
    return r["id"]

def ig_story(ig_id, token, image_url):
    """Crea un contenedor de HISTORIA (9:16) en Instagram."""
    r = http_json(f"{IG_HOST}/{GV}/{ig_id}/media",
                  {"image_url": image_url, "media_type": "STORIES", "access_token": token})
    return r["id"]

def ig_single(ig_id, token, image_url, caption):
    """Crea un contenedor de post de UNA imagen (feed) en Instagram."""
    r = http_json(f"{IG_HOST}/{GV}/{ig_id}/media",
                  {"image_url": image_url, "caption": caption, "access_token": token})
    return r["id"]

FB_HOST = "https://graph.facebook.com"

def fb_photo_unpublished(page_id, token, image_url):
    r = http_json(f"{FB_HOST}/{GV}/{page_id}/photos",
                  {"url": image_url, "published": "false", "access_token": token})
    return r["id"]

def fb_post_carousel(page_id, token, photo_ids, message):
    data = {"message": message, "access_token": token}
    for i, pid in enumerate(photo_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    r = http_json(f"{FB_HOST}/{GV}/{page_id}/feed", data)
    return r["id"]

def fb_photo_published(page_id, token, image_url, message):
    """Publica una foto única en la página de Facebook."""
    r = http_json(f"{FB_HOST}/{GV}/{page_id}/photos",
                  {"url": image_url, "message": message, "published": "true", "access_token": token})
    return r["id"]

def find_piece(data, key):
    for p in data["piezas"]:
        if f"{ABBR[p['dia']]}_p{p['pieza']}" == key:
            return p
    return None

def publish_piece(env, data, key, images=None):
    ig_id = env["IG_USER_ID"]; token = env["IG_ACCESS_TOKEN"]
    p = find_piece(data, key)
    if not p:
        raise SystemExit(f"❌ No encontré la pieza '{key}'")
    ab = ABBR[p["dia"]]; n = p["pieza"]
    if images:
        en_img, es_img = images[0], images[1]
    else:
        en_img = PIEZAS / f"pieza_{ab}_p{n}_EN.jpg"
        es_img = PIEZAS / f"pieza_{ab}_p{n}_ES.jpg"
    caption = f"EN: {p['en']['copy']}\n\nES: {p['es']['copy']}\n\n{HASH}"
    print(f"\n=== Pieza {key} · {p['pilar']} ===")
    print("📤 Subiendo imágenes a URL pública...")
    url_en = upload_public(en_img)
    url_es = upload_public(es_img)
    print("🧩 Creando carrusel (EN, ES)...")
    c1 = ig_child(ig_id, token, url_en)
    c2 = ig_child(ig_id, token, url_es)
    parent = ig_carousel(ig_id, token, [c1, c2], caption)
    print("⏳ Esperando que el contenedor esté listo...")
    ig_wait_ready(token, parent)
    print("🚀 Publicando en Instagram...")
    media_id = ig_publish(ig_id, token, parent)
    print(f"✅ Publicado en Instagram. media_id={media_id}")

    if env.get("META_PAGE_ID") and env.get("META_PAGE_TOKEN"):
        print("📘 Publicando en Facebook...")
        pid = env["META_PAGE_ID"]; ptok = env["META_PAGE_TOKEN"]
        f1 = fb_photo_unpublished(pid, ptok, url_en)
        f2 = fb_photo_unpublished(pid, ptok, url_es)
        post_id = fb_post_carousel(pid, ptok, [f1, f2], caption)
        print(f"✅ Publicado en Facebook. post_id={post_id}")
    else:
        print("ℹ️  Facebook aún no configurado (sin META_PAGE_TOKEN) — por ahora solo Instagram.")

def find_piece2(data, key):
    for p in data["piezas"]:
        if p["key"] == key:
            return p
    return None

def publish_piece2(env, data, key, images=None):
    """Semana 2: bi = carrusel EN+ES; es = post de UNA imagen en español."""
    ig_id = env["IG_USER_ID"]; token = env["IG_ACCESS_TOKEN"]
    p = find_piece2(data, key)
    if not p:
        raise SystemExit(f"❌ No encontré la pieza '{key}' (sem2)")
    pid = env.get("META_PAGE_ID"); ptok = env.get("META_PAGE_TOKEN")
    fb_ok = bool(pid and ptok)

    if p["lang"] == "bi":
        if images:
            en_img, es_img = images[0], images[1]
        else:
            en_img = PIEZAS / f"pieza_w2_{key}_EN.jpg"
            es_img = PIEZAS / f"pieza_w2_{key}_ES.jpg"
        caption = f"EN: {p['en']['copy']}\n\nES: {p['es']['copy']}\n\n{HASH}"
        print(f"\n=== Pieza {key} · {p['pilar']} (carrusel) ===")
        print("📤 Subiendo imágenes...")
        url_en = upload_public(en_img); url_es = upload_public(es_img)
        c1 = ig_child(ig_id, token, url_en); c2 = ig_child(ig_id, token, url_es)
        parent = ig_carousel(ig_id, token, [c1, c2], caption)
        ig_wait_ready(token, parent)
        media_id = ig_publish(ig_id, token, parent)
        print(f"✅ Instagram (carrusel) media_id={media_id}")
        if fb_ok:
            f1 = fb_photo_unpublished(pid, ptok, url_en)
            f2 = fb_photo_unpublished(pid, ptok, url_es)
            post_id = fb_post_carousel(pid, ptok, [f1, f2], caption)
            print(f"✅ Facebook post_id={post_id}")
        else:
            print("ℹ️  Facebook no configurado — solo Instagram.")
    else:
        es_img = images[0] if images else (PIEZAS / f"pieza_w2_{key}_ES.jpg")
        caption = f"{p['es']['copy']}\n\n{HASH_LOCAL}"
        print(f"\n=== Pieza {key} · {p['pilar']} (1 imagen, ES) ===")
        print("📤 Subiendo imagen...")
        url_es = upload_public(es_img)
        cont = ig_single(ig_id, token, url_es, caption)
        ig_wait_ready(token, cont)
        media_id = ig_publish(ig_id, token, cont)
        print(f"✅ Instagram (1 imagen) media_id={media_id}")
        if fb_ok:
            post_id = fb_photo_published(pid, ptok, url_es, caption)
            print(f"✅ Facebook photo_id={post_id}")
        else:
            print("ℹ️  Facebook no configurado — solo Instagram.")

HISTORIAS = PIEZAS / "historias"

def publish_historia(env, image_path):
    """Publica una HISTORIA 9:16 en Instagram (y FB si está configurado).
    image_path: ruta a un JPG ya renderizado (teaser o tip).
    Nota: la API no permite agregar el sticker de link de WhatsApp; el número
    va impreso en la imagen pero no será un botón táctil."""
    ig_id = env["IG_USER_ID"]; token = env["IG_ACCESS_TOKEN"]
    image_path = Path(image_path)
    if not image_path.is_absolute():
        image_path = HISTORIAS / image_path.name
    if not image_path.exists():
        raise SystemExit(f"❌ No encontré la historia '{image_path}'")
    print(f"\n=== Historia {image_path.name} ===")
    print("📤 Subiendo imagen a URL pública...")
    url = upload_public(image_path)
    print("🧩 Creando contenedor de historia...")
    creation = ig_story(ig_id, token, url)
    print("⏳ Esperando que el contenedor esté listo...")
    ig_wait_ready(token, creation)
    print("🚀 Publicando historia en Instagram...")
    media_id = ig_publish(ig_id, token, creation)
    print(f"✅ Historia publicada en Instagram. media_id={media_id}")

    if env.get("META_PAGE_ID") and env.get("META_PAGE_TOKEN"):
        try:
            pid = env["META_PAGE_ID"]; ptok = env["META_PAGE_TOKEN"]
            fbid = fb_photo_unpublished(pid, ptok, url)
            r = http_json(f"{FB_HOST}/{GV}/{pid}/photo_stories",
                          {"photo_id": fbid, "access_token": ptok})
            print(f"✅ Historia publicada en Facebook. {r}")
        except SystemExit as e:
            print(f"ℹ️  Historia de Facebook no publicada ({e}). Instagram OK.")
    return media_id

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", help="clave de la pieza sem1, ej: lun_p1")
    ap.add_argument("--post2", help="clave de la pieza sem2, ej: p1")
    ap.add_argument("--all", action="store_true", help="publicar las 10 (sem1)")
    ap.add_argument("--historia", help="ruta o nombre del JPG de historia a publicar")
    a = ap.parse_args()
    env = load_env(ENV)
    for k in ("IG_USER_ID", "IG_ACCESS_TOKEN"):
        if not env.get(k):
            raise SystemExit(f"❌ Falta {k} en meta.env")
    if a.historia:
        publish_historia(env, a.historia)
        print("\n🏁 Listo.")
        return
    if a.post2:
        data2 = json.load(open(APROB2))
        publish_piece2(env, data2, a.post2)
        print("\n🏁 Listo.")
        return
    data = json.load(open(APROB))
    if a.all:
        keys = [f"{ABBR[p['dia']]}_p{p['pieza']}" for p in data["piezas"]]
    elif a.post:
        keys = [a.post]
    else:
        keys = ["lun_p1"]
        print("ℹ️  Sin --post ni --all: publico la pieza de prueba lun_p1")
    for k in keys:
        publish_piece(env, data, k)
    print("\n🏁 Listo.")

if __name__ == "__main__":
    main()
