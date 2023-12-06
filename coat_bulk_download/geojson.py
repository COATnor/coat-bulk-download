import re
import httpx
from osgeo import gdal
import logging

from .config import TEMPLATES, GEOJSON_PATH


class MissingDataException(Exception):
    def __init__(self, msg="missing coordinates or year files", *args, **kwargs):
        super().__init__(msg, *args, **kwargs)
    

def vrt_to_geojson(context, dataset):
    # Create a virtual in-memory file for the VRT content
    vrt_mem_file = '/vsimem/input.vrt'
    template = TEMPLATES.get_template("definition.xml")

    text = template.render(context)
    gdal.FileFromMemBuffer(vrt_mem_file, bytes(text, 'utf-8'))

    # Convert VRT to GeoJSON
    options = gdal.VectorTranslateOptions(format='GeoJSON')
    gdal.VectorTranslate(str(GEOJSON_PATH / dataset), vrt_mem_file, options=options)



def handle_dataset(dataset):
    resources = dataset['resources']
    base_name_value = None

    for extra in dataset["extras"]:
        if extra["key"] == "base_name":
            base_name_value = extra["value"]
            break

    data = []
    regex = re.compile(f"{base_name_value}_(\d\d\d\d).txt", re.I)
    coords = None
    
    for resource in resources:
        if resource["format"] == "TXT" \
        and "embargo" not in resource["url"] \
        and regex.match(resource["name"]):
            try:
                response = httpx.head(resource["url"])
                response.raise_for_status()
                data.append({
                    "url": resource["url"],
                    "name": f"{base_name_value}_{regex.match(resource['name'])[1]}"
                })
            except httpx.RequestError as exc:
                logging.warning("%s, %s, %s, Error request", dataset['name'], resource['name'], resource['url'])
            except httpx.HTTPStatusError as exc:
                logging.warning("%s, %s, %s, %s, Error response", dataset['name'], resource['name'], resource['url'], exc.response.status_code)
        elif resource["name"].lower() == f"{base_name_value}_coordinates.txt":
            try:
                response = httpx.head(resource["url"])
                response.raise_for_status()
                coords = resource["url"]
            except httpx.RequestError as exc:
                logging.warning("%s, %s, %s, Error request", dataset['name'], resource['name'], resource['url'])
            except httpx.HTTPStatusError as exc:
                logging.warning("%s, %s, %s, %s, Error response", dataset['name'], resource['name'], resource['url'], exc.response.status_code)

    if not coords or not data:
        raise MissingDataException

    vrt_to_geojson({
        "layer_name": base_name_value,
        "coordinates": {
            "url": coords,
            "name": f"{base_name_value}_coordinates"
        },
        "data": data,
    }, dataset['name'])
