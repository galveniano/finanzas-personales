"""Análisis de gastos: en qué se va el dinero, dónde, cómo cambia y qué suscripciones y recibos fijos pagas.

Cada servicio sale una sola vez aunque se cobre en varias cuentas o con conceptos algo distintos
(«NETFLIX.COM», «COMPRA TARJ NETFLIX»…). Los traspasos entre tus cuentas no son gasto, las cuentas
que no son tuyas no cuentan y de las compartidas solo cuenta tu parte."""
import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from finanzas import auth, db
from finanzas.models import Cuenta
from finanzas.prevision import MovTuyo, ids_pagos_previstos, ids_traspaso, movimientos_tuyos

router = APIRouter(prefix="/api", dependencies=[Depends(auth.requiere_sesion)])

# Servicios conocidos: (clave, nombre, grupo, patrones, color de la marca).
# Los patrones se buscan en el concepto en minúsculas, sin tildes, espacios ni signos; los cortos (hasta
# 5 letras: «axa», «digi», «dkv»…), como palabra suelta para no confundirlos con trozos de otras palabras.
# La clave también es el icono que pinta el frontal (si lo tiene); si no, sale la inicial en el color.
SERVICIOS = [
    ("netflix", "Netflix", "Streaming", ["netflix"], "#E50914"),
    ("hbomax", "HBO Max", "Streaming", ["hbomax", "hbo"], "#5822B4"),
    ("disneyplus", "Disney+", "Streaming", ["disneyplus", "disney"], "#113CCF"),
    ("primevideo", "Amazon Prime", "Streaming", ["amazonprime", "primevideo", "amznprime", "primeamzn", "amazonmusic"],
     "#00A8E1"),
    ("appletv", "Apple TV+", "Streaming", ["appletv"], "#000000"),
    ("skyshowtime", "SkyShowtime", "Streaming", ["skyshowtime"], "#1A1A1A"),
    ("movistarplus", "Movistar Plus+", "Streaming", ["movistarplus"], "#019DF4"),
    ("dazn", "DAZN", "Streaming", ["dazn"], "#0C161C"),
    ("filmin", "Filmin", "Streaming", ["filmin"], "#E8473F"),
    ("atresplayer", "Atresplayer", "Streaming", ["atresplayer"], "#FF6A00"),
    ("crunchyroll", "Crunchyroll", "Streaming", ["crunchyroll"], "#F47521"),
    ("mubi", "MUBI", "Streaming", ["mubi"], "#000000"),
    ("paramountplus", "Paramount+", "Streaming", ["paramount"], "#0064FF"),
    ("twitch", "Twitch", "Streaming", ["twitch"], "#9146FF"),
    ("youtube", "YouTube Premium", "Streaming", ["youtubepremium", "youtube", "googleyoutube"], "#FF0000"),
    ("spotify", "Spotify", "Música y libros", ["spotify"], "#1DB954"),
    ("applemusic", "Apple Music", "Música y libros", ["applemusic"], "#FA243C"),
    ("deezer", "Deezer", "Música y libros", ["deezer"], "#A238FF"),
    ("tidal", "TIDAL", "Música y libros", ["tidal"], "#000000"),
    ("audible", "Audible", "Música y libros", ["audible"], "#F8991C"),
    ("kindle", "Kindle Unlimited", "Música y libros", ["kindleunlimited", "kindlesvcs", "kindle"], "#FF9900"),
    ("storytel", "Storytel", "Música y libros", ["storytel"], "#FF5C28"),
    ("apple", "Apple", "Apps y nube", ["applecombill", "applecom", "itunes", "icloud"], "#000000"),
    ("googleone", "Google One", "Apps y nube", ["googleone", "googlestorage"], "#4285F4"),
    ("google", "Google", "Apps y nube", ["googleplay", "google"], "#4285F4"),
    ("dropbox", "Dropbox", "Apps y nube", ["dropbox"], "#0061FF"),
    ("microsoft", "Microsoft 365", "Apps y nube", ["microsoft", "msbill", "office365"], "#0078D4"),
    ("adobe", "Adobe", "Apps y nube", ["adobe"], "#DA1F26"),
    ("notion", "Notion", "Apps y nube", ["notion"], "#000000"),
    ("canva", "Canva", "Apps y nube", ["canva"], "#00C4CC"),
    ("figma", "Figma", "Apps y nube", ["figma"], "#F24E1E"),
    ("github", "GitHub", "Apps y nube", ["github"], "#181717"),
    ("openai", "ChatGPT", "Apps y nube", ["openai", "chatgpt"], "#10A37F"),
    ("claude", "Claude", "Apps y nube", ["anthropic", "claudeai"], "#D97757"),
    ("perplexity", "Perplexity", "Apps y nube", ["perplexity"], "#1FB8CD"),
    ("cursor", "Cursor", "Apps y nube", ["cursor"], "#000000"),
    ("linkedin", "LinkedIn Premium", "Apps y nube", ["linkedin"], "#0A66C2"),
    ("duolingo", "Duolingo", "Apps y nube", ["duolingo"], "#58CC02"),
    ("zoom", "Zoom", "Apps y nube", ["zoomus", "zoomcom", "zoomvideo"], "#0B5CFF"),
    ("playstation", "PlayStation Plus", "Juegos", ["playstation", "sonyinteractive"], "#003791"),
    ("xbox", "Xbox Game Pass", "Juegos", ["xbox"], "#107C10"),
    ("nintendo", "Nintendo", "Juegos", ["nintendo"], "#E60012"),
    ("patreon", "Patreon", "Apps y nube", ["patreon"], "#000000"),
    ("glovo", "Glovo Prime", "Comida y transporte", ["glovoprime"], "#FFC244"),
    ("uber", "Uber One", "Comida y transporte", ["uberone"], "#000000"),
    ("movistar", "Movistar", "Teléfono e internet", ["movistar", "telefonica"], "#019DF4"),
    ("vodafone", "Vodafone", "Teléfono e internet", ["vodafone"], "#E60000"),
    ("orange", "Orange", "Teléfono e internet", ["orange"], "#FF7900"),
    ("digi", "Digi", "Teléfono e internet", ["digimobil", "digispain", "digi"], "#0055A4"),
    ("masmovil", "MásMóvil", "Teléfono e internet", ["masmovil"], "#FFD500"),
    ("yoigo", "Yoigo", "Teléfono e internet", ["yoigo"], "#9C2AA0"),
    ("pepephone", "Pepephone", "Teléfono e internet", ["pepephone"], "#E5007D"),
    ("lowi", "Lowi", "Teléfono e internet", ["lowi"], "#FF4F00"),
    ("simyo", "Simyo", "Teléfono e internet", ["simyo"], "#FF6600"),
    ("jazztel", "Jazztel", "Teléfono e internet", ["jazztel"], "#FFCC00"),
    ("iberdrola", "Iberdrola", "Luz, gas y agua", ["iberdrola", "curenergia"], "#5DA431"),
    ("endesa", "Endesa", "Luz, gas y agua", ["endesa"], "#0091D0"),
    ("naturgy", "Naturgy", "Luz, gas y agua", ["naturgy"], "#E57200"),
    ("holaluz", "Holaluz", "Luz, gas y agua", ["holaluz"], "#00C389"),
    ("totalenergies", "TotalEnergies", "Luz, gas y agua", ["totalenergies"], "#ED0000"),
    ("repsolluz", "Repsol Luz y Gas", "Luz, gas y agua", ["repsolluz", "repsolelectricidad"], "#FF8200"),
    ("emuasa", "Aguas de Murcia", "Luz, gas y agua", ["emuasa", "aguasdemurcia"], "#0077C8"),
    ("basicfit", "Basic-Fit", "Gimnasio", ["basicfit"], "#FF7900"),
    ("altafit", "Altafit", "Gimnasio", ["altafit"], "#E4002B"),
    ("mcfit", "McFit", "Gimnasio", ["mcfit"], "#000000"),
    ("anytimefitness", "Anytime Fitness", "Gimnasio", ["anytimefitness"], "#5E2A84"),
    ("vivagym", "VivaGym", "Gimnasio", ["vivagym"], "#FF5A00"),
    ("gofit", "GO fit", "Gimnasio", ["gofit"], "#00A19A"),
    ("strava", "Strava", "Gimnasio", ["strava"], "#FC4C02"),
    ("mapfre", "Mapfre", "Seguros", ["mapfre"], "#D81E05"),
    ("axa", "AXA", "Seguros", ["axa"], "#00008F"),
    ("allianz", "Allianz", "Seguros", ["allianz"], "#003781"),
    ("sanitas", "Sanitas", "Seguros", ["sanitas"], "#00A0DF"),
    ("adeslas", "Adeslas", "Seguros", ["adeslas", "segurcaixa"], "#00A9E0"),
    ("dkv", "DKV", "Seguros", ["dkv"], "#00843D"),
    ("asisa", "Asisa", "Seguros", ["asisa"], "#0066B3"),
    ("lineadirecta", "Línea Directa", "Seguros", ["lineadirecta"], "#E2001A"),
    ("mutua", "Mutua Madrileña", "Seguros", ["mutuamadrilena"], "#003DA5"),
    ("generali", "Generali", "Seguros", ["generali"], "#C21B17"),
    ("ocaso", "Ocaso", "Seguros", ["ocaso"], "#00539B"),
]
# Lo que es una suscripción (se puede dar de baja con un clic); el resto son recibos fijos
GRUPOS_SUSCRIPCION = {"Streaming", "Música y libros", "Apps y nube", "Juegos", "Comida y transporte", "Gimnasio"}
# Categorías que no son gasto del día a día: van aparte
APARTE = {"Impuestos"}
PERIODOS = {1: "mensual", 3: "trimestral", 6: "semestral", 12: "anual"}


