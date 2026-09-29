# Mage for ComfyUI

Generate images, video, and audio in ComfyUI with [Mage](https://www.mage.space) models, including Mango, Cherry, and Seed Audio, through the [Mage API](https://docs.mage.space/api/overview).

> **Beta.** These nodes are at `0.x`, so their inputs may still change.

Every run spends Gems from the Mage account whose API key you configure. The nodes run on Mage's servers, so they need no GPU and no model downloads.

## Install

- **ComfyUI-Manager:** search for **Mage** and install it.
- **Comfy CLI:** `comfy node install comfyui-mage`
- **By hand:** clone this repository into `ComfyUI/custom_nodes`, then run `pip install -r requirements.txt` with ComfyUI's Python.

The nodes depend on the [Mage Python SDK](https://github.com/mage-space/mage-python) (`mage-space` on PyPI) and on packages ComfyUI already ships.

## Set your API key

Create a key under [API → API Keys](https://www.mage.space/api?tab=api-keys) on mage.space. Then do one of the following:

- Set the `MAGE_API_KEY` environment variable before starting ComfyUI.
- Copy `config.ini.example` to `config.ini` in this folder and paste the key after `api_key =`. Git ignores `config.ini`.

The environment variable wins when both are set. The key is never stored in your workflows, so you can share them safely.

## Nodes

All the nodes are in the **Mage** category.

| Node                          | Makes | Inputs                                                                                                                            |
| ----------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Mage Mango Image**          | IMAGE | Prompt, model, aspect ratio, resolution, seed; optional reference images, or an image to edit                                     |
| **Mage Cherry Video**         | VIDEO | Prompt, model, aspect ratio, resolution, duration, seed; optional reference images and a source video. The video includes sound. |
| **Mage Seed Audio**           | AUDIO | Prompt, duration, seed; optional image for the audio to match                                                                     |
| **Mage Generate (any model)** | any   | Model family, variant, prompt, seed, and any other fields as JSON; optional reference images, first and last frames, and video   |

Each node also outputs the result's `url`. Mage keeps outputs for 30 days, so save anything you want to keep with ComfyUI's save nodes.

**Mage Generate** runs any model the API offers. Put the model's fields in `extra_config` as a JSON object, for example `{"aspect_ratio": "16:9", "duration": "5"}`. The [model reference](https://docs.mage.space/api/models/overview) lists every model's fields and options.

Saved characters and references work as they do on mage.space: mention them by `@handle` in the prompt.

## Costs and caching

- The seed is **fixed** by default. Queueing the same inputs again reuses ComfyUI's cached output instead of paying for a new run. Change the seed, or set it to randomize, when you want a new variation.
- The node shows the request's status and the Gems it cost.
- Interrupting the queue cancels the Mage request. Cancelled runs are not refunded.
- A model that refuses a combination of options, or an account without enough Gems, fails the node with the API's message before any Gems are spent.

## Privacy

Images and videos you connect to a node are uploaded to Mage's storage and deleted after 30 days, like the outputs. The nodes send nothing else: there is no telemetry.

## Development

```bash
pip install -r requirements.txt pytest ruff
ruff check . && ruff format --check . && pytest tests
```

The tests cover the configuration logic. To try the nodes, install this folder into a ComfyUI checkout and run them with a real key.

Pull requests are squash-merged, and their titles become [Conventional Commit](https://www.conventionalcommits.org/) messages (`fix: …`, `feat: …`). release-please turns these into releases, which are published to the Comfy Registry.

**Maintainer setup**, once:

1. A GitHub App for the release bot, installed on this repository. Store its ID in the `MAGE_BOT_APP_ID` Actions variable and its private key in the `MAGE_BOT_PRIVATE_KEY` Actions secret.
2. A Comfy Registry publisher with the ID `mage-space`. Store its API key in the `REGISTRY_ACCESS_TOKEN` secret of the `comfy-registry` environment.
3. Submit the repository to the [ComfyUI-Manager node list](https://github.com/Comfy-Org/ComfyUI-Manager#how-to-register-your-custom-node-into-comfyui-manager).

## License

[MIT](LICENSE)
