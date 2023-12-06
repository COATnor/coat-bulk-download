import urllib.parse
import httpx
import traceback
import logging

from .config import GEOJSON_PATH, COAT_URL
from .geojson import handle_dataset, MissingDataException


def get_datasets():
    package_search = urllib.parse.urljoin(COAT_URL, "api/3/action/package_search?q=type:dataset")
    response = httpx.get(package_search).json()
    datasets = response['result']['results']

    for dataset in datasets:
        logging.info(f'processing {dataset["title"]}')
        f = GEOJSON_PATH / dataset['name']
        try:
            if f.exists():
                f.unlink()
            handle_dataset(dataset)
        except MissingDataException as exc:
            logging.warn('%s, %s, %s', dataset['name'], MissingDataException, exc)
        except Exception:
            logging.error('%s, %s', dataset['name'], traceback.format_exc())


if __name__ == '__main__':
    get_datasets()
