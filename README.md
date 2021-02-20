# Dataplicity integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![Donate](https://img.shields.io/badge/donate-Coffee-yellow.svg)](https://www.buymeacoffee.com/AlexxIT)
[![Donate](https://img.shields.io/badge/donate-Yandex-red.svg)](https://money.yandex.ru/to/41001428278477)

Custom component for public HTTPS access to [Home Assistant](https://www.home-assistant.io/) with [Dataplicity](https://www.dataplicity.com/) service.

Should work on any Linux PC or ARM, not only Raspberry as Dataplicity service said. Don't work on Windows.

With free Dataplicity subscription - limited to only one server.

But if you have an extra $5 per month - it's better to use [Nabu Casa](https://www.nabucasa.com/about/) service for public HTTPS access to Home Assistant. In this way you can support the core developers of Home Assistant.

<img src="screen.png" width="1280">

## Install

You can install component with HACS custom repo ([example](https://github.com/AlexxIT/SonoffLAN#install-with-hacs)): `AlexxIT/Dataplicity`.

Or manually copy `dataplicity` folder from [latest release](https://github.com/AlexxIT/Dataplicity/releases/latest) to `custom_components` folder in your config folder.

# Config

With GUI: Configuration > Integrations > Plus > Dataplicity > Follow instructions.

If the integration is not in the list, you need to clear the browser cache.
