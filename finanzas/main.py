"""Aplicación web local. Arranca con:  uvicorn finanzas.main:app --reload"""
import warnings
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import exc as sa_exc
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import db, patrimonio
from finanzas.categorizar import sembrar_categorias
from finanzas.fiscal import alquiler, autonomo
from finanzas.hipoteca import cuota_mensual, intereses_anio, saldo_pendiente
from finanzas.importers import sabadell
from finanzas.integrations import indexa
from finanzas.models import (
    Activo, CambioRenta, Categoria, Cliente, ContratoAlquiler, Cuenta, Deuda, Factura, GastoAutonomo,
    GastoInmueble, Movimiento, Nomina, Objetivo, PagoPrevisto, Valoracion,
)

# SQLite no tiene tipo decimal nativo; el aviso es esperado.
warnings.filterwarnings("ignore", category=sa_exc.SAWarning, message=".*Decimal.*")

AQUI = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    with db.SessionLocal() as s:
        sembrar_categorias(s)
    yield


app = FastAPI(title="Finanzas personales", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
templates = Jinja2Templates(directory=AQUI / "templates")


def eur(valor) -> str:
    if valor is None:
        return "—"
    v = Decimal(valor).quantize(Decimal("0.01"))
    entero, dec = f"{abs(v):,.2f}".split(".")
    return f"{'-' if v < 0 else ''}{entero.replace(',', '.')},{dec} €"


def fecha_es(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


templates.env.filters["eur"] = eur
templates.env.filters["fecha"] = fecha_es


def D(valor: str | None, defecto: str = "0") -> Decimal:
    """Acepta '1234.56' (campo numérico del navegador) y '1.234,56' (escrito a mano)."""
    v = (valor or "").strip()
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    return Decimal(v or defecto)


def F(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def volver(url: str, msg: str = "") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}msg={msg}" if msg else url, status_code=303)


def render(request: Request, plantilla: str, **ctx) -> HTMLResponse:
    ctx.setdefault("msg", request.query_params.get("msg", ""))
    ctx["hoy"] = date.today()
    return templates.TemplateResponse(request, plantilla, ctx)


SesionDB = Depends(db.get_session)


# --- Panel ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def panel(request: Request, s: Session = SesionDB):
    hoy = date.today()
    p = patrimonio.calcular(s, hoy)
    proximos = s.scalars(
        select(PagoPrevisto).where(~PagoPrevisto.pagado).order_by(PagoPrevisto.fecha).limit(8)
    ).all()
    facturas, gastos = s.scalars(select(Factura)).all(), s.scalars(select(GastoAutonomo)).all()
    t = autonomo.trimestre_de(hoy)
    m303 = autonomo.calcular_303(hoy.year, t, facturas, gastos)
    m130 = autonomo.calcular_130(hoy.year, t, facturas, gastos)
    return render(request, "panel.html", p=p, proximos=proximos, m303=m303, m130=m130)


# --- Cuentas y movimientos --------------------------------------------------

@app.get("/cuentas", response_class=HTMLResponse)
def cuentas(request: Request, cuenta_id: int | None = None, categoria_id: int | None = None,
            s: Session = SesionDB):
    lista = s.scalars(select(Cuenta).order_by(Cuenta.tipo, Cuenta.nombre)).all()
    q = select(Movimiento).order_by(Movimiento.fecha.desc(), Movimiento.id.desc()).limit(300)
    if cuenta_id:
        q = q.where(Movimiento.cuenta_id == cuenta_id)
    if categoria_id == 0:
        q = q.where(Movimiento.categoria_id.is_(None))
    elif categoria_id:
        q = q.where(Movimiento.categoria_id == categoria_id)
    categorias = s.scalars(select(Categoria).order_by(Categoria.nombre)).all()
    return render(request, "cuentas.html", cuentas=lista, movimientos=s.scalars(q).all(),
                  categorias=categorias, cuenta_id=cuenta_id, categoria_id=categoria_id)


@app.post("/cuentas")
def crear_cuenta(nombre: str = Form(...), entidad: str = Form(""), tipo: str = Form("corriente"),
                 iban: str = Form(""), saldo: str = Form("0"), s: Session = SesionDB):
    # Sin saldo inicial, la fecha queda vacía para que el primer extracto importado fije el saldo
    s.add(Cuenta(nombre=nombre, entidad=entidad, tipo=tipo, iban=iban, saldo=D(saldo),
                 saldo_fecha=date.today() if D(saldo) else None))
    s.commit()
    return volver("/cuentas", "Cuenta creada")


@app.post("/cuentas/{cuenta_id}/importar")
async def importar_extracto(cuenta_id: int, fichero: UploadFile = File(...), s: Session = SesionDB):
    cuenta = s.get(Cuenta, cuenta_id)
    try:
        r = sabadell.importar(s, cuenta, fichero.filename or "extracto.csv", await fichero.read())
    except ValueError as e:
        return volver(f"/cuentas?cuenta_id={cuenta_id}", str(e))
    return volver(f"/cuentas?cuenta_id={cuenta_id}",
                  f"{r.nuevos} movimientos nuevos, {r.duplicados} ya estaban")


@app.post("/movimientos/{mov_id}/categoria")
def cambiar_categoria(mov_id: int, categoria_id: str = Form(""), volver_a: str = Form("/cuentas"),
                      s: Session = SesionDB):
    mov = s.get(Movimiento, mov_id)
    mov.categoria_id = int(categoria_id) if categoria_id else None
    s.commit()
    return volver(volver_a)


@app.post("/indexa/sincronizar")
def sincronizar_indexa(s: Session = SesionDB):
    try:
        cuentas = indexa.sincronizar(s)
    except Exception as e:  # mostramos el error en la página, no un 500
        return volver("/cuentas", f"Indexa: {e}")
    return volver("/cuentas", f"Indexa actualizado ({len(cuentas)} cuentas)")


# --- Autónomo ---------------------------------------------------------------

@app.get("/autonomo", response_class=HTMLResponse)
def vista_autonomo(request: Request, anio: int | None = None, s: Session = SesionDB):
    anio = anio or date.today().year
    facturas = s.scalars(select(Factura).order_by(Factura.fecha.desc())).all()
    gastos = s.scalars(select(GastoAutonomo).order_by(GastoAutonomo.fecha.desc())).all()
    trimestres = [
        (autonomo.calcular_303(anio, t, facturas, gastos), autonomo.calcular_130(anio, t, facturas, gastos))
        for t in range(1, 5)
    ]
    clientes = s.scalars(select(Cliente).order_by(Cliente.nombre)).all()
    return render(request, "autonomo.html", anio=anio, trimestres=trimestres,
                  facturas=[f for f in facturas if f.fecha.year == anio],
                  gastos=[g for g in gastos if g.fecha.year == anio], clientes=clientes)


@app.post("/autonomo/facturas")
def crear_factura(numero: str = Form(...), cliente: str = Form(...), fecha: str = Form(...),
                  concepto: str = Form(""), base: str = Form(...), tipo_iva: str = Form("21"),
                  tipo_retencion: str = Form("15"), fecha_cobro: str = Form(""), s: Session = SesionDB):
    cli = s.scalar(select(Cliente).where(Cliente.nombre == cliente.strip()))
    if cli is None:
        cli = Cliente(nombre=cliente.strip())
        s.add(cli)
        s.flush()
    s.add(Factura(numero=numero, cliente_id=cli.id, fecha=F(fecha), concepto=concepto, base=D(base),
                  tipo_iva=D(tipo_iva), tipo_retencion=D(tipo_retencion), fecha_cobro=F(fecha_cobro)))
    s.commit()
    return volver(f"/autonomo?anio={F(fecha).year}", "Factura registrada")


@app.post("/autonomo/gastos")
def crear_gasto_autonomo(fecha: str = Form(...), proveedor: str = Form(""), concepto: str = Form(""),
                         categoria: str = Form("otros"), base: str = Form(...), tipo_iva: str = Form("21"),
                         deducible_pct: str = Form("100"), s: Session = SesionDB):
    s.add(GastoAutonomo(fecha=F(fecha), proveedor=proveedor, concepto=concepto, categoria=categoria,
                        base=D(base), tipo_iva=D(tipo_iva), deducible_pct=D(deducible_pct)))
    s.commit()
    return volver(f"/autonomo?anio={F(fecha).year}", "Gasto registrado")


@app.post("/autonomo/{tipo}/{item_id}/borrar")
def borrar_autonomo(tipo: str, item_id: int, s: Session = SesionDB):
    modelo = {"facturas": Factura, "gastos": GastoAutonomo}[tipo]
    s.delete(s.get(modelo, item_id))
    s.commit()
    return volver("/autonomo", "Borrado")


# --- Nóminas ----------------------------------------------------------------

@app.get("/nominas", response_class=HTMLResponse)
def vista_nominas(request: Request, s: Session = SesionDB):
    nominas = s.scalars(select(Nomina).order_by(Nomina.fecha.desc())).all()
    anio = date.today().year
    del_anio = [n for n in nominas if n.fecha.year == anio]
    totales = {k: sum((getattr(n, k) for n in del_anio), Decimal("0"))
               for k in ("bruto", "retencion_irpf", "seguridad_social", "neto")}
    return render(request, "nominas.html", nominas=nominas, totales=totales, anio=anio)


@app.post("/nominas")
def crear_nomina(empresa: str = Form("Indra"), fecha: str = Form(...), bruto: str = Form(...),
                 retencion_irpf: str = Form(...), seguridad_social: str = Form(...), neto: str = Form(...),
                 s: Session = SesionDB):
    s.add(Nomina(empresa=empresa, fecha=F(fecha), bruto=D(bruto), retencion_irpf=D(retencion_irpf),
                 seguridad_social=D(seguridad_social), neto=D(neto)))
    s.commit()
    return volver("/nominas", "Nómina registrada")


# --- Inmuebles, hipotecas y alquiler ---------------------------------------

@app.get("/inmuebles", response_class=HTMLResponse)
def vista_inmuebles(request: Request, anio: int | None = None, s: Session = SesionDB):
    anio = anio or date.today().year
    hoy = date.today()
    activos = s.scalars(select(Activo).order_by(Activo.nombre)).all()
    fichas = []
    for a in activos:
        deudas = s.scalars(select(Deuda).where(Deuda.activo_id == a.id)).all()
        contratos = s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)).all()
        gastos = s.scalars(select(GastoInmueble).where(GastoInmueble.activo_id == a.id)
                           .order_by(GastoInmueble.fecha.desc())).all()
        pagos = s.scalars(select(PagoPrevisto).where(PagoPrevisto.activo_id == a.id)
                          .order_by(PagoPrevisto.fecha)).all()
        rend = None
        if contratos:
            # Los intereses de la hipoteca se calculan del cuadro si no se han apuntado a mano
            gastos_calc = list(gastos)
            if not any(g.tipo == "intereses" and g.fecha.year == anio for g in gastos):
                for d in deudas:
                    gastos_calc.append(GastoInmueble(activo_id=a.id, fecha=date(anio, 12, 31),
                                                     tipo="intereses", importe=intereses_anio(d, anio)))
            rend = alquiler.calcular_rendimiento(a, contratos, gastos_calc, anio)
        if a.tipo == "inmueble_en_construccion":
            valor = (sum((p.importe for p in pagos if p.pagado), Decimal("0")), "pagado a la promotora")
        else:
            valor = patrimonio.valor_activo(a, hoy)
        fichas.append(dict(
            activo=a, valor=valor,
            deudas=[(d, saldo_pendiente(d, hoy),
                     cuota_mensual(d.capital_inicial, d.tipo_interes_anual, d.plazo_meses)) for d in deudas],
            contratos=contratos, gastos=gastos, pagos=pagos, rend=rend,
        ))
    return render(request, "inmuebles.html", fichas=fichas, anio=anio)


