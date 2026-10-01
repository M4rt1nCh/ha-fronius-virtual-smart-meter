# Home Assistant App: Fronius Virtual Smart Meter

A Home Assistant **app repository** containing the **Fronius Virtual Meter
Bridge** — it aggregates inverter data (from Home Assistant entities) into a
single **virtual Fronius SunSpec smart meter**,
so a Fronius GEN24 / Symo GEN24 Plus can discover it over Modbus TCP and count
generation from extra inverters (e.g. Growatt) as production.

## Installation

This is a Home Assistant **app** (formerly add-on), so it installs via the App Store,
**not HACS** (HACS does not manage apps).

### Option A: Automatic Installation
[![Open your Home Assistant instance and show the add app repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FM4rt1nCh%2Fha-fronius-virtual-smart-meter)

### Option B: Manual Installation

1. In Home Assistant go to **Settings → Apps → Install App**.
2. Click the **⋮** menu (top right) → **Repositories**.
3. Add this repository URL:
   ```
   https://github.com/M4rt1nCh/ha-fronius-virtual-smart-meter
   ```
4. Close the dialog; **Fronius Virtual Smart Meter** now appears in the store.
5. Click it → **Install**, then configure it (see the apps's **Documentation**
   tab) and **Start**.

> Requires a Home Assistant OS / Supervised install (apps are a Supervisor
> feature). Not available on Home Assistant Core installs.

## What's in this repository

```
repository.yaml            # app repository metadata
fronius_meter_bridge/       # the app
├── config.yaml            # app manifest (options + schema)
├── build.yaml             # base images (Python 3.12)
├── Dockerfile
├── run.sh                 # bashio entrypoint
├── requirements.txt
├── README.md              # app summary (store)
├── DOCS.md                # full setup / configuration / troubleshooting
├── CHANGELOG.md
├── app/                   # the bridge (config, meter, sunspec, ha, modbus)
└── translations/          # i8n
```

Full configuration and Fronius setup instructions are in
[`fronius_meter_bridge/DOCS.md`](fronius_meter_bridge/DOCS.md).

## License

MIT — see [LICENSE](LICENSE).
