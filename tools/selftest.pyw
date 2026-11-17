# -*- coding: utf-8 -*-
"""Prueba automática de Glacé Compras con un e-Kuatia SIMULADO (pagina local de prueba).
No toca e-Kuatia ni ningun captcha real: el recuadro «No soy un robot» de la pagina de prueba
lo marca la propia pagina simulada. Escribe el resultado en glace_selftest.txt.
(Uso unico: se borra despues de la prueba.)"""
import os, sys, json, re, time, threading, traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
OUT = os.path.join(HERE, "glace_selftest.txt")

N = 8


def cdc_of(i):
    return "0" * 38 + "%06d" % i          # CDC de prueba (44 digitos)


BAD_XML = {cdc_of(3)}      # el servidor entrega el XML de OTRA factura
NO_BTN = {cdc_of(5)}       # la consulta no muestra el boton de descarga
HOLD = {"v": False}        # mientras sea True, la pagina simulada no «marca» el recuadro

MOCK = r"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>e-Kuatia · PRUEBA LOCAL</title>
<style>body{font:15px 'Segoe UI',Arial,sans-serif;margin:16px;background:#fff8e1;color:#222}h3{margin:0 0 10px;color:#a33}
input.cdc{width:430px;padding:6px;font-size:14px}.g-recaptcha{margin:12px 0;padding:12px;border:1px solid #999;width:290px;background:#fff}
button{padding:8px 16px;margin-top:6px;font-size:14px}#res{margin-top:14px}</style></head><body>
<h3>PÁGINA DE PRUEBA LOCAL (no es e-Kuatia)</h3>
<input class="cdc" placeholder="CDC" autocomplete="off">
<div class="g-recaptcha"><label><input type="checkbox" id="rb" disabled> No soy un robot (simulado)</label>
<textarea name="g-recaptcha-response" id="g-recaptcha-response" style="display:none"></textarea></div>
<button id="go">Consultar</button><div id="res"></div>
<script>
(function(){
 var NOBTN=__NOBTN__;
 var inp=document.querySelector('input.cdc'), ta=document.getElementById('g-recaptcha-response'), rb=document.getElementById('rb'), res=document.getElementById('res'), armed=false;
 function tick(){ fetch('/__hold',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){
   if(j.hold){ setTimeout(tick,300) } else { rb.checked=true; ta.value=new Array(61).join('x'); } }).catch(function(){ setTimeout(tick,500) }); }
 inp.addEventListener('input',function(){ if(inp.value.length===44 && !armed){ armed=true; setTimeout(tick,400+Math.floor(Math.random()*700)); } });
 document.getElementById('go').onclick=function(){
   if(ta.value.length<20){ res.textContent='Falta marcar el captcha'; return; }
   var c=inp.value; res.textContent='Consultando…';
   setTimeout(function(){
     res.innerHTML=''; var d=document.createElement('div'); d.textContent='Resultado para '+c; res.appendChild(d);
     if(NOBTN.indexOf(c)>=0){ var m=document.createElement('p'); m.textContent='Documento no encontrado (prueba)'; res.appendChild(m); return; }
     var b=document.createElement('button'); b.textContent='Descargar Archivo XML';
     b.onclick=function(){ var n=parseInt(c.slice(-3),10);
       if(n%2===0){ location.href='/docs/documento-electronico-xml/'+c; }
       else{ fetch('/docs/documento-electronico-xml/'+c).then(function(r){return r.blob()}).then(function(bl){
         var a=document.createElement('a'); a.href=URL.createObjectURL(bl); a.download=c+'.xml'; document.body.appendChild(a); a.click(); }); } };
     res.appendChild(b);
   },500);
 };
})();
</script></body></html>"""


def xml_for(cdc, wrong=False):
    c = ("9" * 44) if wrong else cdc
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dVerFor>150</dVerFor>'
            '<DE Id="%s"><dDVId>1</dDVId><gTimb><dNumTim>12345678</dNumTim></gTimb>'
            '<gDatGralOpe><gEmis><dNomEmi>Prueba Ñandú ÁÉÍÓÚ</dNomEmi></gEmis></gDatGralOpe></DE></rDE>' % c)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body, extra=None):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/consultas/", "/consultas"):
            html = MOCK.replace("__NOBTN__", json.dumps(sorted(NO_BTN)))
            self._send(200, "text/html; charset=utf-8", html)
        elif p == "/__hold":
            self._send(200, "application/json", json.dumps({"hold": bool(HOLD["v"])}))
        elif p.startswith("/docs/documento-electronico-xml/"):
            c = p.rsplit("/", 1)[1]
            self._send(200, "application/xml; charset=utf-8", xml_for(c, wrong=(c in BAD_XML)),
                       {"Content-Disposition": 'attachment; filename="%s.xml"' % c})
        else:
            self._send(404, "text/plain", "no existe")


def start_server(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def log(*a):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")


def run_test():
    open(OUT, "w", encoding="utf-8").close()
    log("inicio de la prueba · Python", sys.version.split()[0])
    srv = start_server()
    port = srv.server_address[1]
    os.environ["GLACE_PROFILE_SUFFIX"] = "-test"
    os.environ["GLACE_EK_URL"] = "http://127.0.0.1:%d/consultas/" % port
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu-compositing")
    APP = os.path.join(APP_DIR, "Glace_Compras_App.pyw")
    ns = {"__file__": APP, "__name__": "glace_app"}
    exec(compile(open(APP, encoding="utf-8").read(), APP, "exec"), ns)
    QApplication, QTimer = ns["QApplication"], ns["QTimer"]
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        from PyQt6.QtGui import QGuiApplication
        log("PyQt6", PYQT_VERSION_STR, "· Qt", QT_VERSION_STR)
    except Exception:
        log("no pude leer versiones", traceback.format_exc())
    app = QApplication(sys.argv)
    main = ns["Main"]()
    S = {"phase": "boot", "t0": time.time(), "t": time.time(), "left_ok": False, "res": [], "done": False}
    main.left.loadFinished.connect(lambda ok: S.update(left_ok=bool(ok)))

    def chk(name, ok, extra=""):
        S["res"].append((name, bool(ok)))
        log(("OK    " if ok else "FALLO ") + name + ((" · " + str(extra)) if extra != "" else ""))

    def shot(tag):
        try:
            main.grab().save(os.path.join(HERE, "selftest_%s_widget.png" % tag))
            scr = QGuiApplication.primaryScreen()
            scr.grabWindow(int(main.winId())).save(os.path.join(HERE, "selftest_%s_pantalla.png" % tag))
            log("capturas guardadas:", tag)
        except Exception:
            log("captura falló", traceback.format_exc())

    def finish(reason):
        if S["done"]:
            return
        S["done"] = True
        bad = [n for n, ok in S["res"] if not ok]
        log("=" * 50)
        log("RESULTADO: %d comprobaciones, %d fallos (%s)" % (len(S["res"]), len(bad), reason))
        log("PRUEBA_TERMINADA " + ("OK" if not bad else "CON_FALLOS"))
        try:
            app.quit()
        except Exception:
            pass
        threading.Timer(2.5, lambda: os._exit(0)).start()

    JS_STUB = """(function(){
      window.__got=[];window.__calls=[];window.__errs=[];
      var real=window.__ingest;
      window.__ingest=function(n,t){window.__got.push([n,t.length,t.indexOf('Ñandú')>=0]);return Promise.resolve();};
      ['__hostFlight','__hostProg','__hostFail','__hostDone'].forEach(function(k){
        var f=window[k];
        window[k]=function(){window.__calls.push([k].concat([].slice.call(arguments)));
          try{return f.apply(this,arguments);}catch(e){window.__errs.push(k+': '+e.message);}};});
      return typeof real+'|'+typeof window.__takeOutbox+'|'+typeof window.__hostFlight+'|'+(navigator.userAgent.indexOf('GlaceApp')>=0?'HOST':'NOHOST');
    })()"""
    items = [{"cdc": cdc_of(i), "label": "Proveedor de prueba %d · 001-001-%07d" % (i, i), "total": 1000 * (N - i)} for i in range(N)]

    def drive():
        try:
            now = time.time()
            ph = S["phase"]
            if now - S["t0"] > 150:
                chk("tiempo total de la prueba", False, "más de 150 s en la fase " + ph)
                return finish("tiempo agotado")
            if ph == "boot":
                if S["left_ok"]:
                    chk("los 4 portales arrancan en reposo (no cargan e-Kuatia hasta que hay facturas)",
                        all(l.state == "free" and not l.pre and not l.ready for l in main.lanes))
                    chk("la ventana izquierda (Glacé Compras) cargó", True)
                    sz = main.size()
                    log("ventana %dx%d · portales:" % (sz.width(), sz.height()),
                        ["%dx%d" % (l.view.width(), l.view.height()) for l in main.lanes])
                    S["phase"] = "inject"
                elif now - S["t"] > 40:
                    chk("carga inicial", False, "izquierda=%s" % S["left_ok"])
                    return finish("no cargó")
            elif ph == "inject":
                S["phase"] = "wait_inject"
                def cb(r):
                    chk("puente JS (ingest/takeOutbox/hostFlight, modo HOST)", r == "function|function|function|HOST", r)
                    S["phase"] = "start"
                main.left.page().runJavaScript(JS_STUB, cb)
            elif ph == "start":
                HOLD["v"] = True
                main.start_queue(items)
                S["phase"] = "hold"
                S["t"] = now
            elif ph == "hold":
                st = [l.state for l in main.lanes]
                if all(s == "captcha" for s in st):
                    main.tick()
                    heads = [l.head.text() for l in main.lanes]
                    chk("los 4 portales piden «No soy un robot»", all("MARCÁ" in h for h in heads), heads[0])
                    chk("cada portal tiene su propia factura", len({l.cdc for l in main.lanes}) == 4)
                    chk("las 4 primeras de la cola (por monto)", sorted(l.cdc for l in main.lanes) == [cdc_of(i) for i in range(4)])
                    shot("1_espera")
                    S["phase"] = "hold2"
                    S["t"] = now
                elif now - S["t"] > 40:
                    chk("los 4 portales esperan el Häkchen", False, st)
                    return finish("no llegaron a captcha")
            elif ph == "hold2":
                if now - S["t"] > 12:      # tiempo para sacar una captura de pantalla desde afuera
                    HOLD["v"] = False
                    log("se «marcan» los recuadros simulados")
                    S["phase"] = "run"
                    S["t"] = now
            elif ph == "run":
                if main.total == 0 and all(l.state == "free" for l in main.lanes) and main.done == N:
                    S["phase"] = "verify"
                elif now - S["t"] > 90:
                    chk("la cola terminó a tiempo", False, "done=%d ok=%d bad=%d estados=%s" % (main.done, main.ok, main.bad, [l.state for l in main.lanes]))
                    S["phase"] = "verify"
            elif ph == "verify":
                S["phase"] = "wait_verify"
                chk("8 facturas procesadas", main.done == N, main.done)
                chk("6 XML guardados (3 directos + blobs)", main.ok == 6, main.ok)
                chk("2 con problema (XML ajeno + sin botón)", main.bad == 2, main.bad)
                chk("todos los portales quedaron libres", all(l.state == "free" for l in main.lanes))
                try:
                    left = sorted(os.listdir(main.tmp))
                except Exception:
                    left = ["?"]
                chk("sin archivos temporales", left == [], left)
                shot("2_fin")
                def cb2(r):
                    try:
                        j = json.loads(r)
                        got = sorted(x[0] for x in j["got"])
                        want = sorted(cdc_of(i) + ".xml" for i in (0, 1, 2, 4, 6, 7))
                        chk("la ventana izquierda recibió los 6 XML correctos", got == want, got if got != want else "")
                        chk("los XML llegan con acentos intactos (UTF-8)", all(x[2] for x in j["got"]))
                        names = [c[0] for c in j["calls"]]
                        chk("llegó __hostFlight", "__hostFlight" in names)
                        chk("llegó __hostProg", "__hostProg" in names)
                        chk("llegaron 2 avisos de fallo (__hostFail)", names.count("__hostFail") == 2, names.count("__hostFail"))
                        chk("llegó __hostDone al final", names[-1:] == ["__hostDone"] or "__hostDone" in names, names[-3:])
                        chk("las funciones reales de la página no dieron error", j["errs"] == [], j["errs"])
                        fails = [c[1] for c in j["calls"] if c[0] == "__hostFail"]
                        log("mensajes de fallo:", fails)
                    except Exception:
                        chk("lectura del resultado en la ventana izquierda", False, traceback.format_exc())
                    # actualizar el escritorio (el programa lo hace solo al arrancar)
                    import io, contextlib
                    buf = io.StringIO()
                    try:
                        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
                            ns["refresh_desktop"]()
                        chk("refresh_desktop() sin errores", "Traceback" not in buf.getvalue(), buf.getvalue().strip()[:200])
                    except Exception:
                        chk("refresh_desktop() sin errores", False, traceback.format_exc())
                    try:
                        lg = open(os.path.join(APP_DIR, "glace_log.txt"), encoding="utf-8", errors="replace").read()
                        chk("el log del programa no tiene errores", "Traceback" not in lg and "Error" not in lg, lg.strip()[-300:])
                    except Exception:
                        pass
                    finish("fin")
                main.left.page().runJavaScript("JSON.stringify({got:window.__got,calls:window.__calls,errs:window.__errs})", cb2)
        except Exception:
            log("EXCEPCION en la prueba", traceback.format_exc())
            finish("excepción")

    t = QTimer()
    t.timeout.connect(drive)
    t.start(250)
    code = app.exec()
    log("app.exec terminó", code)
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--serve":
        s = start_server(int(sys.argv[2]))
        print("servidor de prueba en", s.server_address, flush=True)
        threading.Event().wait()
    else:
        try:
            run_test()
        except Exception:
            log("ERROR GENERAL", traceback.format_exc())
            os._exit(1)
