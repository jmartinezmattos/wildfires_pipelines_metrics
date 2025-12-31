## Build and push the Docker image to Artifact Registry

From the root folder of the repository (where the Dockerfile is located):

```bash
gcloud builds submit . --tag us-central1-docker.pkg.dev/wildfires-479718/wildfires/wildfires-pipeline-metrics:v1
```