#!/usr/bin/env python3
"""
tiktok_publish.py · S&S Solutions
Publica en TikTok los reels de schedule.json (tipo "post7" con formato Reel) cuya
hora ya llegó, usando la Content Posting API oficial (Direct Post, FILE_UPLOAD).

- Corre en GitHub Actions después de Instagram, en el mismo flujo cada 15 minutos.
- No hace nada si falta el secreto TIKTOK_CLIENT_KEY o si tiktok_config.json dice "activo": false.
- Solo toma piezas programadas desde la fecha "desde" de tiktok_config.json (nunca republica lo viejo).
- Estado por pieza dentro de schedule.json, en el campo "tiktok":
  {"publicado": true/false, "publicado_en", "publish_id", "intentos", "ultimo_error"}.
- Mientras TikTok no audite la app, todo sale en privado (SELF_ONLY). Al aprobarse la
  auditoría se cambia "privacidad" a "PUBLIC_TO_EVERYONE" en tiktok_config.json.

Secretos de GitHub que usa (los pega Salo; Claude nunca los ve):
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
  GH_SECRETS_PAT (opcional): token de GitHub con permiso "Secrets: write" en este
  repositorio, para guardar solo el refresh token nuevo si TikTok lo cambia.
"""
import os, sys, json, time, datetime, base64
from pathlib import Path
import requests

BASE = Path(__file__).parent
SCHED = BASE / "schedule.json"
CONF = BASE / "tiktok_config.json"
APROB7 = BASE.parent / "Contenido" / "aprobados_semana7.json"
ERRORES = BASE / "errores_corrida.txt"
LOG = BASE / "publicaciones.log"
API = "https://open.tiktokapis.com/v2"
MAX_INTENTOS = 3
MB = 1024 * 1024


def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] [TikTok] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def save(sched):
    json.dump(sched, open(SCHED, "w"), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- tokens
def refrescar_token():
    r = requests.post(f"{API}/oauth/token/", timeout=30,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"client_key": os.environ["TIKTOK_CLIENT_KEY"],
                            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
                            "grant_type": "refresh_token",
                            "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"]})
    d = r.json()
    if "access_token" not in d:
        raise RuntimeError(f"No se pudo renovar el permiso de TikTok: {d.get('error')} {d.get('error_description')}")
    nuevo = d.get("refresh_token")
    if nuevo and nuevo != os.environ["TIKTOK_REFRESH_TOKEN"]:
        guardar_refresh_token(nuevo)
    return d["access_token"]


