# models/

Trained model artifacts land in `models/artifacts/` (gitignored — regenerate with
`make train`). Metadata for every version — algorithm, features, target, training
window, validation metrics, artifact path, code commit — is stored in the
`model_versions` table and displayed at `/data-health`.
