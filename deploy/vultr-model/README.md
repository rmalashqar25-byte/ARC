# Separate ARC model server

Proposed hardware: Vultr Cloud Compute `vc2-6c-16gb`, Ubuntu 24.04 x86_64, Atlanta if available. Vultr's public plan API returned 6 vCPUs, 16 GB RAM, $80/month and $0.11/hour on 6 November 2026. This is an additional server, not a replacement for the running ARC VM. Region availability, credit balance and final checkout price must be confirmed in the account before purchase.

Proposed model: `qwen3.5:9b`, served by Ollama. The official model listing includes tools and an Apache-2.0 license. The quantized download is around 6.6–7.6 GB; a 16 GB host is a starting configuration, not a measured performance guarantee. CPU inference can be slower than hosted APIs and a small model is not guaranteed to improve agent quality.

The cloud-init template creates key-only administration, installs the official Ollama image pinned to its downloaded digest, limits resources and downloads the model. It performs no inference or benchmark. Replace the SSH public-key placeholder before provisioning. Do not put private SSH keys or API credentials in cloud-init.

The model endpoint binds only to loopback. Do not expose port 11434 to the internet. After the server exists, connect ARC through a dedicated, restricted SSH tunnel between the two servers, pin the new host key and use a server-managed default connection. Keep browser-provided endpoint validation and personal API overrides separate; do not disable production SSRF checks to enable a local URL. ARC supports a keyless `Vultr Cloud Model` connection. Administrators enable `ARC_VULTR_MODEL_ENABLED=1`, `ARC_VULTR_MODEL=qwen3.5:9b`, and `ARC_DEFAULT_MODEL_PROVIDER=vultr_model` after creating the restricted tunnel on 127.0.0.1:11435. The endpoint cannot be changed by browser input. Personal provider connections take precedence. Hosted requests disable thinking and cap output at 2,048 tokens; CPU requests have longer bounded deadlines and queue leases. Installation and model discovery do not establish agent execution quality.

The 8 GB/$40 alternative would use a smaller 4B model and a separately adjusted memory limit; do not deploy this 13 GB compose profile on an 8 GB machine. Charges continue while the instance exists. Credits can apply only if eligible and available.

Sources: [Vultr public plans](https://api.vultr.com/v2/plans?type=vc2), [Qwen3.5 9B](https://ollama.com/library/qwen3.5:9b), [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility).
