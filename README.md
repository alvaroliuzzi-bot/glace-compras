<div align="center">

<img src=".github/assets/banner.svg" width="100%" alt="Glacé Compras · del comprobante al stock">

![Python](https://img.shields.io/badge/Python-3-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/PyQt6-WebEngine-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![SIFEN](https://img.shields.io/badge/🧾_SIFEN-e--Kuatia_·_Marangatu-B0336A?style=for-the-badge)
![e-Karú](https://img.shields.io/badge/📦_destino-e--Karú-F2A541?style=for-the-badge)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)

<img src="docs/img/flujo.jpg" width="85%" alt="Tres fuentes de compras llegan a e-Karú como un solo archivo">


<a href="https://claude.ai/artifact/6RK7nyF9HsXZztpKUsCuZy"><img src="https://img.shields.io/badge/🗂️_VER_TODOS_LOS_PROYECTOS-en_un_solo_lugar-6D5BD0?style=for-the-badge&labelColor=E0457B" height="40" alt="Ver todos los proyectos en un solo lugar"></a>

</div>

<img src=".github/assets/cards.svg" width="100%" alt="Tres pasos: cargar el Excel, buscar XML, exportar">

### 🔀 De tres fuentes a un solo archivo

```mermaid
flowchart LR
    M["📊 Marangatu<br/>total por factura"]:::plum --> APP
    K["🌐 e-Kuatia × 4<br/>XML por CDC"]:::gold --> APP
    F["📄 Facturas de papel<br/>foto → IA local lee todo"]:::grey --> APP
    APP{"🧾 Glacé Compras<br/>compara totales"}:::pink --> X["📗 Excel para e-Karú<br/>Cabecera · Detalle · Pendientes"]:::teal
    classDef plum fill:#5E1239,stroke:#B0336A,color:#fff
    classDef gold fill:#F2A541,stroke:#B8801A,color:#14231F
    classDef grey fill:#667085,stroke:#344054,color:#fff
    classDef pink fill:#B0336A,stroke:#5E1239,color:#fff
    classDef teal fill:#1D9A84,stroke:#0F5C50,color:#fff
```

## 😩 El problema

e-Karú necesita el **detalle** de cada compra (producto, cantidad, precio), pero Marangatu solo da el total por factura, el XML de cada factura hay que bajarlo uno por uno en e-Kuatia (con captcha), y las facturas de papel no tienen CDC.

<img src=".github/assets/divider.svg" width="100%">

## 💡 La solución, en tres pasos

| Paso | Qué hace el programa |
|---|---|
| **1 · Cargar el Excel del mes** | Lee «DetalleComprobantesRegistrados» de Marangatu y lo guarda por mes |
| **2 · Buscar XML y controlar** | Abre **4 portales de e-Kuatia a la vez**: la persona solo marca «No soy un robot»; el programa escribe la CDC, consulta, descarga el XML y compara el total con Marangatu |
| **3 · Exportar para e-Karú** | Un Excel con hojas Cabecera, Detalle y Pendientes |
| **📷 Facturas de papel** | Solo se sube la foto: la **IA local** lee proveedor, RUC, número, timbrado, fecha, total e ítems y registra la factura sola |

<p align="center"><img src="docs/img/inicio.jpg" width="60%" alt="Pantalla de inicio"></p>
<p align="center"><img src="docs/img/exportar.jpg" width="85%" alt="Exportar para e-Karú"></p>

<img src=".github/assets/divider.svg" width="100%">

## 🤖 IA local para las facturas de papel

En **Facturas manuales**, la zona **«Subir fotos de facturas · la IA completa todo»** (o la carpeta `Biblioteca\_Entrada_IA`) recibe fotos o PDF. La IA corre **en la misma computadora** (sin internet ni costo):

- lee la cabecera (proveedor, RUC, número, timbrado, fecha, condición, total, IVA) y todos los ítems;
- si la factura figura en el Excel de Marangatu le agrega foto e ítems; si no, la crea como factura manual; si es electrónica, avisa que su XML se busca en el paso 2;
- controla cantidad × precio y que la suma dé el total; si no cierra, la IA revisa la foto una segunda vez;
- marca como **dudoso** lo que no se lee bien y como **falta** lo que la factura no dice: eso lo completa la persona;
- nunca pisa los ítems cargados a mano.

**Preparación (una sola vez):** instalar [Bionic](https://lmstudio.ai) (o LM Studio / Ollama), descargar el modelo **Qwen3-VL-8B-Instruct** y encender el *servidor local* (API für lokale Modelle). Abajo a la derecha el programa muestra **● IA local: lista** cuando todo está bien.
En una notebook sin placa de video tarda unos **5 minutos por foto**. Opcional: `ia_local.json` (`url`, `modelo`, `activo`).

<img src=".github/assets/divider.svg" width="100%">

## 🚀 Empezar (Windows)

1. Instalar Python 3 y marcar **«Add python.exe to PATH»**.
2. Doble clic en **`Iniciar_Glace_Compras.bat`**. La primera vez instala PyQt6 y PyQt6-WebEngine (~150 MB) y crea el acceso directo «Glace Compras» en el escritorio.

<img src=".github/assets/divider.svg" width="100%">

## 📁 Archivos

| Archivo | Para qué |
|---|---|
| `Glace_Compras_App.pyw` | Ventana principal y automatización de los 4 portales |
| `Glace_Compras.html` | Interfaz: meses, proveedores, facturas manuales, exportación |
| `ek_helpers.js` | Funciones que se inyectan en el portal de e-Kuatia |
| `lector_local.py` | Lector de facturas con IA local (fotos y PDF → cabecera e ítems) |
| `tools/selftest.pyw` | Prueba automática del programa (`tools/Probar.bat`) |
| `docs/` | Documento del sistema y resultados de la encuesta al personal de caja |

> [!CAUTION]
> 🔒 Los datos reales (Excel de Marangatu, XML de facturas, log) **no** se suben: están en `.gitignore`.

<img src=".github/assets/divider.svg" width="100%">

<div align="center">

<sub>Parte de: [ekaru-procesos](https://github.com/alvaroliuzzi-bot/ekaru-procesos) · [ekaru-etiquetas](https://github.com/alvaroliuzzi-bot/ekaru-etiquetas) · [paginas-web](https://github.com/alvaroliuzzi-bot/paginas-web)</sub>

</div>