def guardar_refresh_token(valor):
    """TikTok puede entregar un refresh token nuevo; hay que guardarlo para la próxima corrida."""
    pat = os.environ.get("GH_SECRETS_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not pat or not repo:
        raise RuntimeError("TikTok entregó un refresh token nuevo y no hay GH_SECRETS_PAT para guardarlo. "
                           "Hay que generar el permiso otra vez con Herramientas/tiktok_tokens.py.")
    from nacl import encoding, public
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    k = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=h, timeout=30).json()
    box = public.SealedBox(public.PublicKey(k["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(valor.encode())).decode()
    r = requests.put(f"https://api.github.com/repos/{repo}/actions/secrets/TIKTOK_REFRESH_TOKEN", headers=h,
                     json={"encrypted_value": enc, "key_id": k["key_id"]}, timeout=30)
    if r.status_code not in (201, 204):
        raise RuntimeError(f"No se pudo guardar el refresh token nuevo en GitHub ({r.status_code}).")
    os.environ["TIKTOK_REFRESH_TOKEN"] = valor
    log("Refresh token renovado y guardado en los secretos de GitHub.")


# ---------------------------------------------------------------- API
def _post(token, path, body):
    r = requests.post(f"{API}{path}", timeout=60, json=body,
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json; charset=UTF-8"})
    d = r.json()
    err = d.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise RuntimeError(f"{path}: {err.get('code')} {err.get('message')}")
    return d.get("data", {})


def creator_info(token):
    return _post(token, "/post/publish/creator_info/query/", {})


def subir_video(token, ruta, titulo, privacidad):
    size = os.path.getsize(ruta)
    if size <= 64 * MB:
        chunk, n = size, 1
    else:
        chunk = 10 * MB
        n = size // chunk           # el último trozo absorbe el resto
    data = _post(token, "/post/publish/video/init/", {
        "post_info": {"title": titulo, "privacy_level": privacidad,
                      "disable_duet": False, "disable_comment": False, "disable_stitch": False,
                      "video_cover_timestamp_ms": 1000},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                        "chunk_size": chunk, "total_chunk_count": n}})
    pid, url = data["publish_id"], data["upload_url"]
    with open(ruta, "rb") as f:
        for i in range(n):
            ini = i * chunk
            fin = size - 1 if i == n - 1 else ini + chunk - 1
            f.seek(ini); parte = f.read(fin - ini + 1)
            r = requests.put(url, data=parte, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(parte)),
                "Content-Range": f"bytes {ini}-{fin}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"Fallo subiendo el trozo {i + 1} de {n}: HTTP {r.status_code} {r.text[:200]}")
    return pid


def estado(token, publish_id):
    return _post(token, "/post/publish/status/fetch/", {"publish_id": publish_id})


def esperar(token, publish_id, maximo=240):
    t0 = time.time()
    while time.time() - t0 < maximo:
        d = estado(token, publish_id)
        s = d.get("status")
        if s == "PUBLISH_COMPLETE":
            return "ok", d
        if s == "FAILED":
            return "fallo", d
        time.sleep(10)
    return "pendiente", {}


# ---------------------------------------------------------------- principal
def titulo_de(piece):
    t = piece["caption"].strip() + "\n\n" + (piece.get("hash") or "")
    t = t.strip()
    return t if len(t.encode("utf-16-le")) // 2 <= 2200 else t[:2150].rsplit(" ", 1)[0] + "..."


def ruta_video(it):
    import calendario
    rutas = calendario.paths_publicables(it)
    if not rutas:
        raise RuntimeError("El video no está en el repositorio")
    return str(rutas[0])


def main():
    if not os.environ.get("TIKTOK_CLIENT_KEY"):
        print("TikTok sin configurar (falta TIKTOK_CLIENT_KEY): no hago nada.")
        return
    conf = json.load(open(CONF))
    if not conf.get("activo"):
        print("TikTok desactivado en tiktok_config.json.")
        return
    desde = datetime.datetime.strptime(conf["desde"], "%Y-%m-%d %H:%M")
    privacidad = conf.get("privacidad", "SELF_ONLY")
    sched = json.load(open(SCHED))
    p7 = {f"p{x['n']}": x for x in json.load(open(APROB7))["piezas"]}
    now = datetime.datetime.now()

    pendientes = []
    for it in sched["items"]:
        if it.get("tipo") != "post7" or it.get("pausado") or it.get("tiktok_omitir"):
            continue
        piece = p7.get(it["key"])
        if not piece or "Reel" not in piece.get("formato", ""):
            continue
        cuando = datetime.datetime.strptime(it["cuando"], "%Y-%m-%d %H:%M")
        if cuando < desde or cuando > now:
            continue
        if now - cuando > datetime.timedelta(hours=conf.get("max_atraso_horas", 48)):
            continue                           # muy viejo: no se publica de golpe
        tk = it.setdefault("tiktok", {})
        if tk.get("publicado") or tk.get("intentos", 0) >= MAX_INTENTOS:
            continue
        pendientes.append((it, piece))
    if not pendientes:
        print("TikTok: sin videos pendientes vencidos.")
        return

    token = refrescar_token()
    info = creator_info(token)
    opciones = info.get("privacy_level_options") or []
    if opciones and privacidad not in opciones:
        raise RuntimeError(f"La privacidad {privacidad} no está permitida para esta cuenta: {opciones}")

    for it, piece in pendientes:
        tk = it["tiktok"]; nombre = it["key"]
        try:
            if tk.get("publish_id"):           # ya se subió en una corrida anterior: solo revisar
                res, d = esperar(token, tk["publish_id"], maximo=30)
            else:
                ruta = ruta_video(it)
                log(f"▶ Subiendo {nombre} ({os.path.getsize(ruta) // MB} MB, {privacidad})")
                tk["publish_id"] = subir_video(token, ruta, titulo_de(piece), privacidad)
                save(sched)                    # guardar el publish_id evita subirlo dos veces
                res, d = esperar(token, tk["publish_id"])
            if res == "ok":
                tk["publicado"] = True
                tk["publicado_en"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                tk.pop("ultimo_error", None)
                log(f"✅ OK {nombre} en TikTok")
            elif res == "fallo":
                tk.pop("publish_id", None)
                raise RuntimeError(f"TikTok rechazó el video: {d.get('fail_reason')}")
            else:
                log(f"⏳ {nombre} sigue procesándose en TikTok; se revisa en la próxima corrida")
            save(sched)
        except Exception as e:
            tk["intentos"] = tk.get("intentos", 0) + 1
            tk["ultimo_error"] = f"{now:%Y-%m-%d %H:%M} {str(e)[:300]}"
            save(sched)
            log(f"❌ ERROR {nombre} en TikTok: {e}")
            with open(ERRORES, "a") as f:
                f.write(f"TikTok {it['cuando']} {nombre} (intento {tk['intentos']} de {MAX_INTENTOS}): {e}\n")


if __name__ == "__main__":
    sys.path.insert(0, str(BASE))
    try:
        main()
    except Exception as e:
        log(f"❌ ERROR general de TikTok: {e}")
        with open(ERRORES, "a") as f:
            f.write(f"TikTok: {e}\n")
