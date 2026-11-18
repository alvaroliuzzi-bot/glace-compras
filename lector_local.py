# -*- coding: utf-8 -*-
"""Glacé Compras · lector local de fotos de facturas (IA en esta computadora).

Busca en Biblioteca\\<mes>\\Manuales\\<día>\\ las facturas manuales que tienen fotos o PDF pero todavía no tienen
ítems, se las da a leer a la IA local (Bionic / LM Studio / Ollama, API compatible con OpenAI) y deja el resultado en
Biblioteca\\<mes>\\Manuales\\lecturas_ia_local_*.json. Glacé Compras toma ese archivo solo, completa los ítems,
los controla contra Marangatu y marca lo dudoso.

Para leer mejor:
- le pasa a la IA lo que ya se sabe de la factura (proveedor, RUC, número, fecha y total de Marangatu);
- prepara las fotos: las endereza según la cámara, sube el contraste y enfoca un poco (si está Pillow);
- un PDF con texto se lee como texto (más exacto; sirve hasta con un modelo sin visión);
- si la suma de los ítems no da el total, le pide a la IA que revise y corrija una vez más.

No usa internet: solo habla con la IA que corre en esta misma computadora (localhost).
Nunca toca lo que la persona cargó a mano: solo lee facturas sin ítems.

Prueba suelta:            py -3 lector_local.py --una-vez
Configuración opcional:   ia_local.json en esta carpeta, por ejemplo
    {"activo": true, "url": "http://127.0.0.1:1234/v1", "modelo": "qwen3-vl-8b-instruct", "modelo_texto": "qwen3-8b"}
"""
import os, sys, re, json, time, base64, hashlib, traceback, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.environ.get("GLACE_LIB_DIR") or os.path.join(HERE, "Biblioteca")
CONF_FILE = os.path.join(HERE, "ia_local.json")
STATE_FILE = os.path.join(LIB, ".ia_local_estado.json")
INBOX = os.path.join(LIB, "_Entrada_IA")   # fotos subidas solo para la IA: lee TODOS los datos y registra la factura
INBOX_EXT = ("jpg", "jpeg", "png", "webp", "gif", "pdf")

URLS = ["http://127.0.0.1:1235/v1",      # Bionic (servidor local de esta computadora)
        "http://127.0.0.1:1234/v1",      # LM Studio
        "http://127.0.0.1:11434/v1"]     # Ollama
MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
MAN_FILE = re.compile(r"^([0-9A-Za-z_\-]{1,150})_(\d{1,3})\.(jpg|png|webp|gif|pdf)$")
MONTH = re.compile(r"^20\d\d-(0[1-9]|1[0-2])$")
DAY = re.compile(r"^(20\d\d-\d\d-\d\d|Sin-fecha)$")
MAX_FOTOS = 4                 # fotos o páginas por factura que se mandan al modelo
MAX_LADO = 2000               # lado mayor de la foto: suficiente para leer letra chica sin hacer lento al modelo
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT = 900                 # en CPU un modelo con visión puede tardar varios minutos por factura
MAX_INTENTOS = 2              # intentos por factura antes de dejarla para carga manual
TOL = 0.01                    # 1 % de diferencia entre la suma de ítems y el total se acepta (redondeos)
VISION_HINT = ("vl", "vision", "llava", "gemma-3", "gemma3", "gemma-4", "gemma4", "minicpm-v", "pixtral", "moondream")

