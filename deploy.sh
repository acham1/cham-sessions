#!/bin/bash
set -euo pipefail

# Read config from config.yaml
PROJECT_ID=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['gcp_project'])")
REGION=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['gcp_region'])")
SECRET_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['secret_name'])")
TOPIC=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['topic'])")

echo "Deploying to project: $PROJECT_ID, region: $REGION"

# Copy config.yaml into each function's source directory
cp config.yaml functions/inbound/config.yaml
cp config.yaml functions/generate_episode/config.yaml
cp config.yaml functions/api/config.yaml

# Create Pub/Sub topic (idempotent)
gcloud pubsub topics create "$TOPIC" --project="$PROJECT_ID" 2>/dev/null || true

# Deploy generate_episode function (Pub/Sub triggered, long-running)
echo "Deploying generate-episode function..."
gcloud functions deploy generate-episode \
    --gen2 \
    --runtime=python312 \
    --region="$REGION" \
    --source=functions/generate_episode \
    --entry-point=generate_episode \
    --trigger-topic="$TOPIC" \
    --timeout=540s \
    --memory=1Gi \
    --set-secrets="/etc/secrets/.env=$SECRET_NAME:latest" \
    --project="$PROJECT_ID"

# Cloud Functions caps event-triggered timeout at 540s, but Cloud Run allows 3600s
echo "Extending Cloud Run timeout to 3600s..."
gcloud run services update generate-episode \
    --timeout=3600 \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --quiet

# Deploy inbound webhook (HTTP, called by Resend Inbound)
echo "Deploying inbound function..."
gcloud functions deploy inbound \
    --gen2 \
    --runtime=python312 \
    --region="$REGION" \
    --source=functions/inbound \
    --entry-point=inbound \
    --trigger-http \
    --allow-unauthenticated \
    --timeout=60s \
    --memory=512Mi \
    --set-secrets="/etc/secrets/.env=$SECRET_NAME:latest" \
    --project="$PROJECT_ID"

# Deploy API function (HTTP)
echo "Deploying api function..."
gcloud functions deploy api \
    --gen2 \
    --runtime=python312 \
    --region="$REGION" \
    --source=functions/api \
    --entry-point=api \
    --trigger-http \
    --allow-unauthenticated \
    --timeout=60s \
    --memory=256Mi \
    --set-secrets="/etc/secrets/.env=$SECRET_NAME:latest" \
    --project="$PROJECT_ID"

# Clean up copied config files
rm -f functions/inbound/config.yaml \
      functions/generate_episode/config.yaml \
      functions/api/config.yaml

INBOUND_URL="https://$REGION-$PROJECT_ID.cloudfunctions.net/inbound"
API_URL="https://$REGION-$PROJECT_ID.cloudfunctions.net/api"
echo ""
echo "Deployment complete!"
echo "Inbound webhook (point Resend Inbound here): $INBOUND_URL"
echo "API: $API_URL"
