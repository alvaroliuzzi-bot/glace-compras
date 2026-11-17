# -*- coding: utf-8 -*-
"""Glacé Compras · programa de escritorio (versión con 4 portales).

Izquierda: Glacé Compras. Derecha: 4 portales de e-Kuatia (cuadrícula 2 x 2).
La persona solo marca «No soy un robot» en cada portal; el resto lo hace el programa:
escribir la CDC, Consultar, Descargar el XML, guardarlo en la biblioteca y preparar
la siguiente factura en el mismo portal (rondas de 4)."""
import os, sys, re, json, time, shutil, tempfile, traceback, faulthandler, base64, hashlib
from collections import deque
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
try:
    _LOG = open(os.path.join(_HERE, "glace_log.txt"), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _LOG
    faulthandler.enable(file=_LOG)
except Exception:
    _LOG = None


def _excepthook(t, v, tb):
    """Un error inesperado en una señal de Qt no debe cerrar el programa: se anota en el log y sigue."""
    try:
        traceback.print_exception(t, v, tb)
    except Exception:
        pass


sys.excepthook = _excepthook

try:
    from PyQt6.QtCore import Qt, QUrl, QTimer, QStandardPaths, QLockFile
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QSplitter, QLabel, QWidget,
                                 QVBoxLayout, QHBoxLayout, QPushButton, QSizePolicy)
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
                                       QWebEngineDownloadRequest)
except Exception:
    traceback.print_exc()
    raise

HERE = os.path.dirname(os.path.abspath(__file__))
try:                                   # lector de fotos con IA local (lector_local.py); si falta, el programa sigue igual
    sys.path.insert(0, HERE)
    import lector_local
except Exception:
    traceback.print_exc()
    lector_local = None
HTML = os.path.join(HERE, "Glace_Compras.html")
HELP = os.path.join(HERE, "ek_helpers.js")
ICON = os.path.join(HERE, "Glace_Compras.ico")

EK_URL = "https://ekuatia.set.gov.py/consultas/"
_t = os.environ.get("GLACE_EK_URL", "")
if re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/", _t):      # solo para pruebas locales
    EK_URL = _t
EK_BASE = re.sub(r"/consultas/?$", "", EK_URL)
PROFILE_SUFFIX = os.environ.get("GLACE_PROFILE_SUFFIX", "")
# Biblioteca en disco: Biblioteca\<AAAA-MM>\Excel, \XML\<AAAA-MM-DD>, \Manuales\<AAAA-MM-DD> (facturas sin CDC: foto + detalle) y \Exportado
LIB = os.environ.get("GLACE_LIB_DIR") or os.path.join(HERE, "Biblioteca")
LEGACY_XML = os.path.join(HERE, "XML_Facturas")     # carpeta de versiones anteriores (se copia a la biblioteca)
CDC_FILE = re.compile(r"^(\d{44})\.xml$", re.I)
IA_INBOX = os.path.join(LIB, "_Entrada_IA")     # fotos para que la IA local lea todo y registre la factura sola
IA_EXT = ("jpg", "png", "webp", "gif", "pdf")

NLANES = 4          # 4 portales de e-Kuatia, en cuadrícula 2 x 2
ZOOM = 0.5          # cada portal se ve reducido para que entre el formulario y el Häkchen
HEAD_IDLE = "background:#2A1D24;color:#cdbfc6;padding:3px 8px;font-size:12px"
HEAD_GO = "background:#B8447D;color:#ffffff;padding:3px 8px;font-size:12px;font-weight:bold"
HEAD_BUSY = "background:#2F5E36;color:#ffffff;padding:3px 8px;font-size:12px"
PARKED_HTML = ("<html><body style='margin:0;background:#1f171c;color:#9c8b94;font:28px sans-serif;"
               "display:flex;align-items:center;justify-content:center;height:100vh'>"
               "Portal %d en reposo · se abre solo al consultar facturas</body></html>")
BTN_SKIP = ("QPushButton{background:#3a2a33;color:#e8dde3;border:0;padding:3px 10px;font-size:12px}"
            "QPushButton:hover{background:#55404c}")


DESK_OK = os.path.join(HERE, ".escritorio_ok")


def refresh_desktop():
    """Avisa a Windows que el escritorio cambió (como pulsar F5): quita iconos viejos.
    Hace falta una sola vez (después de crear el acceso directo) y corre aparte: Windows recarga los
    íconos de todo el sistema y, si el programa lo esperara, la ventana se trababa al arrancar."""
    if os.path.exists(DESK_OK):
        return
    threading.Thread(target=_refresh_desktop, daemon=True, name="escritorio").start()


def _refresh_desktop():
    t0 = time.time()
    try:
        import ctypes
        sh = ctypes.windll.shell32
        sh.SHChangeNotify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        SHCNE_UPDATEDIR, SHCNE_ASSOCCHANGED = 0x00001000, 0x08000000
        SHCNF_PATHW, SHCNF_FLUSH = 0x0005, 0x1000
        home = os.path.expanduser("~")
        seen = set()
        for d in (os.path.dirname(HERE), os.path.join(home, "OneDrive", "Desktop"), os.path.join(home, "Desktop")):
            if d and os.path.isdir(d) and d.lower() not in seen:
                seen.add(d.lower())
                buf = ctypes.create_unicode_buffer(d)
                sh.SHChangeNotify(SHCNE_UPDATEDIR, SHCNF_PATHW | SHCNF_FLUSH, buf, None)
        sh.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_FLUSH, None, None)
        print("escritorio actualizado (%.0f ms, una sola vez)" % ((time.time() - t0) * 1000))
        with open(DESK_OK, "w", encoding="utf-8") as f:
            f.write("ok")
    except Exception:
        traceback.print_exc()


# ---------- biblioteca en disco (todo ordenado por mes y por día) ----------
def safe_month(m):
    """'AAAA-MM' válido o ''. Es lo único que se acepta del navegador para armar rutas."""
    m = str(m or "")
    return m if re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", m) else ""


def cdc_month(cdc):
    """Mes de emisión de una CDC (posiciones 26-31): 'AAAA-MM'."""
    return safe_month(cdc[25:29] + "-" + cdc[29:31])


def cdc_day(cdc):
    return cdc[25:29] + "-" + cdc[29:31] + "-" + cdc[31:33]


