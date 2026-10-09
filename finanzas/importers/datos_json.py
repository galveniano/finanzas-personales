"""Carga de datos en bloque desde un fichero JSON: inmuebles, coches y sus hipotecas, contratos, gastos y
pagos, e inversiones privadas con sus llamadas de capital. Lo que ya existe (mismo nombre) no se duplica:
de un bien que ya existe se actualizan su tipo y uso, sus datos de compra y catastro, sus hipotecas (por nombre),
valoraciones (por fecha), gastos (por fecha y tipo), pagos (por fecha y concepto) y su contrato de alquiler,
para poder corregirlos volviendo a subir el fichero; el mensaje dice qué se ha actualizado.

    {"activos": [{"nombre": "Piso", "tipo": "inmueble", "uso": "alquiler", "precio_compra": 100000,
                  "valoraciones": [...], "hipotecas": [...], "contratos": [...], "gastos": [...], "pagos": [...]}],
     "inversiones": [{"nombre": "Fondo", "compromiso": 20000, "llamadas": [...]}],
     "prevision": {"nomina": {...}, "clientes": [...]}}
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas.models import (Activo, CambioRenta, ContratoAlquiler, Deuda, GastoInmueble, InversionPrivada,
                             PagoPrevisto, Valoracion)

TIPOS_ACTIVO = {"inmueble", "inmueble_en_construccion", "vehiculo", "otro"}


class ErrorDatos(ValueError):
    pass


def _fecha(v) -> date | None:
    try:
        return date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        raise ErrorDatos(f"Fecha no válida: {v!r} (usa AAAA-MM-DD)")


def _dinero(v, defecto="0") -> Decimal:
    try:
        return Decimal(str(v if v is not None else defecto))
    except ArithmeticError:
        raise ErrorDatos(f"Importe no válido: {v!r}")


def _pago(x: dict, **claves) -> PagoPrevisto:
    return PagoPrevisto(concepto=str(x.get("concepto", ""))[:160], fecha=_fecha(x.get("fecha")) or date.today(),
                        importe=_dinero(x.get("importe")), pagado=bool(x.get("pagado")), **claves)


def _activo(s: Session, x: dict) -> str:
    nombre = str(x.get("nombre", "")).strip()[:120]
    if not nombre:
        raise ErrorDatos("Falta el nombre de un inmueble o coche")
    if existente := s.scalar(select(Activo).where(Activo.nombre == nombre)):
        return _actualizar(s, existente, x)
    tipo = x.get("tipo", "inmueble")
    if tipo not in TIPOS_ACTIVO:
        raise ErrorDatos(f"{nombre}: tipo {tipo!r} no válido")
    a = Activo(nombre=nombre, tipo=tipo, uso=x.get("uso", "otro"), fecha_compra=_fecha(x.get("fecha_compra")),
               precio_compra=_dinero(x.get("precio_compra")), gastos_compra=_dinero(x.get("gastos_compra")),
               valor_catastral=_dinero(x.get("valor_catastral")),
               valor_catastral_construccion=_dinero(x.get("valor_catastral_construccion")),
               porcentaje_propiedad=_dinero(x.get("porcentaje_propiedad"), "100"), notas=str(x.get("notas", "")))
    s.add(a)
    s.flush()
    for v in x.get("valoraciones", []):
        s.add(Valoracion(activo_id=a.id, fecha=_fecha(v.get("fecha")) or date.today(), valor=_dinero(v.get("valor"))))
    for h in x.get("hipotecas", []):
        s.add(Deuda(activo_id=a.id, tipo="hipoteca", **_datos_hipoteca(h, nombre)))
    for c in x.get("contratos", []):
        _contrato(s, a, c)
    for g in x.get("gastos", []):
        s.add(GastoInmueble(activo_id=a.id, fecha=_fecha(g.get("fecha")) or date.today(), tipo=g.get("tipo", "otros"),
                            importe=_dinero(g.get("importe")), concepto=str(g.get("concepto", ""))))
    for p in x.get("pagos", []):
        s.add(_pago(p, activo_id=a.id))
    return f"{nombre}: añadido"


CAMPOS_COMPRA = {"fecha_compra": _fecha, "precio_compra": _dinero, "gastos_compra": _dinero,
                 "valor_catastral": _dinero, "valor_catastral_construccion": _dinero, "porcentaje_propiedad": _dinero}


def _datos_hipoteca(h: dict, nombre_activo: str) -> dict:
    manual = h.get("saldo_pendiente_manual")
    return {"nombre": str(h.get("nombre", f"Hipoteca {nombre_activo}"))[:120], "entidad": str(h.get("entidad", ""))[:80],
            "capital_inicial": _dinero(h.get("capital_inicial")), "tipo_interes_anual": _dinero(h.get("tipo_interes_anual")),
            "fecha_inicio": _fecha(h.get("fecha_inicio")), "plazo_meses": int(h.get("plazo_meses", 0)),
            "saldo_pendiente_manual": None if manual is None else _dinero(manual),
            "saldo_fecha": _fecha(h.get("saldo_fecha")) or (date.today() if manual is not None else None)}


def _contrato(s: Session, a: Activo, c: dict) -> ContratoAlquiler:
    contrato = ContratoAlquiler(activo_id=a.id, inquilino=str(c.get("inquilino", ""))[:120],
                                fecha_inicio=_fecha(c.get("fecha_inicio")) or date.today(),
                                fecha_fin=_fecha(c.get("fecha_fin")), renta_mensual=_dinero(c.get("renta_mensual")),
                                reduccion_pct=_dinero(c.get("reduccion_pct"), "60"))
    s.add(contrato)
    s.flush()
    _cambios(s, contrato, c)
    return contrato


def _cambios(s: Session, contrato: ContratoAlquiler, c: dict) -> None:
    ya = {x.desde for x in s.scalars(select(CambioRenta).where(CambioRenta.contrato_id == contrato.id))}
    for cambio in c.get("cambios", []):
        desde = _fecha(cambio.get("desde"))
        if desde and desde not in ya:
            s.add(CambioRenta(contrato_id=contrato.id, desde=desde, renta_mensual=_dinero(cambio.get("renta_mensual"))))


def _actualizar(s: Session, a: Activo, x: dict) -> str:
    """Corrige un bien que ya existe con lo que trae el fichero, sin duplicar nada, y dice qué ha cambiado."""
    que = []
    if any(campo in x for campo in CAMPOS_COMPRA):
        que.append("compra y catastro")
    for campo, conv in CAMPOS_COMPRA.items():
        if campo in x:
            setattr(a, campo, conv(x[campo]))
    if "notas" in x:
        a.notas = str(x["notas"])
        que.append("notas")
    if "tipo" in x:
        if x["tipo"] not in TIPOS_ACTIVO:
            raise ErrorDatos(f"{a.nombre}: tipo {x['tipo']!r} no válido")
        a.tipo = x["tipo"]
        que.append("tipo")
    if "uso" in x:
        a.uso = str(x["uso"])
        que.append("uso")
    deudas = {d.nombre: d for d in s.scalars(select(Deuda).where(Deuda.activo_id == a.id))}
    for h in x.get("hipotecas", []):
        datos = _datos_hipoteca(h, a.nombre)
        if d := deudas.get(datos["nombre"]):
            # Solo lo que trae el fichero; el pendiente real lleva su fecha
            claves = set(h) | ({"saldo_fecha"} if "saldo_pendiente_manual" in h else set())
            for campo, valor in datos.items():
                if campo in claves:
                    setattr(d, campo, valor)
            que.append(f"hipoteca {d.nombre}")
        else:
            s.add(Deuda(activo_id=a.id, tipo="hipoteca", **datos))
            que.append(f"hipoteca {datos['nombre']} (nueva)")
    valoraciones = {v.fecha: v for v in a.valoraciones}
    for v in x.get("valoraciones", []):
        fecha, valor = _fecha(v.get("fecha")) or date.today(), _dinero(v.get("valor"))
        if fecha in valoraciones:
            valoraciones[fecha].valor = valor
        else:
            s.add(Valoracion(activo_id=a.id, fecha=fecha, valor=valor))
    if x.get("valoraciones"):
        que.append(f"{len(x['valoraciones'])} valoraciones")
    gastos = {(g.fecha, g.tipo): g for g in s.scalars(select(GastoInmueble).where(GastoInmueble.activo_id == a.id))}
    for g in x.get("gastos", []):
        clave = (_fecha(g.get("fecha")) or date.today(), g.get("tipo", "otros"))
        if clave in gastos:
            gastos[clave].importe, gastos[clave].concepto = _dinero(g.get("importe")), str(g.get("concepto", ""))
        else:
            s.add(GastoInmueble(activo_id=a.id, fecha=clave[0], tipo=clave[1], importe=_dinero(g.get("importe")),
                                concepto=str(g.get("concepto", ""))))
    if x.get("gastos"):
        que.append(f"{len(x['gastos'])} gastos")
    pagos = {(p.fecha, p.concepto): p for p in s.scalars(select(PagoPrevisto).where(PagoPrevisto.activo_id == a.id))}
    for p in x.get("pagos", []):
        nuevo = _pago(p, activo_id=a.id)
        if viejo := pagos.get((nuevo.fecha, nuevo.concepto)):
            viejo.importe, viejo.pagado = nuevo.importe, nuevo.pagado
        else:
            s.add(nuevo)
    if x.get("pagos"):
        que.append(f"{len(x['pagos'])} pagos")
    contratos = s.scalars(select(ContratoAlquiler).where(ContratoAlquiler.activo_id == a.id)).all()
    if len(contratos) == 1 and len(x.get("contratos", [])) == 1:
        c, nuevo = contratos[0], x["contratos"][0]
        c.fecha_inicio = _fecha(nuevo.get("fecha_inicio")) or c.fecha_inicio
        c.renta_mensual = _dinero(nuevo.get("renta_mensual", c.renta_mensual))
        c.reduccion_pct = _dinero(nuevo.get("reduccion_pct", c.reduccion_pct))
        if "inquilino" in nuevo:
            c.inquilino = str(nuevo["inquilino"])[:120]
        if "fecha_fin" in nuevo:
            c.fecha_fin = _fecha(nuevo["fecha_fin"])
        _cambios(s, c, nuevo)
        que.append("contrato")
    elif not contratos and x.get("contratos"):
        for c in x["contratos"]:
            _contrato(s, a, c)
        que.append(f"{len(x['contratos'])} contratos (nuevos)")
    if not que:
        return f"{a.nombre}: ya existía, sin cambios"
    return f"{a.nombre}: ya existía; actualizado: {', '.join(que)}"


def _inversion(s: Session, x: dict) -> str:
    nombre = str(x.get("nombre", "")).strip()[:120]
    if not nombre:
        raise ErrorDatos("Falta el nombre de una inversión")
    if s.scalar(select(InversionPrivada).where(InversionPrivada.nombre == nombre)):
        return f"{nombre}: ya existía, no se ha tocado"
    inv = InversionPrivada(nombre=nombre, gestora=str(x.get("gestora", ""))[:120], compromiso=_dinero(x.get("compromiso")),
                           fecha_compromiso=_fecha(x.get("fecha_compromiso")), nav=_dinero(x.get("nav")),
                           nav_fecha=_fecha(x.get("nav_fecha")), distribuido=_dinero(x.get("distribuido")),
                           notas=str(x.get("notas", "")))
    s.add(inv)
    s.flush()
    for p in x.get("llamadas", []):
        s.add(_pago(p, inversion_id=inv.id))
    return f"{nombre}: añadido"


def importar(s: Session, datos: dict) -> list[str]:
    """Todo o nada: si algo falla no se guarda nada. Una copia de seguridad completa (lo que baja /exportar)
    se reconoce por su formato y sustituye todos los datos (ver `restaurar`)."""
    if not isinstance(datos, dict):
        raise ErrorDatos("El fichero debe ser un objeto JSON con 'activos' y/o 'inversiones', o una copia de seguridad")
    if es_copia(datos):
        return restaurar(s, datos)
    try:
        mensajes = [_activo(s, x) for x in datos.get("activos", [])]
        mensajes += [_inversion(s, x) for x in datos.get("inversiones", [])]
        if isinstance(datos.get("prevision"), dict):
            from finanzas import prevision
            prevision.guardar(s, {**prevision.leer(s), **datos["prevision"]})
            mensajes.append("Supuestos de la previsión guardados")
        s.commit()
        return mensajes
    except Exception:
        s.rollback()
        raise


# --- Copia de seguridad completa (formato de /exportar) ------------------------------------------

def es_copia(datos) -> bool:
    """Lo que baja /exportar: {"version": 1, "fecha": "AAAA-MM-DD", "tablas": {nombre: [filas...]}}."""
    return isinstance(datos, dict) and "version" in datos and isinstance(datos.get("tablas"), dict)


def vista_previa(datos) -> dict:
    """Qué haría el fichero, sin tocar nada: sirve para pedir confirmación antes de sustituirlo todo."""
    if not isinstance(datos, dict):
        raise ErrorDatos("El fichero debe ser un objeto JSON con 'activos' y/o 'inversiones', o una copia de seguridad")
    if not es_copia(datos):
        return {"copia": False, "activos": len(datos.get("activos") or []), "inversiones": len(datos.get("inversiones") or []),
                "prevision": isinstance(datos.get("prevision"), dict)}
    tablas = [{"tabla": nombre, "filas": len(filas)} for nombre, filas in datos["tablas"].items()
              if isinstance(filas, list) and filas]
    return {"copia": True, "fecha": datos.get("fecha"), "version": datos.get("version"), "tablas": tablas,
            "filas": sum(t["filas"] for t in tablas)}


def _valor(col, v):
    """De lo que hay en el JSON (ISO, base64, float) al tipo de la columna."""
    import base64
    from datetime import datetime
    from sqlalchemy import sql
    if v is None:
        return None
    t = col.type
    try:
        if isinstance(t, sql.sqltypes.LargeBinary):
            return base64.b64decode(v)
        if isinstance(t, sql.sqltypes.DateTime):
            return datetime.fromisoformat(str(v))
        if isinstance(t, sql.sqltypes.Date):
            return date.fromisoformat(str(v)[:10])
        if isinstance(t, sql.sqltypes.Numeric):
            return Decimal(str(v))
        if isinstance(t, sql.sqltypes.Boolean):
            return bool(v)
    except (ValueError, TypeError, ArithmeticError):
        raise ErrorDatos(f"{col.table.name}.{col.name}: valor no válido {v!r}")
    return v


def restaurar(s: Session, datos: dict) -> list[str]:
    """Sustituye TODOS los datos por los de la copia: vacía las tablas (de las hijas a las madres) y vuelve a
    insertar las filas con sus mismos ids, todo en una transacción. Las claves de API cifradas no viajan en la
    copia, así que hay que volver a ponerlas."""
    from sqlalchemy import text
    from finanzas import db
    tablas = datos["tablas"]
    conocidas = {t.name: t for t in db.Base.metadata.sorted_tables}
    for nombre, filas in tablas.items():
        if not isinstance(filas, list):
            raise ErrorDatos(f"La tabla {nombre} de la copia no es una lista de filas")
    mensajes = []
    try:
        for tabla in reversed(db.Base.metadata.sorted_tables):
            s.execute(tabla.delete())
        for tabla in db.Base.metadata.sorted_tables:
            filas = [f for f in tablas.get(tabla.name) or [] if isinstance(f, dict)]
            columnas = {c.name: c for c in tabla.columns}
            # Filas agrupadas por las columnas que traen (las de otra versión pueden traer más o menos)
            grupos: dict[tuple, list[dict]] = {}
            for fila in filas:
                limpia = {k: _valor(columnas[k], v) for k, v in fila.items() if k in columnas}
                grupos.setdefault(tuple(sorted(limpia)), []).append(limpia)
            for grupo in grupos.values():
                s.execute(tabla.insert(), grupo)
            if filas:
                mensajes.append(f"{tabla.name.replace('_', ' ')}: {len(filas)} filas")
        if s.get_bind().dialect.name == "postgresql":
            # En Postgres los ids salen de secuencias: hay que ponerlas detrás del mayor id restaurado
            for tabla in db.Base.metadata.sorted_tables:
                if "id" in tabla.c:
                    s.execute(text(f"SELECT setval(pg_get_serial_sequence('{tabla.name}', 'id'), "
                                   f"COALESCE((SELECT MAX(id) FROM {tabla.name}), 0) + 1, false)"))
        s.commit()
    except Exception:
        s.rollback()
        raise
    desconocidas = sorted(set(tablas) - set(conocidas))
    cuando = datos.get("fecha") or "sin fecha"
    cabecera = f"Copia del {cuando} restaurada: {sum(len(v) for v in tablas.values() if isinstance(v, list))} filas"
    if desconocidas:
        cabecera += f" (sin usar: {', '.join(desconocidas)})"
    return [cabecera, *mensajes,
            "Las claves del asistente no viajan en la copia: vuelve a ponerla en Ajustes → Asistente (IA)."]
