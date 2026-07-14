from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.schemas.profile import ProfileData
from src.config.settings import settings

_PARSE_SYSTEM = (
    "You are a precise resume parser. Extract the candidate's resume into the given "
    "structure. Use empty strings or empty arrays for anything not present. Do not "
    "invent, infer, or embellish any information."
)


def _str() -> dict[str, Any]:
    return {"type": "string"}


def _str_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _object_array(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "object", "properties": properties}}


# RESUME_SCHEMA: dict[str, Any] = {
#     "type": "object",
#     "properties": {
#         "name": _str(),
#         "email": _str(),
#         "phone": _str(),
#         "location": _str(),
#         "linkedin": _str(),
#         "github": _str(),
#         "links": _str_array(),
#         "summary": _str(),
#         "experience": _object_array(
#             {
#                 "title": _str(),
#                 "company": _str(),
#                 "startDate": _str(),
#                 "endDate": _str(),
#                 "bullets": _str_array(),
#             }
#         ),
#         "education": _object_array(
#             {"degree": _str(), "school": _str(), "year": _str(), "gpa": _str()}
#         ),
#         "skills": _str_array(),
#         "certifications": _str_array(),
#         "projects": _object_array({"name": _str(), "description": _str(), "bullets": _str_array()}),
#     },
# }


def extract_resume(text: str) -> dict[str, Any]:
    model = ChatOpenAI(model="gpt-5.5", api_key=SecretStr(settings.openai_api_key))
    agent = create_agent(
        model=model,
        system_prompt=_PARSE_SYSTEM,
        response_format=ProfileData,
    )
    response = agent.invoke(
        {"messages": [{"role": "user", "content": f"Resume text:\n\n{text}"}]}
    )
    return response["structured_response"].model_dump()
