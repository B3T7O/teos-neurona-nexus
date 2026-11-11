# Servicios systemd

Estos archivos son plantillas. **Debes editarlos antes de instalarlos** en tu maquina:

1. Cambia `User=hp_lapto1234` por tu usuario.
2. Cambia `WorkingDirectory=/home/hp_lapto1234/teos-neurona-nexus` por tu ruta.
3. Cambia `ExecStart` con la ruta correcta a python3 y al proyecto.

Instalacion:

```bash
# Editar cada archivo primero
sudo cp systemd/teos-*.service /etc/systemd/system/
# Crear override con tu IP real (ver systemd/overrides/)
sudo mkdir -p /etc/systemd/system/teos-nexus-collector.service.d/
sudo cp systemd/overrides/teos-nexus-collector.service.d.example /etc/systemd/system/teos-nexus-collector.service.d/override.conf
# Editar el override con tu IP real
sudo systemctl daemon-reload
sudo systemctl enable --now teos-nexus-collector teos-neurona-scheduler teos-neurona-api
```
