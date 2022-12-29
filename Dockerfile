FROM python:3.8

RUN python3 -m pip install pdm

WORKDIR /app
COPY pyproject.toml pdm.lock .

RUN pdm install --no-self
COPY app.py ./

EXPOSE 8000/TCP
CMD ["pdm", "run", "python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0"]