FORMA = """Devolvé SOLO un JSON, sin texto antes ni después, con esta forma:
{
 "read": {"proveedor": "razón social del emisor", "ruc": "80012345-6", "numero": "001-001-0000123", "timbrado": "12345678",
          "fecha": "DD/MM/AAAA", "condicion": "CONTADO", "total": 0, "iva10": 0, "iva5": 0, "exento": 0},
 "lines": [
  {"cod": "", "desc": "descripción del producto", "uni": "UNI", "cant": 1, "pu": 0, "dto": 0, "tot": 0, "tasa": 10, "dud": false, "why": ""}
 ],
 "conf": "alta",
 "note": ""
}
Reglas:
- Un elemento en "lines" por cada renglón de producto, en el mismo orden. No inventes renglones ni juntes renglones distintos.
- Copiá la descripción tal como está escrita (con marca, tamaño y presentación). No traduzcas.
- Importes en guaraníes como número entero, sin puntos ni "Gs" (63.200 -> 63200). Cantidades con decimales usan punto (1.5).
- "tasa": 10, 5 o 0 (exenta), según la columna de IVA donde figura el importe del renglón.
- "tot": importe del renglón; "pu": precio unitario; "cant": cantidad; "dto": descuento del renglón si hay.
- Revisá que cant x pu - dto = tot en cada renglón y que la suma de "tot" dé el total de la factura.
- Si un número o texto no se lee bien, poné tu mejor lectura, "dud": true y en "why" qué dudás (corto). No adivines en silencio.
- "read": datos del EMISOR (quien vende, arriba en la factura con su logo, RUC y timbrado), NO los del cliente.
  "numero" con el formato 001-001-0000123 (establecimiento-punto-número). "condicion": "CONTADO" o "CREDITO" según la casilla marcada.
  "total": el total a pagar; "iva10" / "iva5": la liquidación del IVA si figura; "exento": total exento si figura. Lo que no figure: "" o 0.
- "conf": "alta", "media" o "baja" según qué tan legible es.
- "note": observación corta si hace falta (foto cortada, borrosa, es otra factura, faltan páginas, etc.).
/no_think"""


def log(*a):
    print("[ia-local]", *a, flush=True)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"                     # «.tmp» no coincide con lecturas*.json: el programa no lo toma a medias
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def config():
    c = load_json(CONF_FILE, {})
    return c if isinstance(c, dict) else {}


def num(v):
    """63200, "63.200", "63,200", "Gs. 63.200", "1,5" -> número; None si no es un número."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = re.sub(r"[^\d.,\-]", "", str(v or ""))
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:                       # 1.234,5 -> 1234.5
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        a, b = s.rsplit(",", 1)
        s = a.replace(",", "") + ("." + b if len(b) != 3 else b)
    elif s.count(".") > 1 or re.search(r"\.\d{3}$", s):
        s = s.replace(".", "")                      # 63.200 -> 63200 (separador de miles)
    try:
        return float(s)
    except ValueError:
        return None


# ---------- conexión con la IA local
def http_json(url, body=None, timeout=10):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def find_server(cfg):
    """{"url", "vision", "texto"} si hay una IA local; {"why": motivo} si no."""
    urls = [cfg["url"].rstrip("/")] if cfg.get("url") else URLS
    for u in urls:
        try:
            ids = [str(m.get("id")) for m in (http_json(u + "/models", timeout=4).get("data") or []) if m.get("id")]
        except Exception:
            continue
        ids = [i for i in ids if "embed" not in i.lower()]
        vis = [i for i in ids if any(h in i.lower() for h in VISION_HINT)]
        vision = str(cfg.get("modelo") or "") or (vis[0] if vis else "")
        texto = str(cfg.get("modelo_texto") or "") or next((i for i in ids if i not in vis), vision)
        if vision and vision not in ids:
            return {"why": "el modelo «%s» no está cargado en la IA local (%s)" % (vision, ", ".join(ids) or "ninguno")}
        if not ids:
            return {"why": "la IA local responde, pero no tiene ningún modelo cargado"}
        return {"url": u, "vision": vision, "texto": texto, "ids": ids}
    return {"why": "no encontré la IA local. Abrí Bionic y activá la «API für lokale Modelle» (servidor local)."}


def chat(srv, model, messages):
    body = {"model": model, "temperature": 0, "max_tokens": 6000, "messages": messages}
    r = http_json(srv["url"] + "/chat/completions", body, timeout=TIMEOUT)
    return str(((r.get("choices") or [{}])[0].get("message") or {}).get("content") or "")


def parse_answer(text):
    """Saca el JSON de la respuesta del modelo (ignora <think>…</think> y ```json)."""
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    t = re.sub(r"```(?:json)?", "", t)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("la IA no devolvió un JSON")
    raw = re.sub(r",\s*([}\]])", r"\1", t[a:b + 1])          # comas sobrantes al final
    o = json.loads(raw)
    if not isinstance(o, dict) or not isinstance(o.get("lines"), list):
        raise ValueError("la respuesta no trae la lista de ítems")
    return o


# ---------- fotos y PDF
def prep_image(data):
    """Endereza, ajusta el tamaño, sube contraste y enfoca: la IA lee mejor letra chica y fotos con sombra.
    Devuelve (mime, bytes); (None, bytes originales) si Pillow no está o la imagen no se puede abrir."""
    try:
        from PIL import Image, ImageOps, ImageFilter
        import io
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max(im.size) > MAX_LADO:
            im.thumbnail((MAX_LADO, MAX_LADO), Image.LANCZOS)
        elif max(im.size) < 1000:                         # foto muy chica: se agranda para que la letra no se pierda
            f = 1000.0 / max(im.size)
            im = im.resize((int(im.width * f), int(im.height * f)), Image.LANCZOS)
        im = ImageOps.autocontrast(im, cutoff=1)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=3))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return "image/jpeg", buf.getvalue()
    except Exception:
        return None, data


