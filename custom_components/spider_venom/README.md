# Spider Grills Venom Home Assistant Integration

Read-only Home Assistant custom integration for Spider Grills Venom using AWS IoT Device Shadow.

## Install

Copy this directory to:

```text
/config/custom_components/spider_venom
```

Restart Home Assistant, then add the integration from Settings -> Devices & services -> Add integration -> Spider Grills Venom.

## Configuration

Recommended setup uses a Spider Grills email/password account to discover devices. The integration does not store the password or access token after setup; it stores the selected Thing Name and uses the public Cognito/IoT path for ongoing control.

Manual setup is also available. Use the values discovered from the mobile app:

```text
Thing name: 641727b1f30c58f446121adc345b6b5b
AWS IoT endpoint: a1gzggdqzynf8-ats.iot.us-east-2.amazonaws.com
Cognito identity pool ID: us-east-2:900c6051-7296-4d27-9295-a11f72797d14
AWS region: us-east-2
```

No mobile app password, JWT, AWS key, or refresh token is stored. The integration asks Cognito for temporary unauthenticated credentials and uses those to read the IoT shadow.

## Exposed Entities

Sensors:

- Model
- Firmware version
- MAC address
- Current temperature
- Target temperature
- Minimum target temperature
- Maximum target temperature
- Heat intensity
- Heat start time
- High temperature notification limit
- Low temperature notification limit
- Signal strength
- Wi-Fi SSID
- Wi-Fi BSSID
- Update flag
- Trigger flag
- Errors
- Probe 1 temperature / target
- Probe 2 temperature / target

Binary sensors:

- Power
- Engaged
- Paused
- Door
- Heating
- Fahrenheit mode
- High temperature mode
- High temperature notification
- Low temperature notification

Controls:

- Target temperature control
- Power control
- Engaged control
- Paused control
- High temperature mode control

## Setting Target Temperature

The integration exposes a native number entity named `Target temperature control`.

It also exposes one write service:

```yaml
service: spider_venom.set_target_temperature
data:
  temperature: 300
```

If multiple Venoms are configured, include `thing_name`.

```yaml
service: spider_venom.set_target_temperature
data:
  thing_name: 641727b1f30c58f446121adc345b6b5b
  temperature: 300
```

The service only writes `state.desired.heat.t2.trgt` and only accepts integer Fahrenheit values from 150 to 550.

## Notes

This version does not include timer controls. It also does not expose a vent-position entity because the observed shadow state does not include top or bottom vent opening fields.
