# Third-party notices

ARC's original code and documentation are licensed under [MIT](LICENSE). Dependencies retain their own copyrights and licenses; ARC does not relicense them. Dependencies use their declared licenses, not ARC's MIT license. This includes MPL-2.0 for the unmodified certifi certificate bundle and PSF-2.0 for typing_extensions.

## Python runtime

Inventory collected from the deployed Linux backend on 5 November 2026. Full upstream copyright and license notices are preserved in [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt). Regenerate in the isolated runtime with `python tools/generate_license_notices.py`; review changes when updating the lockfile.

| Package | Installed version | Declared license |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| certifi | 2026.10.23 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.141.1 | MIT |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.16.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| httpx2 | 2.16.0 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| jiter | 0.17.0 | MIT |
| openai | 3.8.0 | Apache-2.0 |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pydantic_core | 2.50.1 | MIT |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| sniffio | 1.3.1 | MIT OR Apache-2.0 |
| starlette | 1.9.0 | BSD-3-Clause |
| truststore | 0.10.5 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uvicorn | 0.52.4 | BSD-3-Clause |

## Flutter and browser assets

Flutter generates its dependency notice bundle as part of every build, including Flutter/Dart, Material Icons and the packages in `pubspec.lock`. Open **Workspace settings -> Open-source licenses** in ARC to view those texts and ARC's own MIT license. Preserve the generated `NOTICES` asset when distributing web or platform builds.

Unused legacy bitmap images and Lottie animations were removed because their attribution was not established. The remaining ARC interface/intro uses project code and Flutter icons. The ARC cover artwork is project-created. Service names and model names identify their respective providers; those marks are not relicensed by ARC.

## Deployment and external services

Caddy, Docker/Moby, the Python image, Linux packages and Flutter rendering binaries remain separately licensed upstream components. Their supplied notices must accompany redistributed images/binaries. ARC's source license does not change their terms. Provider APIs and hosted model weights are not distributed in this repository and remain governed by their providers' terms. No third-party model weights are bundled.

The promo video is maintained separately in ARC-media and is not redistributed in this source repository. Submission media must have the necessary rights independently of this source-code license.

## certifi source availability

The unmodified certifi 2026.10.23 bundle is MPL-2.0 licensed. Its corresponding source is available from [the exact PyPI release](https://pypi.org/project/certifi/2026.10.23/#files) and [upstream certifi](https://github.com/certifi/python-certifi). Keep its MPL notice and source availability information with redistributed copies. ARC does not modify certifi files. File-level MPL obligations do not relicense ARC's separate original source; see the [Mozilla FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).
