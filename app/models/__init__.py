"""
Aggregates every ORM model so that:
1. Alembic's `env.py` can do `from app.models import Base` and see the
   full `Base.metadata` (every model must be imported somewhere for
   SQLAlchemy to register it on the shared metadata).
2. Application code can `from app.models import Job, Company, ...` instead
   of reaching into individual submodules.
"""

from app.database.base import Base
from app.models.category import Category
from app.models.company import Company
from app.models.employment_type import EmploymentType
from app.models.error import Error, ErrorStageEnum
from app.models.job import Job
from app.models.location import Location
from app.models.log import Log
from app.models.scrape_history import ScrapeHistory
from app.models.skill import JobSkill, Skill
from app.models.source import Source

__all__ = [
    "Base",
    "Category",
    "Company",
    "EmploymentType",
    "Error",
    "ErrorStageEnum",
    "Job",
    "Location",
    "Log",
    "ScrapeHistory",
    "JobSkill",
    "Skill",
    "Source",
]
