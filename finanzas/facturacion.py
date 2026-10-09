"""Emitir tus facturas: tus datos y los de cada cliente, los días que no trabajas (vacaciones o días que
no puedes) y el documento de cada factura, listo para imprimir o guardar en PDF desde el navegador."""
import json
import re
from datetime import date
from decimal import Decimal
from html import escape
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import ajustes, auth, db
from finanzas.fechas import MESES, MESES_EN
from finanzas.models import Cliente, Factura

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])
SesionDB = Depends(db.get_session)

CLAVE_EMISOR = "facturacion_emisor"
CLAVE_DIAS = "dias_no_disponibles"
TIPOS_DIA = ("vacaciones", "no_disponible")


class Emisor(BaseModel):
    nombre: str = ""
    nif: str = ""
    direccion: str = ""
    email: str = ""
    telefono: str = ""
    iban: str = ""
    pie: str = ""  # texto libre al final de la factura


class DatosCliente(BaseModel):
    nif: str = ""
    direccion: str = ""
    idioma: Literal["es", "en"] = "es"
    nota_factura: str = ""


class CambioDias(BaseModel):
    dias: list[date]
    tipo: Literal["vacaciones", "no_disponible"] | None = None  # vacío: vuelven a ser días normales


def _json(s: Session, clave: str) -> dict:
    try:
        datos = json.loads(ajustes.leer(s, clave, "") or "{}")
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def leer_emisor(s: Session) -> Emisor:
    return Emisor(**{k: v for k, v in _json(s, CLAVE_EMISOR).items() if k in Emisor.model_fields})


def dias_no_disponibles(s: Session) -> dict[str, str]:
    return {k: v for k, v in _json(s, CLAVE_DIAS).items() if v in TIPOS_DIA}


def siguiente_numero(ultimo: str | None, anio_ultimo: int | None, anio: int) -> str:
    """El número que sigue al de tu última factura, con su mismo formato: 2026-014 → 2026-015,
    F/7 → F/8. Si cambia el año y el número lo lleva, empieza en 1: 2025-045 → 2026-001."""
    if not ultimo or anio_ultimo is None:
        return f"{anio}-001"
    grupos = list(re.finditer(r"\d+", ultimo))
    del_anio = [g for g in grupos if g.group() == str(anio_ultimo)]
    contador = next((g for g in reversed(grupos) if g.group() != str(anio_ultimo)), None)
    if contador is None:
        return f"{anio}-001"
    nuevo_anio = anio != anio_ultimo and bool(del_anio)
    valor = 1 if nuevo_anio else int(contador.group()) + 1
    trozos, pos = [], 0
    for g in grupos:
        trozos.append(ultimo[pos:g.start()])
        if g is contador:
            trozos.append(str(valor).zfill(len(g.group())))
        elif nuevo_anio and g in del_anio:
            trozos.append(str(anio))
        else:
            trozos.append(g.group())
        pos = g.end()
    return "".join(trozos) + ultimo[pos:]


def numero_para(s: Session, anio: int) -> str:
    facturas = s.scalars(select(Factura).where(Factura.fecha < date(anio + 1, 1, 1))
                         .order_by(Factura.fecha.desc(), Factura.id.desc())).all()
    existentes = {x.numero for x in s.scalars(select(Factura))}
    ultima = facturas[0] if facturas else None
    numero = siguiente_numero(ultima.numero if ultima else None, ultima.fecha.year if ultima else None, anio)
    for _ in range(1000):  # por si ese número ya está usado (facturas registradas fuera de orden)
        if numero not in existentes:
            break
        numero = siguiente_numero(numero, anio, anio)
    return numero


def _cliente(c: Cliente) -> dict:
    return {"nombre": c.nombre, "nif": c.nif or "", "direccion": c.direccion or "", "idioma": c.idioma or "es",
            "nota_factura": c.nota_factura or ""}


@router.get("/facturacion")
def ver_facturacion(s: Session = SesionDB):
    from finanzas import prevision
    clientes ={c.nombre: _cliente(c) for c in s.scalars(select(Cliente))}
    for c in prevision.leer(s).get("clientes") or []:  # los de Sueldo y tarifas aunque aún no tengan facturas
        if c.get("nombre"):
            clientes.setdefault(c["nombre"], {"nombre": c["nombre"], "nif": "", "direccion": "", "idioma": "es", "nota_factura": ""})
    return {
        "emisor": leer_emisor(s).model_dump(),
        "clientes": sorted(clientes.values(), key=lambda c: c["nombre"].lower()),
        "dias_no_disponibles": dias_no_disponibles(s),
    }


@router.get("/facturacion/siguiente-numero")
def ver_siguiente_numero(anio: int, s: Session = SesionDB):
    return {"numero": numero_para(s, anio)}


@router.put("/facturacion/emisor")
def guardar_emisor(datos: Emisor, s: Session = SesionDB):
    ajustes.guardar(s, CLAVE_EMISOR, datos.model_dump_json())
    return {"ok": True}


