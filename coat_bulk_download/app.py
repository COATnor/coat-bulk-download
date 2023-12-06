#!/usr/bin/env python3

import datetime
import logging
import urllib.parse

import fastapi
import httpx
import stream_zip

from .config import COAT_URL, COAT_PUBLIC_URL, LOGGING, GEOJSON_PATH


app = fastapi.FastAPI()

logging.basicConfig(level=LOGGING)


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


def read_geojson(dataset_id):
    with open(str(GEOJSON_PATH / dataset_id), mode="rb") as geojson:
        yield from geojson


@app.get("/dataset/{dataset_id}/geojson")
async def download_geojson(request: fastapi.Request, dataset_id):
    try:
        return fastapi.responses.StreamingResponse(
            read_geojson(dataset_id),
            media_type='application/json',
            headers={"Content-Disposition": f'attachment; filename="{dataset_id}.json"'},
        )
    except:
        return {
            "type": "FeatureCollection",
            "features": [],
            "name": dataset_id
        }
