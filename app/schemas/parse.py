from pydantic import BaseModel, Field
 
from app.models import Course
from app.schemas.workout import SetIn
 
 
class ParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    course: Course | None = None
 
 
class ParsedWorkout(BaseModel): 
    course: Course | None = None
    duration_min: int | None = Field(default=None, gt=0)
    total_distance: int | None = Field(default=None, gt=0)
    perceived_effort: int | None = Field(default=None, ge=1, le=10)
    sets: list[SetIn] = []
    symptoms: list[str] = []
    notes: str | None = None
 
 
class ParseResponse(ParsedWorkout): 
    missing: list[str] = []
 