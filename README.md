# Spider Grills Venom

Custom Home Assistant integration for Spider Grills Venom controllers.

This integration connects Home Assistant to a Spider Grills Venom through the cloud-backed AWS IoT Device Shadow used by the mobile app. It can discover devices from a Spider Grills email/password account, read grill state, expose temperature/status entities, and control target temperature plus selected Venom operating toggles.

The integration does not store your Spider Grills password or access token after setup. It stores the selected AWS IoT Thing Name and uses temporary Cognito credentials for ongoing shadow reads/writes.

## Features

- Account-based setup with device discovery.
- Temperature, probe, Wi-Fi, firmware, and status entities.
- Power, engaged, paused, and high-temperature mode controls.
- Target temperature number entity and service.

## Installation

### HACS

In HACS, add this repository as a custom repository with category `Integration`, then install it from HACS:

```text
https://github.com/brannonjames/spider-venom-home-assistant
```

Restart Home Assistant after installation, then add `Spider Grills Venom` from Settings -> Devices & services.

### Manual

Copy `custom_components/spider_venom` from this repository into your Home Assistant config directory:

```text
/config/custom_components/spider_venom
```

Restart Home Assistant, then add `Spider Grills Venom` from Settings -> Devices & services.

## Setup

Use the account setup flow with a Spider Grills email/password login. The integration uses it once to discover your devices.

Apple sign-in is not supported yet. Manual Thing Name setup was removed because there is no reliable, user-facing way to obtain the Thing Name and AWS IoT endpoint.

## Entities

Sensors include current temperature, target temperature, probe temperatures, heat intensity, firmware, Wi-Fi details, signal strength, limits, flags, and errors.

Binary sensors include power, engaged, paused, door, heating, Fahrenheit mode, high temperature mode, and temperature notifications.

Controls include target temperature, power, engaged, paused, and high temperature mode.

## Service

The integration also exposes:

```yaml
service: spider_venom.set_target_temperature
data:
  temperature: 300
```

If multiple Venoms are configured, include `thing_name`.

```yaml
service: spider_venom.set_target_temperature
data:
  thing_name: your_thing_name
  temperature: 300
```

## Notes

This version does not include timer controls. It also does not expose a vent-position entity because the observed shadow state does not include top or bottom vent opening fields.

This integration was developed with assistance from AI tools.
