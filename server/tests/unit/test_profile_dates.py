from src.schemas.profile import ProfileData


def test_current_experience_clears_end_date():
    profile = ProfileData.model_validate(
        {
            "experience": [
                {
                    "title": "Engineer",
                    "startDate": "2024-01",
                    "endDate": "Present",
                }
            ]
        }
    )

    experience = profile.experience[0]
    assert experience.startDate == "2024-01"
    assert experience.current is True
    assert experience.endDate == ""


def test_education_supports_month_range_and_current_state():
    profile = ProfileData.model_validate(
        {
            "education": [
                {
                    "school": "Example University",
                    "startDate": "2025-08",
                    "endDate": "2027-05",
                    "current": True,
                }
            ]
        }
    )

    education = profile.education[0]
    assert education.startDate == "2025-08"
    assert education.current is True
    assert education.endDate == ""
