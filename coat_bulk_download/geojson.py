import urllib.parse
from fastapi.responses import Response
import httpx
import re
from osgeo import gdal

from .config import TEMPLATES, COAT_URL


def vrt_to_geojson_in_memory(context):
    # Create a virtual in-memory file for the VRT content
    vrt_mem_file = '/vsimem/input.vrt'
    template = TEMPLATES.get_template("definition.xml")

    text = template.render(context)
    gdal.FileFromMemBuffer(vrt_mem_file, bytes(text, 'utf-8'))

    # Create a virtual in-memory file for the GeoJSON output
    geojson_mem_file = '/vsimem/output.geojson'

    # Convert VRT to GeoJSON
    options = gdal.VectorTranslateOptions(format='GeoJSON')
    gdal.VectorTranslate(geojson_mem_file, vrt_mem_file, options=options)

    # Read the GeoJSON content from the in-memory file
    f = gdal.VSIFOpenL(geojson_mem_file, 'r')
    geojson_content = bytearray()
    chunk_size = 1024
    while True:
        chunk = gdal.VSIFReadL(1, chunk_size, f)
        if not chunk:
            break
        geojson_content.extend(chunk)

    # Clean up virtual files
    gdal.Unlink(vrt_mem_file)
    gdal.Unlink(geojson_mem_file)

    return geojson_content.decode('utf-8')

def handle_geojson(request, id: str):
    package_show = urllib.parse.urljoin(COAT_URL, "api/3/action/package_show")
    response = httpx.post(package_show, json={"id": id}).json()
    dataset = response['result']
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
            data.append({
                "url": resource["url"],
                "name": f"{base_name_value}_{regex.match(resource['name'])[1]}"
            })
        elif resource["name"].lower() == f"{base_name_value}_coordinates.txt":
            coords = resource["url"]

    geojson = vrt_to_geojson_in_memory({
        "layer_name": base_name_value,
        "coordinates": {
            "url": coords,
            "name": f"{base_name_value}_coordinates"
        },
        "data": data,
    })

    return Response(geojson, headers={'Content-Type': 'application/json'})
