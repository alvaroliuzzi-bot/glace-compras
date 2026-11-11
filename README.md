# Glacé Compras

Programa de escritorio (Python + PyQt6 WebEngine) que convierte las facturas de compra de Glacé para cargarlas en **e-Karú**.

- Lee el Excel «DetalleComprobantesRegistrados» de Marangatu (lista de facturas con su CDC).
- Abre 4 portales de e-Kuatia a la vez: la persona solo marca «No soy un robot»; el programa escribe la CDC, consulta, descarga el XML y lo guarda en la biblioteca (`Biblioteca/AAAA-MM/XML/`).
- Junta los ítems de las facturas y genera el Excel para e-Karú. Las facturas sin CDC (papel) se cargan a mano.

## Uso (Windows)

1. Instalar Python 3 (marcar «Add python.exe to PATH»).
2. Doble clic en `Iniciar_Glace_Compras.bat`. La primera vez instala PyQt6 y PyQt6-WebEngine (~150 MB) y crea el acceso directo «Glace Compras» en el escritorio.

## Archivos

| Archivo | Para qué |
|---|---|
| `Glace_Compras_App.pyw` | Ventana principal y automatización de los 4 portales de e-Kuatia |
| `Glace_Compras.html` | Interfaz de Glacé Compras (meses, proveedores, facturas manuales, exportación) |
| `ek_helpers.js` | Funciones que se inyectan en el portal de e-Kuatia |
| `tools/selftest.pyw`, `tools/Probar.bat` | Prueba automática del programa |
| `docs/` | Documento del sistema y resultados de la encuesta al personal de caja |

Los datos reales (Excel de Marangatu, XML de facturas, log) **no** se suben: están en `.gitignore`.