@router.put("/facturacion/clientes/{nombre}")
def guardar_cliente(nombre: str, datos: DatosCliente, s: Session = SesionDB):
    nombre = nombre.strip()
    c = s.scalar(select(Cliente).where(Cliente.nombre == nombre))
    if c is None:
        c = Cliente(nombre=nombre)
        s.add(c)
    c.nif, c.direccion, c.idioma, c.nota_factura = datos.nif.strip(), datos.direccion.strip(), datos.idioma, datos.nota_factura.strip()
    s.commit()
    return {"ok": True}


@router.put("/facturacion/dias")
def marcar_dias(datos: CambioDias, s: Session = SesionDB):
    """Marca días como vacaciones o como días que no puedes trabajar; con tipo vacío los desmarca."""
    dias = dias_no_disponibles(s)
    for d in datos.dias:
        if datos.tipo:
            dias[d.isoformat()] = datos.tipo
        else:
            dias.pop(d.isoformat(), None)
    ajustes.guardar(s, CLAVE_DIAS, json.dumps(dict(sorted(dias.items()))))
    return {"ok": True, "dias_no_disponibles": dias}


# --- Documento de la factura -------------------------------------------------

TEXTOS = {
    "es": {"factura": "Factura", "numero": "Nº", "fecha": "Fecha", "emisor": "Emisor", "cliente": "Cliente",
           "nif": "NIF", "concepto": "Concepto", "horas": "Horas", "precio": "Precio/hora", "importe": "Importe",
           "base": "Base imponible", "iva": "IVA", "retencion": "Retención IRPF", "total": "Total a pagar",
           "pago": "Forma de pago: transferencia a", "dias": "Días trabajados", "imprimir": "Imprimir o guardar en PDF"},
    "en": {"factura": "Invoice", "numero": "No.", "fecha": "Date", "emisor": "From", "cliente": "Bill to",
           "nif": "Tax ID", "concepto": "Description", "horas": "Hours", "precio": "Rate/hour", "importe": "Amount",
           "base": "Subtotal", "iva": "VAT", "retencion": "Spanish income tax withholding", "total": "Total due",
           "pago": "Payment by bank transfer to", "dias": "Days worked", "imprimir": "Print or save as PDF"},
}
NOTA_SIN_IVA = {
    "es": "Operación no sujeta a IVA por reglas de localización (art. 69 de la Ley 37/1992 del IVA).",
    "en": "Not subject to Spanish VAT: place of supply outside Spain (art. 69 Spanish VAT Act 37/1992). "
          "Reverse charge: VAT to be accounted for by the recipient.",
}


def _importe(v: Decimal | float, idioma: str) -> str:
    texto = f"{float(v):,.2f}"
    if idioma == "en":
        return f"€{texto}"
    return texto.replace(",", "·").replace(".", ",").replace("·", ".") + " €"


def _cifra(v: float, idioma: str) -> str:
    texto = f"{v:,.2f}".rstrip("0").rstrip(".")
    return texto if idioma == "en" else texto.replace(",", "·").replace(".", ",").replace("·", ".")


def _fecha(d: date, idioma: str) -> str:
    return f"{MESES_EN[d.month - 1]} {d.day}, {d.year}" if idioma == "en" else d.strftime("%d/%m/%Y")


def _dias_texto(dias: list[date], idioma: str) -> str:
    """1, 2, 3, 6 y 7 de octubre de 2026 (agrupado por mes)."""
    por_mes: dict[tuple[int, int], list[int]] = {}
    for d in sorted(dias):
        por_mes.setdefault((d.year, d.month), []).append(d.day)
    partes = []
    for (anio, mes), nums in por_mes.items():
        lista = ", ".join(str(x) for x in nums)
        partes.append(f"{MESES_EN[mes - 1]} {lista}, {anio}" if idioma == "en" else f"{lista} de {MESES[mes - 1]} de {anio}")
    return "; ".join(partes)