def _plano(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sin_tildes.lower())


def servicio(concepto: str) -> tuple | None:
    """El servicio conocido al que corresponde un concepto del banco, si lo hay."""
    plano = _plano(concepto)
    palabras = {_plano(p) for p in re.split(r"[^A-Za-z0-9]+", unicodedata.normalize("NFKD", concepto or ""))}
    for s in SERVICIOS:
        if any(p in palabras if len(p) <= 5 else p in plano for p in s[3]):
            return s
    return None


def patron(concepto: str) -> str:
    """Concepto sin números, fechas ni palabras del banco, para reconocer el mismo cargo mes a mes."""
    texto = unicodedata.normalize("NFKD", concepto or "").encode("ascii", "ignore").decode().upper()
    texto = re.sub(r"[\d/.,:*#_+-]+", " ", texto)
    texto = re.sub(r"\b(COMPRA|COMPRAS|TARJ|TARJETA|PAGO|PAGOS|RECIBO|ADEUDO|CARGO|EN|DE|DEL|LA|A|SEPA|CONTACTLESS|"
                   r"MOVIL|BIZUM|APPLE ?PAY|GOOGLE ?PAY|COM|ES|WWW|SL|SA|SLU|S L)\b", " ", texto)
    # Fuera los números de tarjeta enmascarados (XXXX) y las letras sueltas
    return " ".join(w for w in texto.split() if len(w) > 1 and not re.fullmatch(r"X{3,}", w))[:40]