@app.post("/inmuebles")
def crear_activo(nombre: str = Form(...), tipo: str = Form("inmueble"), uso: str = Form("otro"),
                 fecha_compra: str = Form(""), precio_compra: str = Form("0"), gastos_compra: str = Form("0"),
                 valor_catastral: str = Form("0"), valor_catastral_construccion: str = Form("0"),
                 porcentaje_propiedad: str = Form("100"), s: Session = SesionDB):
    s.add(Activo(nombre=nombre, tipo=tipo, uso=uso, fecha_compra=F(fecha_compra),
                 precio_compra=D(precio_compra), gastos_compra=D(gastos_compra),
                 valor_catastral=D(valor_catastral),
                 valor_catastral_construccion=D(valor_catastral_construccion),
                 porcentaje_propiedad=D(porcentaje_propiedad, "100")))
    s.commit()
    return volver("/inmuebles", "Inmueble creado")


@app.post("/inmuebles/{activo_id}/valoracion")
def crear_valoracion(activo_id: int, fecha: str = Form(...), valor: str = Form(...), s: Session = SesionDB):
    s.add(Valoracion(activo_id=activo_id, fecha=F(fecha), valor=D(valor)))
    s.commit()
    return volver("/inmuebles", "Valoración guardada")


@app.post("/inmuebles/{activo_id}/hipoteca")
def crear_hipoteca(activo_id: int, nombre: str = Form("Hipoteca"), entidad: str = Form("Banco Sabadell"),
                   capital_inicial: str = Form(...), tipo_interes_anual: str = Form(...),
                   fecha_inicio: str = Form(...), plazo_meses: int = Form(...),
                   saldo_pendiente_manual: str = Form(""), s: Session = SesionDB):
    s.add(Deuda(nombre=nombre, entidad=entidad, tipo="hipoteca", activo_id=activo_id,
                capital_inicial=D(capital_inicial), tipo_interes_anual=D(tipo_interes_anual),
                fecha_inicio=F(fecha_inicio), plazo_meses=plazo_meses,
                saldo_pendiente_manual=D(saldo_pendiente_manual) if saldo_pendiente_manual else None,
                saldo_fecha=date.today() if saldo_pendiente_manual else None))
    s.commit()
    return volver("/inmuebles", "Hipoteca guardada")


