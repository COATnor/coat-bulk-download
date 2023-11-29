from fastapi.templating import Jinja2Templates
import os


TEMPLATES = Jinja2Templates(directory="coat_bulk_download/templates")

COAT_URL = os.environ["COAT_URL"]
COAT_PUBLIC_URL = os.getenv("COAT_PUBLIC_URL", COAT_URL)

LOGGING = os.getenv("LOGGING", "INFO")