def _nombre(patron_: str) -> str:
    return " ".join(p.capitalize() for p in patron_.split()) or "Sin concepto"


def comercio(m: MovTuyo) -> tuple[str, str]:
    """(clave, nombre) del sitio donde se gasta: el servicio conocido o el concepto limpio."""
    s = servicio(m.concepto)
    if s:
        return s[0], s[1]
    p = patron(m.concepto)
    return p, _nombre(p)


def _inicio_mes(d: date, atras: int = 0) -> date:
    d = d.replace(day=1)
    for _ in range(atras):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


def _gastos(s: Session, desde: date, hasta: date) -> tuple[list[MovTuyo], list[MovTuyo], list[MovTuyo]]:
    """(ingresos, gastos del día a día, gastos aparte) de tus cuentas, sin traspasos entre ellas.
    Aparte van los impuestos y los pagos previstos (plazos de la casa, llamadas de capital…)."""
    movs = movimientos_tuyos(s, desde, hasta)
    fuera = ids_traspaso(movs)
    previstos = ids_pagos_previstos(s, movs)
    ingresos, gastos, aparte = [], [], []
    for m in movs:
        if m.tipo == "transferencia" or m.id in fuera or not m.tuyo:
            continue
        if m.tuyo > 0:
            ingresos.append(m)
        elif m.categoria in APARTE or m.id in previstos:
            aparte.append(m)
        else:
            gastos.append(m)
    return ingresos, gastos, aparte


