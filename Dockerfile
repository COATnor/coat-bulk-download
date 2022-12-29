FROM python:3.8

ADD https://raw.githubusercontent.com/eficode/wait-for/v2.2.3/wait-for /wait-for
RUN chmod +x /wait-for

RUN python3 -m pip install pdm

WORKDIR /app
COPY pyproject.toml pdm.lock .

RUN pdm install --no-self

COPY app.py ./
ENV COAT_URL="https://data.coat.no/"

EXPOSE 8000/TCP
ENTRYPOINT ["/bin/bash", "-xeu", "-c", "exec /wait-for $COAT_URL -- $0 $@"]
CMD ["pdm", "run", "python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0"]
