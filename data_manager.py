"""Backwards compatibility shim for DataManager."""
from src.infrastructure.fpl.repository import FPLDataRepository as DataManager

__all__ = ["DataManager"]
