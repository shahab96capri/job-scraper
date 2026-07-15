"""
Platform-standard enumerations.

These are the canonical, source-independent values that the Normalizer
layer (Commit 4) maps every website-specific string onto — e.g. Jobinja's
"دورکاری" and JobVision's "کار از راه دور" both normalize to
`WorkMode.REMOTE`. Storing enums (not free-text) on the `Job` model is what
makes cross-source querying and future AI classification possible without
re-cleaning text at query time.
"""

from __future__ import annotations

import enum


class WorkMode(str, enum.Enum):
    ON_SITE = "ON_SITE"
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


class ExperienceLevel(str, enum.Enum):
    INTERNSHIP = "INTERNSHIP"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    UNKNOWN = "UNKNOWN"


class EducationLevel(str, enum.Enum):
    DIPLOMA = "DIPLOMA"
    ASSOCIATE = "ASSOCIATE"
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    PHD = "PHD"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    ANY = "ANY"
    UNKNOWN = "UNKNOWN"


class MilitaryStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    EXEMPT = "EXEMPT"
    NOT_REQUIRED = "NOT_REQUIRED"  # e.g. not applicable (female candidates)
    UNKNOWN = "UNKNOWN"


class SalaryType(str, enum.Enum):
    FIXED = "FIXED"
    RANGE = "RANGE"
    NEGOTIABLE = "NEGOTIABLE"
    UNKNOWN = "UNKNOWN"


class Currency(str, enum.Enum):
    IRT = "IRT"  # Iranian Toman
    IRR = "IRR"  # Iranian Rial
    USD = "USD"
    EUR = "EUR"


class JobStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    FILLED = "FILLED"
    UNKNOWN = "UNKNOWN"


class CompanySize(str, enum.Enum):
    SIZE_1_10 = "SIZE_1_10"
    SIZE_11_50 = "SIZE_11_50"
    SIZE_51_200 = "SIZE_51_200"
    SIZE_201_500 = "SIZE_201_500"
    SIZE_500_PLUS = "SIZE_500_PLUS"
    UNKNOWN = "UNKNOWN"


class ScrapeStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class LogLevel(str, enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
