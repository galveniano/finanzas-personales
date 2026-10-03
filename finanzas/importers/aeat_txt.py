"""Lee los ficheros .txt de la AEAT: la declaración en el formato de presentación (diseño de registro BOE)
que generan el formulario web o los programas de ayuda.

    <T130020262T0000><AUX>...</AUX><T13001000> I<NIF><APELLIDOS><NOMBRE><EJERCICIO><PERIODO><casillas...></T13001000></T130020262T0000>

La etiqueta de fuera da modelo, ejercicio y periodo. Cada página empieza con <T{modelo}{página}000>,
seguida de un carácter de página complementaria y el tipo de declaración (I ingreso, U domiciliación,
N negativa, D devolución, C compensar...). Los importes son campos de 17 cifras con dos decimales (una N
delante si son negativos). El fichero no prueba que se presentara: no lleva fecha, CSV ni justificante.
"""
import re
from dataclasses import dataclass
from decimal import Decimal

from finanzas.importers.aeat import ErrorAEAT

CABECERA = re.compile(r"<T(\d{3})0(\d{4})(\w{2})0000>")
PAGINA = re.compile(r"<T(?P<mod>\d{3})(?P<pag>\d{2})000>(.*?)</T(?P=mod)(?P=pag)000>", re.S)
AUX = re.compile(r"<AUX>(.*?)</AUX>", re.S)
TIPOS = {"I": "ingresar", "U": "domiciliar", "G": "ingresar", "N": "negativa", "D": "devolver",
         "C": "compensar", "B": "compensar", "X": "devolver", "V": "devolver", "0": "cero"}
SIGNO = {"ingresar": 1, "domiciliar": 1, "devolver": -1, "compensar": -1, "negativa": 0, "cero": 0}

# Dónde está el resultado final en los modelos cuyo diseño conocemos: (página, nº de casilla de importe)
RESULTADO = {"130": ("01", 19)}
# Página 01 de los modelos trimestrales: etiqueta, complementaria, tipo, NIF, apellidos, nombre, ejercicio, periodo
INICIO_CASILLAS = 1 + 1 + 9 + 60 + 20 + 4 + 2


@dataclass
class DeclaracionTxt:
    modelo: str
    ejercicio: int
    periodo: str
    resultado: str
    importe: Decimal
    exacto: bool  # False si el importe se ha deducido sin conocer el diseño del modelo


def _cifra(campo: str) -> Decimal | None:
    negativo = campo.startswith("N")
    digitos = campo[1:] if negativo else campo
    if not digitos.isdigit():
        return None
    valor = Decimal(digitos) / 100
    return -valor if negativo else valor


def _casillas(cuerpo: str) -> list[Decimal | None]:
    numeros = cuerpo[INICIO_CASILLAS:].rstrip()
    return [_cifra(numeros[i:i + 17]) for i in range(0, len(numeros) - 16, 17)]


def leer(contenido: bytes) -> DeclaracionTxt:
    # Los ficheros de la AEAT van en ISO-8859-1, pero si alguien los guarda en UTF-8 la Ñ ocupa dos bytes
    # y descuadra las posiciones: se decodifica como UTF-8 si es válido y si no como Latin-1.
    try:
        texto = contenido.decode("utf-8")
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1")
    m = CABECERA.search(texto)
    if not m:
        raise ErrorAEAT("No parece un fichero de declaración de la AEAT (falta la cabecera <T…>)")
    modelo, ejercicio, periodo = m.group(1), int(m.group(2)), m.group(3)
    paginas = {pag: cuerpo for mod, pag, cuerpo in PAGINA.findall(texto) if mod == modelo}
    if not paginas:
        raise ErrorAEAT(f"El fichero del modelo {modelo} no trae ninguna página")
    primera = paginas[min(paginas)]
    resultado = TIPOS.get(primera[1:2], "otro")

    importe, exacto = None, False
    if modelo in RESULTADO and RESULTADO[modelo][0] in paginas:
        pagina, casilla = RESULTADO[modelo]
        valores = _casillas(paginas[pagina])
        if len(valores) >= casilla and valores[casilla - 1] is not None:
            importe, exacto = valores[casilla - 1], True
    if importe is None:
        # Sin diseño conocido: el bloque AUX que añade el programa de la AEAT termina en importe + tipo
        aux = AUX.search(texto)
        fin = re.search(r"(N?\d{17})([A-Z])\s*$", aux.group(1)) if aux else None
        if not fin:
            raise ErrorAEAT(f"No sé leer el importe del modelo {modelo} en .txt; súbelo en PDF o añádelo a mano")
        importe = _cifra(fin.group(1))
        resultado = TIPOS.get(fin.group(2), resultado)
    importe = abs(importe) * SIGNO.get(resultado, 1) if SIGNO.get(resultado, 1) else Decimal("0")
    return DeclaracionTxt(modelo, ejercicio, periodo, resultado, importe.quantize(Decimal("0.01")), exacto)
