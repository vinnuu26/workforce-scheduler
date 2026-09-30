from .. import models,schemas
from .factory import crud_router
router=crud_router(models.ShiftTemplate,schemas.ShiftTemplateCreate,"/shift-templates")
