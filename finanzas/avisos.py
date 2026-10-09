"""Avisos de Inicio (algo falla o hay un plazo cerca) y calendario de plazos fiscales."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import ajustes, declaraciones, sync
from finanzas.fechas import ahora_utc
from finanzas.fiscal import autonomo
from finanzas.models import Activo, Factura, GastoAutonomo, RegistroSync, Valoracion

CLAVE_ULTIMA_COPIA = "ultima_copia"


def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def plazos(desde: date, hasta: date) -> list[dict]:
    """Plazos de los modelos que presentas (303, 130, 390 y renta) entre dos fechas. `ver` es la sección de
    Impuestos a la que lleva cada uno (?ver=)."""
    lista = []
    for anio in range(desde.year - 1, hasta.year + 1):
        for t in range(1, 5):
            lista.append({"fecha": autonomo.vencimiento(anio, t), "titulo": f"303 y 130 del {t}T {anio}",
                          "detalle": "IVA y pago fraccionado del IRPF. Si domicilias el pago, cinco días antes.",
                          "modelos": [("303", anio, f"{t}T"), ("130", anio, f"{t}T")], "ver": "trimestres"})
        lista.append({"fecha": date(anio + 1, 1, 30), "titulo": f"390 de {anio}", "detalle": "Resumen anual del IVA.",
                      "modelos": [("390", anio, "0A")], "ver": "trimestres"})
        lista.append({"fecha": date(anio + 1, 4, 2), "titulo": f"Empieza la renta {anio}",
                      "detalle": "Ya puedes revisar el borrador.", "modelos": [], "ver": "renta"})
        lista.append({"fecha": date(anio + 1, 6, 25), "titulo": f"Renta {anio} domiciliada",
                      "detalle": "Último día para presentar la renta a pagar con domiciliación.",
                      "modelos": [("100", anio, "0A")], "ver": "renta"})
        lista.append({"fecha": date(anio + 1, 6, 30), "titulo": f"Fin de la renta {anio}", "detalle": "",
                      "modelos": [("100", anio, "0A")], "ver": "renta"})
    return sorted((p for p in lista if desde <= p["fecha"] <= hasta), key=lambda p: p["fecha"])


def plazos_con_estado(s: Session, desde: date, hasta: date, prev: dict | None = None,
                      hoy: date | None = None) -> list[dict]:
    """Los plazos con `presentado` (todo lo que exige ese plazo está presentado; None si no exige nada, como el
    inicio de la renta) y `vencido`. El 130 no se exige en los trimestres en que estás exento: por las facturas
    del año anterior (más del 70 % con retención) o por la previsión (`prev`, que se calcula solo si hace falta)."""
    from finanzas import prevision
    hoy = hoy or date.today()
    facturas = gastos = None
    cache = {"prev": prev}

    def exento_130(anio: int, t: int) -> bool:
        nonlocal facturas, gastos
        if facturas is None:
            facturas = s.scalars(select(Factura)).all()
            gastos = s.scalars(select(GastoAutonomo)).all()
        if autonomo.calcular_130(anio, t, facturas, gastos).exento:
            return True
        if cache["prev"] is None:
            cache["prev"] = prevision.calcular(s) if prevision.tiene_clientes(prevision.leer(s)) else {}
        return bool((cache["prev"].get("trimestres") or {}).get(f"{anio}-{t}", {}).get("exento_130"))

    lista = []
    for p in plazos(desde, hasta):
        exigidos = [m for m in p["modelos"] if not (m[0] == "130" and exento_130(m[1], int(m[2][0])))]
        presentado = all(declaraciones.presentada(s, *m) for m in exigidos) if p["modelos"] else None
        lista.append({**p, "exigidos": exigidos, "presentado": presentado,
                      "vencido": p["fecha"] < hoy and presentado is False})
    return lista


def calcular(s: Session, regularizacion: list[dict] | None = None, prev: dict | None = None) -> list[dict]:
    """Lista de avisos: nivel (error, aviso, info), texto y a dónde ir para arreglarlo. `prev` (la previsión,
    si ya la tienes calculada) evita repetirla para saber si estás exento del 130."""
    hoy = date.today()
    avisos = []
    estado = sync.estado(s)
    for fuente, nombre in (("sabadell", "Sabadell"), ("indexa", "Indexa")):
        e = estado[fuente]
        if not e["configurado"]:
            continue
        ultima = e.get("ultima")
        if ultima and not ultima["ok"]:
            avisos.append({"nivel": "error", "texto": f"La última sincronización de {nombre} falló: {ultima['mensaje'][:160]}",
                           "ir": "/ajustes"})
        ultimo_ok = s.scalar(select(RegistroSync.fecha).where(RegistroSync.fuente == fuente, RegistroSync.ok)
                             .order_by(RegistroSync.id.desc()).limit(1))
        if ultimo_ok and ahora_utc() - ultimo_ok > timedelta(days=3):
            avisos.append({"nivel": "aviso", "texto": f"{nombre} no se sincroniza bien desde el {ultimo_ok:%d/%m}.",
                           "ir": "/ajustes"})
    sab = estado["sabadell"]
    if sab["configurado"] and not sab["conectado"]:
        avisos.append({"nivel": "error", "texto": "El permiso de Sabadell ha caducado: vuelve a conectarlo.", "ir": "/ajustes"})
    elif sab["valida_hasta"]:
        quedan = (date.fromisoformat(sab["valida_hasta"]) - hoy).days
        if quedan <= 15:
            avisos.append({"nivel": "aviso", "texto": f"El permiso de Sabadell caduca en {quedan} días: renuévalo.",
                           "ir": "/ajustes"})
    for p in plazos_con_estado(s, hoy, hoy + timedelta(days=15), prev, hoy):
        if p["presentado"]:
            continue
        dias = (p["fecha"] - hoy).days
        cuando = "hoy" if dias == 0 else "mañana" if dias == 1 else f"en {dias} días"
        avisos.append({"nivel": "aviso" if dias <= 5 else "info", "texto": f"{p['titulo']}: el plazo acaba {cuando}.",
                       "ir": f"/impuestos?ver={p['ver']}"})
    ultima_copia = ajustes.leer(s, CLAVE_ULTIMA_COPIA)
    if not ultima_copia or (hoy - date.fromisoformat(ultima_copia[:10])).days > 31:
        avisos.append({"nivel": "info", "texto": "Haz una copia de tus datos: hace más de un mes de la última."
                       if ultima_copia else "Aún no has hecho ninguna copia de tus datos.", "ir": "/ajustes"})
    for a in s.scalars(select(Activo).where(Activo.tipo == "inmueble")):
        ultima = s.scalar(select(Valoracion.fecha).where(Valoracion.activo_id == a.id)
                          .order_by(Valoracion.fecha.desc()).limit(1))
        if not ultima or (hoy - ultima).days > 365:
            avisos.append({"nivel": "info", "texto": f"Actualiza lo que vale {a.nombre}: "
                           + (f"la última valoración es del {ultima:%m/%Y}." if ultima else "aún vale lo que costó."),
                           "ir": "/inmuebles"})
    for r in regularizacion or []:
        neto = r["a_pagar"] - r["a_devolver"] - r["devolucion_pluriactividad"]
        if r["a_pagar"] >= 200:
            texto = (f"Cuota de autónomos {r['anio']}: por tus rendimientos te tocaría cotizar unos "
                     f"{_eur(r['cuota_minima_anual'])} y {'llevas' if r['previsto'] else 'pagaste'} "
                     f"{_eur(r['cuota_pagada'])}. La Seguridad Social puede reclamar la diferencia")
            if not r["devolucion_pluriactividad"]:
                texto += "."
            elif neto > 0:
                texto += f" (con la devolución por pluriactividad, unos {_eur(neto)} netos)."
            else:
                texto += ", aunque la devolución por pluriactividad lo compensaría."
            avisos.append({"nivel": "aviso", "texto": texto, "ir": "/impuestos?ver=hucha"})
    from finanzas import prevision
    for p in prevision.plazos_rentas(s, hoy):
        cuando = date.fromisoformat(p["fecha"])
        if (cuando - hoy).days <= 60:
            avisos.append({"nivel": "aviso" if (cuando - hoy).days <= 15 else "info",
                           "texto": f"El {cuando:%d/%m/%Y} Hacienda te carga {_eur(p['importe'])} de la {p['concepto'][0].lower()}"
                                    f"{p['concepto'][1:]}: ten el dinero en la cuenta domiciliada.", "ir": "/impuestos?ver=hucha"})
    from finanzas import actividad, presupuestos
    avisos += presupuestos.avisos(s)
    avisos += actividad.avisos(s)
    orden = {"error": 0, "aviso": 1, "info": 2}
    return sorted(avisos, key=lambda a: orden[a["nivel"]])
