"""Backwards compatibility shim for XPEngine."""
from src.infrastructure.xp.rule_engine import RuleBasedXPEngine as XPEngine

__all__ = ["XPEngine"]
