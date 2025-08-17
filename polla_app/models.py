"""Data models for the Polla scraper."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class PrizeData:
    """Prize data model matching the original structure."""
    
    loto: int
    recargado: int
    revancha: int
    desquite: int
    jubilazo: int
    multiplicar: int
    jubilazo_50: int
    
    def __post_init__(self) -> None:
        """Validate prize amounts are non-negative."""
        for field_name, value in self.__dict__.items():
            if value < 0:
                raise ValueError(f"Prize amount cannot be negative: {field_name}={value}")
    
    def to_sheet_values(self) -> List[List[int]]:
        """Convert to Google Sheets format (7 rows, 1 column each)."""
        return [
            [self.loto],
            [self.recargado],
            [self.revancha],
            [self.desquite],
            [self.jubilazo],
            [self.multiplicar],
            [self.jubilazo_50]
        ]
    
    @property
    def total_prize_money(self) -> int:
        """Calculate total prize money."""
        return sum([
            self.loto, self.recargado, self.revancha,
            self.desquite, self.jubilazo, self.multiplicar,
            self.jubilazo_50
        ])
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"PrizeData(loto={self.loto:,}, recargado={self.recargado:,}, "
            f"revancha={self.revancha:,}, desquite={self.desquite:,}, "
            f"jubilazo={self.jubilazo:,}, multiplicar={self.multiplicar:,}, "
            f"jubilazo_50={self.jubilazo_50:,}, total={self.total_prize_money:,})"
        )