@app.post("/inmuebles/{activo_id}/contrato")
def crear_contrato(activo_id: int, inquilino: str = Form(""), fecha_inicio: str = Form(...),
                   fecha_fin: str = Form(""), renta_mensual: str = Form(...), reduccion_pct: str = Form("60"),
                   s: Session = SesionDB):
    s.add(ContratoAlquiler(activo_id=activo_id, inquilino=inquilino, fecha_inicio=F(fecha_inicio),
                           fecha_fin=F(fecha_fin), renta_mensual=D(renta_mensual),
                           reduccion_pct=D(reduccion_pct, "60")))
    s.commit()
    return volver("/inmuebles", "Contrato guardado")


@app.post("/contratos/{contrato_id}/renta")
def actualizar_renta(contrato_id: int, desde: str = Form(...), renta_mensual: str = Form(...),
                     s: Session = SesionDB):
    s.add(CambioRenta(contrato_id=contrato_id, desde=F(desde), renta_mensual=D(renta_mensual)))
    s.commit()
    return volver("/inmuebles", "Renta actualizada")


@app.post("/inmuebles/{activo_id}/gasto")
def crear_gasto_inmueble(activo_id: int, fecha: str = Form(...), tipo: str = Form(...),
                         importe: str = Form(...), concepto: str = Form(""), s: Session = SesionDB):
    s.add(GastoInmueble(activo_id=activo_id, fecha=F(fecha), tipo=tipo, importe=D(importe), concepto=concepto))
    s.commit()
    return volver("/inmuebles", "Gasto guardado")


