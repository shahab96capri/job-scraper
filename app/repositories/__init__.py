"""Repository layer: the ONLY layer in the codebase allowed to import
`sqlalchemy` query constructs directly. Every repository receives an
`AsyncSession` via constructor injection.
"""

from app.repositories.base_repository import BaseRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.employment_type_repository import EmploymentTypeRepository
from app.repositories.error_repository import ErrorRepository
from app.repositories.job_repository import JobRepository
from app.repositories.location_repository import LocationRepository
from app.repositories.log_repository import LogRepository
from app.repositories.scrape_history_repository import ScrapeHistoryRepository
from app.repositories.skill_repository import SkillRepository
from app.repositories.source_repository import SourceRepository

__all__ = [
    "BaseRepository",
    "CategoryRepository",
    "CompanyRepository",
    "EmploymentTypeRepository",
    "ErrorRepository",
    "JobRepository",
    "LocationRepository",
    "LogRepository",
    "ScrapeHistoryRepository",
    "SkillRepository",
    "SourceRepository",
]