def read_files(fotos):
    """Imágenes [(mime, b64)] y texto de PDFs con capa de texto."""
    imgs, textos = [], []
    for path, ext in fotos:
        try:
            if ext == "pdf":
                try:
                    import fitz                       # PyMuPDF (opcional)
                except Exception:
                    log("PDF sin leer (instalá PyMuPDF: py -3 -m pip install --user pymupdf):", os.path.basename(path))
                    continue
                doc = fitz.open(path)
                txt = "\n".join(p.get_text() for p in doc)[:20000]
                if len(txt.strip()) > 150:            # PDF con texto: se lee como texto (exacto)
                    textos.append(txt)
                else:                                 # PDF escaneado: sus páginas van como imágenes
                    for p in list(doc)[:MAX_FOTOS]:
                        mime, data = prep_image(p.get_pixmap(dpi=200).tobytes("png"))
                        imgs.append((mime or "image/png", base64.b64encode(data).decode("ascii")))
                continue
            with open(path, "rb") as f:
                data = f.read()
            mime, data2 = prep_image(data)
            mime = mime or MIME.get(ext, "image/jpeg")
            if len(data2) > MAX_BYTES:
                log("foto demasiado grande y sin Pillow para achicarla, se salta:", os.path.basename(path))
                continue
            imgs.append((mime, base64.b64encode(data2).decode("ascii")))
        except Exception:
            traceback.print_exc()
    return imgs[:MAX_FOTOS], textos


def hints(head):
    """Lo que ya se sabe de la factura por Marangatu: ayuda a la IA a ubicarse y a no confundir números."""
    h = head if isinstance(head, dict) else {}
    parts = []
    for k, lab in (("proveedor", "Proveedor"), ("ruc", "RUC del proveedor"), ("numero", "Número de factura"),
                   ("timbrado", "Timbrado"), ("fecha", "Fecha"), ("total", "Total"), ("condicion", "Condición")):
        v = h.get(k)
        if v not in (None, "", 0):
            parts.append("%s: %s" % (lab, v))
    if not parts:
        return ""
    return ("Datos que ya conocemos de esta factura (de Marangatu). Usalos para ubicarte y para controlar, "
            "pero escribí lo que dice la factura; si algo no coincide, anotalo en \"note\":\n- " + "\n- ".join(parts) + "\n\n")


def check(o, head):
    """Problemas de la lectura que vale la pena hacer revisar a la IA ([] si está bien)."""
    probs = []
    total = 0.0
    for i, l in enumerate(o.get("lines") or [], 1):
        if not isinstance(l, dict):
            continue
        t, c, p, d = num(l.get("tot")), num(l.get("cant")), num(l.get("pu")), num(l.get("dto")) or 0
        if t is None:
            probs.append("el renglón %d no tiene importe" % i)
            continue
        total += t
        if c and p and abs(c * p - d - t) > max(2, abs(t) * TOL):
            probs.append("renglón %d: %s x %s - %s = %s, pero dice %s" % (i, c, p, d, round(c * p - d), t))
    rd = o.get("read") if isinstance(o.get("read"), dict) else {}
    ref = num(rd.get("total")) or num((head or {}).get("total") if isinstance(head, dict) else None)
    if ref and abs(total - ref) > max(2, ref * TOL):
        probs.append("la suma de los ítems da %s y el total de la factura es %s" % (round(total), round(ref)))
    return probs[:8]


