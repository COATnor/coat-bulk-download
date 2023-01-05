#!/usr/bin/env python3

import csv
import datetime
import io
import itertools
import json
import logging
import os
import re
import urllib.parse

import fastapi
import httpx
import jinja2
import stream_zip

app = fastapi.FastAPI()
COAT_URL = os.environ["COAT_URL"]
COAT_PUBLIC_URL = os.getenv("COAT_PUBLIC_URL", COAT_URL)

logging.basicConfig(level=os.getenv("LOGGING", "INFO"))
csv.register_dialect("coat", quoting=csv.QUOTE_ALL, delimiter=";", quotechar='"')
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(searchpath="templates/"),
    autoescape=jinja2.select_autoescape(
        enabled_extensions=("xml"),
        default_for_string=True,
    ),
)


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


def get_extra(response, key):
    for extra in response["extras"]:
        if extra["key"] == key:
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


def merge_csv(resources, cookies):
    buffer = io.StringIO()
    writer = None
    for resource in resources:
        internal_url = external_to_internal(resource["url"])
        lines = httpx.get(internal_url, cookies=cookies).iter_lines()
        content = csv.DictReader(lines, dialect="coat")
        header = next(content)
        if not writer:
            writer = csv.DictWriter(buffer, header, dialect="coat")
            writer.writeheader()
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate()
        for row in content:
            writer.writerow(row)
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate()


def peek(iterable):
    first = next(iterable)
    return first, itertools.chain([first], iterable)


def get_bbox_from_points(points):
    return {
        "west": min(lon for lon, lat in points),
        "east": max(lon for lon, lat in points),
        "south": min(lat for lon, lat in points),
        "north": max(lat for lon, lat in points),
    }


def generate_dwca(data, cookies):
    package_show = urllib.parse.urljoin(COAT_URL, "api/3/action/package_show")
    response = httpx.post(package_show, json=data, cookies=cookies).json()
    result = response["result"]
    # Detect type
    name = result["name"]
    if "_metadata_" in name:
        return
    elif "_example_" in name:
        dwc_template_name = "example.xml"
    else:
        return
    # Data
    basename = get_extra(result, "base_name")
    csvs = list(filter_csvs(basename, result["resources"]))
    modified_at = get_latest_modified(csvs)
    header, csv = peek(merge_csv(csvs, cookies))
    csv_name = result["name"] + ".csv"
    yield csv_name, modified_at, 0o600, stream_zip.ZIP_32, csv
    # EML
    modified_metadata = datetime.datetime.fromisoformat(result["metadata_modified"])
    points = json.loads(get_extra(result, "spatial"))["coordinates"]
    bbox = get_bbox_from_points(*points)
    result["url"] = urllib.parse.urljoin(COAT_URL, "dataset/" + result["name"])
    eml_template = jinja_env.get_template("eml.xml")
    eml = (chunk.encode("utf-8") for chunk in eml_template.stream(**result, **bbox))
    yield "eml.xml", modified_metadata, 0o600, stream_zip.ZIP_32, eml
    # DarwinCore
    params = {
        "metadata": "eml.xml",
        "location": csv_name,
    }
    dwc_template = jinja_env.get_template(dwc_template_name)
    dwc = (chunk.encode("utf-8") for chunk in dwc_template.stream(**params))
    yield "meta.xml", modified_at, 0o600, stream_zip.ZIP_32, dwc


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
