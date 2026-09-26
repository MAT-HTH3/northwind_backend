"""The four Legacy Systems a Human Agent used to check one screen at a time.

Each is a Protocol with a mock backed by fixture JSON, so a real integration can replace a
mock without touching the Analyzer or the routes.
"""

from dataclasses import dataclass
from functools import lru_cache

from src.legacy.billing import LegacyBilling, MockLegacyBilling
from src.legacy.casetrack import CaseTrack, MockCaseTrack
from src.legacy.crm import Crm, MockCrm
from src.legacy.metering import Metering, MockMetering


@dataclass(frozen=True)
class LegacySystems:
    billing: LegacyBilling
    metering: Metering
    crm: Crm
    casetrack: CaseTrack


@lru_cache
def get_legacy_systems() -> LegacySystems:
    return LegacySystems(
        billing=MockLegacyBilling(),
        metering=MockMetering(),
        crm=MockCrm(),
        casetrack=MockCaseTrack(),
    )
