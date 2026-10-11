"""Contrato entre el frontal y la API: toda ruta que el frontal llama (`api.get/post/patch/put/del('…')`,
`href="/api/…"`, `fetch('/api/…')`) existe en el servidor con ese método. Así un endpoint renombrado o borrado
en el backend no deja un botón roto en la web."""
import re
from pathlib import Path

from starlette.routing import Match, Mount

from finanzas.main import app

FRONTAL = Path(__file__).resolve().parent.parent / "frontend" / "src"
METODOS = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "del": "DELETE"}


def _literal(texto: str, i: int) -> tuple[str, int] | None:
    """Lee un literal de cadena que empieza en `i` ('…', "…" o `…` con ${…}) y lo devuelve con las expresiones
    `${…}` sustituidas por `1`, junto con la posición siguiente. None si en `i` no empieza una cadena."""
    comilla = texto[i]
    if comilla not in "'\"`":
        return None
    partes, j, prof = [], i + 1, 0
    while j < len(texto):
        c = texto[j]
        if prof == 0:
            if c == "\\":
                partes.append(texto[j + 1]); j += 2; continue
            if c == comilla:
                return "".join(partes), j + 1
            if comilla == "`" and texto.startswith("${", j):
                prof, j = 1, j + 2
                # Un valor en un segmento (`/pagos/${id}`, `?anio=${anio}`) cuenta como «1»; pegado a una palabra
                # (`datos${previa ? '?previa=true' : ''}`) es una cola opcional y no cambia la ruta
                if not partes or partes[-1] in "/=?&":
                    partes.append("1")
                continue
            partes.append(c)
        else:
            if c in "'\"":  # cadena anidada dentro de ${…}: la saltamos entera
                fin = texto.index(c, j + 1)
                j = fin + 1
                continue
            if c == "{":
                prof += 1
            elif c == "}":
                prof -= 1
        j += 1
    raise ValueError(f"cadena sin cerrar en {texto[i:i+40]!r}")


def _llamadas(fuente: str) -> list[tuple[str, str]]:
    """(método, ruta) por cada `api.<método>[<T>](<cadena>` y cada cadena `/api/…` suelta (enlaces y fetch)."""
    salida = []
    for m in re.finditer(r"\bapi\.(get|post|put|patch|del)\b", fuente):
        j = m.end()
        if fuente[j] == "<":  # genérico <T>, con posibles <> anidados
            prof = 0
            while True:
                prof += {"<": 1, ">": -1}.get(fuente[j], 0)
                j += 1
                if prof == 0:
                    break
        if fuente[j] != "(":
            continue
        j += 1
        while fuente[j].isspace():
            j += 1
        lit = _literal(fuente, j)
        if lit:
            salida.append((METODOS[m.group(1)], "/api" + lit[0]))
    for m in re.finditer(r"""(?<![\w.])(['"`])/api/""", fuente):
        lit = _literal(fuente, m.start())
        if lit:
            salida.append(("GET", lit[0]))
    return salida


def _rutas_frontal() -> dict[tuple[str, str], str]:
    rutas = {}
    for fichero in FRONTAL.rglob("*.ts*"):
        if fichero.name == "api.ts":
            continue
        for metodo, ruta in _llamadas(fichero.read_text(encoding="utf-8")):
            ruta = ruta.split("?")[0]
            rutas[(metodo, ruta)] = str(fichero.relative_to(FRONTAL))
    return rutas


def test_el_frontal_solo_llama_a_rutas_que_existen():
    rutas = _rutas_frontal()
    assert len(rutas) > 100, "la lectura del frontal no ha encontrado llamadas: revisa el analizador"
    # Se pregunta a las propias rutas (incluidos los routers anidados) si atienden ese método y esa ruta; el
    # Mount del frontal compilado atiende cualquier ruta y no cuenta
    servidor = [r for r in app.routes if not isinstance(r, Mount)]
    faltan = []
    for (metodo, ruta), fichero in sorted(rutas.items()):
        scope = {"type": "http", "method": metodo, "path": ruta, "root_path": "", "path_params": {}, "headers": [],
                 "query_string": b""}
        if not any(r.matches(scope)[0] == Match.FULL for r in servidor):
            faltan.append(f"{metodo} {ruta}  ({fichero})")
    assert not faltan, "rutas que usa el frontal y no existen en el servidor:\n" + "\n".join(faltan)


def test_el_analizador_entiende_plantillas():
    assert _llamadas("api.get<X<Y>>(`/a/${x ? 'b' : `c`}/d?q=${encodeURIComponent(q)}`)") == [("GET", "/api/a/1/d?q=1")]
    assert _llamadas("api.del(`/pagos/${p.id}`); fetch('/api/exportar?pdfs=true')") == [
        ("DELETE", "/api/pagos/1"), ("GET", "/api/exportar?pdfs=true")]
    assert _llamadas('api.post("/x", { a: 1 })') == [("POST", "/api/x")]
    assert _llamadas("api.post(`/importar/datos${previa ? '?previa=true' : ''}`)") == [("POST", "/api/importar/datos")]
