FROM registry.opensuse.org/opensuse/bci/python:3.11 as base
RUN --mount=type=cache,target=/var/cache/zypper \
    zypper install --no-recommends -y gdal proj
WORKDIR /app
ENV PYTHONPATH=/app/.venv/lib
ENV PATH=$PATH:/app/.venv/bin

FROM base as pdm
RUN --mount=type=cache,target=/var/cache/zypper \
    zypper install --no-recommends -y python311-pdm wget
COPY ./pyproject.toml ./pdm.lock .

FROM pdm as production_deps
RUN --mount=type=cache,target=/var/cache/zypper \
    zypper install --no-recommends -y gdal-devel gcc gcc-c++
RUN pdm add gdal==$(rpm -q --queryformat='%{VERSION}' gdal)
RUN --mount=type=cache,target=/root/.cache/pdm \
    pdm install -G production

FROM pdm
COPY --from=production_deps /app .
ADD https://raw.githubusercontent.com/eficode/wait-for/v2.2.3/wait-for /wait-for
RUN chmod +x /wait-for

COPY coat_bulk_download coat_bulk_download
ENV COAT_URL="https://data.coat.no/"
ENV TIMEOUT=300

EXPOSE 8000/TCP
ENTRYPOINT ["/bin/bash", "-xeu", "-c", "exec /wait-for --timeout $TIMEOUT $COAT_URL -- $0 $@"]
CMD ["pdm", "run", "python3", "-m", "uvicorn", "coat_bulk_download.app:app", "--host", "0.0.0.0"]
