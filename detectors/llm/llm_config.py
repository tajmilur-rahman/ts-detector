OLLAMA_MODEL = "qwen2.5-coder:7b"
OLLAMA_BASE_URL = "http://localhost:11434"
MAX_FILE_CHARS = 16000  # characters sent to LLM per file; qwen2.5-coder:7b has 32K token ctx
MAX_TOGGLES_PER_PROMPT = 40  # cap toggle list length in a single prompt