def documento(x: Factura, emisor: Emisor) -> str:
    c = x.cliente
    idioma = c.idioma if c.idioma in TEXTOS else "es"
    t, e = TEXTOS[idioma], lambda v: escape(str(v or ""))
    try:
        detalle = json.loads(x.detalle) if x.detalle else None
    except ValueError:
        detalle = None
    # El detalle por horas solo se enseña si cuadra con la base (la factura pudo editarse después)
    if detalle and abs(Decimal(str(detalle["horas"])) * Decimal(str(detalle["precio_hora"])) - x.base) > Decimal("0.05"):
        detalle = None
    concepto = e(x.concepto).replace("\n", "<br>")
    if detalle:
        fila = (f"<td>{concepto}</td><td class=n>{_cifra(detalle['horas'], idioma)}</td>"
                f"<td class=n>{_importe(detalle['precio_hora'], idioma)}</td><td class=n>{_importe(x.base, idioma)}</td>")
        cabecera = f"<th>{t['concepto']}</th><th class=n>{t['horas']}</th><th class=n>{t['precio']}</th><th class=n>{t['importe']}</th>"
    else:
        fila = f"<td colspan=3>{concepto}</td><td class=n>{_importe(x.base, idioma)}</td>"
        cabecera = f"<th colspan=3>{t['concepto']}</th><th class=n>{t['importe']}</th>"
    dias = [date.fromisoformat(d) for d in (detalle or {}).get("dias", [])]
    totales = [(t["base"], x.base)]
    if x.tipo_iva:
        totales.append((f"{t['iva']} {_cifra(float(x.tipo_iva), idioma)} %", x.cuota_iva))
    if x.tipo_retencion:
        totales.append((f"{t['retencion']} {_cifra(float(x.tipo_retencion), idioma)} %", -x.retencion))
    filas_totales = "".join(f"<tr><td>{e(k)}</td><td class=n>{_importe(v, idioma)}</td></tr>" for k, v in totales)
    nota = c.nota_factura or (NOTA_SIN_IVA[idioma] if not x.tipo_iva else "")

    def bloque(titulo: str, nombre: str, nif: str, direccion: str, extra: str = "") -> str:
        return (f"<div><h3>{titulo}</h3><strong>{e(nombre)}</strong>"
                + (f"<br>{t['nif']}: {e(nif)}" if nif else "")
                + (f"<br>{e(direccion).replace(chr(10), '<br>')}" if direccion else "") + extra + "</div>")

    contacto = "".join(f"<br>{e(v)}" for v in (emisor.email, emisor.telefono) if v)
    return f"""<!doctype html>
<html lang="{idioma}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t['factura']} {e(x.numero)} {e(c.nombre)}</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font: 14px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1c1c1e; background: #fff;
         max-width: 800px; margin: 0 auto; padding: 32px 16px 96px; }}
  header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 32px; }}
  h1 {{ font-size: 28px; margin: 0; letter-spacing: .02em; }}
  h3 {{ font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #6b6b70; margin: 0 0 6px; }}
  .meta {{ text-align: right; }}
  .partes {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #6b6b70;
        border-bottom: 1.5px solid #1c1c1e; padding: 8px 6px; }}
  td {{ padding: 10px 6px; border-bottom: 1px solid #e3e3e6; vertical-align: top; }}
  .n {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
  .totales {{ width: 320px; margin: 16px 0 0 auto; }}
  .totales td {{ border: 0; padding: 4px 6px; }}
  .totales tr:last-child td {{ border-top: 1.5px solid #1c1c1e; font-weight: 700; font-size: 16px; padding-top: 10px; }}
  .notas {{ margin-top: 32px; font-size: 12.5px; color: #3a3a3c; }}
  .notas p {{ margin: 0 0 8px; }}
  .imprimir {{ position: fixed; right: 16px; bottom: 16px; padding: 10px 16px; border: 0; border-radius: 10px;
               background: #1c1c1e; color: #fff; font: inherit; cursor: pointer; }}
  @media (max-width: 560px) {{ .partes {{ grid-template-columns: 1fr; }} header {{ flex-direction: column; }} .meta {{ text-align: left; }}
                               .totales {{ width: 100%; }} }}
  @media print {{ body {{ padding: 0; }} .imprimir {{ display: none; }} }}
</style></head><body>
<header><h1>{t['factura']}</h1>
<div class="meta">{t['numero']} <strong>{e(x.numero)}</strong><br>{t['fecha']}: {_fecha(x.fecha, idioma)}</div></header>
<div class="partes">
{bloque(t['emisor'], emisor.nombre, emisor.nif, emisor.direccion, contacto)}
{bloque(t['cliente'], c.nombre, c.nif or "", c.direccion or "")}
</div>
<table><thead><tr>{cabecera}</tr></thead><tbody><tr>{fila}</tr></tbody></table>
<table class="totales"><tbody>{filas_totales}<tr><td>{t['total']}</td><td class=n>{_importe(x.total_a_cobrar, idioma)}</td></tr></tbody></table>
<div class="notas">
{f"<p>{t['dias']}: {_dias_texto(dias, idioma)}.</p>" if dias else ""}
{f"<p>{t['pago']} {e(emisor.iban)}.</p>" if emisor.iban else ""}
{f"<p>{e(nota)}</p>" if nota else ""}
{f"<p>{e(emisor.pie)}</p>" if emisor.pie else ""}
</div>
<button class="imprimir" onclick="window.print()">{t['imprimir']}</button>
</body></html>"""


@router.get("/autonomo/facturas/{factura_id}/documento", response_class=HTMLResponse)
def ver_documento(factura_id: int, s: Session = SesionDB):
    x = s.get(Factura, factura_id)
    if x is None:
        raise HTTPException(404, "No existe esa factura")
    return HTMLResponse(documento(x, leer_emisor(s)), headers={"Cache-Control": "no-store"})
