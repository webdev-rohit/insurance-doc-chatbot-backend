from io import BytesIO
from urllib.parse import urlparse

from google.cloud import storage

def download_file(gcs_url: str) -> BytesIO:
    """
    Downloads a file from GCS and returns it as a BytesIO object.
    Supports URLs of the form:
        gs://bucket/path/to/file
    """
    client = storage.Client()

    parsed = urlparse(gcs_url)

    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip("/")

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    file_obj = BytesIO()
    blob.download_to_file(file_obj)
    file_obj.seek(0)

    return file_obj