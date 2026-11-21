# TEOS Stratum Lite Proxy — Runbook operativo

Fecha de verificación: 2026-11-21

## Estado confirmado

- Servicio systemd usuario: `teos-proxy.service`
- Script: `core/lite_proxy.py`
- Proxy escucha: `0.0.0.0:3333`
- Upstream: `solo.ckpool.org:3333` (`15.204.102.129:3333`)
- Cliente/miner conectado desde WSL host: `172.21.176.1`
- Logs stdout: `data/logs/lite_proxy.log`
- Logs stderr: `data/logs/lite_proxy_error.log`

## Cambios aplicados

Se añadió un drop-in de systemd para forzar Python sin buffering y redirigir stdout/stderr a archivos:

`~/.config/systemd/user/teos-proxy.service.d/10-force-log.conf`

Copia versionada en el repo:

`ops/systemd/teos-proxy.service.d/10-force-log.conf`

## Verificación rápida

```bash

sudo timeout 30 tcpdump -i any -nn -s0 -A 'tcp port 3333' 2>/dev/null |
  strings -n 4 |
  grep -Eo '"method"[[:space:]]*:[[:space:]]*"[^"]+"|"result"[[:space:]]*:[[:space:]]*(true|false|null)|"error"[[:space:]]*:[[:space:]]*[^,}]+' |
  sort | uniq -c | sort -rn
```

Resultado sano observado:

```text
44 "result":true
44 "method":"mining.submit"
44 "error":null
6  "method":"mining.notify"
```

## Significado

- `mining.submit`: shares enviadas por el miner.
- `result:true`: pool aceptó la share.
- `error:null`: sin error en la respuesta.
- `mining.notify`: pool envió nuevas jobs.

## Rollback

Si se necesita quitar el drop-in:

```bash
rm -f ~/.config/systemd/user/teos-proxy.service.d/10-force-log.conf
systemctl --user daemon-reload
systemctl --user restart teos-proxy
```

## Seguridad

No commitear capturas `tcpdump` ni logs crudos sin redactar. Pueden contener job IDs, nonces, workers, direcciones u otros datos sensibles de operación.
