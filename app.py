#!/usr/bin/env python3

import datetime
import os
import urllib.parse

import fastapi
import httpx
import stream_zip

app = fastapi.FastAPI()
URL = os.environ["COAT_URL"]


def generate_archive(data, cookies):
    package_show = urllib.parse.urljoin(URL, "api/3/action/package_show")
    response = httpx.post(package_show, json=data, cookies=cookies).json()
    for resource in response["result"]["resources"]:
        modified_at = datetime.datetime.fromisoformat(resource["last_modified"])
        content = httpx.get(resource["url"], cookies=cookies).iter_bytes()
        yield resource["name"], modified_at, 0o600, stream_zip.ZIP_32, content


@app.get("/dataset/{dataset_id}/zip")
async def download_zip(dataset_id, ckan=fastapi.Cookie(), auth_tkt=fastapi.Cookie()):
    cookies = {"ckan": ckan, "auth_tkt": auth_tkt}
    data = {"id": dataset_id}
    return fastapi.responses.StreamingResponse(
        stream_zip.stream_zip(generate_archive(data, cookies)),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{dataset_id}.zip"'},
    )
