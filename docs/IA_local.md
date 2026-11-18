# 🤖 IA local en Glacé Compras

Guía para dejar funcionando la lectura automática de facturas de papel.
La IA corre **en la misma computadora**: no manda nada a internet y no tiene costo por uso.

---

## Qué hace

Subís la foto (o PDF) de una factura de papel y la IA:

1. **Lee la cabecera:** proveedor, RUC, número (001-001-0000123), timbrado, fecha, condición (contado/crédito), total e IVA.
2. **Lee todos los ítems:** descripción, cantidad, unidad, precio unitario, descuento, importe y tasa de IVA (10 %, 5 % o exenta).
3. **Controla:** que cantidad × precio − descuento dé el importe de cada renglón y que la suma dé el total. Si no cierra, **vuelve a mirar la foto** y corrige lo que leyó mal.
4. **Registra la factura:**
   - si figura en el Excel de Marangatu del mes → le agrega la foto y los ítems;
   - si no figura → la crea como factura manual;
   - si es electrónica (tiene CDC) → avisa que su XML se busca en el paso 2.
5. **Marca lo que hay que mirar:**
   - **dudoso** = algo que no se leyó bien (la IA dice qué);
   - **falta** = un dato que la factura no muestra. Eso lo completás vos con «Editar datos».

Nunca pisa los ítems que cargaste a mano.

---

## Preparación (una sola vez)

### 1. Instalar Bionic

