# Publicación en la nube — S&S Solutions

Este repositorio publica solo el contenido de S&S en Instagram y Facebook, desde un
servidor de GitHub que **nunca se apaga**. Ya no depende de que tu Mac esté encendido.

Tú solo tienes que hacer una configuración inicial (unos 15 minutos). Después, cero mantenimiento.

---

## Paso 1 · Subir esta carpeta a GitHub (con GitHub Desktop, lo más fácil)

1. Descarga e instala **GitHub Desktop**: https://desktop.github.com
2. Ábrelo y **crea una cuenta / inicia sesión** en GitHub (es gratis).
3. En GitHub Desktop: menú **File → Add local repository**.
4. Elige esta carpeta: `Documents/S&S/Nube`. Si te dice que no es un repositorio,
   haz clic en **"create a repository"** (crear repositorio aquí) y luego **Create repository**.
5. Arriba verás **"Publish repository"**. Haz clic.
6. **MUY IMPORTANTE:** deja marcada la casilla **"Keep this code private"** (privado).
   Ponle un nombre (ej: `ss-publicador`) y dale **Publish repository**.

Listo, tu contenido ya está en GitHub (en privado, solo tú lo ves).

---

## Paso 2 · Guardar las credenciales de Meta (en la "caja fuerte" de GitHub)

Estas son las mismas que ya tienes en tu archivo `Automatizacion/meta.env`.
Ábrelo con TextEdit para copiar los valores. GitHub los guarda encriptados; yo nunca los veo.

1. Entra a tu repositorio en https://github.com (te sale en tu lista).
2. Ve a **Settings** (Configuración) → menú izquierdo **Secrets and variables → Actions**.
3. Botón **New repository secret**. Crea estos **4 secretos** (nombre exacto + su valor):

   | Name (nombre exacto) | Value (cópialo de meta.env) |
   |---|---|
   | `IG_USER_ID` | el valor de IG_USER_ID |
   | `IG_ACCESS_TOKEN` | el valor de IG_ACCESS_TOKEN |
   | `META_PAGE_ID` | el valor de META_PAGE_ID |
   | `META_PAGE_TOKEN` | el valor de META_PAGE_TOKEN |

   (Uno por uno: pegas el nombre, pegas el valor, **Add secret**. Repite para los 4.)

---

## Paso 3 · Apagar el publicador de tu Mac (para que no se dupliquen)

Como ahora publica la nube, hay que apagar el de tu Mac. En la Terminal, pega:

```
launchctl unload ~/Library/LaunchAgents/com.ss.publisher.plist
```

(Si algún día quieres volver al de tu Mac, se reactiva con `launchctl load` en vez de `unload`.)

---

## Paso 4 · Probar que funciona

1. En tu repositorio de GitHub, ve a la pestaña **Actions** (arriba).
2. Si te pide habilitar los workflows, dale **"I understand… enable"**.
3. En la lista izquierda, clic en **"Publicar S&S Solutions"** → botón **Run workflow** → **Run workflow**.
4. Espera ~1 minuto y refresca. Debe aparecer una corrida en verde ✅.
   Si había algo pendiente y vencido, se publica; si no, dice "sin piezas pendientes".

¡Y listo! De ahí en adelante revisa **solo** cada 15 minutos y publica lo que toque, para siempre.

---

## Cómo sigue el día a día

- **Tú:** apruebas los textos de cada semana como siempre (conmigo).
- **Yo:** cuando aprobemos una semana nueva, subo las imágenes nuevas a este repositorio.
- **La nube:** publica todo solo, a sus horas, aunque tu Mac esté apagado.

## Nota
- El token de Meta caduca cada ~60 días. Cuando toque, se renueva y se actualiza el
  secreto `IG_ACCESS_TOKEN` (y `META_PAGE_TOKEN` si aplica) en GitHub. Te aviso antes.
- Horario: los posts salen dentro de ~15 min de su hora programada (hora Colombia).