def suscripciones(s: Session, hoy: date | None = None) -> list[dict]:
    """Suscripciones y recibos que se repiten, una vez cada uno aunque se cobren en varias cuentas.

    Un servicio conocido (Netflix, Movistar, Mapfre…) basta con que se cobre; cualquier otro cargo
    cuenta si se repite en al menos 2 meses distintos, como mucho una vez al mes y por un importe parecido."""
    hoy = hoy or date.today()
    desde = _inicio_mes(hoy, 13)
    movs = movimientos_tuyos(s, desde, hoy + timedelta(days=1))
    fuera = ids_traspaso(movs) | ids_pagos_previstos(s, movs)
    cuentas = {c.id: c.nombre for c in s.scalars(select(Cuenta))}
    grupos: dict[str, list[MovTuyo]] = defaultdict(list)
    conocidos: dict[str, tuple] = {}
    for m in movs:
        if m.importe >= 0 or m.tuyo >= 0 or m.tipo == "transferencia" or m.id in fuera or m.categoria in APARTE:
            continue
        sv = servicio(m.concepto)
        clave = sv[0] if sv else patron(m.concepto)
        if not clave:
            continue
        if sv:
            conocidos[clave] = sv
        grupos[clave].append(m)

    lista = []
    for clave, cargos in grupos.items():
        sv = conocidos.get(clave)
        cargos.sort(key=lambda m: m.fecha)
        por_mes: dict[str, float] = defaultdict(float)
        cuentas_mes: dict[str, set[int]] = defaultdict(set)
        for m in cargos:
            k = m.fecha.strftime("%Y-%m")
            por_mes[k] -= m.tuyo
            cuentas_mes[k].add(m.cuenta_id)
        meses = sorted(por_mes)
        importes = [por_mes[k] for k in meses]
        mediana = statistics.median(importes)
        if not sv:
            # Un cargo cualquiera: varios meses, como mucho una vez al mes y siempre por lo mismo (±20 %)
            if (len(meses) < 2 or len(cargos) > len(meses) + 1 or mediana <= 0
                    or any(abs(i - mediana) / mediana > 0.2 for i in importes)):
                continue
        # Cada cuánto se cobra: la mediana de días entre cargos de meses distintos
        primeros = [min(m.fecha for m in cargos if m.fecha.strftime("%Y-%m") == k) for k in meses]
        saltos = [(b - a).days for a, b in zip(primeros, primeros[1:])]
        if saltos:
            salto = statistics.median(saltos)
            cada = 1 if salto < 45 else 3 if salto < 135 else 6 if salto < 270 else 12
        else:
            # Un solo cargo de un servicio conocido, de hace más de mes y medio: si es caro (≥ 30 €) será un
            # pago anual (Amazon Prime…); si no, un mes suelto que ya no se cobra
            cada = 12 if (hoy - cargos[-1].fecha).days > 45 and mediana >= 30 else 1
        ultimo = cargos[-1]
        ultimo_importe = por_mes[meses[-1]]
        activa = (hoy - ultimo.fecha).days <= cada * 31 + 20
        # Lo de ahora: la mediana de los 3 últimos meses (si te suben el precio, cuenta el nuevo)
        al_mes = statistics.median(importes[-3:]) if cada == 1 else ultimo_importe / cada
        subida = None
        doble = {k for k, v in cuentas_mes.items() if len(v) > 1}
        if cada == 1 and sv and sv[2] in GRUPOS_SUSCRIPCION:  # la luz o el teléfono cambian cada mes
            # El último cambio de precio, si fue a más y en los últimos 6 meses
            for i in range(len(importes) - 1, 0, -1):
                if meses[i] in doble:  # dos cargos ese mes en dos cuentas: no es que suba
                    break
                if abs(importes[i] - importes[i - 1]) > importes[i - 1] * 0.02:
                    if (importes[i] > importes[i - 1] and len(importes) - i <= 6
                            and all(abs(x - importes[i]) <= importes[i] * 0.02 for x in importes[i:])):
                        subida = {"antes": round(importes[i - 1], 2), "ahora": round(importes[i], 2)}
                    break
        varias = sorted({cuentas.get(c, "") for c in {m.cuenta_id for m in cargos}})
        grupo = sv[2] if sv else ("Ocio y suscripciones" if ultimo.categoria == "Ocio y suscripciones"
                                  else ultimo.categoria or "Otros recibos")
        lista.append({
            "clave": clave, "nombre": sv[1] if sv else _nombre(clave), "icono": sv[0] if sv else None,
            "color": sv[4] if sv else None, "grupo": grupo, "categoria": ultimo.categoria,
            "tipo": "suscripcion" if (sv and sv[2] in GRUPOS_SUSCRIPCION) or grupo == "Ocio y suscripciones"
            else "recibo",
            "periodicidad": PERIODOS[cada], "importe": round(ultimo_importe if cada != 1 else al_mes, 2),
            "mes": round(al_mes, 2), "anual": round(al_mes * 12, 2),
            "ultimo_cargo": ultimo.fecha.isoformat(), "concepto": ultimo.concepto, "veces": len(cargos),
            "proximo": _proximo(ultimo.fecha, cada).isoformat() if activa else None,
            "activa": activa, "cuentas": varias, "cobro_doble": bool(doble & set(meses[-3:])), "subida": subida,
        })
    lista.sort(key=lambda x: (not x["activa"], -x["mes"]))
    return lista