# ---------- facturas pendientes
def has_lines(o):
    for l in o.get("lines") or []:
        if isinstance(l, dict) and str(l.get("desc") or "").strip() and (num(l.get("tot")) or 0) != 0:
            return True
    return False


def pending(state):
    """Facturas manuales con fotos y sin ítems: [(mes, clave, firma, [(ruta, ext)], json)]."""
    out = []
    if not os.path.isdir(LIB):
        return out
    for mdir in sorted(os.listdir(LIB), reverse=True):
        root = os.path.join(LIB, mdir, "Manuales")
        if not (MONTH.match(mdir) and os.path.isdir(root)):
            continue
        for day in sorted(os.listdir(root)):
            folder = os.path.join(root, day)
            if not (DAY.match(day) and os.path.isdir(folder)):
                continue
            names = sorted(os.listdir(folder))
            for fn in names:
                if not fn.lower().endswith(".json"):
                    continue
                o = load_json(os.path.join(folder, fn), None)
                if not (isinstance(o, dict) and isinstance(o.get("key"), str)) or has_lines(o) or o.get("lec"):
                    continue
                base = fn[:-5]
                fotos = sorted((int(m.group(2)), os.path.join(folder, g), m.group(3).lower())
                               for g in names for m in [MAN_FILE.match(g)] if m and m.group(1) == base)
                if not fotos:
                    continue
                firma = hashlib.sha1("|".join("%s:%d" % (p, os.path.getsize(p)) for _, p, _ in fotos).encode()).hexdigest()[:16]
                st = state.get(o["key"]) or {}
                if st.get("firma") == firma and (st.get("ok") or st.get("n", 0) >= MAX_INTENTOS):
                    continue                  # ya leída (o falló varias veces) con estas mismas fotos
                out.append((mdir, o["key"], firma, [(p, e) for _, p, e in fotos][:MAX_FOTOS], o))
    return out


def clean_lines(lines):
    keep = ("cod", "desc", "uni", "cant", "pu", "dto", "tot", "tasa", "dud", "why")
    out = []
    for l in lines[:200]:
        if not (isinstance(l, dict) and str(l.get("desc") or "").strip()):
            continue
        x = {k: l[k] for k in keep if k in l}
        for k in ("cant", "pu", "dto", "tot", "tasa"):     # números «63.200» -> 63200 para que el programa no dude
            if k in x and num(x[k]) is not None:
                v = num(x[k])
                x[k] = int(v) if v == int(v) else v
        out.append(x)
    return out


def leer(srv, fotos, head):
    """Lee una factura completa. Devuelve (json, modelo, revisada, problemas_restantes, ítems_limpios)."""
    imgs, textos = read_files(fotos)
    if imgs and not srv.get("vision"):
        imgs = []                                       # sin modelo que vea: solo sirve lo que haya en texto
    if not imgs and not textos:
        raise ValueError("ninguna foto o PDF se pudo usar (¿falta un modelo que lea fotos?)")
    model = srv["vision"] if imgs else srv["texto"]
    intro = hints(head) + "Leé esta factura de compra de Paraguay. "
    if textos:
        intro += "Este es el texto del PDF:\n\n" + "\n\n".join(textos) + "\n\n"
    if imgs:
        intro += "Mirá la(s) foto(s) adjunta(s). "
    intro += FORMA
    content = [{"type": "text", "text": intro}] + [
        {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (m, b)}} for m, b in imgs]
    msgs = [{"role": "user", "content": content if imgs else intro}]
    t0 = time.time()
    ans = chat(srv, model, msgs)
    try:
        o = parse_answer(ans)
    except Exception as e:                              # respuesta sin JSON válido: se le pide una vez más
        msgs += [{"role": "assistant", "content": ans[:4000]},
                 {"role": "user", "content": "Tu respuesta no es un JSON válido (%s). Devolvé SOLO el JSON pedido. /no_think" % e}]
        ans = chat(srv, model, msgs)
        o = parse_answer(ans)
    probs = check(o, head)
    revisada = False
    if probs:                                           # la suma o algún renglón no cierra: segunda revisión
        msgs += [{"role": "assistant", "content": json.dumps(o, ensure_ascii=False)[:8000]},
                 {"role": "user", "content": "Revisá de nuevo la factura con cuidado. Encontré esto:\n- " + "\n- ".join(probs) +
                  "\nPuede faltar un renglón, sobrar uno o haber un número mal leído (8/3, 1/7, 0/6, 5/6, puntos de miles). "
                  "Corregí lo que esté mal leído; si la factura realmente dice eso, dejalo y marcá \"dud\": true. "
                  "Devolvé SOLO el JSON completo corregido. /no_think"}]
        try:
            o2 = parse_answer(chat(srv, model, msgs))
            if len(check(o2, head)) <= len(probs):
                o, revisada = o2, True
        except Exception:
            traceback.print_exc()
    lines = clean_lines(o.get("lines") or [])
    resto = check({"lines": lines, "read": o.get("read")}, head) if lines else []
    log("leída en %.0f s con %s: %d ítems%s" % (time.time() - t0, model, len(lines), " · " + "; ".join(resto) if resto else ""))
    return o, model, revisada, resto, lines


