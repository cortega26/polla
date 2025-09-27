"""Data models for normalized draw information."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable


@dataclass
class PrizeBreakdown:
    """Prize amount and winners for a specific category."""

    categoria: str
    premio_clp: int
    ganadores: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrizeBreakdown":
        return cls(
            categoria=data.get("categoria", "").strip(),
            premio_clp=int(data.get("premio_clp", 0) or 0),
            ganadores=int(data.get("ganadores", 0) or 0),
        )

    def to_row(self) -> list[Any]:
        return [self.categoria, self.premio_clp, self.ganadores]


@dataclass
class DrawSourceRecord:
    """Represents the parsed result from a single source."""

    sorteo: int | None
    fecha: str | None
    fuente: str
    premios: list[PrizeBreakdown] = field(default_factory=list)
    html_sha256: str | None = None
    titulo: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DrawSourceRecord":
        premios = [PrizeBreakdown.from_dict(p) for p in data.get("premios", [])]
        return cls(
            sorteo=data.get("sorteo"),
            fecha=data.get("fecha"),
            fuente=data.get("fuente", ""),
            premios=premios,
            html_sha256=data.get("sha256"),
            titulo=data.get("titulo"),
        )

    def to_summary_row(self) -> list[Any]:
        return [self.fuente, self.sorteo, self.fecha or "", self.titulo or "", self.html_sha256 or ""]


@dataclass
class JackpotRecord:
    """Stores next-draw jackpot information from an aggregator."""

    fuente: str
    pozos: dict[str, int]
    fetched_at: datetime

    def to_row(self) -> list[Any]:
        base = [self.fuente, self.fetched_at.isoformat()]
        for key, value in sorted(self.pozos.items()):
            base.append(f"{key}: {value}")
        return base


@dataclass
class ComparisonResult:
    """Outcome of comparing two prize tables."""

    fuente: str
    matches: bool
    differences: list[str] = field(default_factory=list)

    def to_rows(self) -> list[list[Any]]:
        if not self.differences:
            return [[self.fuente, "Coincide", ""]]
        rows: list[list[Any]] = []
        rows.append([self.fuente, "Diferencias", self.differences[0]])
        for diff in self.differences[1:]:
            rows.append(["", "", diff])
        return rows


@dataclass
class DrawReport:
    """Aggregated report combining primary and secondary sources."""

    primary: DrawSourceRecord
    secondary_sources: list[DrawSourceRecord] = field(default_factory=list)
    comparisons: list[ComparisonResult] = field(default_factory=list)
    jackpots: list[JackpotRecord] = field(default_factory=list)
    last_recorded_sorteo: int | None = None

    @property
    def sorteo(self) -> int | None:
        return self.primary.sorteo

    @property
    def fecha(self) -> str | None:
        return self.primary.fecha

    def iter_prize_rows(self) -> Iterable[list[Any]]:
        for prize in self.primary.premios:
            yield prize.to_row() + [self.primary.fuente]

    def to_sheet_values(self) -> list[list[Any]]:
        values: list[list[Any]] = []
        values.append([
            "Sorteo",
            self.sorteo or "",
            "Fecha",
            self.fecha or "",
            "Último registrado",
            self.last_recorded_sorteo or "",
        ])
        values.append(["Fuente principal", self.primary.fuente, "SHA-256", self.primary.html_sha256 or ""])
        values.append(["Categoría", "Premio CLP", "Ganadores", "Fuente"])
        values.extend(self.iter_prize_rows())
        if self.secondary_sources:
            values.append(["", "", "", ""])
            values.append(["Otras fuentes", "Sorteo", "Fecha", "Título", "SHA-256"])
            for secondary in self.secondary_sources:
                values.append(secondary.to_summary_row())
        if self.comparisons:
            values.append(["", "", ""])
            values.append(["Comparaciones", "Estado", "Detalle"])
            for comparison in self.comparisons:
                values.extend(comparison.to_rows())
        if self.jackpots:
            values.append(["", "", ""])
            values.append(["Próximos pozos", "Fuente", "Detalle"])
            for jackpot in self.jackpots:
                row = jackpot.to_row()
                values.append([row[0], row[1], " | ".join(row[2:])])
        return values