def _proximo(ultimo: date, cada: int) -> date:
    mes = ultimo.month - 1 + cada
    anio, mes = ultimo.year + mes // 12, mes % 12 + 1
    for dia in (ultimo.day, 30, 29, 28):
        try:
            return date(anio, mes, dia)
        except ValueError:
            continue
    return date(anio, mes, 28)


def analisis(s: Session, meses: int = 6, hoy: date | None = None) -> dict:
    """Todo el gasto de los últimos meses completos, comparado con el periodo anterior de la misma duración."""
    hoy = hoy or date.today()
    fin = _inicio_mes(hoy)
    inicio = _inicio_mes(hoy, meses)
    antes = _inicio_mes(inicio, meses)
    ingresos, gastos, aparte = _gastos(s, inicio, fin)
    _, gastos_antes, _ = _gastos(s, antes, inicio)
    hay_antes = bool(gastos_antes)
    _, gastos_mes_actual, _ = _gastos(s, fin, hoy + timedelta(days=1))

    total_in = sum(m.tuyo for m in ingresos)
    total_g = -sum(m.tuyo for m in gastos)

    # Mes a mes
    por_mes = {_inicio_mes(fin, i).strftime("%Y-%m"): {"ingresos": 0.0, "gastos": 0.0, "aparte": 0.0}
               for i in range(meses, 0, -1)}
    for lista, campo, signo in ((ingresos, "ingresos", 1), (gastos, "gastos", -1), (aparte, "aparte", -1)):
        for m in lista:
            k = m.fecha.strftime("%Y-%m")
            if k in por_mes:
                por_mes[k][campo] += signo * m.tuyo

    # Por categoría, con los sitios donde más se gasta en cada una
    def por_categoria(lista: list[MovTuyo]) -> dict[str, float]:
        r: dict[str, float] = defaultdict(float)
        for m in lista:
            r[m.categoria or "Sin categoría"] -= m.tuyo
        return r
    cat, cat_antes = por_categoria(gastos), por_categoria(gastos_antes)
    sitios_cat: dict[str, dict[str, list]] = defaultdict(dict)
    sitios: dict[str, list] = {}
    for m in gastos:
        clave, nombre = comercio(m)
        for destino in (sitios_cat[m.categoria or "Sin categoría"], sitios):
            fila = destino.setdefault(clave, [nombre, 0.0, 0, servicio(m.concepto), m.categoria])
            fila[1] -= m.tuyo
            fila[2] += 1
    categorias = []
    for nombre, total in sorted(cat.items(), key=lambda x: -x[1]):
        previo = cat_antes.get(nombre, 0.0)
        top = sorted(sitios_cat[nombre].values(), key=lambda x: -x[1])[:5]
        categorias.append({
            "categoria": nombre, "total": round(total, 2), "mes": round(total / meses, 2),
            "peso": round(total / total_g * 100, 1) if total_g else 0,
            "mes_antes": round(previo / meses, 2) if hay_antes else None,
            "cambio": round((total - previo) / previo * 100, 1) if hay_antes and previo else None,
            "sitios": [{"nombre": n_, "total": round(t, 2), "veces": v} for n_, t, v, _, _ in top],
        })

    def fila_sitio(x: list) -> dict:
        n_, t, v, sv, categoria = x
        return {"nombre": n_, "total": round(t, 2), "veces": v, "mes": round(t / meses, 2), "categoria": categoria,
                "icono": sv[0] if sv else None, "color": sv[4] if sv else None}

    subs = suscripciones(s, hoy)
    fijos = {x["clave"] for x in subs}
    activas = [x for x in subs if x["activa"]]
    fijo = sum(x["mes"] for x in activas)
    gasto_mes = total_g / meses
    ultimo_mes = list(por_mes.values())[-1]["gastos"] if por_mes else 0.0
    return {
        "desde": inicio.isoformat(), "hasta": (fin - timedelta(days=1)).isoformat(), "meses": meses,
        "ingresos_mes": round(total_in / meses, 2), "gastos_mes": round(gasto_mes, 2),
        "ahorro_mes": round((total_in - total_g) / meses, 2),
        "tasa_ahorro": round((total_in - total_g) / total_in * 100, 1) if total_in else None,
        "gastos_mes_antes": round(-sum(m.tuyo for m in gastos_antes) / meses, 2) if hay_antes else None,
        "ultimo_mes": {"mes": list(por_mes)[-1] if por_mes else None, "gastos": round(ultimo_mes, 2)},
        "este_mes": {"gastos": round(-sum(m.tuyo for m in gastos_mes_actual), 2), "dia": hoy.day},
        "fijo_mes": round(fijo, 2), "variable_mes": round(max(gasto_mes - fijo, 0), 2),
        "por_mes": [{"mes": k, **{c: round(v, 2) for c, v in d.items()}} for k, d in por_mes.items()],
        "categorias": categorias,
        "sitios": [fila_sitio(x) for x in sorted(sitios.values(), key=lambda x: -x[1])[:10]],
        "mayores": [{"fecha": m.fecha.isoformat(), "concepto": m.concepto, "nombre": comercio(m)[1],
                     "categoria": m.categoria, "importe": round(-m.tuyo, 2)}
                    for m in sorted((m for m in gastos if comercio(m)[0] not in fijos), key=lambda m: m.tuyo)[:8]],
        "aparte": {"total": round(-sum(m.tuyo for m in aparte), 2),
                   "impuestos": round(-sum(m.tuyo for m in aparte if m.categoria in APARTE), 2)},
        "suscripciones": [x for x in subs if x["tipo"] == "suscripcion"],
        "recibos": [x for x in subs if x["tipo"] == "recibo"],
        "suscripciones_mes": round(sum(x["mes"] for x in activas if x["tipo"] == "suscripcion"), 2),
        "recibos_mes": round(sum(x["mes"] for x in activas if x["tipo"] == "recibo"), 2),
    }


@router.get("/gastos")
def ver_gastos(meses: int = 6, s: Session = Depends(db.get_session)):
    return analisis(s, max(1, min(meses, 12)))