Bionic es la app de LM Studio para usar modelos abiertos. Se descarga gratis desde **[lmstudio.ai/download](https://lmstudio.ai/download)** («Download Bionic for Windows»).

> También sirve **LM Studio** o **Ollama**: el programa los busca solo (puertos 1234 y 11434).

### 2. Descargar el modelo que lee fotos

En Bionic: **Einstellungen → Lokale Modelle → Erkunden**, buscá `qwen3-vl-8b-instruct` y descargá el de **Qwen** (`Qwen/Qwen3-VL-8B-Instruct-GGUF`, versión **Q4_K_M**, unos 6,2 GB).

| Modelo | ¿Sirve? |
|---|---|
| **Qwen3-VL-8B-Instruct** | ✅ Lee fotos (tiene el ícono del ojo 👁 en la biblioteca) |
| Qwen3-8B | Solo texto: sirve para PDF con texto, **no** para fotos |

Con 16 GB de RAM o más funciona bien. Sin placa de video tarda unos **5 minutos por foto**.

### 3. Encender el servidor local

En Bionic: **Einstellungen → API für lokale Modelle → Lokaler API-Server** → encendido («Wird ausgeführt»).
Dejá activado **«Modelle bei Bedarf laden»**: así el modelo se carga solo cuando llega una foto.

La dirección que muestra (por ejemplo `http://localhost:1235/v1`) el programa la encuentra sola.

### 4. (Opcional) Chat de Bionic más rápido

En el chat de Bionic, al lado del modelo: **Denkaufwand → Aus**. Con «Ein» el modelo «piensa» antes de contestar y una respuesta puede tardar más de 10 minutos.
*(Glacé Compras ya le pide al modelo que no piense; esto es solo para el chat de Bionic.)*

### 5. Comprobar

Abrí Glacé Compras. Abajo a la derecha:

| Etiqueta | Significa |
|---|---|
| 🟢 **● IA local: lista · qwen3-vl-8b-instruct** | Todo bien |
| 🔴 **IA local: abrí Bionic y encendé su servidor local** | Bionic cerrado o servidor apagado (paso 3) |
| 🔴 **IA local: solo lee PDF con texto · falta un modelo que lea fotos** | Falta Qwen3-VL (paso 2) |
| 🔴 **IA local: apagada (ia_local.json)** | Se apagó a propósito en la configuración |

La etiqueta se actualiza sola cada 20 segundos.

---

## Uso diario

1. Andá a **Facturas manuales**.
2. Arrastrá las fotos o PDF a la zona **«Subir fotos de facturas · la IA completa todo»** (o hacé clic y elegilas). Se pueden subir varias juntas.
   *Otra forma:* copiar las fotos a la carpeta `Biblioteca\_Entrada_IA`.
3. Listo: abajo se ve «IA local: leyendo foto 1 de 3…». Podés seguir trabajando mientras tanto.
4. Cuando termina, la factura aparece en la lista con su foto. Revisá los ítems marcados **dudoso** y completá lo que diga **falta**.

Para facturas manuales que ya tenían foto pero no ítems, el botón **«Leer fotos con IA»** (abajo a la derecha) las lee enseguida. Si no, se leen solas.

### Dónde quedan las fotos

| Carpeta | Contenido |
|---|---|
| `Biblioteca\_Entrada_IA` | Fotos esperando ser leídas |
| `Biblioteca\_Entrada_IA\_procesadas` | Fotos ya registradas |
| `Biblioteca\_Entrada_IA\_no_leidas` | Fotos que no se pudieron leer o registrar |
| `Biblioteca\<mes>\Manuales\<día>` | La factura registrada (detalle + foto), como siempre |

---

## Consejos para que lea mejor

- Foto **derecha, de frente y con buena luz**, sin sombras sobre los números.
- Que se vea **la factura entera**, incluido el total.
- Una factura por foto (si tiene varias páginas, varias fotos o un PDF).
- Los **PDF con texto** (los que se pueden seleccionar) se leen como texto: son los más exactos.
- La letra a mano se lee, pero revisá precios e importes: si un número escrito no cierra con el total, la IA lo marca como dudoso o anota la diferencia.

El programa prepara cada foto antes de dársela a la IA: la endereza según la cámara, la achica a un tamaño cómodo, sube el contraste y enfoca un poco (si está instalado Pillow).

---

## Problemas frecuentes

| Problema | Qué hacer |
|---|---|
| La etiqueta está roja | Ver la tabla de «Comprobar». Lo más común: Bionic cerrado o el servidor apagado. |
| Tarda mucho | Normal en una notebook sin placa de video: ~5 min por foto. Cerrá programas pesados (Chrome con muchas pestañas). |
| Una foto quedó en `_no_leidas` | Mirá el mensaje abajo a la izquierda y `glace_log.txt`. Probá con una foto más nítida y volvé a copiarla a `_Entrada_IA`. |
| «primero cargá el Excel de Marangatu del mes» | La foto llegó antes del Excel: cargá el Excel y volvé a copiar la foto a `_Entrada_IA`. |
| Leyó mal un número | Corregilo a mano en la factura: lo que tocás vos pasa a ser tuyo y la IA no lo vuelve a pisar. |
| PDF escaneado no se lee | Instalá PyMuPDF: `py -3 -m pip install --user pymupdf` |
| Quiero apagar la IA | Creá `ia_local.json` con `{"activo": false}` |

---

## Configuración opcional: `ia_local.json`

Archivo en la carpeta del programa (no se sube a GitHub). Todo es opcional:

```json
{
  "activo": true,
  "url": "http://127.0.0.1:1235/v1",
  "modelo": "qwen3-vl-8b-instruct",
  "modelo_texto": "qwen3-8b"
}
```

| Campo | Para qué |
|---|---|
| `activo` | `false` apaga la IA |
| `url` | Dirección del servidor si no es la de siempre (1235 Bionic, 1234 LM Studio, 11434 Ollama) |
| `modelo` | Modelo para fotos (si no, elige uno con visión) |
| `modelo_texto` | Modelo para PDF con texto |

---

## Para desarrolladores

- **`lector_local.py`** — lector. Habla con cualquier servidor compatible con la API de OpenAI (`/v1/models`, `/v1/chat/completions`). Corre en un hilo aparte dentro del programa; también se puede probar suelto: `py -3 lector_local.py --una-vez`.
- **Entrada:** `Biblioteca\_Entrada_IA\*` → `leer()` → el programa llama a `window.__iaFoto(json, foto, tipo, nombre)` en la página, que registra la factura y contesta `iaFotoDone`.
- **Facturas manuales sin ítems:** `lecturas_ia_local_*.json` en `Biblioteca\<mes>\Manuales` → `window.__ingestLecturas` (el mismo formato que ya usaba el programa).
- **Estado:** `.ia_local_estado.json` en la Biblioteca recuerda qué fotos ya se leyeron (por nombre y tamaño), para no leer dos veces.
- **Control de calidad:** `check()` revisa cantidad × precio y la suma contra el total; si algo no cierra, pide una segunda revisión con la lista de problemas.
