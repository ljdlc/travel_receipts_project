# Azure Receipt OCR & Translation Pipeline (Japan Travel Receipts)

## Goal
Automatically process Japanese receipt images uploaded to Azure Blob Storage by:

1. Detecting uploads via Event Grid  
2. Extracting structured receipt data using Azure AI Document Intelligence  
3. Translating merchant names and line items from Japanese → English  
4. Renaming and moving processed files  
5. Persisting clean, queryable data for future analytics (SQL / Databricks)

---

## Final Architecture

Blob Storage (`raw`)
→ Event Grid (`BlobCreated`)
→ Azure Function (HTTP webhook, Python v2)
→ Azure AI Document Intelligence (`prebuilt-receipt`)
→ Azure Translator (JP → EN)
→ Blob Storage (`processed`, `datasets`)
→ SQL / Databricks / Lakehouse (future)

---

## Processing Flow (End-to-End)

1. Receipt image is uploaded to `raw/`
2. Event Grid fires `BlobCreated`
3. Azure Function executes:
   - Downloads image
   - Runs OCR (receipt model)
   - Translates text fields
   - Renames the file
   - Copies file to `processed/`
   - Writes structured JSON dataset to `datasets/`
4. (Optional) Raw file is deleted
5. Data is ready for SQL / Databricks ingestion

---

## Key Decisions (Frozen)

- **Python version:** 3.11  
- **Function trigger:** HTTP trigger (Webhook)  
- **Auth level:** `FUNCTION`  
- **Event Grid creation:** Azure CLI only  
- **OCR model:** `prebuilt-receipt`  
- **Translation:** Azure Translator (key + region)  
- **Storage auth:** Managed Identity  
- **Output format:** JSON (analytics-friendly)  

---

## Required Azure Resources

### 1. Storage Account
Containers (all private):

- `raw`  
  Original uploaded receipt images

- `processed`  
  Renamed, cleaned receipt images

- `datasets`  
  Structured JSON outputs for analytics

---

### 2. Azure AI Document Intelligence
- Model: `prebuilt-receipt`
- Used for:
  - Merchant name
  - Transaction date/time
  - Total amount
  - Line items

---

### 3. Azure Translator
- Used to translate:
  - Merchant name
  - Item descriptions
- Authentication via:
  - Subscription key
  - Region header
- Global REST endpoint

---

### 4. Azure Key Vault
Secrets:

| Secret Name | Purpose |
|-----------|--------|
| `docint-endpoint` | Document Intelligence endpoint |
| `docint-key` | Document Intelligence key |
| `translator-key` | Translator subscription key |
| `translator-region` | Translator resource region |

---

### 5. Azure Function App
- Runtime: Python 3.11
- Hosting: Consumption
- OS: Linux
- System Assigned Managed Identity: ENABLED

---

## Required RBAC Permissions

Assign to **Function App Managed Identity**:

| Resource | Role |
|-------|------|
| Storage Account | Storage Blob Data Contributor |
| Key Vault | Key Vault Secrets User |

---

## Blob Naming & Movement Strategy

### Original upload
raw/IMG_1234.jpg

### After processing
processed/2024-10-03_18-42_Lawson.jpg


Filename is derived from:
- Transaction datetime (OCR)
- Translated merchant name
- Original extension

---

## Dataset Output (Analytics-Ready)

Structured JSON is written to:
datasets/receipts-json/<receipt_id>.json

### Example schema
```json
{
  "receipt_id": "a1b2c3d4",
  "source_blob": "raw/IMG_1234.jpg",
  "processed_blob": "processed/2024-10-03_18-42_Lawson.jpg",
  "merchant_name_jp": "ローソン",
  "merchant_name_en": "Lawson",
  "transaction_datetime_utc": "2024-10-03T09:42:00Z",
  "total": 1280,
  "currency": "JPY",
  "items": [
    {
      "description_jp": "おにぎり",
      "description_en": "Rice ball",
      "price": 180
    }
  ]
}