def read_one(srv, mk, key, fotos, head, state, firma):
    st = state.setdefault(key, {})
    if st.get("firma") != firma:
        st.clear()
    st.update({"firma": firma, "n": st.get("n", 0) + 1, "at": int(time.time())})
    o, model, revisada, resto, lines = leer(srv, fotos, head)
    if not lines:
        st["error"] = "la IA no encontró ítems"
        return None
    read = o.get("read") if isinstance(o.get("read"), dict) else {}
    conf = o.get("conf") if o.get("conf") in ("alta", "media", "baja") else "media"
    if resto and conf == "alta":
        conf = "media"
    note = "Leído por IA local (%s%s). " % (model, ", revisado" if revisada else "")
    if resto:
        note += "Controlar: " + "; ".join(resto[:3]) + ". "
    note += str(o.get("note") or "")
    st.update({"ok": True, "error": ""})
    return {"key": key, "month": mk, "read": read, "lines": lines, "conf": conf, "note": note[:600],
            "files": [os.path.basename(p) for p, _ in fotos]}


avisar = [False]              # la persona apretó «Leer fotos con IA»: se le contesta aunque no haya nada
_entregadas = set()           # fotos de la entrada ya leídas y entregadas al programa (esperan su confirmación)


def inbox_files():
    try:
        return [os.path.join(INBOX, f) for f in sorted(os.listdir(INBOX))
                if f.rsplit(".", 1)[-1].lower() in INBOX_EXT and os.path.isfile(os.path.join(INBOX, f))
                and os.path.join(INBOX, f) not in _entregadas]
    except OSError:
        return []


def entregar_archivo(path, text, msg=""):
    """Sin el programa (prueba suelta): deja la lectura al lado de la foto."""
    write_atomic(path + ".ia.json", text or json.dumps({"error": msg}, ensure_ascii=False))


def run_inbox(srv, say, deliver):
    """Fotos subidas solo para la IA: se lee todo (cabecera + ítems) y se entrega al programa para registrar."""
    n = 0
    fotos = inbox_files()
    for i, path in enumerate(fotos):
        if time.time() - os.path.getmtime(path) < 2:     # todavía copiándose
            continue
        say("IA local: leyendo foto %d de %d (%s)… puede tardar unos minutos" % (i + 1, len(fotos), os.path.basename(path)))
        _entregadas.add(path)
        try:
            ext = path.rsplit(".", 1)[-1].lower()
            o, model, revisada, resto, lines = leer(srv, [(path, "jpg" if ext == "jpeg" else ext)], None)
            o["lines"] = lines
            o["conf"] = o.get("conf") if o.get("conf") in ("alta", "media", "baja") else "media"
            if resto and o["conf"] == "alta":
                o["conf"] = "media"
            o["note"] = ("Leído por IA local (%s%s). " % (model, ", revisado" if revisada else "")
                         + ("Controlar: " + "; ".join(resto[:3]) + ". " if resto else "") + str(o.get("note") or ""))[:600]
            deliver(path, json.dumps(o, ensure_ascii=False), "")
            n += 1
        except Exception as e:
            traceback.print_exc()
            deliver(path, None, str(e)[:200])
    return n