# --- Objetivos y pagos previstos -------------------------------------------

@app.get("/planificacion", response_class=HTMLResponse)
def vista_planificacion(request: Request, s: Session = SesionDB):
    objetivos = s.scalars(select(Objetivo).order_by(Objetivo.fecha_objetivo)).all()
    pagos = s.scalars(select(PagoPrevisto).order_by(PagoPrevisto.fecha)).all()
    activos = s.scalars(select(Activo).order_by(Activo.nombre)).all()
    hoy = date.today()
    ahorro_mensual = {}
    for o in objetivos:
        if o.fecha_objetivo and o.fecha_objetivo > hoy:
            meses = max(1, (o.fecha_objetivo.year - hoy.year) * 12 + o.fecha_objetivo.month - hoy.month)
            ahorro_mensual[o.id] = max(Decimal("0"), (o.importe_objetivo - o.ahorrado) / meses)
    return render(request, "planificacion.html", objetivos=objetivos, pagos=pagos, activos=activos,
                  ahorro_mensual=ahorro_mensual)


@app.post("/objetivos")
def crear_objetivo(nombre: str = Form(...), tipo: str = Form("otro"), fecha_objetivo: str = Form(""),
                   importe_objetivo: str = Form("0"), ahorrado: str = Form("0"), s: Session = SesionDB):
    s.add(Objetivo(nombre=nombre, tipo=tipo, fecha_objetivo=F(fecha_objetivo),
                   importe_objetivo=D(importe_objetivo), ahorrado=D(ahorrado)))
    s.commit()
    return volver("/planificacion", "Objetivo creado")


@app.post("/pagos")
def crear_pago(concepto: str = Form(...), fecha: str = Form(...), importe: str = Form(...),
               objetivo_id: str = Form(""), activo_id: str = Form(""), pagado: str = Form(""),
               s: Session = SesionDB):
    s.add(PagoPrevisto(concepto=concepto, fecha=F(fecha), importe=D(importe),
                       objetivo_id=int(objetivo_id) if objetivo_id else None,
                       activo_id=int(activo_id) if activo_id else None, pagado=bool(pagado)))
    s.commit()
    return volver("/planificacion", "Pago previsto guardado")


@app.post("/pagos/{pago_id}/pagado")
def marcar_pagado(pago_id: int, s: Session = SesionDB):
    p = s.get(PagoPrevisto, pago_id)
    p.pagado = not p.pagado
    s.commit()
    return volver("/planificacion")
