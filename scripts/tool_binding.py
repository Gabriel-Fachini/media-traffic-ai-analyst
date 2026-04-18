from langchain_core.messages import HumanMessage
from app.graph import build_tool_enabled_llm

question = "Qual foi o volume de usuarios de Search entre 2024-01-01 e 2024-01-31?"
llm = build_tool_enabled_llm()
response = llm.invoke([HumanMessage(content=question)])
print(response.tool_calls)
