# Spider Grills Venom Home Assistant Integration

Custom Home Assistant integration for Spider Grills Venom controllers.

This integration connects Home Assistant to a Spider Grills Venom through the same cloud-backed AWS IoT Device Shadow used by the mobile app. It can discover devices from a Spider Grills email/password account, read grill state, expose temperature/status entities, and control the target temperature plus a small set of Venom operating toggles.

The integration does not store your Spider Grills password or access token after setup. It stores the selected AWS IoT Thing Name and uses temporary Cognito credentials for ongoing shadow reads/writes.

## Features

- Account-based setup with device discovery.
- Manual setup by AWS IoT Thing Name.
- Temperature, probe, Wi-Fi, firmware, and status sensors.
- Power, engaged, paused, and high-temperature-mode controls.
- Target temperature number entity and service.
- HACS-compatible repository layout.

## Installation

Both HACS and manual installation are valid. HACS is recommended because it can track updates.

## HACS

In HACS, add this repository as a custom repository with category `Integration`, then install it from HACS:

```text
https://github.com/brannonjames/spider-venom-home-assistant
```

Restart Home Assistant after installation, then add `Spider Grills Venom` from Settings -> Devices & services.

## Manual Install

Copy `custom_components/spider_venom` from this repository into your Home Assistant config directory:

```text
/config/custom_components/spider_venom
```

Restart Home Assistant, then add `Spider Grills Venom` from Settings -> Devices & services.

See [custom_components/spider_venom/README.md](custom_components/spider_venom/README.md) for setup and entity details.
