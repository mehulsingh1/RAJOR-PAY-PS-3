# Revenue Recovery Ops Center — common tasks
.PHONY: demo test backend frontend dataset mcp

demo:            ## reproducible agent-vs-baseline numbers (no LLM, ~2s)
	AGENT_MODE=playbook python -m scripts.demo

test:            ## unit + API test suite
	python -m pytest -q

dataset:         ## regenerate data/transactions_v2.csv
	python data/generate_dataset.py

backend:         ## FastAPI backend (playbook mode = offline)
	AGENT_MODE=playbook uvicorn api.main:app --reload

backend-llm:     ## FastAPI backend using Groq
	uvicorn api.main:app --reload

frontend:        ## React dev server
	cd frontend && npm run dev

mcp:             ## MCP server demo
	python -m scripts.mcp_demo
