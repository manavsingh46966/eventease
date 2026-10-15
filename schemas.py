import re
from datetime import date as date_cls

from pydantic import BaseModel, Field, field_validator


class EventIn(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(default="", max_length=300)
    date: str
    venue: str = Field(min_length=2, max_length=100)
    total_seats: int = Field(ge=1, le=5000)

    @field_validator("date")
    @classmethod
    def valid_date(cls, v):
        try:
            date_cls.fromisoformat(v)
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @field_validator("title", "venue", "description")
    @classmethod
    def strip(cls, v):
        return v.strip()


class RegistrationIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    roll_no: str = Field(min_length=3, max_length=20)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        v = v.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,79}", v):
            raise ValueError("Name may contain letters, spaces, . ' - only")
        return v

    @field_validator("roll_no")
    @classmethod
    def clean_roll(cls, v):
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z0-9/_-]{3,20}", v):
            raise ValueError("Roll number may contain letters, digits, / _ - only")
        return v
