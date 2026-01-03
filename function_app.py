import json
import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential


app = func.FunctionApp()


def _env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise ValueError(f"Missing env var: {name}")
    return v


def _parse_subject(subject: str) -> tuple[str, str]:
    # subject: /blobServices/default/containers/raw/blobs/file.jpg
    parts = subject.split("/")
    container = parts[parts.index("containers") + 1]
    blob_name = "/".join(parts[parts.index("blobs") + 1:])
    return container, blob_name


@app.function_name(name="lem-travel-receipts")
@app.route(route="receipt-ocr", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def receipt_ocr(req: func.HttpRequest) -> func.HttpResponse:
    # Event Grid sends an array of events
    try:
        events = req.get_json()
        if isinstance(events, dict):
            events = [events]
    except Exception:
        return func.HttpResponse("Invalid JSON", status_code=400)

    # 1) Handle Event Grid subscription validation handshake
    for e in events:
        if e.get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
            code = e["data"]["validationCode"]
            return func.HttpResponse(
                json.dumps({"validationResponse": code}),
                mimetype="application/json",
                status_code=200,
            )

    credential = DefaultAzureCredential()

    # 2) Read Doc Intelligence secrets from Key Vault
    kv = SecretClient(vault_url=_env("KEYVAULT_URL"), credential=credential)
    docint_endpoint = kv.get_secret("docint-endpoint").value
    docint_key = kv.get_secret("docint-key").value

    # 3) Connect to Blob using Managed Identity
    blob_service = BlobServiceClient(account_url=_env("STORAGE_ACCOUNT_URL"), credential=credential)
    raw_container_expected = _env("RAW_CONTAINER")

    processed = 0

    for e in events:
        if e.get("eventType") not in ("Microsoft.Storage.BlobCreated", "BlobCreated"):
            continue

        container, blob_name = _parse_subject(e.get("subject", ""))

        if container != raw_container_expected:
            logging.info(f"Skipping container={container} blob={blob_name}")
            continue

        logging.info(f"OCR receipt: {container}/{blob_name}")

        # Download the image bytes
        blob = blob_service.get_container_client(container).get_blob_client(blob_name)
        image_bytes = blob.download_blob().readall()

        # Analyze with prebuilt receipt model
        di = DocumentIntelligenceClient(docint_endpoint, AzureKeyCredential(docint_key))
        poller = di.begin_analyze_document(model_id="prebuilt-receipt", body=image_bytes)
        result = poller.result().as_dict()

        # For now, just log the result (you can store it later)
        logging.info(json.dumps(result, ensure_ascii=False)[:3000])

        processed += 1

    return func.HttpResponse(f"OK. OCR processed {processed} receipt(s).", status_code=200)
