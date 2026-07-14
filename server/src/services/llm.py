from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.schemas.profile import ProfileData
from src.config.settings import settings

_PARSE_SYSTEM_PROMPT = (
    "You are a precise resume parser. Extract the candidate's resume into the given "
    "structure. Use empty strings or empty arrays for anything not present. Do not "
    "invent, infer, or embellish any information."
)


def extract_resume(text: str) -> dict[str, Any]:
    model = ChatOpenAI(model="gpt-5.5", api_key=SecretStr(settings.openai_api_key))
    agent = create_agent(
        model=model,
        system_prompt=_PARSE_SYSTEM_PROMPT,
        response_format=ProfileData,
    )
    response = agent.invoke({"messages": [{"role": "user", "content": f"Resume text:\n\n{text}"}]})
    return response["structured_response"]
