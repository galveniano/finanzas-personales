"""Modelo de datos. Todos los importes en euros, con Numeric(14, 2)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finanzas.db import Base

Dinero = Numeric(14, 2, asdecimal=True)
Porcentaje = Numeric(5, 2, asdecimal=True)


# --- Cuentas y movimientos -------------------------------------------------

class Cuenta(Base):
    __tablename__ = "cuentas"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    entidad: Mapped[str] = mapped_column(String(80), default="")
    # corriente | ahorro | tarjeta | inversion
    tipo: Mapped[str] = mapped_column(String(20), default="corriente")
    iban: Mapped[str] = mapped_column(String(34), default="")
    # manual | csv | enable_banking | indexa
    origen: Mapped[str] = mapped_column(String(20), default="manual")
    id_externo: Mapped[str] = mapped_column(String(80), default="")
    saldo: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    saldo_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    # Conexión bancaria de la que viene (Enable Banking) y su id de cuenta en esa sesión
    conexion_id: Mapped[int | None] = mapped_column(ForeignKey("conexiones_bancarias.id"), nullable=True)
    uid_externo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ultima_sincronizacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    movimientos: Mapped[list["Movimiento"]] = relationship(back_populates="cuenta")


class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    # gasto | ingreso | transferencia
    tipo: Mapped[str] = mapped_column(String(20), default="gasto")
    # personal | autonomo | piso | nomina
    ambito: Mapped[str] = mapped_column(String(20), default="personal")


class ReglaCategoria(Base):
    """Si el concepto del movimiento contiene `patron`, se asigna la categoría."""
    __tablename__ = "reglas_categoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    patron: Mapped[str] = mapped_column(String(120))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    categoria: Mapped[Categoria] = relationship()


class Movimiento(Base):
    __tablename__ = "movimientos"
    __table_args__ = (UniqueConstraint("cuenta_id", "huella"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuentas.id"))
    fecha: Mapped[date] = mapped_column(Date)
    fecha_valor: Mapped[date | None] = mapped_column(Date, nullable=True)
    concepto: Mapped[str] = mapped_column(Text, default="")
    importe: Mapped[Decimal] = mapped_column(Dinero)
    saldo: Mapped[Decimal | None] = mapped_column(Dinero, nullable=True)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    nota: Mapped[str] = mapped_column(Text, default="")
    # Huella para no duplicar al reimportar el mismo extracto
    huella: Mapped[str] = mapped_column(String(64))

    cuenta: Mapped[Cuenta] = relationship(back_populates="movimientos")
    categoria: Mapped[Categoria | None] = relationship()


# --- Activos y deudas ------------------------------------------------------

class Activo(Base):
    __tablename__ = "activos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    # inmueble | inmueble_en_construccion | vehiculo | otro
    tipo: Mapped[str] = mapped_column(String(30), default="inmueble")
    # vivienda_habitual | alquiler | otro
    uso: Mapped[str] = mapped_column(String(30), default="otro")
    fecha_compra: Mapped[date | None] = mapped_column(Date, nullable=True)
    precio_compra: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    gastos_compra: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    valor_catastral: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    valor_catastral_construccion: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    porcentaje_propiedad: Mapped[Decimal] = mapped_column(Porcentaje, default=Decimal("100"))
    notas: Mapped[str] = mapped_column(Text, default="")

    valoraciones: Mapped[list["Valoracion"]] = relationship(
        back_populates="activo", order_by="Valoracion.fecha"
    )


class Valoracion(Base):
    __tablename__ = "valoraciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    activo_id: Mapped[int] = mapped_column(ForeignKey("activos.id"))
    fecha: Mapped[date] = mapped_column(Date)
    valor: Mapped[Decimal] = mapped_column(Dinero)
    activo: Mapped[Activo] = relationship(back_populates="valoraciones")


class Deuda(Base):
    __tablename__ = "deudas"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    entidad: Mapped[str] = mapped_column(String(80), default="")
    # hipoteca | prestamo | otro
    tipo: Mapped[str] = mapped_column(String(20), default="hipoteca")
    activo_id: Mapped[int | None] = mapped_column(ForeignKey("activos.id"), nullable=True)
    capital_inicial: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    tipo_interes_anual: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("0"))
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    plazo_meses: Mapped[int] = mapped_column(default=0)
    # Si se rellena, manda sobre el cálculo teórico del cuadro de amortización
    saldo_pendiente_manual: Mapped[Decimal | None] = mapped_column(Dinero, nullable=True)
    saldo_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    activo: Mapped[Activo | None] = relationship()


# --- Piso alquilado ---------------------------------------------------------

class ContratoAlquiler(Base):
    __tablename__ = "contratos_alquiler"
    id: Mapped[int] = mapped_column(primary_key=True)
    activo_id: Mapped[int] = mapped_column(ForeignKey("activos.id"))
    inquilino: Mapped[str] = mapped_column(String(120), default="")
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    renta_mensual: Mapped[Decimal] = mapped_column(Dinero)
    # Reducción IRPF por alquiler de vivienda (60 % contratos anteriores al 26/05/2023)
    reduccion_pct: Mapped[Decimal] = mapped_column(Porcentaje, default=Decimal("60"))
    activo: Mapped[Activo] = relationship()
    cambios_renta: Mapped[list["CambioRenta"]] = relationship(
        back_populates="contrato", order_by="CambioRenta.desde"
    )

    def renta_en(self, d: date) -> Decimal:
        """Renta vigente en una fecha: la inicial o la última actualización (IPC, acuerdo...)."""
        renta = self.renta_mensual
        for cambio in self.cambios_renta:
            if cambio.desde <= d:
                renta = cambio.renta_mensual
        return renta


class CambioRenta(Base):
    """Actualización de la renta de un contrato que sigue vigente (no es un contrato nuevo)."""
    __tablename__ = "cambios_renta"
    id: Mapped[int] = mapped_column(primary_key=True)
    contrato_id: Mapped[int] = mapped_column(ForeignKey("contratos_alquiler.id"))
    desde: Mapped[date] = mapped_column(Date)
    renta_mensual: Mapped[Decimal] = mapped_column(Dinero)
    contrato: Mapped[ContratoAlquiler] = relationship(back_populates="cambios_renta")


class GastoInmueble(Base):
    __tablename__ = "gastos_inmueble"
    id: Mapped[int] = mapped_column(primary_key=True)
    activo_id: Mapped[int] = mapped_column(ForeignKey("activos.id"))
    fecha: Mapped[date] = mapped_column(Date)
    # intereses | ibi | comunidad | seguro | reparacion | suministros | gestion | otros
    tipo: Mapped[str] = mapped_column(String(30))
    importe: Mapped[Decimal] = mapped_column(Dinero)
    concepto: Mapped[str] = mapped_column(Text, default="")
    activo: Mapped[Activo] = relationship()


# --- Autónomo ---------------------------------------------------------------

class Cliente(Base):
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    nif: Mapped[str] = mapped_column(String(20), default="")


class Factura(Base):
    """Factura emitida como autónomo. Se registra aquí, no se emite desde la app."""
    __tablename__ = "facturas"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(40))
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    fecha: Mapped[date] = mapped_column(Date)
    concepto: Mapped[str] = mapped_column(Text, default="")
    base: Mapped[Decimal] = mapped_column(Dinero)
    tipo_iva: Mapped[Decimal] = mapped_column(Porcentaje, default=Decimal("21"))
    tipo_retencion: Mapped[Decimal] = mapped_column(Porcentaje, default=Decimal("15"))
    fecha_cobro: Mapped[date | None] = mapped_column(Date, nullable=True)
    cliente: Mapped[Cliente] = relationship()

    @property
    def cuota_iva(self) -> Decimal:
        return (self.base * self.tipo_iva / 100).quantize(Decimal("0.01"))

    @property
    def retencion(self) -> Decimal:
        return (self.base * self.tipo_retencion / 100).quantize(Decimal("0.01"))

    @property
    def total_a_cobrar(self) -> Decimal:
        return self.base + self.cuota_iva - self.retencion


class GastoAutonomo(Base):
    __tablename__ = "gastos_autonomo"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date)
    proveedor: Mapped[str] = mapped_column(String(120), default="")
    concepto: Mapped[str] = mapped_column(Text, default="")
    # cuota_reta | gestoria | software | equipos | formacion | suministros | otros
    categoria: Mapped[str] = mapped_column(String(30), default="otros")
    base: Mapped[Decimal] = mapped_column(Dinero)
    tipo_iva: Mapped[Decimal] = mapped_column(Porcentaje, default=Decimal("21"))
    # % de la base deducible en IRPF y % de la cuota de IVA deducible (p. ej. 30 % suministros)
    deducible_pct: Mapped[Decimal] = mapped_column(Porcentaje, default=Decimal("100"))

    @property
    def cuota_iva(self) -> Decimal:
        return (self.base * self.tipo_iva / 100).quantize(Decimal("0.01"))


# --- Trabajo por cuenta ajena ----------------------------------------------

class Nomina(Base):
    __tablename__ = "nominas"
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa: Mapped[str] = mapped_column(String(80))
    fecha: Mapped[date] = mapped_column(Date)
    bruto: Mapped[Decimal] = mapped_column(Dinero)
    retencion_irpf: Mapped[Decimal] = mapped_column(Dinero)
    seguridad_social: Mapped[Decimal] = mapped_column(Dinero)
    neto: Mapped[Decimal] = mapped_column(Dinero)


# --- Objetivos y pagos previstos -------------------------------------------

class Objetivo(Base):
    __tablename__ = "objetivos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    # boda | viaje | casa | colchon | otro
    tipo: Mapped[str] = mapped_column(String(20), default="otro")
    fecha_objetivo: Mapped[date | None] = mapped_column(Date, nullable=True)
    importe_objetivo: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    ahorrado: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    notas: Mapped[str] = mapped_column(Text, default="")


class PagoPrevisto(Base):
    """Pagos futuros conocidos: plazos de la obra nueva, señal de la boda, impuestos..."""
    __tablename__ = "pagos_previstos"
    id: Mapped[int] = mapped_column(primary_key=True)
    concepto: Mapped[str] = mapped_column(String(160))
    fecha: Mapped[date] = mapped_column(Date)
    importe: Mapped[Decimal] = mapped_column(Dinero)
    objetivo_id: Mapped[int | None] = mapped_column(ForeignKey("objetivos.id"), nullable=True)
    activo_id: Mapped[int | None] = mapped_column(ForeignKey("activos.id"), nullable=True)
    pagado: Mapped[bool] = mapped_column(Boolean, default=False)


# --- Sincronización ----------------------------------------------------------

class ConexionBancaria(Base):
    """Consentimiento PSD2 vía Enable Banking. Caduca (máximo 180 días) y hay que renovarlo."""
    __tablename__ = "conexiones_bancarias"
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor: Mapped[str] = mapped_column(String(30), default="enable_banking")
    banco: Mapped[str] = mapped_column(String(80))
    session_id: Mapped[str] = mapped_column(String(80))
    valida_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class RegistroSync(Base):
    __tablename__ = "registro_sync"
    id: Mapped[int] = mapped_column(primary_key=True)
    fuente: Mapped[str] = mapped_column(String(30))  # sabadell | indexa
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    mensaje: Mapped[str] = mapped_column(Text, default="")


class Instantanea(Base):
    """Foto diaria del patrimonio para dibujar su evolución."""
    __tablename__ = "instantaneas"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True)
    liquidez: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    inversiones: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    inmuebles: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    otros: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    deudas: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))

    @property
    def neto(self) -> Decimal:
        return self.liquidez + self.inversiones + self.inmuebles + self.otros - self.deudas


# --- Hacienda ---------------------------------------------------------------

class Declaracion(Base):
    """Modelo presentado a la Agencia Tributaria (303, 130, 100...), normalmente desde su justificante PDF."""
    __tablename__ = "declaraciones"
    __table_args__ = (UniqueConstraint("modelo", "ejercicio", "periodo", "justificante"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    modelo: Mapped[str] = mapped_column(String(5))
    ejercicio: Mapped[int] = mapped_column()
    # 1T..4T trimestral, 01..12 mensual, 0A anual
    periodo: Mapped[str] = mapped_column(String(3))
    # ingresar | devolver | compensar | negativa | cero | domiciliar | otro
    resultado: Mapped[str] = mapped_column(String(12), default="ingresar")
    # Importe con signo: positivo a pagar, negativo a devolver o compensar
    importe: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    fecha_presentacion: Mapped[date | None] = mapped_column(Date, nullable=True)
    justificante: Mapped[str] = mapped_column(String(20), default="")
    csv: Mapped[str] = mapped_column(String(20), default="")
    nombre_fichero: Mapped[str] = mapped_column(String(200), default="")
    pdf: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    notas: Mapped[str] = mapped_column(Text, default="")


class DocumentoDrive(Base):
    """Fichero de Google Drive ya revisado: así no se vuelve a leer y se sabe qué se creó con él."""
    __tablename__ = "documentos_drive"
    id: Mapped[int] = mapped_column(primary_key=True)
    drive_id: Mapped[str] = mapped_column(String(80), unique=True)
    nombre: Mapped[str] = mapped_column(String(250))
    modificado: Mapped[str] = mapped_column(String(40), default="")
    enlace: Mapped[str] = mapped_column(String(300), default="")
    # emitida | recibida | aeat | otro
    tipo: Mapped[str] = mapped_column(String(12), default="otro")
    # importado | pendiente | ignorado | error
    estado: Mapped[str] = mapped_column(String(12), default="pendiente")
    mensaje: Mapped[str] = mapped_column(Text, default="")
    datos: Mapped[str] = mapped_column(Text, default="{}")  # lo extraído, en JSON
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("facturas.id", ondelete="SET NULL"), nullable=True)
    gasto_id: Mapped[int | None] = mapped_column(ForeignKey("gastos_autonomo.id", ondelete="SET NULL"), nullable=True)
    declaracion_id: Mapped[int | None] = mapped_column(ForeignKey("declaraciones.id", ondelete="SET NULL"), nullable=True)
    revisado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
