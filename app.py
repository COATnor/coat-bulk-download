#!/usr/bin/env python3

import datetime
import logging
import os
import re
import urllib.parse

import fastapi
import httpx
import stream_zip

app = fastapi.FastAPI()
COAT_URL = os.environ["COAT_URL"]
COAT_PUBLIC_URL = os.getenv("COAT_PUBLIC_URL", COAT_URL)

logging.basicConfig(level=os.getenv("LOGGING", "INFO"))


def external_to_internal(external_url):
    if not external_url.startswith(COAT_PUBLIC_URL):
        logging.error(
            f"{external_url} does not start with the URL of the project {COAT_PUBLIC_URL}"
        )
        return external_url
    elif COAT_URL == COAT_PUBLIC_URL:
        return external_url
    else:
        external_splitted = list(urllib.parse.urlsplit(external_url))
        # replace scheme and netloc
        external_splitted[0:2] = list(urllib.parse.urlsplit(COAT_URL))[0:2]
        # rewrite path
        external_splitted[2] = external_splitted[2].replace(
            COAT_PUBLIC_URL, COAT_URL, 1
        )
        return urllib.parse.urlunsplit(external_splitted)


def generate_archive(data, cookies):
    package_show = urllib.parse.urljoin(COAT_URL, "api/3/action/package_show")
    response = httpx.post(package_show, json=data, cookies=cookies).json()
    for resource in response["result"]["resources"]:
        modified_at = datetime.datetime.fromisoformat(resource["last_modified"])
        internal_url = external_to_internal(resource["url"])
        content = httpx.get(internal_url, cookies=cookies).iter_bytes()
        yield resource["name"], modified_at, 0o600, stream_zip.ZIP_32, content


@app.get("/dataset/{dataset_id}/zip")
async def download_zip(request: fastapi.Request, dataset_id):
    data = {"id": dataset_id}
    return fastapi.responses.StreamingResponse(
        stream_zip.stream_zip(generate_archive(data, request.cookies)),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{dataset_id}.zip"'},
    )


def get_basename(response):
    for extra in response["extras"]:
        if extra["key"] == "base_name":
            return extra["value"]


def filter_csvs(basename, resources):
    filename_filter = re.compile("^%s_\d{4}.txt$" % basename, re.I)
    for resource in resources:
        if filename_filter.match(resource["name"]):
            yield resource


def get_latest_modified(resources):
    latest_modified = None
    for resource in resources:
        modified_at = datetime.datetime.fromisoformat(resource["last_modified"])
        if not latest_modified or latest_modified < modified_at:
            latest_modified = modified_at
    return latest_modified


def merge_csv(csvs, cookies):
    for index, csv in enumerate(csvs):
        internal_url = external_to_internal(csv["url"])
        content = httpx.get(internal_url, cookies=cookies).iter_lines()
        if index > 0:
            next(content)  # skip header
        for line in content:
            yield line.encode("utf-8")


def generate_dwca(data, cookies):
    package_show = urllib.parse.urljoin(COAT_URL, "api/3/action/package_show")
    response = httpx.post(package_show, json=data, cookies=cookies).json()
    result = response["result"]
    basename = get_basename(result)
    csvs = list(filter_csvs(basename, result["resources"]))
    modified_at = get_latest_modified(csvs)
    csv = merge_csv(csvs, cookies)
    yield result["name"] + ".csv", modified_at, 0o600, stream_zip.ZIP_32, csv


@app.get("/dataset/{dataset_id}/dwca")
async def download_dwca(request: fastapi.Request, dataset_id):
    data = {"id": dataset_id}
    return fastapi.responses.StreamingResponse(
        stream_zip.stream_zip(generate_dwca(data, request.cookies)),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{dataset_id}_dwca.zip"'
        },
    )