def write_atomic(path, data):
    """Escribe en un archivo temporal y lo renombra: un corte a mitad de camino no deja un XML a medias."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        with open(path, "wb") as f:           # carpeta sincronizada que bloquea el renombrado: se escribe directo
            f.write(data)


def lib_save_xml(month, cdc, data):
    """Guarda el XML en Biblioteca\\<mes>\\XML\\<día de emisión>\\<CDC>.xml (idempotente)."""
    if not re.fullmatch(r"\d{44}", str(cdc)):
        raise ValueError("CDC inválida")
    mes = safe_month(month) or cdc_month(cdc)
    if not mes:
        raise ValueError("mes inválido")
    path = os.path.join(LIB, mes, "XML", cdc_day(cdc), cdc + ".xml")
    write_atomic(path, data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def lib_save_misc_xml(month, name, data):
    """XML con otro nombre (por ejemplo, varios comprobantes en un archivo): Biblioteca\\<mes>\\XML\\Sueltos."""
    mes = safe_month(month) or time.strftime("%Y-%m")
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", os.path.basename(str(name))).strip(" .") or "factura.xml"
    if not base.lower().endswith(".xml"):
        base += ".xml"
    path = os.path.join(LIB, mes, "XML", "Sueltos", base)
    write_atomic(path, data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def lib_save_excel(month, name, data):
    """Guarda el Excel de Marangatu en Biblioteca\\<mes>\\Excel. Un archivo igual no se duplica;
    uno distinto del mismo mes se conserva con la fecha y hora de carga en el nombre."""
    mes = safe_month(month)
    if not mes:
        raise ValueError("mes inválido")
    folder = os.path.join(LIB, mes, "Excel")
    os.makedirs(folder, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(str(name)))
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", base).strip(" .") or "Marangatu"
    ext = ext.lower() if ext.lower() in (".xlsx", ".csv", ".txt") else ".xlsx"
    h = hashlib.sha1(data).hexdigest()
    for fn in os.listdir(folder):
        fp = os.path.join(folder, fn)
        try:
            if fn.lower().endswith((".xlsx", ".csv", ".txt")) and os.path.getsize(fp) == len(data):
                with open(fp, "rb") as f:
                    if hashlib.sha1(f.read()).hexdigest() == h:
                        return fp
        except OSError:
            pass
    stamp = time.strftime("%Y%m%d-%H%M")
    path = os.path.join(folder, "%s_%s%s" % (base, stamp, ext))
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "%s_%s_%d%s" % (base, stamp, n, ext))
        n += 1
    write_atomic(path, data)
    return path


def lib_unique(folder, name):
    """Nombre libre dentro de la carpeta: nunca pisa una exportación anterior."""
    base, ext = os.path.splitext(name)
    out, n = name, 2
    while os.path.exists(os.path.join(folder, out)):
        out = "%s_%d%s" % (base, n, ext)
        n += 1
    return out


def lib_folder(month, sub):
    """Carpeta de la biblioteca para abrir: la raíz, la de un mes o una de sus subcarpetas."""
    mes = safe_month(month)
    path = os.path.join(LIB, mes) if mes else LIB
    if mes and sub in ("Excel", "XML", "Exportado", "Manuales"):
        path = os.path.join(path, sub)
    return path


# ---------- facturas manuales (sin CDC): Biblioteca\<mes>\Manuales\<día>\<base>.json y <base>_<n>.<ext> ----------
MAN_TRASH = "_quitadas"                       # lo que la persona quita no se borra: se mueve acá
MAN_EXT = ("jpg", "png", "webp", "gif", "pdf")
MAN_FILE = re.compile(r"^([0-9A-Za-z_\-]{1,150})_(\d{1,3})\.(jpg|png|webp|gif|pdf)$")
MAN_JSON_MAX = 2 * 1024 * 1024                # el detalle de una factura es un texto chico
MAN_MAX = 40 * 1024 * 1024                    # tope por foto o PDF
MAN_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif", "pdf": "application/pdf"}


def safe_day(d):
    """'AAAA-MM-DD' (o 'Sin-fecha') válido o ''. Solo esto se acepta del navegador para armar rutas."""
    d = str(d or "")
    return d if re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])|Sin-fecha", d) else ""


def safe_base(b):
    b = str(b or "")
    return b if re.fullmatch(r"[0-9A-Za-z_\-]{1,150}", b) else ""


def man_trash(mes, day, fn):
    """Mueve un archivo de una factura manual a Manuales\\_quitadas\\<día> (nunca se borra nada)."""
    src = os.path.join(LIB, mes, "Manuales", day, fn)
    if not os.path.isfile(src):
        return
    tdir = os.path.join(LIB, mes, "Manuales", MAN_TRASH, day)
    os.makedirs(tdir, exist_ok=True)
    os.replace(src, os.path.join(tdir, lib_unique(tdir, fn)))


def lib_save_manual(c):
    """Guarda una factura manual: el detalle (.json) y sus fotos o PDF, por mes y por día.
    'from' = ubicación anterior si cambió la fecha o el número (los archivos se mueven);
    'drop' = fotos quitadas; 'remove' = se quitó toda la factura. Devuelve la carpeta."""
    mes, day, base = safe_month(c.get("month")), safe_day(c.get("day")), safe_base(c.get("base"))
    if not (mes and day and base):
        raise ValueError("datos de la factura inválidos")
    root = os.path.join(LIB, mes, "Manuales")
    folder = os.path.join(root, day)
    frm = c.get("from") if isinstance(c.get("from"), dict) else None
    fday, fbase = (safe_day(frm.get("day")), safe_base(frm.get("base"))) if frm else ("", "")
    if fday and fbase and (fday, fbase) != (day, base):          # cambió la fecha o el número: se mueve lo que ya estaba
        src = os.path.join(root, fday)
        if os.path.isdir(src):
            os.makedirs(folder, exist_ok=True)
            for fn in sorted(os.listdir(src)):
                m = MAN_FILE.match(fn)
                if fn == fbase + ".json":
                    dst = base + ".json"
                elif m and m.group(1) == fbase:
                    dst = "%s_%s.%s" % (base, m.group(2), m.group(3))
                else:
                    continue
                if not os.path.exists(os.path.join(folder, dst)):  # nunca se pisa otra factura
                    os.replace(os.path.join(src, fn), os.path.join(folder, dst))
            try:
                os.rmdir(src)
            except OSError:
                pass
    if c.get("remove"):                                             # se quitó la factura: todo va a _quitadas
        for where_day, where_base in {(day, base), (fday, fbase)}:
            if not (where_day and where_base):
                continue
            d = os.path.join(root, where_day)
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    m = MAN_FILE.match(fn)
                    if fn == where_base + ".json" or (m and m.group(1) == where_base):
                        man_trash(mes, where_day, fn)
        return folder
    text = str(c.get("json") or "")
    if not text or len(text.encode("utf-8")) > MAN_JSON_MAX:
        raise ValueError("el detalle de la factura está vacío o es demasiado grande")
    obj = json.loads(text)
    if not isinstance(obj, dict) or not isinstance(obj.get("key"), str):
        raise ValueError("detalle de factura inválido")
    write_atomic(os.path.join(folder, base + ".json"), text.encode("utf-8"))
    for f in (c.get("files") or [])[:40]:                           # fotos y PDF nuevos
        name = os.path.basename(str(f.get("name") or ""))
        m = MAN_FILE.match(name)
        if not m or m.group(1) != base:
            continue
        data = base64.b64decode(f.get("b64") or "")
        if data and len(data) <= MAN_MAX:
            write_atomic(os.path.join(folder, name), data)
    for name in (c.get("drop") or [])[:40]:                         # fotos quitadas: a _quitadas
        name = os.path.basename(str(name or ""))
        m = MAN_FILE.match(name)
        if m and m.group(1) == base:
            man_trash(mes, day, name)
    return folder


def man_open_path(month, day, name):
    """Ruta de una foto o PDF de la biblioteca para abrirla con el visor del equipo ('' si no existe o el nombre no vale)."""
    mes, d, name = safe_month(month), safe_day(day), str(name or "")
    if not (mes and d and name == os.path.basename(name) and MAN_FILE.match(name)):
        return ""
    p = os.path.join(LIB, mes, "Manuales", d, name)
    return p if os.path.isfile(p) else ""


def man_scan(known_keys, known_imgs):
    """Facturas manuales y fotos que están en la carpeta Biblioteca y la memoria del programa no conoce."""
    jobs_m, jobs_f = [], []
    try:
        for mdir in sorted(os.listdir(LIB), reverse=True):
            mk = safe_month(mdir)
            root = os.path.join(LIB, mdir, "Manuales")
            if not (mk and os.path.isdir(root)):
                continue
            for dday in sorted(os.listdir(root)):
                folder = os.path.join(root, dday)
                if not (safe_day(dday) and os.path.isdir(folder)):   # salta _quitadas y cualquier otra cosa
                    continue
                for fn in sorted(os.listdir(folder)):
                    base = fn[:-5]
                    if not (fn.lower().endswith(".json") and safe_base(base)):
                        continue
                    path = os.path.join(folder, fn)
                    try:
                        with open(path, "rb") as f:
                            raw = f.read(MAN_JSON_MAX + 1)
                        if len(raw) > MAN_JSON_MAX:
                            continue
                        o = json.loads(raw.decode("utf-8-sig"))
                    except Exception:
                        traceback.print_exc()
                        continue
                    if not (isinstance(o, dict) and isinstance(o.get("key"), str)):
                        continue
                    if o["key"] not in known_keys:
                        jobs_m.append(("manual", path, mk))
                    for fe in (o.get("files") or []) if isinstance(o.get("files"), list) else []:
                        try:
                            fid, n, ext = str(fe.get("id")), int(fe.get("n")), str(fe.get("ext"))
                        except Exception:
                            continue
                        if ext not in MAN_EXT or not re.fullmatch(r"[a-z0-9_\-]{6,48}", fid) or not (1 <= n < 1000) or fid in known_imgs:
                            continue
                        fp = os.path.join(folder, "%s_%d.%s" % (base, n, ext))
                        if os.path.isfile(fp):
                            jobs_f.append(("mfile", fp, fid, ext, str(fe.get("name") or "")))
    except OSError:
        traceback.print_exc()
    return jobs_m, jobs_f


# ---------- lecturas de fotos: Biblioteca\<mes>\Manuales\lecturas*.json ----------
# Quien lee las fotos (Claude, cuando la persona se lo pide en el chat) deja ahí un archivo con los ítems de cada factura.
# El programa lo entrega a la pantalla, que completa los ítems y los controla contra Marangatu; después lo archiva en Manuales\_leidas.
LEC_FILE = re.compile(r"^lecturas[0-9A-Za-z_\-]{0,80}\.json$", re.I)
LEC_DONE = "_leidas"
LEC_MAX = 1024 * 1024         # una lectura es texto: más de 1 MB no es una lectura
LEC_EVERY = 3                 # se mira la carpeta cada 3 ciclos (≈ 2 s)
LEC_SETTLE = 2.0              # un archivo recién escrito espera un momento por si todavía se está copiando
LEC_BAD_AFTER = 20.0          # si pasado este tiempo sigue ilegible, se archiva como error
LEC_WAIT = 90.0               # cuánto se espera la respuesta de la pantalla antes de volver a intentar
LEC_TRIES = 3                 # intentos con una misma lectura antes de archivarla como error


def lec_find():
    """Archivos de lecturas pendientes: [(fecha, mes, ruta)], el más viejo primero."""
    out = []
    try:
        for mdir in os.listdir(LIB):
            mk = safe_month(mdir)
            root = os.path.join(LIB, mdir, "Manuales")
            if not (mk and os.path.isdir(root)):
                continue
            for fn in os.listdir(root):
                p = os.path.join(root, fn)
                if LEC_FILE.match(fn) and os.path.isfile(p):
                    out.append((os.path.getmtime(p), mk, p))
    except OSError:
        traceback.print_exc()
    out.sort()
    return out


def lec_read(path):
    """(texto, '') si el archivo de lecturas sirve; ('', motivo) si no."""
    try:
        with open(path, "rb") as f:
            raw = f.read(LEC_MAX + 1)
        if len(raw) > LEC_MAX:
            return "", "el archivo es demasiado grande"
        text = raw.decode("utf-8-sig")
        o = json.loads(text)
    except Exception as e:
        return "", "no se pudo leer (%s)" % str(e)[:80]
    if not (isinstance(o, dict) and isinstance(o.get("items"), list)):
        return "", "formato inválido (falta la lista «items»)"
    return text, ""


def lec_archive(path, tag=""):
    """Una lectura procesada no se borra: pasa a Manuales\\_leidas. Devuelve la ruta nueva ('' si no se pudo)."""
    try:
        d = os.path.join(os.path.dirname(path), LEC_DONE)
        os.makedirs(d, exist_ok=True)
        base, ext = os.path.splitext(os.path.basename(path))
        dst = os.path.join(d, lib_unique(d, base + tag + ext))
        os.replace(path, dst)
        return dst
    except OSError:
        traceback.print_exc()
        return ""


class Lane:
    """Un portal de e-Kuatia con su propia máquina de estados:
    free -> loading -> captcha (espera el Häkchen de la persona) -> result -> downloading -> free"""

    def __init__(self, main, idx):
        self.main = main
        self.idx = idx
        self.view = QWebEngineView()
        self.view.setPage(QWebEnginePage(main.ek_profile, self.view))
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        self.view.setZoomFactor(ZOOM)
        self.view.loadFinished.connect(self.on_loaded)
        # bloque visible: barra con el estado + botón «Saltar» + el portal
        self.box = QWidget()
        lay = QVBoxLayout(self.box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.head = QLabel("")
        self.head.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.head.setStyleSheet(HEAD_IDLE)
        self.skip_btn = QPushButton("Saltar")
        self.skip_btn.setStyleSheet(BTN_SKIP)
        self.skip_btn.setToolTip("Omitir esta factura y pasar a la siguiente")
        self.skip_btn.clicked.connect(self.on_skip)
        bl.addWidget(self.head, 1)
        bl.addWidget(self.skip_btn, 0)
        lay.addWidget(bar)
        lay.addWidget(self.view, 1)
        self.ready = False          # página de e-Kuatia recién cargada y sin usar
        self.pre = False            # precargando la página
        self.dl_taken = False
        self._style = None
        self._text = None
        self.reset()

    # ----- estado
    def reset(self):
        self.state = "free"
        self.item = None
        self.cdc = None
        self.t = time.time()
        self.busy = False
        self.fallback = False
        self.retry = False
        self.fill_tries = 0
        self.reveal_tries = 0
        self.revealed = False
        self.dl_taken = False
        self.refills = 0
        self.noinput_t = 0
        self.reloaded = False
        self.busy_t = 0
        self.seq = 0

    def set(self, st):
        self.state = st
        self.t = time.time()

    def free_up(self):
        """Libera el portal. Si quedan facturas en cola precarga e-Kuatia; si no, lo deja en reposo
        (una página vacía no gasta procesador ni memoria como e-Kuatia abierto)."""
        self.reset()
        if self.main.queue:
            self.prewarm()
        else:
            self.park()

    def park(self):
        self.ready = False
        self.pre = False
        self.view.setHtml(PARKED_HTML % (self.idx + 1))

    def prewarm(self):
        self.ready = False
        self.pre = True
        self.view.load(QUrl(EK_URL))

    def run(self, call, cb=None):
        src = self.main.helpers + ";" + call
        if cb:
            self.view.page().runJavaScript(src, cb)
        else:
            self.view.page().runJavaScript(src)

    # ----- encabezado
    def update_head(self):
        n = self.idx + 1
        lab = (self.item or {}).get("label", "")
        if len(lab) > 44:
            lab = lab[:43] + "…"
        st = self.state
        if st == "free":
            text, style = "Portal %d · libre" % n, HEAD_IDLE
        elif st == "loading":
            text, style = "Portal %d · abriendo… · %s" % (n, lab), HEAD_IDLE
        elif st == "captcha":
            text, style = "Portal %d · ◀ MARCÁ «No soy un robot» · %s" % (n, lab), HEAD_GO
        elif st == "result":
            text, style = "Portal %d · consultando… · %s" % (n, lab), HEAD_BUSY
        else:
            text, style = "Portal %d · descargando XML… · %s" % (n, lab), HEAD_BUSY
        if text != self._text:
            self._text = text
            self.head.setText(text)
            self.head.setToolTip((self.item or {}).get("label", ""))
        if style != self._style:
            self._style = style
            self.head.setStyleSheet(style)
        self.skip_btn.setVisible(st in ("loading", "captcha"))

    def on_skip(self):
        if self.state in ("loading", "captcha") and self.cdc:
            self.main.lane_fail(self, "Factura saltada.")

    # ----- carga y CDC
    def begin(self, item, seq):
        self.reset()
        self.item = item
        self.cdc = item["cdc"]
        self.seq = seq
        self.set("loading")
        if self.ready:                  # página fresca ya lista: se escribe la CDC de una vez
            self.ready = False
            self.fill()
        elif self.pre:                  # todavía cargando: on_loaded sigue solo
            pass
        else:
            self.view.load(QUrl(EK_URL))

    def on_loaded(self, ok):
        if self.state == "free":
            if self.pre:
                self.pre = False
                self.ready = bool(ok)
            return
        if self.state != "loading":
            return
        self.pre = False
        if not ok:
            if not self.retry:          # una navegación cancelada por otra también avisa «no ok»
                self.retry = True
                self.view.load(QUrl(EK_URL))
                return
            return self.main.lane_fail(self, "No se pudo abrir e-Kuatia (¿hay internet?).")
        self.fill()

    def fill(self):
        cdc = self.cdc
        self.run("window.__glFill(%s)" % json.dumps(cdc), lambda r, c=cdc: self.on_filled(r, c))

    def on_filled(self, res, cdc):
        if self.state != "loading" or self.cdc != cdc:
            return
        if res != "ok":                 # la página aún se está armando: reintenta unos segundos
            self.fill_tries += 1
            if self.fill_tries <= 14:
                QTimer.singleShot(500, lambda c=cdc: self.fill() if (self.state == "loading" and self.cdc == c) else None)
                return
            return self.main.lane_fail(self, "No encontré el campo CDC en e-Kuatia.")
        self.set("captcha")

    # ----- ciclo (lo llama el temporizador del programa)
    def poll(self, now):
        if self.state == "free":
            return
        if self.busy:
            if now - self.busy_t < 8:   # una respuesta de la página que nunca llegó no debe trabar el portal
                return
            self.busy = False
        cdc = self.cdc
        if self.state == "loading":
            if now - self.t > 45:
                self.main.lane_fail(self, "e-Kuatia tardó demasiado en abrir.")
        elif self.state == "captcha":
            self.go_busy()
            self.run("window.__glState()", lambda r, c=cdc: self.on_captcha(r, c))
        elif self.state == "result":
            if now - self.t > 30:
                return self.main.lane_fail(self, "e-Kuatia no devolvió la factura a tiempo.")
            self.go_busy()
            self.run("window.__glState()", lambda r, c=cdc: self.on_result(r, c))
        elif self.state == "downloading":
            if now - self.t > 12 and not self.fallback and cdc:
                self.fallback = True
                self.view.page().download(QUrl(EK_BASE + "/docs/documento-electronico-xml/" + cdc))
            if now - self.t > 40:
                self.main.lane_fail(self, "La descarga del XML no terminó.")

    def go_busy(self):
        self.busy = True
        self.busy_t = time.time()

    def parse(self, res, cdc, want):
        self.busy = False
        if self.state != want or self.cdc != cdc:
            return None
        try:
            return json.loads(res)
        except Exception:
            return None

    def on_captcha(self, res, cdc):
        st = self.parse(res, cdc, "captcha")
        if st is None:
            return
        if not st.get("input"):         # la página no muestra el formulario: tras 20 s se recarga una vez
            if not self.noinput_t:
                self.noinput_t = time.time()
            elif time.time() - self.noinput_t > 20 and not self.reloaded:
                self.reloaded = True
                self.noinput_t = 0
                self.retry = False
                self.fill_tries = 0
                self.set("loading")
                self.view.load(QUrl(EK_URL))
            return
        self.noinput_t = 0
        if st.get("val") != cdc and self.refills < 3:   # la página borró el campo: se vuelve a escribir
            self.refills += 1
            self.fill()
            return
        if not self.revealed and self.reveal_tries < 14:   # deja el Häkchen a la vista en el bloque chico
            self.reveal_tries += 1
            self.run("window.__glReveal()", lambda r: setattr(self, "revealed", r == "ok"))
        if st.get("captcha"):           # la persona ya marcó «No soy un robot»
            self.go_busy()
            self.run("window.__glConsult()", lambda r, c=cdc: self.on_consulted(r, c))

    def on_consulted(self, res, cdc):
        self.busy = False
        if self.state == "captcha" and self.cdc == cdc and res == "ok":
            self.set("result")

    def on_result(self, res, cdc):
        st = self.parse(res, cdc, "result")
        if st and st.get("dl"):
            self.set("downloading")     # antes del clic: así la descarga siempre encuentra su portal
            self.run("window.__glDownload()")


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Glacé Compras")
        if os.path.exists(ICON):
            self.setWindowIcon(QIcon(ICON))
        with open(HELP, "r", encoding="utf-8") as f:
            self.helpers = f.read()
        self.tmp = tempfile.mkdtemp(prefix="glace_xml_")
        self.queue = deque()
        self.total = self.done = self.ok = self.bad = 0
        self.seq = 0
        self.last_flight = None
        self.last_prog = None
        self.feed = deque()          # restauración desde la carpeta Biblioteca: XML y Excel que la memoria no conoce
        self.feed_total = self.feed_done = 0
        self.man_total = self.man_done = 0
        self.page_ready = False      # la pantalla ya se presentó (hello) y puede recibir lecturas de fotos
        self.lec_tick = 0
        self.lec_cur = None          # (ruta, nombre, mes, desde cuándo) de la lectura que la pantalla está procesando
        self.lec_tries = {}          # ruta -> intentos
        self.lec_dead = set()        # lecturas que no se pudieron archivar: no se vuelven a entregar
        try:
            os.makedirs(LIB, exist_ok=True)
        except OSError:
            traceback.print_exc()

        # --- perfiles (guardan datos entre sesiones)
        self.ui_profile = QWebEngineProfile("glace-ui" + PROFILE_SUFFIX, self)
        self.ui_profile.setHttpUserAgent(self.ui_profile.httpUserAgent() + " GlaceApp/1")
        self.ui_profile.downloadRequested.connect(self.on_ui_download)
        self.ek_profile = QWebEngineProfile("glace-ekuatia" + PROFILE_SUFFIX, self)
        self.ek_profile.setHttpUserAgent(re.sub(r" QtWebEngine/[\d.]+", "", self.ek_profile.httpUserAgent()))
        self.ek_profile.downloadRequested.connect(self.on_ek_download)

        # --- vistas
        self.left = QWebEngineView()
        self.left.loadStarted.connect(self.on_left_load)
        self.left.setPage(QWebEnginePage(self.ui_profile, self.left))
        s = self.left.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        self.lanes = [Lane(self, i) for i in range(NLANES)]
        rows = [QSplitter(Qt.Orientation.Horizontal) for _ in range((NLANES + 1) // 2)]
        for i, ln in enumerate(self.lanes):
            rows[i // 2].addWidget(ln.box)
        for r in rows:
            for k in range(r.count()):
                r.setStretchFactor(k, 1)
        self.right_col = QSplitter(Qt.Orientation.Vertical)
        for r in rows:
            self.right_col.addWidget(r)
            self.right_col.setStretchFactor(self.right_col.count() - 1, 1)
        self.left.load(QUrl.fromLocalFile(HTML))
        for ln in self.lanes:
            ln.park()                   # los portales se abren recién cuando hay facturas para consultar (arranque rápido)

        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self.left)
        sp.addWidget(self.right_col)
        sp.setStretchFactor(0, 10)
        sp.setStretchFactor(1, 11)
        sp.setSizes([700, 760])
        self.setCentralWidget(sp)
        self.lbl = QLabel("Listo.")
        self.statusBar().addWidget(self.lbl)
        self.ia_lbl = QLabel("IA local: buscando…")
        self.ia_lbl.setStyleSheet("padding:2px 10px;border-radius:9px;background:#3a2a33;color:#e8dde3")
        self.ia_lbl.setToolTip("Lee solas las fotos de facturas manuales sin ítems, con la IA de esta computadora (Bionic).")
        self.ia_btn = QPushButton("Leer fotos con IA")
        self.ia_btn.setToolTip("Buscar ya facturas con foto y sin ítems y leerlas con la IA local")
        self.ia_btn.clicked.connect(self.on_ia_now)
        self.statusBar().addPermanentWidget(self.ia_lbl)
        self.statusBar().addPermanentWidget(self.ia_btn)
        self.resize(1420, 880)
        self.showMaximized()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(700)

        # --- IA local: lee en segundo plano las fotos de facturas manuales sin ítems
        self.ia_msg = ""
        self.ia_shown = ""
        self.ia_stop = threading.Event()
        self.ia_wake = threading.Event()
        self.ia_out = deque()            # lecturas de la entrada que esperan ser registradas en la pantalla
        self.ia_cur = None               # (ruta, nombre, desde cuándo, json) que la pantalla está registrando
        self.ia_state = None             # (lista, texto) que manda el hilo de la IA
        self.ia_state_shown = None
        if lector_local:
            def _ia_status(msg):
                print(msg)
                self.ia_msg = msg
            def _ia_estado(ok, text):
                print(text)
                self.ia_state = (ok, text)
            def _ia_deliver(path, text, err):
                self.ia_out.append((path, text, err))
            threading.Thread(target=lector_local.watch,
                             kwargs={"status": _ia_status, "stop": self.ia_stop, "wake": self.ia_wake, "on_estado": _ia_estado,
                                     "deliver": _ia_deliver},
                             daemon=True, name="ia-local").start()
        else:
            self.ia_state = (False, "IA local: falta lector_local.py")

    # ---------- utilidades
    def js_left(self, call):
        self.left.page().runJavaScript(call)

    def on_left_load(self):
        """La pantalla se está (re)cargando: hasta su próximo hello no se le entregan lecturas."""
        self.page_ready = False
        self.lec_cur = None

    def lane_by_cdc(self, cdc, states):
        for ln in self.lanes:
            if ln.cdc == cdc and ln.state in states:
                return ln
        return None

    # ---------- ciclo principal
    def tick(self):
        t0 = time.time()
        try:
            self._tick()
        finally:
            d = (time.time() - t0) * 1000
            if d > 40:
                print("programa: ciclo lento %.0f ms" % d)

    def _tick(self):
        self.left.page().runJavaScript("window.__takeOutbox ? window.__takeOutbox() : '[]'", self.on_outbox)
        now = time.time()
        for ln in self.lanes:
            ln.poll(now)
        self.pump()
        self.update_ui()
        self.feed_step()
        self.lec_step()
        if self.ia_msg != self.ia_shown:     # mensajes del lector de fotos con IA local
            self.ia_shown = self.ia_msg
            self.lbl.setText(self.ia_msg)
        self.ia_step()
        if self.ia_state and self.ia_state != self.ia_state_shown:
            self.ia_state_shown = self.ia_state
            ok, text = self.ia_state
            self.ia_lbl.setText(("● " if ok else "○ ") + text)
            self.ia_lbl.setStyleSheet("padding:2px 10px;border-radius:9px;color:#ffffff;background:%s" % ("#2F5E36" if ok else "#7a3b2e"))

    # ---------- fotos para la IA: Biblioteca\_Entrada_IA
    def ia_fotos(self, files):
        """La persona subió fotos solo para la IA: se dejan en la entrada y la IA empieza enseguida."""
        n = 0
        os.makedirs(IA_INBOX, exist_ok=True)
        for f in files[:40]:
            ext = str(f.get("ext") or "jpg").lower()
            if ext not in IA_EXT:
                continue
            base = re.sub(r"[^0-9A-Za-z_\- ]", "_", os.path.splitext(os.path.basename(str(f.get("name") or "foto")))[0])[:80] or "foto"
            data = base64.b64decode(f.get("b64") or "")
            if not data or len(data) > MAN_MAX:
                continue
            write_atomic(os.path.join(IA_INBOX, lib_unique(IA_INBOX, "%s.%s" % (base, ext))), data)
            n += 1
        if n:
            self.lbl.setText("IA local: %d foto(s) recibida(s), leyendo…" % n)
            self.ia_wake.set()

    def ia_move(self, path, sub):
        try:
            d = os.path.join(IA_INBOX, sub)
            os.makedirs(d, exist_ok=True)
            os.replace(path, os.path.join(d, lib_unique(d, os.path.basename(path))))
        except OSError:
            traceback.print_exc()
        if lector_local:
            lector_local.confirmar(path)

    def ia_step(self):
        """Entrega a la pantalla, de a una, las facturas que la IA leyó de la entrada."""
        if self.ia_cur:
            if time.time() - self.ia_cur[2] < 120:
                return
            print("IA local: la pantalla no confirmó", self.ia_cur[1])
            self.ia_out.appendleft((self.ia_cur[0], self.ia_cur[3], ""))
            self.ia_cur = None
        if not (self.ia_out and self.page_ready) or self.feed:
            return
        path, text, err = self.ia_out.popleft()
        name = os.path.basename(path)
        if not text or not os.path.isfile(path):
            if os.path.isfile(path):
                self.ia_move(path, "_no_leidas")
            self.lbl.setText("IA local: no pude leer «%s» (%s). Quedó en _Entrada_IA\\_no_leidas." % (name, err or "sin respuesta"))
            return
        ext = name.rsplit(".", 1)[-1].lower()
        mime = MAN_MIME.get("jpg" if ext == "jpeg" else ext, "image/jpeg")
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        self.ia_cur = (path, name, time.time(), text)
        self.lbl.setText("IA local: registrando «%s»…" % name)
        self.js_left("window.__iaFoto && window.__iaFoto(%s, %s, %s, %s)" % (json.dumps(text), json.dumps(data), json.dumps(mime), json.dumps(name)))

    def ia_done(self, c):
        cur = self.ia_cur
        if not cur or cur[1] != str(c.get("name") or ""):
            return
        self.ia_cur = None
        ok = bool(c.get("ok"))
        self.ia_move(cur[0], "_procesadas" if ok else "_no_leidas")
        msg = str(c.get("msg") or "")[:200]
        self.ia_msg = self.ia_shown = ""
        self.lbl.setText(("IA local: " + msg) if ok else ("IA local: no se pudo registrar «%s»: %s" % (cur[1], msg)))

    def on_ia_now(self):
        if not lector_local:
            self.lbl.setText("Falta el archivo lector_local.py en la carpeta del programa.")
            return
        self.lbl.setText("IA local: buscando facturas con foto sin ítems…")
        lector_local.avisar[0] = True
        self.ia_wake.set()

    def on_outbox(self, res):
        try:
            cmds = json.loads(res or "[]")
        except Exception:
            return
        for c in cmds:
            try:
                self.run_cmd(c)
            except Exception:                # un comando defectuoso no frena a los demás
                traceback.print_exc()

    def run_cmd(self, c):
        cmd = c.get("cmd")
        if cmd == "queue":
            items = []
            for x in c.get("items") or c.get("cdcs") or []:
                it = x if isinstance(x, dict) else {"cdc": x}
                if re.fullmatch(r"\d{44}", str(it.get("cdc", ""))):
                    it.setdefault("label", it["cdc"][-12:])
                    it["month"] = safe_month(it.get("month")) or cdc_month(it["cdc"])
                    items.append(it)
            self.start_queue(items)
        elif cmd == "stop":
            self.stop_all("Detenido. Las descargas ya marcadas terminan solas.")
        elif cmd == "hello":
            self.page_ready = True
            self.lec_cur = None
            self.lec_tries.clear()
            self.lib_sync(c.get("known") or {})
        elif cmd == "lecturasDone":
            self.lec_done(c)
        elif cmd == "perf":
            print("pantalla: %s %s ms (a los %.1f s)" % (c.get("what"), c.get("ms"), (c.get("at") or 0) / 1000.0))
        elif cmd == "iaFotos":
            self.ia_fotos(c.get("files") or [])
        elif cmd == "iaFotoDone":
            self.ia_done(c)
        elif cmd == "saveExcel":
            path = lib_save_excel(c.get("month"), c.get("name"), base64.b64decode(c.get("b64") or ""))
            self.lbl.setText("Excel guardado en la biblioteca: " + path)
        elif cmd == "saveXml":
            n = 0
            for f in c.get("files") or []:
                name = os.path.basename(str(f.get("name") or ""))
                data = str(f.get("text") or "").encode("utf-8")
                m = CDC_FILE.match(name)
                if m:
                    lib_save_xml(f.get("month"), m.group(1), data)
                else:
                    lib_save_misc_xml(f.get("month"), name, data)
                n += 1
            if n:
                self.lbl.setText("XML guardados en la biblioteca: %d." % n)
        elif cmd == "saveManual":
            key = str(c.get("key") or "")
            try:
                folder = lib_save_manual(c)
                self.lbl.setText("Factura manual guardada en la biblioteca: " + folder)
                if c.get("files") and not c.get("remove") and lector_local:   # foto nueva: la IA local la lee enseguida
                    self.lbl.setText("Foto guardada · la IA local empieza a leerla…")
                    self.ia_wake.set()
                self.js_left("window.__hostManualAck && window.__hostManualAck(%s, true, '')" % json.dumps(key))
            except Exception as e:
                traceback.print_exc()
                self.js_left("window.__hostManualAck && window.__hostManualAck(%s, false, %s)" % (json.dumps(key), json.dumps(str(e)[:160])))
        elif cmd == "openFile":
            path = man_open_path(c.get("month"), c.get("day"), c.get("name"))
            if not path:
                self.lbl.setText("No encontré esa foto en la biblioteca.")
            else:
                try:
                    os.startfile(path)           # solo Windows: la abre con el visor del equipo
                except AttributeError:
                    print("abrir archivo:", path)
        elif cmd == "openDir":
            path = lib_folder(c.get("month"), c.get("sub"))
            os.makedirs(path, exist_ok=True)
            try:
                os.startfile(path)           # solo Windows: abre la carpeta en el Explorador
            except AttributeError:
                print("abrir carpeta:", path)

    # ---------- biblioteca: restaurar lo que la memoria del programa no conoce
    def lib_say(self, msg):
        self.js_left("window.__hostLib && window.__hostLib(%s)" % json.dumps({"root": LIB, "msg": msg}))

    def lib_sync(self, known):
        """El navegador interno avisa qué conoce (CDC y meses). Se compara con la carpeta Biblioteca:
        los XML y el Excel de cada mes que falten se le entregan de a poco, sin trabar la pantalla."""
        self.feed.clear()
        have = set(str(x) for x in (known.get("cdcs") or []))
        months = known.get("months") or {}
        jobs_m, jobs_f = man_scan(set(str(x) for x in (known.get("man") or [])), set(str(x) for x in (known.get("imgs") or [])))
        jobs_x, jobs_e, seen = [], [], set()
        try:
            for mdir in sorted(os.listdir(LIB), reverse=True):          # meses nuevos primero
                mk = safe_month(mdir)
                if not mk:
                    continue
                ed = os.path.join(LIB, mdir, "Excel")
                if mk not in months and os.path.isdir(ed):
                    fs = [os.path.join(ed, f) for f in os.listdir(ed) if f.lower().endswith((".xlsx", ".csv", ".txt"))]
                    if fs:
                        jobs_e.append(("excel", max(fs, key=os.path.getmtime), mk, 1))
            for root, _dirs, files in os.walk(LIB):
                for fn in sorted(files):
                    if not fn.lower().endswith(".xml"):
                        continue
                    m = CDC_FILE.match(fn)
                    if m:
                        if m.group(1) in have or m.group(1) in seen:
                            continue
                        seen.add(m.group(1))
                    jobs_x.append(("xml", os.path.join(root, fn)))
        except OSError:
            traceback.print_exc()
        # carpeta de versiones anteriores: se copia a la biblioteca (ordenada) y, si hace falta, se entrega
        try:
            if os.path.isdir(LEGACY_XML):
                for fn in sorted(os.listdir(LEGACY_XML)):
                    fp = os.path.join(LEGACY_XML, fn)
                    m = CDC_FILE.match(fn)
                    if not (m and os.path.isfile(fp)) or not cdc_month(m.group(1)):
                        continue
                    cdc = m.group(1)
                    try:
                        dest = os.path.join(LIB, cdc_month(cdc), "XML", cdc_day(cdc), cdc + ".xml")
                        if not os.path.exists(dest):
                            with open(fp, "rb") as f:
                                lib_save_xml(cdc_month(cdc), cdc, f.read())
                        if cdc not in have and cdc not in seen:
                            seen.add(cdc)
                            jobs_x.append(("xml", dest))
                    except Exception:
                        traceback.print_exc()
                if not months and not jobs_e:          # memoria vacía y sin Excel en la biblioteca: se usa el viejo
                    fs = [os.path.join(LEGACY_XML, f) for f in os.listdir(LEGACY_XML) if f.lower().endswith(".xlsx")]
                    if fs:
                        jobs_e.append(("excel", max(fs, key=os.path.getmtime), "", 0))
        except Exception:
            traceback.print_exc()
        self.feed.extend(jobs_e)
        self.feed.extend(jobs_m)
        self.feed.extend(jobs_f)
        self.feed.extend(jobs_x)
        self.feed_total = len(jobs_x)
        self.feed_done = 0
        self.man_total = len(jobs_m) + len(jobs_f)
        self.man_done = 0
        print("biblioteca: %d Excel, %d facturas manuales (%d fotos) y %d XML por restaurar" % (len(jobs_e), len(jobs_m), len(jobs_f), len(jobs_x)))
        self.lib_say("Restaurando la biblioteca…" if self.feed else "")

    def feed_step(self):
        if not self.feed:
            return
        job = self.feed[0]
        if job[0] == "excel":
            self.feed.popleft()
            _, path, month, saved = job
            try:
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("ascii")
            except OSError:
                traceback.print_exc()
                return
            self.js_left("window.__ingestExcel && window.__ingestExcel(%s, %s, %s, %d)" % (
                json.dumps(os.path.basename(path)), json.dumps(data), json.dumps(month), saved))
            return
        if job[0] in ("manual", "mfile"):                  # facturas manuales y sus fotos, de a una
            self.feed.popleft()
            self.man_done += 1
            try:
                if job[0] == "manual":
                    with open(job[1], "rb") as f:
                        text = f.read().decode("utf-8-sig")
                    self.js_left("window.__ingestManual && window.__ingestManual(%s, %s)" % (json.dumps(text), json.dumps(job[2])))
                else:
                    _, path, fid, ext, name = job
                    if os.path.getsize(path) <= MAN_MAX:
                        with open(path, "rb") as f:
                            data = base64.b64encode(f.read()).decode("ascii")
                        self.js_left("window.__ingestManualFile && window.__ingestManualFile(%s, %s, %s, %s)" % (
                            json.dumps(fid), json.dumps(MAN_MIME.get(ext, "image/jpeg")), json.dumps(name), json.dumps(data)))
            except Exception:
                traceback.print_exc()
            if self.feed:
                self.lib_say("Restaurando facturas manuales: %d de %d…" % (self.man_done, self.man_total) if self.man_done <= self.man_total else "Restaurando la biblioteca…")
            else:
                self.lib_say("")
            return
        batch = []
        while self.feed and self.feed[0][0] == "xml" and len(batch) < 25:
            path = self.feed.popleft()[1]
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                batch.append([os.path.basename(path), raw.decode("utf-8-sig"), int(os.path.getmtime(path) * 1000)])
            except Exception:
                traceback.print_exc()
        self.feed_done += len(batch)
        if batch:
            self.js_left("window.__ingestMany && window.__ingestMany(%s)" % json.dumps(batch))
        if self.feed:
            self.lib_say("Restaurando la biblioteca: %d de %d XML…" % (self.feed_done, self.feed_total))
        else:
            self.lib_say("")
            print("biblioteca restaurada: %d XML" % self.feed_done)

    # ---------- lecturas de fotos (Manuales\lecturas*.json)
    def lec_step(self):
        """Entrega a la pantalla, de a una, las lecturas de fotos que haya en la biblioteca.
        Espera a que la pantalla se haya presentado y a que termine la restauración: así las facturas ya existen cuando llega la lectura."""
        self.lec_tick += 1
        if self.lec_tick % LEC_EVERY or not self.page_ready or self.feed:
            return
        now = time.time()
        if self.lec_cur:
            if now - self.lec_cur[3] < LEC_WAIT:
                return
            print("lecturas: la pantalla no respondió por", self.lec_cur[1])
            self.lec_cur = None                   # se vuelve a intentar (hasta LEC_TRIES veces)
        for mt, mk, path in lec_find():
            if path in self.lec_dead or now - mt < LEC_SETTLE:
                continue
            name = os.path.basename(path)
            text, err = lec_read(path)
            if err:
                if now - mt >= LEC_BAD_AFTER:     # antes de eso puede estar copiándose todavía
                    self.lec_fail(path, mk, name, err)
                continue
            n = self.lec_tries.get(path, 0) + 1
            self.lec_tries[path] = n
            if n > LEC_TRIES:
                self.lec_fail(path, mk, name, "la pantalla no la pudo procesar")
                continue
            self.lec_cur = (path, name, mk, now)
            self.lbl.setText("Lecturas de fotos: aplicando «%s»…" % name)
            self.js_left("window.__ingestLecturas && window.__ingestLecturas(%s, %s, %s)" % (json.dumps(text), json.dumps(name), json.dumps(mk)))
            return

    def lec_fail(self, path, mk, name, why):
        """Una lectura que no sirve no se borra: se archiva con el sufijo _ERROR y la pantalla lo avisa."""
        self.lec_tries.pop(path, None)
        if not lec_archive(path, "_ERROR"):
            self.lec_dead.add(path)
        self.js_left("window.__hostLecturas && window.__hostLecturas(%s)" % json.dumps({"name": name, "month": mk, "ok": False, "msg": why}))
        self.lbl.setText("Lecturas de fotos: «%s» no sirve (%s); quedó en Manuales\\%s." % (name, why, LEC_DONE))

    def lec_done(self, c):
        """La pantalla terminó de aplicar una lectura: el archivo pasa a Manuales\\_leidas."""
        cur = self.lec_cur
        if not cur or cur[1] != str(c.get("name") or ""):
            return
        self.lec_cur = None
        self.lec_tries.pop(cur[0], None)
        ok = bool(c.get("ok"))
        if not lec_archive(cur[0], "" if ok else "_ERROR"):
            self.lec_dead.add(cur[0])
        msg = str(c.get("msg") or "")[:160]
        self.lbl.setText(("Lecturas de fotos aplicadas: " if ok else "Lecturas de fotos con error: ") + msg)

    # ---------- cola y portales
    def start_queue(self, items):
        """Reemplaza la cola. Los portales que ya consultaron siguen hasta guardar su XML;
        los que todavía esperan el Häkchen se reinician con la nueva lista."""
        busy = {ln.cdc for ln in self.lanes if ln.state in ("result", "downloading")}
        for ln in self.lanes:
            if ln.state in ("loading", "captcha"):
                ln.free_up()
        self.queue = deque(it for it in items if it["cdc"] not in busy)
        self.total = len(self.queue) + len(busy)
        self.done = self.ok = self.bad = 0
        self.last_flight = None
        self.last_prog = None
        self.lbl.setText("Preparando e-Kuatia…")
        self.pump()

    def stop_all(self, msg):
        self.queue.clear()
        for ln in self.lanes:
            if ln.state in ("loading", "captcha"):
                ln.free_up()
        self.total = 0
        self.last_flight = None
        self.lbl.setText(msg)
        flight = [ln.cdc for ln in self.lanes if ln.cdc]
        self.js_left("window.__hostFlight && window.__hostFlight(%s, %s)" % (json.dumps(flight), json.dumps(msg)))

    def pump(self):
        for ln in self.lanes:
            if not self.queue:
                break
            if ln.state == "free":
                self.seq += 1
                ln.begin(self.queue.popleft(), self.seq)
        if self.total and not self.queue and all(ln.state == "free" for ln in self.lanes):
            msg = "Listo: %d factura(s) guardadas%s." % (self.ok, (" y %d con problema" % self.bad) if self.bad else "")
            self.total = 0
            self.last_flight = None
            self.lbl.setText(msg)
            self.js_left("window.__hostProg && window.__hostProg(%d, %d, %d, %d)" % (self.done, self.done, self.ok, self.bad))
            self.js_left("window.__hostDone && window.__hostDone(%s)" % json.dumps(msg))

    def update_ui(self):
        for ln in self.lanes:
            ln.update_head()
        flight = [ln.cdc for ln in self.lanes if ln.cdc]
        waiting = sum(1 for ln in self.lanes if ln.state == "captcha")
        key = (tuple(flight), waiting)
        if self.total and key != self.last_flight:
            self.last_flight = key
            if waiting:
                msg = ("Marcá «No soy un robot» en %s." %
                       ("el portal resaltado" if waiting == 1 else "los %d portales resaltados" % waiting))
            else:
                msg = "Consultando y descargando… la siguiente ronda se prepara sola."
            self.lbl.setText(msg)
            self.js_left("window.__hostFlight && window.__hostFlight(%s, %s)" % (json.dumps(flight), json.dumps(msg)))
        pk = (self.done, self.total, self.ok, self.bad)
        if self.total and pk != self.last_prog:
            self.last_prog = pk
            self.js_left("window.__hostProg && window.__hostProg(%d, %d, %d, %d)" % pk)

    def lane_fail(self, ln, msg):
        cdc = ln.cdc
        if not cdc:
            return
        label = (ln.item or {}).get("label", "")
        self.done += 1
        self.bad += 1
        ln.free_up()
        self.js_left("window.__hostFail && window.__hostFail(%s, %s)" % (json.dumps((msg + " · " + label) if label else msg), json.dumps(cdc)))
        self.pump()
        self.update_ui()

    def lane_done(self, ln, text, raw=None):
        cdc = ln.cdc
        month = (ln.item or {}).get("month")
        warn = ""
        try:                                   # primero a disco: Biblioteca\<mes>\XML\<día>\<CDC>.xml
            lib_save_xml(month, cdc, raw if raw is not None else text.encode("utf-8"))
        except Exception as e:
            traceback.print_exc()
            warn = " (no se pudo guardar en la carpeta Biblioteca: %s)" % e
        self.done += 1
        self.ok += 1
        ln.free_up()
        self.lbl.setText((("XML recibido (%d de %d)." % (self.ok, self.total)) if self.total else "XML recibido.") + warn)
        self.js_left("window.__ingest && window.__ingest(%s, %s, 1, %d)" % (json.dumps(cdc + ".xml"), json.dumps(text), int(time.time() * 1000)))
        if warn:
            self.lib_say("Atención: un XML no se pudo guardar en la carpeta Biblioteca.")
        self.pump()
        self.update_ui()

    # ---------- descargas de e-Kuatia
    def lane_for_download(self, dl):
        page = None
        try:
            page = dl.page()
        except Exception:
            pass
        if page is not None:
            for ln in self.lanes:
                if ln.view.page() == page and ln.state in ("result", "downloading"):
                    return ln
        m = re.search(r"\d{44}", dl.url().toString())
        if m:
            ln = self.lane_by_cdc(m.group(0), ("result", "downloading"))
            if ln:
                return ln
        cands = [ln for ln in self.lanes if ln.state == "downloading" and not ln.dl_taken]
        return cands[0] if len(cands) == 1 else None

    def on_ek_download(self, dl):
        ln = self.lane_for_download(dl)
        if not ln or ln.dl_taken:
            dl.cancel()
            return
        ln.set("downloading")
        ln.dl_taken = True
        dl.setDownloadDirectory(self.tmp)
        dl.setDownloadFileName(ln.cdc + ".xml")
        dl.isFinishedChanged.connect(lambda d=dl, l=ln, c=ln.cdc: self.on_ek_finished(d, l, c))
        dl.accept()

    def on_ek_finished(self, dl, ln, cdc):
        if ln.cdc != cdc or ln.state != "downloading":
            return
        ln.dl_taken = False
        if dl.state() != QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            return self.lane_fail(ln, "La descarga del XML se interrumpió.")
        path = os.path.join(dl.downloadDirectory(), dl.downloadFileName())
        try:
            raw = open(path, "rb").read()
            text = raw.decode("utf-8-sig")
        except Exception:
            return self.lane_fail(ln, "El XML descargado no se pudo leer.")
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
        if cdc not in text or "<DE" not in text:
            return self.lane_fail(ln, "e-Kuatia entregó un archivo que no es esta factura.")
        self.lane_done(ln, text, raw)

    def on_ui_download(self, dl):
        """Exportaciones de Glacé Compras: si el nombre lleva el mes (glace_AAAA-MM_...) van a
        Biblioteca\\<mes>\\Exportado; lo demás (copias de seguridad) a la carpeta Descargas."""
        name = os.path.basename(dl.downloadFileName() or "") or "glace.xlsx"
        m = re.search(r"_(\d{4}-\d{2})_", name)
        mes = safe_month(m.group(1)) if m else ""
        folder = os.path.join(LIB, mes, "Exportado") if mes else ""
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
        except OSError:
            traceback.print_exc()
            folder, mes = "", ""
        if not folder:
            folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or os.path.expanduser("~")
        final = lib_unique(folder, name)
        dl.setDownloadDirectory(folder)
        if final != dl.downloadFileName():
            dl.setDownloadFileName(final)
        dl.isFinishedChanged.connect(lambda d=dl, f=folder, n=final, mo=mes: self.on_ui_saved(d, f, n, mo))
        dl.accept()

    def on_ui_saved(self, dl, folder, name, mes):
        try:
            ok = dl.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted
        except Exception:
            ok = True
        if not ok:
            self.lbl.setText("No se pudo guardar la descarga: " + name)
            return
        self.lbl.setText(("Guardado en la biblioteca: " if mes else "Guardado en Descargas: ") + os.path.join(folder, name))
        if mes:
            self.js_left("window.__hostSaved && window.__hostSaved(%s, %s, %s)" % (json.dumps(name), json.dumps(folder), json.dumps(mes)))

    def closeEvent(self, ev):
        try:
            self.timer.stop()
            self.ia_stop.set()
            shutil.rmtree(self.tmp, ignore_errors=True)
        except Exception:
            pass
        super().closeEvent(ev)


GPU_TRY = os.path.join(HERE, ".gpu_probando")   # marca mientras se prueba la placa de video
GPU_OFF = os.path.join(HERE, ".gpu_off")        # la placa de video falló una vez: se usa el modo seguro


def _gpu_ok():
    """El programa funcionó con placa de video: se quita la marca de prueba."""
    try:
        os.remove(GPU_TRY)
    except OSError:
        pass


def chromium_flags():
    """Con la placa de video el scroll es fluido. Si un arranque con placa de video se cerró de golpe
    (quedó la marca .gpu_probando), se vuelve solo al modo seguro de antes y se recuerda en .gpu_off."""
    safe = "--disable-gpu-compositing --enable-smooth-scrolling"
    if os.environ.get("GLACE_SIN_GPU") == "1" or os.path.exists(GPU_OFF):
        print("dibujo: modo seguro (sin placa de video)")
        return safe
    try:
        if os.path.exists(GPU_TRY):
            with open(GPU_OFF, "w", encoding="utf-8") as f:
                f.write("El arranque con placa de video se cerró de golpe. Borrá este archivo para volver a probar.\n")
            _gpu_ok()
            print("dibujo: el intento con placa de video falló; modo seguro desde ahora")
            return safe
        with open(GPU_TRY, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except OSError:
        return safe
    print("dibujo: con placa de video (scroll fluido)")
    return "--enable-smooth-scrolling"


def main():
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", chromium_flags())
    app = QApplication(sys.argv)
    app.setApplicationName("Glacé Compras")
    lock = QLockFile(os.path.join(tempfile.gettempdir(), "glace_compras.lock"))
    if not lock.tryLock(200):
        print("Ya hay una ventana de Glacé Compras abierta.")
        sys.exit(0)
    w = Main()
    w.show()
    QTimer.singleShot(1500, refresh_desktop)
    QTimer.singleShot(20000, _gpu_ok)          # 20 s funcionando: la placa de video sirve
    code = app.exec()
    _gpu_ok()
    lock.unlock()
    sys.exit(code)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