def run_once(status=None, deliver=None):
    """Lee las fotos de la entrada y las facturas pendientes. Devuelve cuántas se leyeron.
    status(msg) recibe mensajes para la pantalla; deliver(ruta, json, error) entrega las lecturas de la entrada."""
    say = status or log
    cfg = config()
    if cfg.get("activo") is False:
        return 0
    n_in = 0
    if inbox_files():
        srv = find_server(cfg)
        if srv.get("url"):
            n_in = run_inbox(srv, say, deliver or entregar_archivo)
        elif not status:
            say("IA local: hay fotos en _Entrada_IA, pero " + srv["why"])
    state = load_json(STATE_FILE, {})
    state = state if isinstance(state, dict) else {}
    todo = pending(state)
    if not todo:
        return n_in
    srv = find_server(cfg)
    if not srv.get("url"):
        if not status:      # en el programa, la etiqueta de estado de la IA ya lo muestra
            say("IA local: hay %d factura(s) con foto sin leer, pero %s" % (len(todo), srv["why"]))
        return n_in
    n = 0
    for i, (mk, key, firma, fotos, o) in enumerate(todo):
        prov = (o.get("head") or {}).get("proveedor") if isinstance(o.get("head"), dict) else ""
        say("IA local: leyendo factura %d de %d (%s)… puede tardar unos minutos" % (i + 1, len(todo), prov or "sin nombre"))
        try:
            item = read_one(srv, mk, key, fotos, o.get("head"), state, firma)
        except Exception as e:
            traceback.print_exc()
            state.setdefault(key, {})["error"] = str(e)[:200]
            item = None
        write_atomic(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=1))
        if item:
            name = "lecturas_ia_local_%s_%s.json" % (time.strftime("%Y%m%d_%H%M%S"), hashlib.sha1(key.encode()).hexdigest()[:6])
            write_atomic(os.path.join(LIB, mk, "Manuales", name),
                         json.dumps({"by": "IA local", "items": [item]}, ensure_ascii=False, indent=1))
            n += 1
    say("IA local: %d factura(s) leída(s). Revisá los ítems marcados como dudosos." % n if n
        else "IA local: no pude leer las fotos pendientes (ver glace_log.txt).")
    return n + n_in


def estado():
    """(lista, texto corto) para mostrar en la barra del programa."""
    cfg = config()
    if cfg.get("activo") is False:
        return False, "IA local: apagada (ia_local.json)"
    srv = find_server(cfg)
    if srv.get("url"):
        if srv.get("vision"):
            return True, "IA local: lista · %s" % srv["vision"]
        return False, "IA local: solo lee PDF con texto · falta un modelo que lea fotos (Qwen3-VL-8B)"
    if "no encontré" in srv["why"]:
        return False, "IA local: abrí Bionic y encendé su servidor local"
    return False, "IA local: " + srv["why"][:90]


def watch(status=None, every=20, stop=None, wake=None, on_estado=None, deliver=None):
    """Bucle para correr en segundo plano dentro de Glacé Compras.
    wake: Event que despierta el bucle enseguida (botón «Leer fotos con IA»).
    on_estado(lista, texto): estado de la IA para la barra del programa."""
    last = None
    while not (stop and stop.is_set()):
        try:
            if on_estado:
                st = estado()
                if st != last:
                    last = st
                    on_estado(*st)
            pedido = avisar[0]
            avisar[0] = False
            n = run_once(status, deliver)
            if pedido and status and not n:
                status("IA local: no hay facturas con foto sin ítems para leer." if last and last[0]
                       else (last[1] if last else "IA local: no disponible"))
        except Exception:
            traceback.print_exc()
        for _ in range(every):
            if stop and stop.is_set():
                return
            if wake and wake.is_set():
                wake.clear()
                break
            time.sleep(1)


def confirmar(path):
    """El programa registró (o descartó) la foto: ya se puede volver a mirar ese nombre."""
    _entregadas.discard(path)


if __name__ == "__main__":
    if "--una-vez" in sys.argv:
        print("Facturas leídas:", run_once())
    else:
        watch()
