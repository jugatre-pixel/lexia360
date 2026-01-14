import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

def _wrap(texto: str, max_chars: int = 110) -> list[str]:
    words = (texto or "").split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def generar_pdf_informe(inmueble: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    left = 18 * mm
    right = w - 18 * mm
    top = h - 18 * mm
    y = top

    def header(page_num: int):
        nonlocal y
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, top, "Lexia360")
        c.setFont("Helvetica", 10)
        c.drawRightString(right, top, "Informe legal del inmueble")
        c.setLineWidth(1)
        c.line(left, top - 6*mm, right, top - 6*mm)
        y = top - 12*mm

        c.setFont("Helvetica", 8)
        c.setFillGray(0.35)
        c.drawString(left, 12*mm, "Confidencial · Generado por Lexia360")
        c.drawRightString(right, 12*mm, f"Página {page_num}")
        c.setFillGray(0)

    def section_title(t: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left, y, t)
        y -= 6 * mm
        c.setLineWidth(0.5)
        c.setStrokeGray(0.85)
        c.line(left, y, right, y)
        c.setStrokeGray(0)
        y -= 7 * mm

    def kv(k: str, v: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, f"{k}:")
        c.setFont("Helvetica", 10)
        c.drawString(left + 48*mm, y, v)
        y -= 6 * mm

    def ensure_space(min_y: float, page_num: int) -> int:
        nonlocal y
        if y < min_y:
            c.showPage()
            page_num += 1
            header(page_num)
        return page_num

    page = 1
    header(page)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, "Resumen ejecutivo")
    y -= 8 * mm

    res = inmueble.get("resultados") or {}
    sem = res.get("semaforo") or inmueble.get("semaforo") or "—"
    zona = "Sí" if res.get("zona_tensionada") else "No"
    fuente = res.get("zona_tensionada_fuente") or "—"
    fecha_analisis = res.get("fecha_analisis") or inmueble.get("fecha_analisis") or "—"
    dur = res.get("duracion_minima_anios", "—")
    renta_max = res.get("renta_maxima_mvp", None)
    fianza = res.get("fianza_minima", None)

    c.setFont("Helvetica", 10)
    resumen = [
        f"Semáforo: {sem}",
        f"Zona tensionada: {zona}",
        f"Fecha de análisis: {fecha_analisis}",
        f"Duración mínima aplicable: {dur} años",
    ]
    for line in resumen:
        c.drawString(left, y, line)
        y -= 5.5 * mm

    y -= 2 * mm
    c.setLineWidth(0.5)
    c.setStrokeGray(0.85)
    c.line(left, y, right, y)
    c.setStrokeGray(0)
    y -= 9 * mm

    section_title("1) Datos del inmueble")
    page = ensure_space(40*mm, page)

    kv("Dirección", inmueble.get("direccion") or "—")
    kv("Municipio", inmueble.get("municipio") or "—")
    kv("Comunidad", inmueble.get("comunidad_autonoma") or "—")
    kv("Código postal", inmueble.get("codigo_postal") or "—")
    kv("Superficie", f"{inmueble.get('superficie_m2') or '—'} m²")
    kv("Tipo arrendamiento", inmueble.get("tipo_arrendamiento") or "—")
    kv("Tipo arrendador", inmueble.get("tipo_arrendador") or "—")
    kv("Renta propuesta", f"{inmueble.get('renta_propuesta') if inmueble.get('renta_propuesta') is not None else '—'} €")
    kv("Renta anterior", f"{inmueble.get('renta_anterior')} €" if inmueble.get("renta_anterior") is not None else "—")

    y -= 2 * mm
    section_title("2) Resultado automático (MVP)")
    page = ensure_space(45*mm, page)

    kv("Semáforo de riesgo", sem)
    kv("Zona tensionada", zona)
    kv("Fuente oficial", fuente)
    kv("Duración mínima", f"{dur} años")
    kv("Renta máxima (MVP)", f"{renta_max} €" if renta_max is not None else "—")
    kv("Fianza mínima (MVP)", f"{fianza} €" if fianza is not None else "—")

    y -= 2 * mm
    section_title("3) Alertas y recomendaciones")
    page = ensure_space(45*mm, page)

    alertas = inmueble.get("alertas") or []
    if not alertas:
        alertas = ["—"]

    c.setFont("Helvetica", 10)
    for a in alertas:
        page = ensure_space(28*mm, page)
        for line in _wrap(f"• {a}", max_chars=110):
            c.drawString(left, y, line)
            y -= 5.2 * mm

    y -= 3 * mm
    section_title("4) Aviso legal")
    page = ensure_space(35*mm, page)

    aviso = (
        "Este informe es informativo y se genera mediante reglas automatizadas (MVP). "
        "No constituye asesoramiento jurídico personalizado. "
        "Para un análisis completo y/o redacción contractual final, consulta con un profesional o usa la versión Pro."
    )
    c.setFont("Helvetica", 9)
    for line in _wrap(aviso, max_chars=110):
        c.drawString(left, y, line)
        y -= 4.8 * mm

    c.showPage()
    c.save()
    out = buf.getvalue()
    buf.close()
    return out

