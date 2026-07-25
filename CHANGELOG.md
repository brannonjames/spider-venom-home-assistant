# Changelog

## v0.2.0 - 2026-07-25

### Added

- Add target temperature controls for Probe 1 and Probe 2.
- Add debug response-body logging for API discovery with token redaction.

### Notes

- Debug response logging is only emitted when `custom_components.spider_venom` is set to `debug`.
- Debug logs may include device and network metadata such as model, firmware version, Wi-Fi SSID, BSSID, and MAC address.
