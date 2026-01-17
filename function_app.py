import json
import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.serialization import as_attribute_dict


app = func.FunctionApp()

# App settings (set locally in local.settings.json and in Azure Function App Configuration)
DOC_INTEL_ENDPOINT = os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"]
DOC_INTEL_KEY = os.environ["DOCUMENT_INTELLIGENCE_KEY"]
OUTPUT_CONTAINER = os.environ.get("OUTPUT_CONTAINER", "output")

# Clients are created once per worker for efficiency
doc_client = DocumentIntelligenceClient(
    endpoint=DOC_INTEL_ENDPOINT,
    credential=AzureKeyCredential(DOC_INTEL_KEY),
)

@app.blob_trigger(
    arg_name="inblob",
    path="raw/{name}",
    connection="AzureWebJobsStorage",
)
def receipt_extract_to_json(inblob: func.InputStream):
    """
    Trigger: fires when a blob is created/updated in raw/
    Action: sends bytes to Document Intelligence prebuilt-receipt
    Output: writes JSON result to output/{name}.receipt.json
    """
    blob_name = inblob.name  # includes container path like "raw/xyz.jpg" depending on runtime
    logging.info(f"Triggered by blob: {blob_name}, Size: {inblob.length} bytes")

    # Read the uploaded file bytes
    receipt_bytes = inblob.read()

    # Analyze with prebuilt receipt model (Document Intelligence)
    poller = doc_client.begin_analyze_document(
        model_id="prebuilt-receipt",
        body=receipt_bytes,
    )
    result = poller.result()

    # Convert result to a JSON-serializable dict
    # (Document Intelligence SDK objects expose to_dict() in current SDKs)
    result_dict = as_attribute_dict(result)

    # Decide output name
    # inblob.name may include "raw/". We'll normalize.
    base_name = blob_name.split("/")[-1]
    out_name = f"{base_name}.receipt.json"

    # Write to output container
    blob_service = BlobServiceClient.from_connection_string(
        os.environ["AZURITE_BLOB_CONNECTION_STRING"]
    )
    out_blob = blob_service.get_blob_client(container=OUTPUT_CONTAINER, blob=out_name)
    logging.info(f"Upload target URL: {out_blob.url}")

    out_blob.upload_blob(
        json.dumps(result_dict, ensure_ascii=False, indent=2).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )

    logging.info(f"Wrote receipt JSON to: {OUTPUT_CONTAINER}/{out_name}")