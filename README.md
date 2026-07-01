# Home Assistant Add-on: Fronius Virtual Smart Meter

A Home Assistant **add-on repository** containing the **Fronius Virtual Meter
Bridge** — it aggregates inverter data (from Home Assistant entities) into a
single **virtual Fronius SunSpec smart meter**,
so a Fronius GEN24 / Symo GEN24 Plus can discover it over Modbus TCP and count
generation from extra inverters (e.g. Growatt) as production.

## Installation

This is a Home Assistant **add-on**, so it installs via the Add-on Store, **not
HACS** (HACS does not manage add-ons).

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮** menu (top right) → **Repositories**.
3. Add this repository URL:
   ```
   https://github.com/M4rt1nCh/ha-fronius-virtual-smart-meter
   ```
4. Close the dialog; **Fronius Virtual Smart Meter** now appears in the store.
5. Click it → **Install**, then configure it (see the add-on's **Documentation**
   tab) and **Start**.

> Requires a Home Assistant OS / Supervised install (add-ons are a Supervisor
> feature). Not available on Home Assistant Core installs.

## What's in this repository

```
repository.yaml            # add-on repository metadata
fronius_meter_bridge/       # the add-on
├── config.yaml            # add-on manifest (options + schema)
├── build.yaml             # base images (Python 3.12)
├── Dockerfile
├── run.sh                 # bashio entrypoint
├── requirements.txt
├── README.md              # add-on summary (store)
├── DOCS.md                # full setup / configuration / troubleshooting
├── CHANGELOG.md
├── app/                   # the bridge (config, meter, sunspec, ha, modbus)
└── tools/                 # dev helpers
```

Full configuration and Fronius setup instructions are in
[`fronius_meter_bridge/DOCS.md`](fronius_meter_bridge/DOCS.md).

## License

MIT — see [LICENSE](LICENSE).
